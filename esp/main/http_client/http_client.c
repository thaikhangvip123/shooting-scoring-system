/**
 * http_client.c
 *
 * Pulls existing shot history from GET /history?limit=20 on startup.
 * The backend returns:
 * {
 *   "shots": [ { "id":..., "x_mm":..., "y_mm":..., "score":..., "ring":... }, ... ],
 *   "total": 42
 * }
 */

#include "http_client.h"
#include "app_events/app_events.h"

#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "cJSON.h"

static const char *TAG = "http_client";

#define HTTP_RECV_BUF_SIZE  (16 * 1024)   // 16 KB — enough for 100 shots
#define HISTORY_LIMIT        20

// Dynamic receive buffer filled by the HTTP event handler
static char   *s_recv_buf  = NULL;
static int     s_recv_len  = 0;

// ─── HTTP event handler ───────────────────────────────────────────────────────

static esp_err_t http_event_handler(esp_http_client_event_t *evt)
{
    switch (evt->event_id) {

        case HTTP_EVENT_ON_DATA:
            if (!esp_http_client_is_chunked_response(evt->client)) {
                if (s_recv_buf && (s_recv_len + evt->data_len < HTTP_RECV_BUF_SIZE)) {
                    memcpy(s_recv_buf + s_recv_len, evt->data, evt->data_len);
                    s_recv_len += evt->data_len;
                }
            }
            break;

        case HTTP_EVENT_ON_FINISH:
        case HTTP_EVENT_ERROR:
        case HTTP_EVENT_DISCONNECTED:
        default:
            break;
    }
    return ESP_OK;
}

// ─── JSON parsing helper ──────────────────────────────────────────────────────

static void enqueue_shots_from_json(const char *json_str, int len)
{
    cJSON *root = cJSON_ParseWithLength(json_str, len);
    if (!root) {
        ESP_LOGE(TAG, "History JSON parse error");
        return;
    }

    // Root can be either the object {"shots":[...]} or a bare array [...]
    cJSON *shots_arr = cJSON_GetObjectItem(root, "shots");
    if (!shots_arr) shots_arr = root;   // bare array fallback

    if (!cJSON_IsArray(shots_arr)) {
        ESP_LOGE(TAG, "Expected shots array in history response");
        cJSON_Delete(root);
        return;
    }

    int enqueued = 0;
    cJSON *item  = NULL;
    cJSON_ArrayForEach(item, shots_arr) {
        cJSON *x  = cJSON_GetObjectItem(item, "x_mm");
        cJSON *y  = cJSON_GetObjectItem(item, "y_mm");
        cJSON *sc = cJSON_GetObjectItem(item, "score");

        if (!cJSON_IsNumber(x) || !cJSON_IsNumber(y) || !cJSON_IsNumber(sc)) {
            continue;
        }

        shot_event_t shot = {0};
        shot.x_mm  = (float)x->valuedouble;
        shot.y_mm  = (float)y->valuedouble;
        shot.score = sc->valueint;

        cJSON *id   = cJSON_GetObjectItem(item, "id");
        cJSON *ring = cJSON_GetObjectItem(item, "ring");
        cJSON *r    = cJSON_GetObjectItem(item, "radius_mm");

        if (cJSON_IsString(id)   && id->valuestring)
            snprintf(shot.id,   sizeof(shot.id),   "%s", id->valuestring);
        if (cJSON_IsString(ring) && ring->valuestring)
            snprintf(shot.ring, sizeof(shot.ring), "%s", ring->valuestring);
        if (cJSON_IsNumber(r))
            shot.radius_mm = (float)r->valuedouble;
        else
            shot.radius_mm = sqrtf(shot.x_mm * shot.x_mm + shot.y_mm * shot.y_mm);

        if (xQueueSend(app_get_shot_queue(), &shot, pdMS_TO_TICKS(50)) == pdTRUE) {
            enqueued++;
        } else {
            ESP_LOGW(TAG, "Shot queue full during history load, stopping at %d", enqueued);
            break;
        }
    }

    ESP_LOGI(TAG, "History: enqueued %d shots", enqueued);
    cJSON_Delete(root);
}

// ─── Public API ───────────────────────────────────────────────────────────────

void http_pull_history(void)
{
    char url[160];
    snprintf(url, sizeof(url),
             "http://%s:%d/history?limit=%d",
             CONFIG_SHOOT_BACKEND_HOST,
             CONFIG_SHOOT_BACKEND_PORT,
             HISTORY_LIMIT);

    ESP_LOGI(TAG, "Pulling history: GET %s", url);

    s_recv_buf = calloc(1, HTTP_RECV_BUF_SIZE);
    if (!s_recv_buf) {
        ESP_LOGE(TAG, "OOM allocating HTTP receive buffer");
        goto done;
    }
    s_recv_len = 0;

    esp_http_client_config_t config = {
        .url            = url,
        .timeout_ms     = 10000,
        .event_handler  = http_event_handler,
        .buffer_size    = 4096,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "Failed to init HTTP client");
        goto done;
    }

    esp_err_t err = esp_http_client_perform(client);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "HTTP request failed: %s", esp_err_to_name(err));
    } else {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "HTTP response: %d (%d bytes)", status, s_recv_len);

        if (status == 200 && s_recv_len > 0) {
            enqueue_shots_from_json(s_recv_buf, s_recv_len);
        }
    }

    esp_http_client_cleanup(client);

done:
    free(s_recv_buf);
    s_recv_buf = NULL;

    // Signal callers even if we failed — they shouldn't block forever.
    xEventGroupSetBits(app_get_event_group(), EVT_HISTORY_LOADED);
    ESP_LOGI(TAG, "History pull complete");
}