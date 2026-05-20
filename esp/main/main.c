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
 *   Double click → scroll to oldest shot
 *   Long press   → scroll to latest shot
 */

#include <stdio.h>
#include <string.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_log.h"
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

    // ── 4. Keep status fresh; UI owns button queue events ─────────────────────
    while (1) {
        bool wifi_ok = (xEventGroupGetBits(app_get_event_group()) & EVT_WIFI_CONNECTED) != 0;
        bool ws_ok = (xEventGroupGetBits(app_get_event_group()) & EVT_WS_CONNECTED) != 0;
        ui_set_status(wifi_ok, ws_ok);
        vTaskDelay(pdMS_TO_TICKS(1000));
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
    xSemaphoreTake(display_get_lvgl_mutex(), portMAX_DELAY);
    ui_init();

    // ── 5. Register queue-drain as an LVGL timer (fires every 50 ms) ──────────
    // This replaces the need for any external task to poke the LVGL mutex;
    // the drain happens inside lv_timer_handler() on Core 1.
    lv_timer_create(lvgl_queue_timer_cb, 50, NULL);
    xSemaphoreGive(display_get_lvgl_mutex());

    // ── 6. Button ─────────────────────────────────────────────────────────────
    button_init();

    // ── 7. WiFi (non-blocking — connection happens in the event loop) ──────────
    wifi_init_sta();

    // ── 8. Network task on Core 0 ─────────────────────────────────────────────
    xTaskCreatePinnedToCore(
        network_task, "net_task",
        8192,           // 8 KB stack for HTTP history and WebSocket startup
        NULL, 4,
        NULL, 0         // Core 0 (WiFi stack runs there too)
    );

    ESP_LOGI(TAG, "app_main done — all tasks launched");
    // app_main returns; FreeRTOS scheduler continues running all tasks.
}
