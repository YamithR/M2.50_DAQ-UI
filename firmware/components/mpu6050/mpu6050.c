#include "mpu6050.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include <math.h>
#include <string.h>

static const char *TAG = "mpu6050";

/* MPU-6050 register addresses */
#define REG_PWR_MGMT_1  0x6B
#define REG_SMPLRT_DIV  0x19
#define REG_CONFIG      0x1A
#define REG_GYRO_CFG    0x1B
#define REG_ACCEL_CFG   0x1C
#define REG_ACCEL_XOUT  0x3B  /* 14 bytes: accel(6) + temp(2) + gyro(6) */
#define REG_WHO_AM_I    0x75

/* Scaling factors:
   Accel: ±2g range → 16384 LSB/g
   Gyro:  ±250 °/s  → 131.0 LSB/(°/s)  */
#define ACCEL_SCALE  16384.0f
#define GYRO_SCALE   131.0f

static i2c_master_bus_handle_t  s_bus_handle;
static i2c_master_dev_handle_t  s_dev_handle;

/* Complementary filter state */
static float s_pitch = 0.0f;
static float s_roll  = 0.0f;
static float s_yaw   = 0.0f;

/* ------------------------------------------------------------------ */
static esp_err_t mpu_write_reg(uint8_t reg, uint8_t value)
{
    uint8_t buf[2] = { reg, value };
    return i2c_master_transmit(s_dev_handle, buf, 2, pdMS_TO_TICKS(50));
}

static esp_err_t mpu_read_regs(uint8_t reg, uint8_t *data, size_t len)
{
    return i2c_master_transmit_receive(s_dev_handle,
                                       &reg, 1,
                                       data, len,
                                       pdMS_TO_TICKS(50));
}

/* ------------------------------------------------------------------ */
esp_err_t mpu6050_init(int port, int sda_gpio, int scl_gpio, uint32_t clk_hz)
{
    /* Configure I2C master bus */
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port     = port,
        .sda_io_num   = sda_gpio,
        .scl_io_num   = scl_gpio,
        .clk_source   = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    ESP_ERROR_CHECK(i2c_new_master_bus(&bus_cfg, &s_bus_handle));

    /* Add MPU-6050 device */
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address  = MPU6050_ADDR,
        .scl_speed_hz    = clk_hz,
    };
    ESP_ERROR_CHECK(i2c_master_bus_add_device(s_bus_handle, &dev_cfg, &s_dev_handle));

    /* Verify WHO_AM_I */
    uint8_t who;
    ESP_ERROR_CHECK(mpu_read_regs(REG_WHO_AM_I, &who, 1));
    if (who != MPU6050_ADDR) {
        ESP_LOGE(TAG, "WHO_AM_I mismatch: expected 0x%02X got 0x%02X",
                 MPU6050_ADDR, who);
        return ESP_FAIL;
    }

    /* Wake from sleep */
    ESP_ERROR_CHECK(mpu_write_reg(REG_PWR_MGMT_1, 0x00));
    /* Sample rate divider: 1kHz / (1+8) ≈ 111 Hz */
    ESP_ERROR_CHECK(mpu_write_reg(REG_SMPLRT_DIV, 0x08));
    /* Low-pass filter: ~44 Hz */
    ESP_ERROR_CHECK(mpu_write_reg(REG_CONFIG, 0x03));
    /* Gyro ±250 °/s */
    ESP_ERROR_CHECK(mpu_write_reg(REG_GYRO_CFG, 0x00));
    /* Accel ±2g */
    ESP_ERROR_CHECK(mpu_write_reg(REG_ACCEL_CFG, 0x00));

    ESP_LOGI(TAG, "MPU-6050 initialised (I2C port %d, SDA=%d, SCL=%d)",
             port, sda_gpio, scl_gpio);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
esp_err_t mpu6050_read(mpu6050_data_t *out)
{
    uint8_t raw[14];
    ESP_ERROR_CHECK(mpu_read_regs(REG_ACCEL_XOUT, raw, 14));

    /* Parse big-endian signed 16-bit words */
    out->ax_raw = (int16_t)((raw[0]  << 8) | raw[1]);
    out->ay_raw = (int16_t)((raw[2]  << 8) | raw[3]);
    out->az_raw = (int16_t)((raw[4]  << 8) | raw[5]);
    /* raw[6], raw[7] = temperature (unused) */
    out->gx_raw = (int16_t)((raw[8]  << 8) | raw[9]);
    out->gy_raw = (int16_t)((raw[10] << 8) | raw[11]);
    out->gz_raw = (int16_t)((raw[12] << 8) | raw[13]);

    /* Convert to physical units */
    float ax = out->ax_raw / ACCEL_SCALE;
    float ay = out->ay_raw / ACCEL_SCALE;
    float az = out->az_raw / ACCEL_SCALE;
    float gx = out->gx_raw / GYRO_SCALE;  /* °/s */
    float gy = out->gy_raw / GYRO_SCALE;
    float gz = out->gz_raw / GYRO_SCALE;

    /* Accelerometer angles */
    float pitch_acc = atan2f(ay, az) * (180.0f / (float)M_PI);
    float roll_acc  = atan2f(-ax, az) * (180.0f / (float)M_PI);

    /* Complementary filter */
    s_pitch = MPU6050_ALPHA * (s_pitch + gx * MPU6050_DT) +
              (1.0f - MPU6050_ALPHA) * pitch_acc;
    s_roll  = MPU6050_ALPHA * (s_roll  + gy * MPU6050_DT) +
              (1.0f - MPU6050_ALPHA) * roll_acc;
    s_yaw  += gz * MPU6050_DT;

    /* Wrap yaw to 0..360 */
    if (s_yaw >= 360.0f) s_yaw -= 360.0f;
    if (s_yaw <    0.0f) s_yaw += 360.0f;

    out->pitch = s_pitch;
    out->roll  = s_roll;
    out->yaw   = s_yaw;

    return ESP_OK;
}

/* ------------------------------------------------------------------ */
void mpu6050_reset_yaw(void)
{
    s_yaw = 0.0f;
    ESP_LOGI(TAG, "Yaw integrator reset to 0");
}
