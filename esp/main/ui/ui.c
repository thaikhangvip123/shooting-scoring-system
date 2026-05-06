/**
 * ui.c
 *
 * Screen layout (portrait 240 × 320):
 *
 *  ┌──────────────────────────┐  ← y=0
 *  │  Shots: 0    Score: 0    │  header (60 px)
 *  │──────────────────────────│
 *  │  #1  [10][X]  +2.1,-3.4 │
 *  │  #2  [ 9][9]  -5.3, 8.1 │  shot list (244 px, scrollable)
 *  │  ...                     │
 *  │──────────────────────────│
 *  │  WiFi ✓  WS ✓            │  status bar (16 px)
 *  └──────────────────────────┘  ← y=320
 *
 * Thread model:
 *   ui_add_shot / ui_reset / ui_set_status are mutex-safe wrappers that
 *   CAN be called from any task.
 *
 *   ui_process_queues() is called from the LVGL task (which holds the mutex
 *   while running lv_timer_handler). This drains the shot/button queues
 *   without any additional locking — since we're already inside the task
 *   that owns the mutex.
 */

#include "ui.h"
#include "display/display.h"
#include "app_events/app_events.h"

#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "lvgl.h"

static const char *TAG = "ui";

// ── Layout constants ──────────────────────────────────────────────────────────
#define LCD_W           240
#define LCD_H           320
#define HEADER_H        60
#define STATUS_H        16
#define LISTTEXT_H          (LCD_H - HEADER_H - STATUS_H)
#define MAX_ROWS        CONFIG_SHOOT_MAX_ROWS

// ── Module state ──────────────────────────────────────────────────────────────
static lv_obj_t *s_label_shots  = NULL;
static lv_obj_t *s_label_score  = NULL;
static lv_obj_t *s_shot_list    = NULL;
static lv_obj_t *s_label_status = NULL;

static int s_total_shots = 0;
static int s_total_score = 0;

// ── Colour helpers ────────────────────────────────────────────────────────────

/** Map score 0-10 to an LVGL colour: green for high, red for low. */
static lv_color_t score_to_color(int score)
{
    if (score == 10) return lv_color_make(100, 210, 255);  // cyan  (X/10)
    if (score >= 8)  return lv_color_make( 80, 220,  80);  // green (8-9)
    if (score >= 6)  return lv_color_make(255, 200,  40);  // amber (6-7)
    if (score >= 3)  return lv_color_make(255, 120,  20);  // orange(3-5)
    if (score >= 1)  return lv_color_make(220,  50,  50);  // red   (1-2)
    return lv_color_make(120, 120, 120);                    // grey  (miss)
}

// ── Mutex helpers ─────────────────────────────────────────────────────────────
// Convenience macros so every call site is concise.

#define LVGL_LOCK()   xSemaphoreTake(display_get_lvgl_mutex(), portMAX_DELAY)
#define LVGL_UNLOCK() xSemaphoreGive(display_get_lvgl_mutex())

// ── Internal widget update (must be called WITH mutex held) ──────────────────

static void _update_counters(void)
{
    char buf[32];
    snprintf(buf, sizeof(buf), "Shots: %d", s_total_shots);
    lv_label_set_text(s_label_shots, buf);

    snprintf(buf, sizeof(buf), "Score: %d", s_total_score);
    lv_label_set_text(s_label_score, buf);
}

static void _add_shot_row(const shot_event_t *shot)
{
    // Evict oldest row if at limit
    uint32_t child_cnt = lv_obj_get_child_cnt(s_shot_list);
    if ((int)child_cnt >= MAX_ROWS) {
        lv_obj_t *oldest = lv_obj_get_child(s_shot_list, 0);
        if (oldest) lv_obj_del(oldest);
    }

    // Format: "#N  [score][ring]  (+X.X, +Y.Y)mm"
    char text[56];
    snprintf(text, sizeof(text),
             "#%-2d [%2d][%-2s]  %+.1f, %+.1f",
             s_total_shots, shot->score, shot->ring,
             shot->x_mm, shot->y_mm);

    lv_obj_t *row = lv_label_create(s_shot_list);
    lv_label_set_text(row, text);
    lv_obj_set_style_text_color(row, score_to_color(shot->score), 0);
    lv_obj_set_style_text_font(row, &lv_font_montserrat_14, 0);
    lv_obj_set_width(row, lv_pct(100));

    // Auto-scroll the list so the newest row is visible
    lv_obj_scroll_to_y(s_shot_list,
                       lv_obj_get_scroll_top(s_shot_list) + 9999,
                       LV_ANIM_ON);
}

static void _reset_list(void)
{
    lv_obj_clean(s_shot_list);
    s_total_shots = 0;
    s_total_score = 0;
    _update_counters();
    ESP_LOGI(TAG, "UI reset");
}

// ── Public API ────────────────────────────────────────────────────────────────

