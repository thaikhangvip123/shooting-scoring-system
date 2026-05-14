/**
 * ws_client.h
 * Long-lived WebSocket client — subscribes to /ws/shots on the FastAPI backend.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Start the WebSocket client task.
 * The URI is built from Kconfig (SHOOT_BACKEND_HOST:PORT/ws/shots).
 *
 * On receiving a text frame the client:
 *   1. Filters heartbeat messages  (type=ping / type=connected)
 *   2. Parses shot JSON with cJSON
 *   3. Enqueues a shot_event_t to app_get_shot_queue()
 *   4. Sets/clears EVT_WS_CONNECTED in the app event group
 */
void ws_client_start(void);

/**
 * Disconnect and free the WebSocket client.
 * Call before deep-sleep or OTA.
 */
void ws_client_stop(void);

#ifdef __cplusplus
}
#endif