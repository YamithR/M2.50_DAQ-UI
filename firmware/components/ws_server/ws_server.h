#pragma once
#include "nvs_config.h"
#include "esp_err.h"
#include "sensor_task.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Start the HTTP server with WebSocket and SPIFFS static file serving.
 *        Registers all URI handlers: GET /, GET /js/*, GET /css/*, GET /vendor/*,
 *        GET /ws (WebSocket), GET/POST /api/config, POST /api/config/bluetooth,
 *        POST /api/calibrate.
 *
 * @param port   TCP port (from nvs_config, default 80)
 * @return ESP_OK on success
 */
esp_err_t ws_server_start(uint16_t port);

/**
 * @brief Broadcast a sensor_data_t packet as JSON to all connected WebSocket clients.
 *        Called from sensor_task via callback at 50 Hz.
 *        Must be non-blocking.
 */
void ws_server_broadcast(const sensor_data_t *data, void *ctx);

#ifdef __cplusplus
}
#endif
