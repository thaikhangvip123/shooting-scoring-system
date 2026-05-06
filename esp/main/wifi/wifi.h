/**
 * wifi.h
 * WPA2 station-mode WiFi with automatic reconnect.
 */

#pragma once

#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Initialise NVS flash, the TCP/IP stack, and the default WiFi event loop.
 * Starts the station connection using SSID/password from Kconfig.
 * Sets EVT_WIFI_CONNECTED in app_get_event_group() when an IP is obtained.
 */
void wifi_init_sta(void);

/**
 * Block until WiFi is connected (EVT_WIFI_CONNECTED is set)
 * or until the retry limit is reached.
 *
 * @return  true  = connected
 *          false = retry limit exceeded
 */
bool wifi_wait_connected(TickType_t timeout_ticks);

#ifdef __cplusplus
}
#endif