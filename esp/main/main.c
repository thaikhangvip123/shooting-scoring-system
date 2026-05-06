#include <stdio.h>
#include <stdbool.h>
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_timer.h"

#include "lv_conf.h"

// ── Pin & LCD config ──────────────────────────────────────────────────────
#define LCD_HOST            SPI3_HOST
#define PIN_NUM_SCLK        12
#define PIN_NUM_MOSI        11
#define PIN_NUM_MISO        13
#define PIN_NUM_CS          10
#define PIN_NUM_BL          45
#define PIN_NUM_RST         -1
#define PIN_NUM_DC          46

#define LCD_H_RES           240
#define LCD_V_RES           320
#define LCD_PIXEL_CLOCK_HZ  (20 * 1000 * 1000)
#define LCD_CMD_BITS        8
#define LCD_PARAM_BITS      8
#define LVGL_DRAW_BUF_LINES (LCD_V_RES / 2)

// ── Global handles ────────────────────────────────────────────────────────
esp_lcd_panel_io_handle_t  io_handle        = NULL;
esp_lcd_panel_handle_t     lcd_panel_handle = NULL;
static lv_disp_drv_t       disp_drv;   // static: address used by DMA callback

// ── DMA done callback → tells LVGL flush is complete ─────────────────────
static bool IRAM_ATTR lcd_trans_done_cb(esp_lcd_panel_io_handle_t panel_io,
                                         esp_lcd_panel_io_event_data_t *edata,
                                         void *user_ctx)
{
    lv_disp_drv_t *drv = (lv_disp_drv_t *)user_ctx;
    lv_disp_flush_ready(drv);
    return false;
}

// ── LVGL flush callback ───────────────────────────────────────────────────
static void my_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map)
{
    esp_lcd_panel_handle_t panel = (esp_lcd_panel_handle_t)drv->user_data;
    esp_lcd_panel_draw_bitmap(panel,
                              area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1,
                              color_map);
    // lv_disp_flush_ready() is called by lcd_trans_done_cb when DMA finishes
}

// ── 2 ms LVGL tick ────────────────────────────────────────────────────────
static void tick_cb(void *arg)
{
    lv_tick_inc(2);
}

// ── LVGL task (core 1) ────────────────────────────────────────────────────
static void lvgl_task(void *arg)
{
    while (1) {
        lv_timer_handler();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// ── Display init — mirrors working bitmap code exactly ────────────────────
static void display_init(void)
{
    gpio_set_direction(PIN_NUM_BL, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_NUM_BL, 1);

    spi_bus_config_t buscfg = {
        .sclk_io_num     = PIN_NUM_SCLK,
        .mosi_io_num     = PIN_NUM_MOSI,
        .miso_io_num     = PIN_NUM_MISO,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num         = PIN_NUM_DC,
        .cs_gpio_num         = PIN_NUM_CS,
        .pclk_hz             = LCD_PIXEL_CLOCK_HZ,
        .lcd_cmd_bits        = LCD_CMD_BITS,
        .lcd_param_bits      = LCD_PARAM_BITS,
        .spi_mode            = 0,
        .trans_queue_depth   = 10,
        .on_color_trans_done = lcd_trans_done_cb,  // safe: disp_drv already init'd
        .user_ctx            = &disp_drv,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(
        (esp_lcd_spi_bus_handle_t)LCD_HOST, &io_config, &io_handle));

    esp_lcd_panel_dev_config_t panel_config = {
        .reset_gpio_num = PIN_NUM_RST,
        .rgb_ele_order  = LCD_RGB_ELEMENT_ORDER_BGR,  // ILI9341 uses BGR
        .bits_per_pixel = 16,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(io_handle, &panel_config, &lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(lcd_panel_handle, true));
    ESP_ERROR_CHECK(esp_lcd_panel_mirror(lcd_panel_handle, true, false));  // landscape mode
}

void app_main(void)
{
    // lv_disp_drv_init MUST come before display_init so &disp_drv is valid
    // when the DMA done callback is registered inside display_init()
    lv_init();
    lv_disp_drv_init(&disp_drv);

    display_init();

    // DMA-capable draw buffers
    lv_color_t *buf1 = heap_caps_malloc(
        LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t), MALLOC_CAP_DMA);
    lv_color_t *buf2 = heap_caps_malloc(
        LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t), MALLOC_CAP_DMA);
    assert(buf1 && buf2);

    static lv_disp_draw_buf_t draw_buf;
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_H_RES * LVGL_DRAW_BUF_LINES);

    disp_drv.hor_res   = LCD_H_RES;
    disp_drv.ver_res   = LCD_V_RES;
    disp_drv.flush_cb  = my_flush_cb;
    disp_drv.draw_buf  = &draw_buf;
    disp_drv.user_data = lcd_panel_handle;
    lv_disp_drv_register(&disp_drv);

    // 2 ms tick timer
    const esp_timer_create_args_t timer_args = {
        .callback = tick_cb,
        .name     = "lv_tick",
    };
    esp_timer_handle_t timer;
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(timer, 2000));

    // ── UI ────────────────────────────────────────────────────────────────

    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    // Header
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, LCD_H_RES, 60);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(header, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_pad_all(header, 0, 0);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    lv_obj_t *label_total_shot = lv_label_create(header);
    lv_obj_set_style_text_font(label_total_shot, &lv_font_montserrat_20, 0);
    lv_label_set_text(label_total_shot, "Total shot: 0");
    lv_obj_align(label_total_shot, LV_ALIGN_TOP_LEFT, 5, 5);
    lv_obj_set_style_text_color(label_total_shot, lv_color_white(), 0);

    lv_obj_t *label_total_score = lv_label_create(header);
    lv_obj_set_style_text_font(label_total_score, &lv_font_montserrat_20, 0);
    lv_label_set_text(label_total_score, "Total score: 0");
    lv_obj_align(label_total_score, LV_ALIGN_TOP_LEFT, 5, 30);
    lv_obj_set_style_text_color(label_total_score, lv_color_white(), 0);

    // Separator
    lv_obj_t *sep = lv_obj_create(header);
    lv_obj_set_size(sep, LCD_H_RES, 1);
    lv_obj_align(sep, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(sep, lv_color_make(60, 60, 60), 0);
    lv_obj_set_style_border_width(sep, 0, 0);

    // Scrollable shot list
    lv_obj_t *shot_list = lv_obj_create(scr);
    lv_obj_set_size(shot_list, LCD_H_RES, LCD_V_RES - 60);
    lv_obj_align(shot_list, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(shot_list, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(shot_list, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(shot_list, 0, 0);
    lv_obj_set_style_pad_all(shot_list, 4, 0);
    lv_obj_set_style_pad_row(shot_list, 4, 0);
    lv_obj_set_style_text_font(shot_list, &lv_font_montserrat_20, 0);
    lv_obj_set_scroll_dir(shot_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(shot_list, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_flex_flow(shot_list, LV_FLEX_FLOW_COLUMN);

    // Static test data
    for (int i = 1; i <= 10; i++) {
        char buf[32];
        lv_obj_t *row = lv_label_create(shot_list);
        snprintf(buf, sizeof(buf), "Shot %d: %d", i, i % 4 + 1);
        lv_label_set_text(row, buf);
        lv_obj_set_style_text_color(row, lv_color_white(), 0);
    }

    xTaskCreatePinnedToCore(lvgl_task, "lvgl", 8192, NULL, 5, NULL, 1);
}