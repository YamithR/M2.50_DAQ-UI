#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char     ssid[32];
    char     password[64];
    char     hostname[32];
    uint16_t port;
    float    hid_sens_x;   /* encoder counts per pixel, horizontal */
    float    hid_sens_y;   /* encoder counts per pixel, vertical   */
    bool     bt_enabled;
} m2_config_t;

/* Default values applied on first boot (NVS empty) */
#define M2_CFG_DEFAULT_SSID      "M2-DAQ_AP"
#define M2_CFG_DEFAULT_PASSWORD  ""
#define M2_CFG_DEFAULT_HOSTNAME  "m2daq"
#define M2_CFG_DEFAULT_PORT      80
#define M2_CFG_DEFAULT_SENS_X    1.0f
#define M2_CFG_DEFAULT_SENS_Y    1.0f
#define M2_CFG_DEFAULT_BT        false

/**
 * @brief Initialise NVS flash and write defaults if namespace is empty.
 *        Must be called before any other nvs_config_* function.
 */
esp_err_t nvs_config_init(void);

/** @brief Load current configuration into *out. */
esp_err_t nvs_config_load(m2_config_t *out);

/** @brief Persist the full configuration struct. */
esp_err_t nvs_config_save(const m2_config_t *cfg);

/* --- Partial hot-update helpers (called from REST API handlers) --- */
esp_err_t nvs_config_set_bt_enabled(bool enabled);
esp_err_t nvs_config_set_sensitivity(float sx, float sy);
esp_err_t nvs_config_set_wifi(const char *ssid, const char *password);
esp_err_t nvs_config_set_hostname(const char *hostname);
esp_err_t nvs_config_set_port(uint16_t port);

#ifdef __cplusplus
}
#endif
