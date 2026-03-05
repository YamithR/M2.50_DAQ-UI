#pragma once
#include "nvs_config.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Initialise TinyUSB and register a standard HID boot-protocol mouse.
 *        Register the HID report callback with sensor_task.
 *        Must be called before WiFi init to ensure USB is enumerated first.
 *
 * @param cfg  Pointer to loaded config (reads hid_sens_x / hid_sens_y)
 * @return ESP_OK on success
 */
esp_err_t hid_mouse_start(const m2_config_t *cfg);

/**
 * @brief Update cached sensitivity values (called after REST config update).
 */
void hid_mouse_set_sensitivity(float sx, float sy);

#ifdef __cplusplus
}
#endif
