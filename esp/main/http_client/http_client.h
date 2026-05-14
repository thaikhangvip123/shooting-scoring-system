/**
 * http_client.h
 * One-shot HTTP GET to pull the last N shots from the backend on startup.
 * Results are enqueued to the shot queue so the UI shows existing data
 * before any new shot arrives via WebSocket.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Fetch GET /history?limit=20, parse the JSON array,
 * and enqueue each shot_event_t to app_get_shot_queue().
 *
 * Blocks until the request completes or times out (10 s).
 * Sets EVT_HISTORY_LOADED in the app event group when done
 * (regardless of success/failure so callers don't block forever).
 *
 * Should be called from a task (not from app_main) after WiFi is ready.
 */
void http_pull_history(void);

#ifdef __cplusplus
}
#endif