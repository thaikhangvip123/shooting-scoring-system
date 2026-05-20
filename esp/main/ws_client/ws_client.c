/**
 * ws_client.c
 *
 * Connects to ws://HOST:PORT/ws/shots and pushes every valid shot JSON
 * into the shared shot queue for the LVGL task to consume.
 *
 * JSON shape expected from the FastAPI backend:
 * {
 *   "id":        "uuid-string",
 *   "x_mm":     12.4,
 *   "y_mm":    -8.7,
 *   "radius_mm": 15.2,
 *   "score":    9,
 *   "ring":     "9",
 *   "timestamp": "2024-05-14T08:01:00Z",
 *   "session_id": "abc"
 * }
 *
 * Heartbeat / control frames (filtered out):
 * { "type": "ping", ... }
 * { "type": "connected", ... }
 */

#include "ws_client.h"
#include "app_events/app_events.h"
#include "ui/ui.h"

#include <string.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "cJSON.h"
#include "math.h"

static const char *TAG = "ws_client";

static esp_websocket_client_handle_t s_client = NULL;

static cJSON *get_first_present(cJSON *root, const char *primary, const char *fallback)
{
    cJSON *item = cJSON_GetObjectItem(root, primary);
    return item ? item : cJSON_GetObjectItem(root, fallback);
}

static void copy_target_type(cJSON *root, shot_event_t *out)
{
    snprintf(out->target_type, sizeof(out->target_type), "TRON");

    cJSON *target = cJSON_GetObjectItem(root, "target_type");
    if (!cJSON_IsString(target)) {
        cJSON *metadata = cJSON_GetObjectItem(root, "metadata");
        if (cJSON_IsObject(metadata)) {
            target = cJSON_GetObjectItem(metadata, "target_type");
        }
    }

    if (cJSON_IsString(target) && target->valuestring) {
        snprintf(out->target_type, sizeof(out->target_type), "%s", target->valuestring);
    }
}

// ─── JSON → shot_event_t ──────────────────────────────────────────────────────

/**
 * Parse a text WebSocket frame into a shot_event_t.
 *
 * Returns true and fills *out on success.
 * Returns false for:
 *  - Parse errors
 *  - Heartbeat / control messages (type field present)
 *  - Missing mandatory fields (x_mm, y_mm, score)
 */
static bool parse_shot(const char *data, int len, shot_event_t *out)
{
    // Make a null-terminated copy (data from esp_websocket_client is not
    // guaranteed to be null-terminated, and cJSON_Parse requires it)
    char *buf = malloc(len + 1);
    if (!buf) {
        ESP_LOGE(TAG, "OOM allocating parse buffer");
        return false;
    }
    memcpy(buf, data, len);
    buf[len] = '\0';

    bool ok = false;
    cJSON *root = cJSON_Parse(buf);
    if (!root) {
        ESP_LOGW(TAG, "JSON parse error: %.40s", buf);
        goto done;
    }

    // Filter control messages — any object with a "type" field
    if (cJSON_GetObjectItem(root, "type")) {
        goto done;  // heartbeat/ping — silently ignore
    }

    // Mandatory numeric fields
    cJSON *x    = get_first_present(root, "x_mm", "x_px");
    cJSON *y    = get_first_present(root, "y_mm", "y_px");
    cJSON *sc   = cJSON_GetObjectItem(root, "score");
    if (!cJSON_IsNumber(x) || !cJSON_IsNumber(y) || !cJSON_IsNumber(sc)) {
        ESP_LOGW(TAG, "Shot JSON missing x/y/score: %.80s", buf);
        goto done;
    }

    memset(out, 0, sizeof(*out));
    out->x_mm  = (float)x->valuedouble;
    out->y_mm  = (float)y->valuedouble;
    out->score = sc->valueint;

    // Optional: id
    cJSON *id = cJSON_GetObjectItem(root, "id");
    if (cJSON_IsString(id) && id->valuestring) {
        snprintf(out->id, sizeof(out->id), "%s", id->valuestring);
    }

    // Optional: radius_mm
    cJSON *r = get_first_present(root, "radius_mm", "radius_px");
    if (cJSON_IsNumber(r)) {
        out->radius_mm = (float)r->valuedouble;
    } else {
        // Compute locally if backend omitted it
        out->radius_mm = sqrtf(out->x_mm * out->x_mm + out->y_mm * out->y_mm);
    }

    // Optional: ring label
    cJSON *ring = cJSON_GetObjectItem(root, "ring");
    if (cJSON_IsString(ring) && ring->valuestring) {
        snprintf(out->ring, sizeof(out->ring), "%s", ring->valuestring);
    } else {
        snprintf(out->ring, sizeof(out->ring), "%d", out->score);
    }

    copy_target_type(root, out);

    ok = true;
done:
    cJSON_Delete(root);
    free(buf);
    return ok;
}

