#pragma once
#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GPIO assignments (ESP32-S3 DevKitC-1) */
#define GPIO_I2C_SDA    8
#define GPIO_I2C_SCL    9
#define GPIO_MPU_INT    10

#define GPIO_ENC_H_A    1
#define GPIO_ENC_H_B    2
#define GPIO_ENC_V_A    3
#define GPIO_ENC_V_B    4

#define GPIO_S1         5   /* S1_BLOQUEADO  — active-low */
#define GPIO_S2         6   /* S2_RETENEDOR  — active-low */
#define GPIO_S3         7   /* S3_VALVULA    — active-low */

#define GPIO_STATUS_LED 21  /* Active-high status LED */

/* Sampling rate */
#define SENSOR_TASK_HZ          50
#define SENSOR_TASK_PERIOD_MS   (1000 / SENSOR_TASK_HZ)

/**
 * @brief Canonical data packet — shared between all output channels
 *        (WebSocket, HID mouse, BLE GATT notify).
 *        JSON wire format mirrors field names exactly.
 */
typedef struct {
    /* Firing mechanism position sensors (active-low inverted) */
    bool  s1;           /* S1_BLOQUEADO  */
    bool  s2;           /* S2_RETENEDOR  */
    bool  s3;           /* S3_VALVULA    */
    bool  gas_valve;    /* = s3          */

    /* IMU (MPU-6050 complementary filter output) */
    float pitch;        /* degrees, ≈ -90..+90  */
    float roll;         /* degrees, ≈ -90..+90  */
    float yaw;          /* degrees, 0..360      */

    /* Quadrature encoder accumulators */
    int64_t enc_h;      /* horizontal, counts since boot */
    int64_t enc_v;      /* vertical,   counts since boot */

    /* Monotonic timestamp */
    uint64_t ts;        /* milliseconds since boot (esp_timer_get_time/1000) */
} sensor_data_t;

/**
 * @brief Initialise hardware (I2C, PCNT, GPIO) and start the 50 Hz task.
 *        Call once from app_main() after nvs_config_init().
 */
esp_err_t sensor_task_start(void);

/**
 * @brief Thread-safe snapshot of the latest sensor data.
 * @param out  Destination struct
 */
void sensor_task_get_data(sensor_data_t *out);

/**
 * @brief Callback type for downstream consumers (ws_server, hid_mouse, ble_stream).
 *        Registered via sensor_task_register_callback().
 *        Called from sensor task context at 50 Hz — must be non-blocking.
 */
typedef void (*sensor_callback_t)(const sensor_data_t *data, void *user_ctx);

/**
 * @brief Register a callback that is invoked with every new sensor packet.
 *        Up to 4 callbacks can be registered.
 */
esp_err_t sensor_task_register_callback(sensor_callback_t cb, void *user_ctx);

#ifdef __cplusplus
}
#endif
