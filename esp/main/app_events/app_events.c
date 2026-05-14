/**
 * app_events.c
 * Creates and exposes all shared FreeRTOS primitives.
 */

#include "app_events.h"
#include "esp_log.h"

static const char *TAG = "app_events";

#define SHOT_QUEUE_LEN  32    // buffer up to 32 shot events
#define BTN_QUEUE_LEN   8

static QueueHandle_t      s_shot_queue   = NULL;
static QueueHandle_t      s_btn_queue    = NULL;
static EventGroupHandle_t s_event_group  = NULL;

void app_events_init(void)
{
    s_shot_queue  = xQueueCreate(SHOT_QUEUE_LEN, sizeof(shot_event_t));
    s_btn_queue   = xQueueCreate(BTN_QUEUE_LEN,  sizeof(btn_event_t));
    s_event_group = xEventGroupCreate();

    if (!s_shot_queue || !s_btn_queue || !s_event_group) {
        ESP_LOGE(TAG, "Failed to create FreeRTOS primitives — heap too small?");
        abort();
    }
    ESP_LOGI(TAG, "Queues and event group created");
}

QueueHandle_t app_get_shot_queue(void)    { return s_shot_queue;  }
QueueHandle_t app_get_btn_queue(void)     { return s_btn_queue;   }
EventGroupHandle_t app_get_event_group(void) { return s_event_group; }