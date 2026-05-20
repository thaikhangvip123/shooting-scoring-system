/**
 * button.c
 *
 * State machine for a single active-low GPIO button:
 *
 *  IDLE ──(falling edge)──► DEBOUNCE ──(50 ms timer, still low)──► PRESSED
 *       ──(rising / bounce)──► IDLE
 *
 *  PRESSED ──(rising edge)──► CLICK_WAIT ──(dbl-click window expires)──► SINGLE_CLICK
 *                          └──(falling edge within window)──► DOUBLE_CLICK
 *
 *  PRESSED ──(held > long_press_ms)──► LONG_PRESS (fires once; stays until release)
 *
 * All timer callbacks run in ISR context (esp_timer high-res); they only
 * set/clear flags and enqueue events — no LVGL calls here.
 */

#include "button.h"
#include "app_events/app_events.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "button";

// ── Config from Kconfig ───────────────────────────────────────────────────────
#define BTN_GPIO           0
#define DEBOUNCE_US        50000ULL                          // 50 ms
#define DBLCLICK_US        ((uint64_t)CONFIG_SHOOT_BUTTON_DBLCLICK_MS  * 1000)
#define LONG_PRESS_US      ((uint64_t)CONFIG_SHOOT_BUTTON_LONG_PRESS_MS * 1000)

// ── State ─────────────────────────────────────────────────────────────────────
typedef enum {
    STATE_IDLE,
    STATE_DEBOUNCE,
    STATE_PRESSED,
    STATE_CLICK_WAIT,       // waiting to see if a second click arrives
} btn_state_t;

static volatile btn_state_t s_state      = STATE_IDLE;
static volatile int64_t     s_press_time = 0;    // esp_timer_get_time() at press
static volatile bool        s_long_fired = false;

static esp_timer_handle_t s_debounce_timer  = NULL;
static esp_timer_handle_t s_dblclick_timer  = NULL;
static esp_timer_handle_t s_longpress_timer = NULL;

// ── Helper: enqueue button event (safe from timer / ISR context) ──────────────
static void enqueue(btn_action_t action)
{
    btn_event_t evt = { .action = action };
    BaseType_t  woken = pdFALSE;
    xQueueSendFromISR(app_get_btn_queue(), &evt, &woken);
    if (woken) portYIELD_FROM_ISR();
}

// ── Timer callbacks ───────────────────────────────────────────────────────────

// Called 50 ms after the initial falling edge — confirm the button is still low
static void debounce_timer_cb(void *arg)
{
    if (gpio_get_level(BTN_GPIO) == 0) {
        // Genuinely pressed
        s_state      = STATE_PRESSED;
        s_press_time = esp_timer_get_time();
        s_long_fired = false;
        // Start long-press watchdog
        esp_timer_start_once(s_longpress_timer, LONG_PRESS_US);
    } else {
        s_state = STATE_IDLE;
    }
}

// Called when no second click arrives within the double-click window
static void dblclick_timer_cb(void *arg)
{
    if (s_state == STATE_CLICK_WAIT) {
        s_state = STATE_IDLE;
        ESP_LOGD(TAG, "Single click");
        enqueue(BTN_SINGLE_CLICK);
    }
}

// Called after the button is held for LONG_PRESS_US
static void longpress_timer_cb(void *arg)
{
    if (s_state == STATE_PRESSED && !s_long_fired) {
        s_long_fired = true;
        ESP_LOGD(TAG, "Long press");
        enqueue(BTN_LONG_PRESS);
    }
}

// ── GPIO ISR ─────────────────────────────────────────────────────────────────

static void IRAM_ATTR gpio_isr_handler(void *arg)
{
    int level = gpio_get_level(BTN_GPIO);

    switch (s_state) {

        case STATE_IDLE:
            if (level == 0) {
                // Falling edge — start debounce
                s_state = STATE_DEBOUNCE;
                esp_timer_start_once(s_debounce_timer, DEBOUNCE_US);
            }
            break;

        case STATE_DEBOUNCE:
            // Bouncing — ignore
            break;

        case STATE_PRESSED:
            if (level == 1) {
                // Rising edge = release
                esp_timer_stop(s_longpress_timer);
                if (!s_long_fired) {
                    // Was a click (not long press)
                    s_state = STATE_CLICK_WAIT;
                    esp_timer_start_once(s_dblclick_timer, DBLCLICK_US);
                } else {
                    s_state = STATE_IDLE;
                }
            }
            break;

        case STATE_CLICK_WAIT:
            if (level == 0) {
                // Second click within window = double click
                esp_timer_stop(s_dblclick_timer);
                s_state = STATE_IDLE;
                ESP_LOGD(TAG, "Double click");
                enqueue(BTN_DOUBLE_CLICK);
            }
            break;
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

void button_init(void)
{
    // ── GPIO setup ────────────────────────────────────────────────────────────
    gpio_config_t io_cfg = {
        .pin_bit_mask  = BIT64(BTN_GPIO),
        .mode          = GPIO_MODE_INPUT,
        .pull_up_en    = GPIO_PULLUP_ENABLE,
        .pull_down_en  = GPIO_PULLDOWN_DISABLE,
        .intr_type     = GPIO_INTR_ANYEDGE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_cfg));

    // ── Timers ────────────────────────────────────────────────────────────────
    const esp_timer_create_args_t debounce_args = {
        .callback = debounce_timer_cb,
        .name     = "btn_debounce",
        .dispatch_method = ESP_TIMER_TASK,
    };
    ESP_ERROR_CHECK(esp_timer_create(&debounce_args, &s_debounce_timer));

    const esp_timer_create_args_t dblclick_args = {
        .callback = dblclick_timer_cb,
        .name     = "btn_dblclick",
        .dispatch_method = ESP_TIMER_TASK,
    };
    ESP_ERROR_CHECK(esp_timer_create(&dblclick_args, &s_dblclick_timer));

    const esp_timer_create_args_t longpress_args = {
        .callback = longpress_timer_cb,
        .name     = "btn_longpress",
        .dispatch_method = ESP_TIMER_TASK,
    };
    ESP_ERROR_CHECK(esp_timer_create(&longpress_args, &s_longpress_timer));

    // ── ISR service ───────────────────────────────────────────────────────────
    gpio_install_isr_service(0);
    gpio_isr_handler_add(BTN_GPIO, gpio_isr_handler, NULL);

    ESP_LOGI(TAG, "Button init: GPIO %d (long=%lums, dbl=%lums)",
             BTN_GPIO,
             (unsigned long)CONFIG_SHOOT_BUTTON_LONG_PRESS_MS,
             (unsigned long)CONFIG_SHOOT_BUTTON_DBLCLICK_MS);
}
