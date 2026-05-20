/**
 * app_events.h
 *
 * Central place for:
 *  - shot_event_t  : parsed shot data ready for LVGL
 *  - btn_event_t   : button action type
 *  - Shared queue / event-group handles
 *
 * Producers: ws_client.c, http_client.c, button.c
 * Consumer:  ui.c (drained inside the LVGL task)
 */

#pragma once

#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/event_groups.h"

#ifdef __cplusplus
extern "C" {
#endif

// ─── Event-group bits ────────────────────────────────────────────────────────

#define EVT_WIFI_CONNECTED     BIT0   // WiFi IP obtained
#define EVT_WS_CONNECTED       BIT1   // WebSocket handshake complete
#define EVT_HISTORY_LOADED     BIT2   // Initial HTTP pull done

// ─── Shot event (from WS or HTTP history pull) ───────────────────────────────

#define SHOT_ID_LEN     37    // UUID string length + null
#define SHOT_RING_LEN   4     // "X", "10".."1", "M" + null
#define SHOT_TARGET_LEN 8     // "TRON", "IPSC", "NGUOI" + null

typedef struct {
    char    id[SHOT_ID_LEN];
    float   x_mm;
    float   y_mm;
    float   radius_mm;
    int     score;
    char    ring[SHOT_RING_LEN];
    char    target_type[SHOT_TARGET_LEN];
    // timestamp kept as epoch seconds (parsed from ISO string) for display
    int64_t ts_epoch;
} shot_event_t;

// ─── Button event ─────────────────────────────────────────────────────────────

typedef enum {
    BTN_SINGLE_CLICK = 1,
    BTN_DOUBLE_CLICK,
    BTN_LONG_PRESS,
} btn_action_t;

typedef struct {
    btn_action_t action;
} btn_event_t;

// ─── Queue / event-group handles ─────────────────────────────────────────────

/**
 * Call once in app_main before any task is created.
 * Creates the shot queue, button queue, and app event group.
 */
void app_events_init(void);

/** Queue for shot_event_t  (WS/HTTP → UI) */
QueueHandle_t app_get_shot_queue(void);

/** Queue for btn_event_t   (button → UI / HTTP) */
QueueHandle_t app_get_btn_queue(void);

/** App-wide event group (WiFi, WS, history bits) */
EventGroupHandle_t app_get_event_group(void);

#ifdef __cplusplus
}
#endif
