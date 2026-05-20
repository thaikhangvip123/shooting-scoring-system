/**
 * ui.h
 *
 * All LVGL widget creation and update functions.
 * Every public function is mutex-safe: it acquires the LVGL mutex internally,
 * so callers DO NOT need to lock anything themselves.
 */

#pragma once

#include "app_events/app_events.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Build the initial screen layout (header + shot list + status bar).
 * Call ONCE from app_main, before starting the LVGL task and before
 * any network tasks that may call ui_add_shot().
 *
 * lv_init() and display_init() must have been called first.
 */
void ui_init(void);

/**
 * Add a new shot row to the scrollable list and update counters.
 * Thread-safe: acquires LVGL mutex internally.
 * Can be called from any task context.
 */
void ui_add_shot(const shot_event_t *shot);

/**
 * Remove all shot rows, reset counters to 0.
 * Thread-safe.
 */
void ui_reset(void);

void ui_scroll_latest(void);
void ui_scroll_oldest(void);

/**
 * Update the WiFi / WebSocket status string shown in the status bar.
 * Thread-safe.
 *
 * @param wifi_ok   true = WiFi connected
 * @param ws_ok     true = WebSocket open
 */
void ui_set_status(bool wifi_ok, bool ws_ok);

/**
 * Drain the shot queue and button queue, updating widgets as needed.
 * Called once per LVGL timer tick from within the LVGL task so that
 * all widget updates happen on the same task — zero mutex contention
 * for items coming through the queues.
 *
 * Handles:
 *   - shot_queue   → ui_add_shot()
 *   - btn_queue    → long press scrolls latest, double click scrolls oldest
 */
void ui_process_queues(void);

#ifdef __cplusplus
}
#endif
