idf_component_register(
    SRCS "ws_server.c"
    INCLUDE_DIRS "."
    REQUIRES
        esp_http_server
        esp_wifi
        spiffs
        nvs_config
        sensor_task
        esp_log
        json
)
