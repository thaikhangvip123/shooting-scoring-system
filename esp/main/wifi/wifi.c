/**
 * wifi.c
 * WiFi station connection with exponential back-off reconnect.
 *
 * On successful IP assignment: sets EVT_WIFI_CONNECTED.
 * On disconnect: clears EVT_WIFI_CONNECTED and attempts reconnect up to
 * CONFIG_SHOOT_WIFI_MAX_RETRY times.
 */

#include "wifi.h"
#include "app_events/app_events.h"

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "lwip/err.h"
#include "lwip/sys.h"

static const char *TAG = "wifi";

static int s_retry_count = 0;

// ── Event handler ─────────────────────────────────────────────────────────────

static void wifi_event_handler(void *arg, esp_event_base_t base,
                                int32_t id, void *data)
{
    EventGroupHandle_t eg = app_get_event_group();

    if (base == WIFI_EVENT) {
        switch (id) {
            case WIFI_EVENT_STA_START:
                ESP_LOGI(TAG, "STA started, connecting to \"%s\"…",
                         CONFIG_SHOOT_WIFI_SSID);
                esp_wifi_connect();
                break;

            case WIFI_EVENT_STA_DISCONNECTED: {
                xEventGroupClearBits(eg, EVT_WIFI_CONNECTED);
                wifi_event_sta_disconnected_t *disc = data;
                ESP_LOGW(TAG, "Disconnected (reason %d), retry %d/%d",
                         disc->reason, s_retry_count + 1,
                         CONFIG_SHOOT_WIFI_MAX_RETRY);

                if (s_retry_count < CONFIG_SHOOT_WIFI_MAX_RETRY) {
                    s_retry_count++;
                    // Back-off: wait 1s × retry count before reconnecting
                    vTaskDelay(pdMS_TO_TICKS(1000 * s_retry_count));
                    esp_wifi_connect();
                } else {
                    ESP_LOGE(TAG, "Giving up after %d retries",
                             CONFIG_SHOOT_WIFI_MAX_RETRY);
                }
                break;
            }
            default:
                break;
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_count = 0;
        xEventGroupSetBits(eg, EVT_WIFI_CONNECTED);
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

void wifi_init_sta(void)
{
    // NVS is required by WiFi driver for calibration data
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS erase + re-init");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_cfg = {
        .sta = {
            .ssid              = CONFIG_SHOOT_WIFI_SSID,
            .password          = CONFIG_SHOOT_WIFI_PASSWORD,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg = {
                .capable  = true,
                .required = false,
            },
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "WiFi init done, waiting for connection…");
}

bool wifi_wait_connected(TickType_t timeout_ticks)
{
    EventBits_t bits = xEventGroupWaitBits(
        app_get_event_group(),
        EVT_WIFI_CONNECTED,
        pdFALSE,          // don't clear
        pdTRUE,           // wait for all listed bits
        timeout_ticks
    );
    return (bits & EVT_WIFI_CONNECTED) != 0;
}