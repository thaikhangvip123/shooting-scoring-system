/**
 * main.c — Shooting Scoring ESP32-S3 Firmware
 *
 * Startup sequence:
 *  1. app_events_init()   — queues + event group
 *  2. lv_init()           — LVGL core
 *  3. display_init()      — SPI LCD + LVGL driver + LVGL task (Core 1)
 *  4. ui_init()           — build screen layout
 *  5. ui_process_queues() — register as LVGL timer so queue drain runs
 *                           inside the LVGL task on every tick
 *  6. button_init()       — GPIO button + debounce timers
 *  7. wifi_init_sta()     — start WiFi connection
 *  8. Network task        — waits for WiFi, pulls history, starts WS client
 *
 * Data flow:
 *   Backend WS broadcast
 *       → ws_client.c WS event handler (Core 0 task)
 *           → parse JSON → enqueue shot_event_t
 *               → ui_process_queues() (LVGL task, Core 1)
 *                   → _add_shot_row() + _update_counters()
 *
 * Button (GPIO ISR → timer callbacks):
 *   Single click → POST test shot to backend (score 1 position)
 *   Double click → POST test shot to backend (score 8 position)
 *   Long press   → btn_event_t(BTN_LONG_PRESS) → ui_process_queues() → ui_reset()
 *                  + DELETE /shots via http task
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_log.h"
#include "esp_http_client.h"
#include "cJSON.h"
#include "lvgl.h"

#include "app_events/app_events.h"
#include "display/display.h"
#include "ui/ui.h"
#include "wifi/wifi.h"
#include "ws_client/ws_client.h"
#include "http_client/http_client.h"
#include "button/button.h"

static const char *TAG = "main";

// ─── LVGL timer: drain queues on every LVGL tick ─────────────────────────────
// This is called from lv_timer_handler() — already inside the LVGL task
// with the mutex held — so all lv_* calls in ui_process_queues() are safe.

static void lvgl_queue_timer_cb(lv_timer_t *timer)
{
    ui_process_queues();
}

// ─── Test shot injection (button single/double click) ────────────────────────
// These functions run in the button's ISR timer context (Core 0).
// They build a minimal JSON payload and POST it to the backend.
// The backend will broadcast it back via WebSocket → appears on screen.

static void post_test_shot(float x_mm, float y_mm)
{
    char url[128];
    snprintf(url, sizeof(url),
             "http://%s:%d/shot",
             CONFIG_SHOOT_BACKEND_HOST,
             CONFIG_SHOOT_BACKEND_PORT);

    // Build JSON body
    cJSON *body = cJSON_CreateObject();
    cJSON_AddNumberToObject(body, "x_mm",      x_mm);
    cJSON_AddNumberToObject(body, "y_mm",      y_mm);
    cJSON_AddStringToObject(body, "session_id", CONFIG_SHOOT_BACKEND_SESSION_ID);

    cJSON *meta = cJSON_CreateObject();
    cJSON_AddStringToObject(meta, "source", "esp32_button");
    cJSON_AddItemToObject(body, "metadata", meta);

    char *json_str = cJSON_PrintUnformatted(body);
    cJSON_Delete(body);
    if (!json_str) return;

    esp_http_client_config_t cfg = {
        .url        = url,
        .method     = HTTP_METHOD_POST,
        .timeout_ms = 5000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, json_str, strlen(json_str));

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int code = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "Test shot POST → %d (%.1f, %.1f)", code, x_mm, y_mm);
    } else {
        ESP_LOGW(TAG, "Test shot POST failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    free(json_str);
}

// ─── Network task (Core 0) ────────────────────────────────────────────────────
// Runs after app_main returns; handles the post-WiFi network operations.

static void network_task(void *arg)
{
    ESP_LOGI(TAG, "Network task started");

    // ── 1. Wait for WiFi ──────────────────────────────────────────────────────
    ui_set_status(false, false);

    bool connected = wifi_wait_connected(pdMS_TO_TICKS(30000));
    if (!connected) {
        ESP_LOGE(TAG, "WiFi connection timed out — check SSID/password in menuconfig");
        ui_set_status(false, false);
        // Don't abort; the WiFi driver keeps retrying in the background.
    } else {
        ESP_LOGI(TAG, "WiFi connected");
        ui_set_status(true, false);
    }

    // ── 2. Pull existing shot history ─────────────────────────────────────────
    if (connected) {
        http_pull_history();   // populates shot queue; LVGL task drains it
        // Wait for history to be loaded (or timeout 5 s)
        xEventGroupWaitBits(app_get_event_group(), EVT_HISTORY_LOADED,
                            pdFALSE, pdTRUE, pdMS_TO_TICKS(5000));
    }

    // ── 3. Start WebSocket client ─────────────────────────────────────────────
    if (connected) {
        ws_client_start();
        // ws_client sets EVT_WS_CONNECTED in its event handler
    }

    // ── 4. Button event loop ──────────────────────────────────────────────────
    // The button ISR enqueues events; we handle single/double clicks here
    // by POSTing test shots to the backend. Long press is handled in
    // ui_process_queues() (reset) — we just call DELETE /shots here too.

    btn_event_t btn;
    while (1) {
        if (xQueuePeek(app_get_btn_queue(), &btn, pdMS_TO_TICKS(100)) == pdTRUE) {

            // Leave the event in the queue — ui_process_queues() will also
            // read it for LONG_PRESS reset. We only act on click types here.
            if (xQueueReceive(app_get_btn_queue(), &btn, 0) == pdTRUE) {
                switch (btn.action) {

                    case BTN_SINGLE_CLICK:
                        // Score-1 region: ~210 mm radius, on the X axis
                        if (connected)
                            post_test_shot(210.0f, 0.0f);
                        break;

                    case BTN_DOUBLE_CLICK:
                        // Score-8 region: ~60 mm radius, 45° angle
                        if (connected)
                            post_test_shot(42.4f, 42.4f);
                        break;

                    case BTN_LONG_PRESS: {
                        // Session reset: clear UI + DELETE /shots on backend
                        // ui_reset() is already called by ui_process_queues()
                        // when it reads BTN_LONG_PRESS from the queue.
                        // But we already consumed it above, so call it explicitly.
                        ui_reset();

                        // POST DELETE to backend
                        if (connected) {
                            char url[128];
                            snprintf(url, sizeof(url),
                                     "http://%s:%d/shots",
                                     CONFIG_SHOOT_BACKEND_HOST,
                                     CONFIG_SHOOT_BACKEND_PORT);
                            esp_http_client_config_t cfg = {
                                .url    = url,
                                .method = HTTP_METHOD_DELETE,
                                .timeout_ms = 5000,
                            };
                            esp_http_client_handle_t c = esp_http_client_init(&cfg);
                            esp_http_client_perform(c);
                            ESP_LOGI(TAG, "Session reset: DELETE /shots → %d",
                                     esp_http_client_get_status_code(c));
                            esp_http_client_cleanup(c);
                        }
                        break;
                    }
                }
            }
        }

        // Small yield to prevent watchdog trigger
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

// ─── app_main ────────────────────────────────────────────────────────────────

void app_main(void)
{
    ESP_LOGI(TAG, "=== Shooting Scoring System — ESP32-S3 ===");
    ESP_LOGI(TAG, "Backend: %s:%d", CONFIG_SHOOT_BACKEND_HOST, CONFIG_SHOOT_BACKEND_PORT);

    // ── 1. Shared FreeRTOS primitives ─────────────────────────────────────────
    app_events_init();

    // ── 2. LVGL core ──────────────────────────────────────────────────────────
    // lv_init() MUST come before display_init() (lv_disp_drv_init is inside
    // display_init and requires lv_init to have run).
    lv_init();

    // ── 3. LCD + LVGL driver + LVGL task (Core 1) ─────────────────────────────
    display_init();

    // ── 4. Build UI (called before LVGL task starts draining the queue, so
    //       no mutex is needed here — we are the only task at this point) ──────
    ui_init();

    // ── 5. Register queue-drain as an LVGL timer (fires every 50 ms) ──────────
    // This replaces the need for any external task to poke the LVGL mutex;
    // the drain happens inside lv_timer_handler() on Core 1.
    lv_timer_create(lvgl_queue_timer_cb, 50, NULL);

    // ── 6. Button ─────────────────────────────────────────────────────────────
    button_init();

    // ── 7. WiFi (non-blocking — connection happens in the event loop) ──────────
    wifi_init_sta();

    // ── 8. Network task on Core 0 ─────────────────────────────────────────────
    xTaskCreatePinnedToCore(
        network_task, "net_task",
        8192,           // 8 KB stack — cJSON and HTTP need headroom
        NULL, 4,
        NULL, 0         // Core 0 (WiFi stack runs there too)
    );

    ESP_LOGI(TAG, "app_main done — all tasks launched");
    // app_main returns; FreeRTOS scheduler continues running all tasks.
}