#include <stdio.h>
#include <stdbool.h>
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_lcd_sh8601.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_timer.h"
#include "button_bsp.h"

#include "lv_conf.h"

#define LCD_HOST         SPI3_HOST
#define PIN_NUM_RST      9
#define PIN_NUM_SCLK     10
#define PIN_NUM_DC       11
#define PIN_NUM_CS       12
#define PIN_NUM_MOSI     13

#define LCD_H_RES        170
#define LCD_V_RES        320
#define LCD_PIXEL_CLOCK_HZ  (20 * 1000 * 1000)
#define LCD_CMD_BITS     8
#define LCD_PARAM_BITS   8
#define LVGL_DRAW_BUF_LINES  (LCD_V_RES / 2)

// ── LCD init commands ─────────────────────────────────────────────────
static const sh8601_lcd_init_cmd_t lcd_init_cmds[] = {
    {0x11, NULL,              0,    120}, // SLPOUT
    {0x3A, (uint8_t[]){0x55}, 1,      0}, // COLMOD RGB565
    {0x53, (uint8_t[]){0x20}, 1,      0}, // WRCTRLD brightness on
    {0xB1, (uint8_t[]){0xFF}, 1,      0}, // WRDISBV max brightness
    {0x29, NULL,              0,     20}, // DISPON
};

esp_lcd_panel_io_handle_t  io_handle        = NULL;
esp_lcd_panel_handle_t     lcd_panel_handle = NULL;
static lv_disp_drv_t       disp_drv;        // static — pointer used in ISR

// Global UI --------------------------------------
static lv_obj_t *label_total_shot;
static lv_obj_t *label_total_score;
static lv_obj_t *shot_list;

static int total_shot = 0;
static int total_score = 0;
static SemaphoreHandle_t lvgl_mutex;

#define BTN_SINGLE_CLICK_BIT  (0x01 << 0)
#define BTN_DOUBLE_CLICK_BIT  (0x01 << 1)
#define BTN_LONG_PRESS_BIT    (0x01 << 2)

// ── Async flush done callback ─────────────────────────────────────
static bool IRAM_ATTR lcd_trans_done_cb(esp_lcd_panel_io_handle_t panel_io,
                                         esp_lcd_panel_io_event_data_t *edata,
                                         void *user_ctx)
{
    lv_disp_drv_t *drv = (lv_disp_drv_t *)user_ctx;
    lv_disp_flush_ready(drv);
    return false;
}

static void my_flush_cb(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map)
{
    esp_lcd_panel_handle_t panel = (esp_lcd_panel_handle_t)drv->user_data;
    int offsetx1 = area->x1 + 35;
    int offsetx2 = area->x2 + 35;
    int offsety1 = area->y1;
    int offsety2 = area->y2;

    esp_lcd_panel_draw_bitmap(panel, offsetx1, offsety1, offsetx2 + 1, offsety2 + 1, color_map);
}