// ─── WebSocket event handler ──────────────────────────────────────────────────

static void ws_event_handler(void *handler_args,
                              esp_event_base_t base,
                              int32_t event_id,
                              void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;
    EventGroupHandle_t eg = app_get_event_group();

    switch (event_id) {

        case WEBSOCKET_EVENT_CONNECTED:
            ESP_LOGI(TAG, "WebSocket connected to %s",
                     CONFIG_SHOOT_BACKEND_HOST);
            xEventGroupSetBits(eg, EVT_WS_CONNECTED);
            ui_set_status(true, true);
            break;

        case WEBSOCKET_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "WebSocket disconnected");
            xEventGroupClearBits(eg, EVT_WS_CONNECTED);
            ui_set_status(true, false);
            break;

        case WEBSOCKET_EVENT_DATA: {
            // Only process text frames (opcode 0x01)
            if (data->op_code != 0x01) break;
            if (data->data_len <= 0)   break;

            shot_event_t shot;
            if (!parse_shot(data->data_ptr, data->data_len, &shot)) break;

            // Enqueue for LVGL task — non-blocking; drop on overflow
            if (xQueueSend(app_get_shot_queue(), &shot, 0) != pdTRUE) {
                ESP_LOGW(TAG, "Shot queue full — event dropped");
            }
            break;
        }

        case WEBSOCKET_EVENT_ERROR:
            ESP_LOGE(TAG, "WebSocket error");
            xEventGroupClearBits(eg, EVT_WS_CONNECTED);
            ui_set_status(true, false);
            break;

        default:
            break;
    }
}

// ─── Public API ───────────────────────────────────────────────────────────────

void ws_client_start(void)
{
    // Build URI: ws://HOST:PORT/ws/shots
    char uri[128];
    snprintf(uri, sizeof(uri),
             "ws://%s:%d/ws/shots",
             CONFIG_SHOOT_BACKEND_HOST,
             CONFIG_SHOOT_BACKEND_PORT);

    ESP_LOGI(TAG, "Starting WebSocket client: %s", uri);

    esp_websocket_client_config_t ws_cfg = {
        .uri              = uri,
        .buffer_size      = 4096,
        .task_stack       = 6144,
        .reconnect_timeout_ms  = 5000,
        .network_timeout_ms    = 10000,
    };

    s_client = esp_websocket_client_init(&ws_cfg);
    ESP_ERROR_CHECK(esp_websocket_register_events(
        s_client, WEBSOCKET_EVENT_ANY, ws_event_handler, NULL));
    ESP_ERROR_CHECK(esp_websocket_client_start(s_client));

    ESP_LOGI(TAG, "WebSocket client started");
}

void ws_client_stop(void)
{
    if (s_client) {
        esp_websocket_client_stop(s_client);
        esp_websocket_client_destroy(s_client);
        s_client = NULL;
        ESP_LOGI(TAG, "WebSocket client stopped");
    }
}
