idf_component_register(
    SRCS "hid_mouse.c"
    INCLUDE_DIRS "."
    REQUIRES
        tinyusb
        nvs_config
        sensor_task
        freertos
        esp_log
)
