#pragma once
#include "esp_err.h"
#include "sensor_task.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* UUIDs for the custom GATT service (128-bit, little-endian in BLE) */
#define BLE_SVC_UUID   "12345678-1234-1234-1234-000000000001"
#define BLE_CHAR_SENSOR_UUID "12345678-1234-1234-1234-000000000002"  /* NOTIFY */
#define BLE_CHAR_CTRL_UUID   "12345678-1234-1234-1234-000000000003"  /* WRITE  */

/**
 * @brief Initialise NimBLE stack and GATT server.
 *        Starts BLE advertising under the name "<hostname>-BLE".
 *
 * @param enabled   If false, BLE is configured but advertising is suppressed
 *                  until ble_stream_set_enabled(true) is called.
 * @param hostname  Device name prefix (from nvs_config, e.g. "m2daq")
 * @return ESP_OK on success
 */
esp_err_t ble_stream_start(bool enabled, const char *hostname);

/**
 * @brief Send sensor data as a BLE GATT notification to subscribed clients.
 *        Registered as a sensor_task callback — called at 50 Hz.
 *        Silently drops the packet when no client is subscribed.
 */
void ble_stream_notify(const sensor_data_t *data, void *ctx);

/**
 * @brief Enable or disable BLE advertising and notifications at runtime.
 *        Called when the web UI toggles BT mode via POST /api/config/bluetooth.
 */
void ble_stream_set_enabled(bool enabled);

#ifdef __cplusplus
}
#endif
