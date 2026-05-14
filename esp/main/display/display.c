/**
 * display.c
 *
 * Responsibilities:
 *  1. SPI bus + ILI9341 panel initialisation (verbatim from original main.c)
 *  2. LVGL DMA-capable draw buffers
 *  3. LVGL 2 ms tick via esp_timer
 *  4. A FreeRTOS mutex that all tasks MUST hold before calling any lv_* API
 *
 * Thread-safety model
 * ───────────────────
 * The LVGL task (running on Core 1) calls lv_timer_handler() in a loop.
 * Before each call it acquires lvgl_mutex; it releases it after.
 * Any other task (WS client, button handler) also acquires lvgl_mutex
 * before making lv_* calls — this prevents concurrent access to LVGL state.
 */

#include "display.h"

#include <assert.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_ili9341.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "display";

// ── Pin & LCD config (match original main.c exactly) ─────────────────────────
#define LCD_HOST             SPI3_HOST
#define PIN_NUM_SCLK         12
#define PIN_NUM_MOSI         11
#define PIN_NUM_MISO         13
#define PIN_NUM_CS           10
#define PIN_NUM_BL           45
#define PIN_NUM_RST          -1
#define PIN_NUM_DC           46

#define LCD_H_RES            240
#define LCD_V_RES            320
#define LCD_PIXEL_CLOCK_HZ   (20 * 1000 * 1000)
#define LCD_CMD_BITS         8
#define LCD_PARAM_BITS       8
#define LVGL_DRAW_BUF_LINES  (LCD_V_RES / 2)   // double-buffer half the screen

// ── Module statics ────────────────────────────────────────────────────────────
static esp_lcd_panel_io_handle_t  s_io_handle  = NULL;
static esp_lcd_panel_handle_t     s_panel      = NULL;
static lv_disp_drv_t              s_disp_drv;          // static: DMA callback holds ptr
static SemaphoreHandle_t          s_lvgl_mutex = NULL;

// ── DMA transaction-done callback → signals LVGL flush complete ──────────────
static bool IRAM_ATTR lcd_trans_done_cb(esp_lcd_panel_io_handle_t io,
                                        esp_lcd_panel_io_event_data_t *data,
                                        void *user_ctx)
{
    lv_disp_drv_t *drv = (lv_disp_drv_t *)user_ctx;
    lv_disp_flush_ready(drv);
    return false;
}

// ── LVGL flush callback ───────────────────────────────────────────────────────
static void my_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map)
{
    esp_lcd_panel_handle_t panel = (esp_lcd_panel_handle_t)drv->user_data;
    esp_lcd_panel_draw_bitmap(panel,
                              area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1,
                              color_map);
    // lv_disp_flush_ready() called by lcd_trans_done_cb when DMA completes
}

// ── 2 ms LVGL tick timer ─────────────────────────────────────────────────────
static void lvgl_tick_cb(void *arg)
{
    lv_tick_inc(2);
}

// ── LVGL task (Core 1, priority 5) ───────────────────────────────────────────
// Declared here; started from main.c after UI is built.
// The LVGL task acquires the mutex for each lv_timer_handler() call so other
// tasks can safely update widgets between iterations.
static void lvgl_task(void *arg)
{
    ESP_LOGI(TAG, "LVGL task started on core %d", xPortGetCoreID());
    while (1) {
        // Give other tasks a chance to take the mutex between iterations.
        if (xSemaphoreTake(s_lvgl_mutex, pdMS_TO_TICKS(10)) == pdTRUE) {
            lv_timer_handler();
            xSemaphoreGive(s_lvgl_mutex);
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

void display_init(void)
{
    // ── Mutex ────────────────────────────────────────────────────────────────
    s_lvgl_mutex = xSemaphoreCreateMutex();
    assert(s_lvgl_mutex);

    // ── Backlight ─────────────────────────────────────────────────────────────
    gpio_config_t bl_cfg = {
        .pin_bit_mask = BIT64(PIN_NUM_BL),
        .mode         = GPIO_MODE_OUTPUT,
    };
    gpio_config(&bl_cfg);
    gpio_set_level(PIN_NUM_BL, 1);

    // ── SPI bus ───────────────────────────────────────────────────────────────
    spi_bus_config_t buscfg = {
        .sclk_io_num     = PIN_NUM_SCLK,
        .mosi_io_num     = PIN_NUM_MOSI,
        .miso_io_num     = PIN_NUM_MISO,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

    // ── Panel IO ──────────────────────────────────────────────────────────────
    esp_lcd_panel_io_spi_config_t io_cfg = {
        .dc_gpio_num         = PIN_NUM_DC,
        .cs_gpio_num         = PIN_NUM_CS,
        .pclk_hz             = LCD_PIXEL_CLOCK_HZ,
        .lcd_cmd_bits        = LCD_CMD_BITS,
        .lcd_param_bits      = LCD_PARAM_BITS,
        .spi_mode            = 0,
        .trans_queue_depth   = 10,
        .on_color_trans_done = lcd_trans_done_cb,
        .user_ctx            = &s_disp_drv,   // static: safe to take address
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(
        (esp_lcd_spi_bus_handle_t)LCD_HOST, &io_cfg, &s_io_handle));

    // ── ILI9341 panel ─────────────────────────────────────────────────────────
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = PIN_NUM_RST,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_BGR,
        .bits_per_pixel = 16,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(s_io_handle, &panel_cfg, &s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(s_panel, true));
    ESP_ERROR_CHECK(esp_lcd_panel_mirror(s_panel, true, false));

    // ── LVGL draw buffers (DMA-capable) ──────────────────────────────────────
    size_t buf_sz = LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t);
    lv_color_t *buf1 = heap_caps_malloc(buf_sz, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    lv_color_t *buf2 = heap_caps_malloc(buf_sz, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!buf1 || !buf2) {
        ESP_LOGE(TAG, "Failed to allocate DMA draw buffers (%u bytes each)", (unsigned)buf_sz);
        abort();
    }

    static lv_disp_draw_buf_t draw_buf;
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_H_RES * LVGL_DRAW_BUF_LINES);

    // ── LVGL display driver ───────────────────────────────────────────────────
    lv_disp_drv_init(&s_disp_drv);
    s_disp_drv.hor_res   = LCD_H_RES;
    s_disp_drv.ver_res   = LCD_V_RES;
    s_disp_drv.flush_cb  = my_flush_cb;
    s_disp_drv.draw_buf  = &draw_buf;
    s_disp_drv.user_data = s_panel;
    lv_disp_drv_register(&s_disp_drv);

    // ── 2 ms tick timer ───────────────────────────────────────────────────────
    const esp_timer_create_args_t tick_timer_args = {
        .callback = lvgl_tick_cb,
        .name     = "lv_tick",
    };
    esp_timer_handle_t tick_timer;
    ESP_ERROR_CHECK(esp_timer_create(&tick_timer_args, &tick_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(tick_timer, 2000)); // 2000 µs = 2 ms

    // ── LVGL task (Core 1, priority 5) ───────────────────────────────────────
    BaseType_t ret = xTaskCreatePinnedToCore(
        lvgl_task, "lvgl", 8192, NULL, 5, NULL, 1);
    assert(ret == pdPASS);

    ESP_LOGI(TAG, "Display init complete — %dx%d ILI9341 @ %lu MHz",
             LCD_H_RES, LCD_V_RES, (unsigned long)(LCD_PIXEL_CLOCK_HZ / 1000000));
}

SemaphoreHandle_t display_get_lvgl_mutex(void)
{
    return s_lvgl_mutex;
}