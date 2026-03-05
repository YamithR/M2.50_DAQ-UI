idf_component_register(
    SRCS "ble_stream.c"
    INCLUDE_DIRS "."
    REQUIRES
        bt
        nvs_config
        sensor_task
        freertos
        esp_log
)
