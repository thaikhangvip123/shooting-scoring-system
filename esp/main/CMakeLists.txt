idf_component_register(
    SRCS
        "main.c"
        "app_events/app_events.c"
        "display/display.c"
        "ui/ui.c"
        "wifi/wifi.c"
        "ws_client/ws_client.c"
        "http_client/http_client.c"
        "button/button.c"

    INCLUDE_DIRS
        "."               # so #include "app_events/app_events.h" works
        "app_events"
        "display"
        "ui"
        "wifi"
        "ws_client"
        "http_client"
        "button"

    REQUIRES
        ## Display stack
        driver
        esp_lcd
        esp_lcd_ili9341
        lvgl

        ## Networking
        esp_wifi
        esp_http_client
        esp_websocket_client

        ## System
        nvs_flash
        esp_timer
        esp_event
        freertos
        json                  # cJSON
        log
)