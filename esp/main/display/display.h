/**
 * display.h
 * SPI LCD (ILI9341, 240×320) + LVGL v8 driver initialisation.
 * Extracted from the original main.c so app_main stays clean.
 */

#pragma once

#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Initialise the SPI bus, ILI9341 panel, LVGL draw buffers,
 * and register the display driver.
 *
 * Must be called AFTER lv_init() and lv_disp_drv_init().
 * The LVGL tick timer is also started here.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

void display_init(void);

/**
 * Returns the SemaphoreHandle_t that guards all lv_* calls.
 * Any task that wants to update LVGL widgets must acquire this
 * mutex before calling any lv_* function.
 */
SemaphoreHandle_t display_get_lvgl_mutex(void);

#ifdef __cplusplus
}
#endif