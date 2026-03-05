idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        nvs_flash
        nvs_config
        sensor_task
        ws_server
        hid_mouse
        ble_stream
        esp_wifi
        esp_netif
        esp_event
        mdns
)