// LGVL Tick
static void tick_cb(void *arg)
{
    lv_tick_inc(5);
}
// ── lvgl_task — add mutex ─────────────────────────────────────────────────
static void lvgl_task(void *arg)
{
    while (1) {
        xSemaphoreTake(lvgl_mutex, portMAX_DELAY);
        lv_timer_handler();
        xSemaphoreGive(lvgl_mutex);
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// ── Add shot function ─────────────────────────────────────────────────────
static void add_shot(int score);

// ── Button task (core 0) ──────────────────────────────────────────────────
static void button_task(void *arg)
{
    while (1) {
        EventBits_t bits = xEventGroupWaitBits(
            key_groups,
            BTN_SINGLE_CLICK_BIT | BTN_DOUBLE_CLICK_BIT | BTN_LONG_PRESS_BIT,
            pdTRUE, pdFALSE, portMAX_DELAY);

        // Issue 2 fix: hold mutex for ALL lvgl calls
        xSemaphoreTake(lvgl_mutex, portMAX_DELAY);

        if (bits & BTN_SINGLE_CLICK_BIT) {
            add_shot(1);
        }
        if (bits & BTN_DOUBLE_CLICK_BIT) {
            add_shot(3);
        }
        if (bits & BTN_LONG_PRESS_BIT) {
            total_shot  = 0;
            total_score = 0;
            lv_label_set_text(label_total_shot,  "Total shot: 0");
            lv_label_set_text(label_total_score, "Total score: 0");
            lv_obj_clean(shot_list);
        }

        xSemaphoreGive(lvgl_mutex);
    }
}

static void add_shot(int score)
{
    total_shot++;
    total_score += score;

    char buf[64];

    // update header
    sprintf(buf, "Total shot: %d", total_shot);
    lv_label_set_text(label_total_shot, buf);

    sprintf(buf, "Total score: %d", total_score);
    lv_label_set_text(label_total_score, buf);

    // add new shot
    lv_obj_t *shot_label = lv_label_create(shot_list);
    sprintf(buf, "Shot %d: %d", total_shot, score);
    lv_label_set_text(shot_label, buf);

    // auto scroll xuống dưới
    lv_obj_scroll_to_view(shot_label, LV_ANIM_ON);
}
// Display init
static void display_init(void)
{
    spi_bus_config_t buscfg = {
        .sclk_io_num      = PIN_NUM_SCLK,
        .mosi_io_num      = PIN_NUM_MOSI,
        .quadwp_io_num    = -1,
        .quadhd_io_num    = -1,
        .max_transfer_sz  = LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(uint16_t),
    };
    ESP_ERROR_CHECK(spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num        = PIN_NUM_DC,
        .cs_gpio_num        = PIN_NUM_CS,
        .pclk_hz            = LCD_PIXEL_CLOCK_HZ,
        .lcd_cmd_bits       = LCD_CMD_BITS,
        .lcd_param_bits     = LCD_PARAM_BITS,
        .spi_mode           = 0,
        .trans_queue_depth  = 10,
        .on_color_trans_done = lcd_trans_done_cb, // Step 3: wire up done CB
        .user_ctx           = &disp_drv,
    };

    sh8601_vendor_config_t vendor_config = {
        .init_cmds      = lcd_init_cmds,
        .init_cmds_size = sizeof(lcd_init_cmds) / sizeof(lcd_init_cmds[0]),
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(
        (esp_lcd_spi_bus_handle_t)LCD_HOST, &io_config, &io_handle));

    esp_lcd_panel_dev_config_t panel_config = {
        .reset_gpio_num  = PIN_NUM_RST,
        .rgb_ele_order   = LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel  = 16,
        .vendor_config   = &vendor_config,
        .data_endian     = LCD_RGB_DATA_ENDIAN_BIG,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_sh8601(io_handle, &panel_config, &lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_reset(lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_init(lcd_panel_handle));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(lcd_panel_handle, true));
}

void app_main(void)
{
    lvgl_mutex = xSemaphoreCreateMutex();
    display_init();
    button_Init();  
    lv_init();

    // ── Step 2: DMA buffers ─────────────────────────────────────────────
    size_t buf_size = LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t);
    lv_color_t *buf1 = heap_caps_malloc(LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t), MALLOC_CAP_DMA);
    lv_color_t *buf2 = heap_caps_malloc(LCD_H_RES * LVGL_DRAW_BUF_LINES * sizeof(lv_color_t), MALLOC_CAP_DMA);
    assert(buf1 && buf2);

    static lv_disp_draw_buf_t draw_buf;
    lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LCD_H_RES * LVGL_DRAW_BUF_LINES);

    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res   = LCD_H_RES;
    disp_drv.ver_res   = LCD_V_RES;
    disp_drv.flush_cb  = my_flush_cb;
    disp_drv.draw_buf  = &draw_buf;
    disp_drv.user_data = lcd_panel_handle;
    lv_disp_drv_register(&disp_drv);

    // 2ms tick timer
    const esp_timer_create_args_t timer_args = {
        .callback = tick_cb,
        .name     = "lv_tick"
    };
    esp_timer_handle_t timer;
    ESP_ERROR_CHECK(esp_timer_create(&timer_args, &timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(timer, 2000));

    // ── UI ─────────────────────────────────────────────────────────────

    // background
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    
    // HEADER (fixed)
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, LCD_H_RES, 60);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_style_bg_color(header, lv_color_black(), 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_pad_all(header, 0, 0);
    lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

    label_total_shot = lv_label_create(header); 
    lv_obj_set_style_text_font(label_total_shot, &lv_font_montserrat_20, 0);
    lv_label_set_text(label_total_shot, "Total shot: 0");
    lv_obj_align(label_total_shot, LV_ALIGN_TOP_LEFT, 5, 5);
    lv_obj_set_style_text_color(label_total_shot, lv_color_white(), 0);

    label_total_score = lv_label_create(header);
    lv_obj_set_style_text_font(label_total_score, &lv_font_montserrat_20, 0);
    lv_label_set_text(label_total_score, "Total score: 0");
    lv_obj_align(label_total_score, LV_ALIGN_TOP_LEFT, 5, 25);
    lv_obj_set_style_text_color(label_total_score, lv_color_white(), 0);
    // separator line
    lv_obj_t *sep = lv_obj_create(header);
    lv_obj_set_size(sep, LCD_H_RES, 1);
    lv_obj_align(sep, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(sep, lv_color_make(60, 60, 60), 0);
    lv_obj_set_style_border_width(sep, 0, 0);

    // SHOT LIST (scrollable)
    shot_list = lv_obj_create(lv_scr_act());
    lv_obj_set_style_text_font(shot_list, &lv_font_montserrat_20, 0);
    lv_obj_set_size(shot_list, LCD_H_RES, LCD_V_RES - 60);
    lv_obj_align(shot_list, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(shot_list, lv_color_black(), 0);
    lv_obj_set_style_border_width(shot_list, 0, 0);
    lv_obj_set_style_pad_all(shot_list, 4, 0);
    lv_obj_set_style_pad_row(shot_list, 4, 0);

    lv_obj_set_scroll_dir(shot_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(shot_list, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_flex_flow(shot_list, LV_FLEX_FLOW_COLUMN);

    // test data
    for (int i = 0; i < 10; i++) {
        add_shot(i % 10);
    }

    // LVGL task
    xTaskCreatePinnedToCore(lvgl_task, "lvgl", 8192, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(button_task, "btn", 4096, NULL, 4, NULL, 0); // core 0
}