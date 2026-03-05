idf_component_register(
    SRCS "sensor_task.c"
    INCLUDE_DIRS "."
    REQUIRES
        freertos
        driver
        mpu6050
        encoder
        nvs_config
        esp_timer
)
