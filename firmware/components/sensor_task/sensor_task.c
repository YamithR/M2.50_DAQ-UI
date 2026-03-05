#include "sensor_task.h"
#include "mpu6050.h"
#include "encoder.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/portmacro.h"

static const char *TAG = "sensor_task";

/* ------------------------------------------------------------------ */
/* Registered downstream callbacks                                      */
#define MAX_CALLBACKS 4
static sensor_callback_t s_callbacks[MAX_CALLBACKS];
static void             *s_cb_ctx[MAX_CALLBACKS];
static int               s_cb_count = 0;

/* Shared data protected by a spinlock */
static sensor_data_t  s_data;
static portMUX_TYPE   s_mux = portMUX_INITIALIZER_UNLOCKED;

/* Encoder handles */
static encoder_handle_t s_enc_h;
static encoder_handle_t s_enc_v;

/* ------------------------------------------------------------------ */
static void init_gpio_sensors(void)
{
    gpio_config_t io_cfg = {
        .pin_bit_mask = (1ULL << GPIO_S1) | (1ULL << GPIO_S2) | (1ULL << GPIO_S3),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,  /* Polled at 50 Hz — no ISR needed */
    };
    ESP_ERROR_CHECK(gpio_config(&io_cfg));

    gpio_config_t led_cfg = {
        .pin_bit_mask = (1ULL << GPIO_STATUS_LED),
        .mode         = GPIO_MODE_OUTPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&led_cfg));
}

/* ------------------------------------------------------------------ */
static void sensor_task_fn(void *pvParam)
{
    TickType_t last_wake = xTaskGetTickCount();

    while (1) {
        /* --- Read MPU-6050 ---------------------------------------- */
        mpu6050_data_t imu;
        if (mpu6050_read(&imu) != ESP_OK) {
            ESP_LOGW(TAG, "MPU read failed");
        }

        /* --- Read encoder accumulators ---------------------------- */
        int64_t enc_h_val = 0, enc_v_val = 0;
        encoder_get_count(s_enc_h, &enc_h_val);
        encoder_get_count(s_enc_v, &enc_v_val);

        /* --- Read digital sensors (active-low) -------------------- */
        bool s1 = (gpio_get_level(GPIO_S1) == 0);
        bool s2 = (gpio_get_level(GPIO_S2) == 0);
        bool s3 = (gpio_get_level(GPIO_S3) == 0);

        /* --- Update shared data ----------------------------------- */
        portENTER_CRITICAL(&s_mux);
        s_data.s1        = s1;
        s_data.s2        = s2;
        s_data.s3        = s3;
        s_data.gas_valve = s3;
        s_data.pitch     = imu.pitch;
        s_data.roll      = imu.roll;
        s_data.yaw       = imu.yaw;
        s_data.enc_h     = enc_h_val;
        s_data.enc_v     = enc_v_val;
        s_data.ts        = (uint64_t)(esp_timer_get_time() / 1000);
        portEXIT_CRITICAL(&s_mux);

        /* --- Status LED: ON when any sensor active ---------------- */
        gpio_set_level(GPIO_STATUS_LED, (s1 || s2 || s3) ? 1 : 0);

        /* --- Invoke downstream callbacks (non-blocking) ----------- */
        for (int i = 0; i < s_cb_count; i++) {
            s_callbacks[i](&s_data, s_cb_ctx[i]);
        }

        vTaskDelayUntil(&last_wake, pdMS_TO_TICKS(SENSOR_TASK_PERIOD_MS));
    }
}

/* ------------------------------------------------------------------ */
esp_err_t sensor_task_start(void)
{
    /* Initialise hardware */
    ESP_ERROR_CHECK(mpu6050_init(0, GPIO_I2C_SDA, GPIO_I2C_SCL, 400000));
    ESP_ERROR_CHECK(encoder_init(GPIO_ENC_H_A, GPIO_ENC_H_B, &s_enc_h));
    ESP_ERROR_CHECK(encoder_init(GPIO_ENC_V_A, GPIO_ENC_V_B, &s_enc_v));
    init_gpio_sensors();

    /* Spawn task on Core 0, high priority */
    BaseType_t ret = xTaskCreatePinnedToCore(
        sensor_task_fn,
        "sensor_task",
        4096,
        NULL,
        configMAX_PRIORITIES - 2,
        NULL,
        0   /* Core 0 */
    );
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create sensor_task");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Sensor task started at %d Hz", SENSOR_TASK_HZ);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
void sensor_task_get_data(sensor_data_t *out)
{
    portENTER_CRITICAL(&s_mux);
    *out = s_data;
    portEXIT_CRITICAL(&s_mux);
}

/* ------------------------------------------------------------------ */
esp_err_t sensor_task_register_callback(sensor_callback_t cb, void *user_ctx)
{
    if (s_cb_count >= MAX_CALLBACKS) {
        ESP_LOGE(TAG, "Callback limit (%d) reached", MAX_CALLBACKS);
        return ESP_ERR_NO_MEM;
    }
    s_callbacks[s_cb_count] = cb;
    s_cb_ctx[s_cb_count]    = user_ctx;
    s_cb_count++;
    return ESP_OK;
}
