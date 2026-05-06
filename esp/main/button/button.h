/**
 * button.h
 * GPIO button driver with hardware debounce, single-click, double-click,
 * and long-press detection.
 *
 * Uses:
 *  - GPIO interrupt (falling edge) as the raw trigger
 *  - esp_timer one-shot for debounce (50 ms)
 *  - esp_timer one-shot for double-click window (CONFIG_SHOOT_BUTTON_DBLCLICK_MS)
 *  - Tick counting for long-press (CONFIG_SHOOT_BUTTON_LONG_PRESS_MS)
 *
 * Results are enqueued to app_get_btn_queue() as btn_event_t values.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Configure the button GPIO, enable interrupts, and start the detection
 * state machine.  Must be called after app_events_init().
 */
void button_init(void);

#ifdef __cplusplus
}
#endif