void ui_init(void)
{
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    // ── Header ───────────────────────────────────────────────────────────────
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, LCD_W, HEADER_H);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_make(18, 22, 34), 0);
    lv_obj_set_style_bg_opa(header, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_pad_all(header, 6, 0);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    s_label_shots = lv_label_create(header);
    lv_obj_set_style_text_font(s_label_shots, &lv_font_montserrat_20, 0);
    lv_label_set_text(s_label_shots, "Shots: 0");
    lv_obj_align(s_label_shots, LV_ALIGN_TOP_LEFT, 0, 0);
    lv_obj_set_style_text_color(s_label_shots, lv_color_white(), 0);

    s_label_score = lv_label_create(header);
    lv_obj_set_style_text_font(s_label_score, &lv_font_montserrat_20, 0);
    lv_label_set_text(s_label_score, "Score: 0");
    lv_obj_align(s_label_score, LV_ALIGN_BOTTOM_LEFT, 0, 0);
    lv_obj_set_style_text_color(s_label_score, lv_color_make(100, 210, 255), 0);

    // Separator line
    lv_obj_t *sep = lv_obj_create(scr);
    lv_obj_set_size(sep, LCD_W, 1);
    lv_obj_align(sep, LV_ALIGN_TOP_MID, 0, HEADER_H);
    lv_obj_set_style_bg_color(sep, lv_color_make(50, 55, 70), 0);
    lv_obj_set_style_border_width(sep, 0, 0);

    // ── Scrollable shot list ──────────────────────────────────────────────────
    s_shot_list = lv_obj_create(scr);
    lv_obj_set_size(s_shot_list, LCD_W, LISTTEXT_H);
    lv_obj_align(s_shot_list, LV_ALIGN_TOP_MID, 0, HEADER_H + 1);
    lv_obj_set_style_bg_color(s_shot_list, lv_color_make(10, 12, 18), 0);
    lv_obj_set_style_bg_opa(s_shot_list, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_shot_list, 0, 0);
    lv_obj_set_style_pad_all(s_shot_list, 4, 0);
    lv_obj_set_style_pad_row(s_shot_list, 3, 0);
    lv_obj_set_scroll_dir(s_shot_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(s_shot_list, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_flex_flow(s_shot_list, LV_FLEX_FLOW_COLUMN);

    // ── Status bar ────────────────────────────────────────────────────────────
    lv_obj_t *status_bar = lv_obj_create(scr);
    lv_obj_set_size(status_bar, LCD_W, STATUS_H);
    lv_obj_align(status_bar, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(status_bar, lv_color_make(20, 24, 36), 0);
    lv_obj_set_style_bg_opa(status_bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(status_bar, 0, 0);
    lv_obj_set_style_pad_all(status_bar, 2, 0);
    lv_obj_clear_flag(status_bar, LV_OBJ_FLAG_SCROLLABLE);

    s_label_status = lv_label_create(status_bar);
    lv_obj_set_style_text_font(s_label_status, &lv_font_montserrat_14, 0);
    lv_label_set_text(s_label_status, "WiFi... | WS...");
    lv_obj_align(s_label_status, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_text_color(s_label_status, lv_color_make(120, 130, 160), 0);

    ESP_LOGI(TAG, "UI layout built");
}

void ui_add_shot(const shot_event_t *shot)
{
    LVGL_LOCK();
    s_total_shots++;
    s_total_score += shot->score;
    _update_counters();
    _add_shot_row(shot);
    LVGL_UNLOCK();

    ESP_LOGI(TAG, "Shot #%d: score=%d ring=%s (%.1f, %.1f)",
             s_total_shots, shot->score, shot->ring, shot->x_mm, shot->y_mm);
}

void ui_reset(void)
{
    LVGL_LOCK();
    _reset_list();
    LVGL_UNLOCK();
}

void ui_set_status(bool wifi_ok, bool ws_ok)
{
    char buf[40];
    snprintf(buf, sizeof(buf),
             "WiFi %s | WS %s",
             wifi_ok ? "\xE2\x9C\x93" : "...",   // UTF-8 checkmark / ellipsis
             ws_ok   ? "\xE2\x9C\x93" : "...");

    LVGL_LOCK();
    lv_label_set_text(s_label_status, buf);
    lv_obj_set_style_text_color(s_label_status,
        (wifi_ok && ws_ok)
            ? lv_color_make(80, 200, 80)
            : lv_color_make(200, 100, 40),
        0);
    LVGL_UNLOCK();
}

// ── Queue drain (called from LVGL task — mutex already held) ─────────────────
// This function intentionally does NOT lock — it is called from within
// lv_timer_handler() via a registered LVGL timer, which already runs
// inside the LVGL task's mutex window.

void ui_process_queues(void)
{
    // ── Shot queue ────────────────────────────────────────────────────────────
    shot_event_t shot;
    while (xQueueReceive(app_get_shot_queue(), &shot, 0) == pdTRUE) {
        s_total_shots++;
        s_total_score += shot.score;
        _update_counters();
        _add_shot_row(&shot);
        ESP_LOGD(TAG, "Queue: shot #%d score=%d", s_total_shots, shot.score);
    }

    // ── Button queue ──────────────────────────────────────────────────────────
    btn_event_t btn;
    while (xQueueReceive(app_get_btn_queue(), &btn, 0) == pdTRUE) {
        switch (btn.action) {
            case BTN_LONG_PRESS:
                _reset_list();
                ESP_LOGI(TAG, "Button: long press → session reset");
                break;
            default:
                // BTN_SINGLE_CLICK / BTN_DOUBLE_CLICK are handled by main.c
                // which posts a test shot to the shot queue.
                break;
        }
    }
}