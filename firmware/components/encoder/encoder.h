#pragma once
#include "esp_err.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Internal PCNT counter range — hardware counter is 16-bit signed.
   We detect overflow when the delta exceeds HALF this range.         */
#define ENCODER_PCNT_HIGH_LIMIT  32767
#define ENCODER_PCNT_LOW_LIMIT  -32768
#define ENCODER_OVERFLOW_THRESH  16000

typedef struct encoder_s *encoder_handle_t;

/**
 * @brief Allocate and configure a quadrature encoder using PCNT.
 *
 * @param gpio_a    GPIO for encoder phase A
 * @param gpio_b    GPIO for encoder phase B
 * @param handle    Output handle; pass to other encoder_* functions
 * @return ESP_OK on success
 */
esp_err_t encoder_init(int gpio_a, int gpio_b, encoder_handle_t *handle);

/**
 * @brief Read the accumulated encoder count since init (or last reset).
 *        Handles PCNT 16-bit overflow transparently.
 *
 * @param handle  Encoder handle from encoder_init()
 * @param count   Output: signed 64-bit accumulator value
 * @return ESP_OK on success
 */
esp_err_t encoder_get_count(encoder_handle_t handle, int64_t *count);

/**
 * @brief Zero both the PCNT hardware counter and the software accumulator.
 */
esp_err_t encoder_reset(encoder_handle_t handle);

#ifdef __cplusplus
}
#endif
