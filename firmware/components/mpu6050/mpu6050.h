#pragma once
#include "esp_err.h"
#include "driver/i2c_master.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* MPU-6050 I2C address (AD0 pin to GND) */
#define MPU6050_ADDR  0x68

/* Complementary filter tuning */
#define MPU6050_ALPHA 0.98f   /* gyro weight (short-term trust)  */
#define MPU6050_DT    0.02f   /* seconds, matches 50 Hz task     */

typedef struct {
    float pitch;   /* degrees, range: approx -90..+90  */
    float roll;    /* degrees, range: approx -90..+90  */
    float yaw;     /* degrees, range: 0..360 (gyro int.)*/
    /* Raw 16-bit ADC values (for calibration / debug) */
    int16_t ax_raw, ay_raw, az_raw;
    int16_t gx_raw, gy_raw, gz_raw;
} mpu6050_data_t;

/**
 * @brief Initialise I2C master bus and wake the MPU-6050 from sleep.
 * @param port       I2C port number (I2C_NUM_0 or I2C_NUM_1)
 * @param sda_gpio   GPIO number for I2C SDA
 * @param scl_gpio   GPIO number for I2C SCL
 * @param clk_hz     I2C clock frequency in Hz (e.g. 400000)
 * @return ESP_OK on success
 */
esp_err_t mpu6050_init(int port, int sda_gpio, int scl_gpio, uint32_t clk_hz);

/**
 * @brief Read one sample and update complementary filter state.
 *        Must be called at a fixed rate equal to 1/MPU6050_DT (50 Hz).
 * @param out  Pointer to mpu6050_data_t that will receive the result.
 * @return ESP_OK on success
 */
esp_err_t mpu6050_read(mpu6050_data_t *out);

/**
 * @brief Reset yaw integrator to zero (call via REST /api/calibrate).
 */
void mpu6050_reset_yaw(void);

#ifdef __cplusplus
}
#endif
