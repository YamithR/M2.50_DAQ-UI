#include "nvs_config.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "nvs_config";
#define NVS_NAMESPACE "m2_cfg"

/* ------------------------------------------------------------------ */
esp_err_t nvs_config_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
        err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition erased (reason: %s)", esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    /* Check if namespace exists; if not, write defaults */
    nvs_handle_t h;
    err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "First boot detected — writing default config");
        m2_config_t def = {
            .ssid       = M2_CFG_DEFAULT_SSID,
            .password   = M2_CFG_DEFAULT_PASSWORD,
            .hostname   = M2_CFG_DEFAULT_HOSTNAME,
            .port       = M2_CFG_DEFAULT_PORT,
            .hid_sens_x = M2_CFG_DEFAULT_SENS_X,
            .hid_sens_y = M2_CFG_DEFAULT_SENS_Y,
            .bt_enabled = M2_CFG_DEFAULT_BT,
        };
        return nvs_config_save(&def);
    }
    if (err == ESP_OK) nvs_close(h);
    return err;
}

/* ------------------------------------------------------------------ */
esp_err_t nvs_config_load(m2_config_t *out)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READONLY, &h));

    size_t len;

    len = sizeof(out->ssid);
    nvs_get_str(h, "ssid",     out->ssid,     &len);
    len = sizeof(out->password);
    nvs_get_str(h, "password", out->password, &len);
    len = sizeof(out->hostname);
    nvs_get_str(h, "hostname", out->hostname, &len);

    uint16_t port = M2_CFG_DEFAULT_PORT;
    nvs_get_u16(h, "port", &port);
    out->port = port;

    int32_t sx_int = (int32_t)(M2_CFG_DEFAULT_SENS_X * 1000);
    int32_t sy_int = (int32_t)(M2_CFG_DEFAULT_SENS_Y * 1000);
    nvs_get_i32(h, "hid_sx", &sx_int);
    nvs_get_i32(h, "hid_sy", &sy_int);
    out->hid_sens_x = sx_int / 1000.0f;
    out->hid_sens_y = sy_int / 1000.0f;

    uint8_t bt = M2_CFG_DEFAULT_BT ? 1 : 0;
    nvs_get_u8(h, "bt_enabled", &bt);
    out->bt_enabled = (bt != 0);

    nvs_close(h);
    ESP_LOGI(TAG, "Config loaded: ssid=%s host=%s port=%u bt=%d",
             out->ssid, out->hostname, out->port, out->bt_enabled);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
esp_err_t nvs_config_save(const m2_config_t *cfg)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));

    nvs_set_str(h, "ssid",     cfg->ssid);
    nvs_set_str(h, "password", cfg->password);
    nvs_set_str(h, "hostname", cfg->hostname);
    nvs_set_u16(h, "port",     cfg->port);
    nvs_set_i32(h, "hid_sx",  (int32_t)(cfg->hid_sens_x * 1000));
    nvs_set_i32(h, "hid_sy",  (int32_t)(cfg->hid_sens_y * 1000));
    nvs_set_u8 (h, "bt_enabled", cfg->bt_enabled ? 1 : 0);

    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}

/* --- Partial helpers ----------------------------------------------- */
esp_err_t nvs_config_set_bt_enabled(bool enabled)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    nvs_set_u8(h, "bt_enabled", enabled ? 1 : 0);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t nvs_config_set_sensitivity(float sx, float sy)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    nvs_set_i32(h, "hid_sx", (int32_t)(sx * 1000));
    nvs_set_i32(h, "hid_sy", (int32_t)(sy * 1000));
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t nvs_config_set_wifi(const char *ssid, const char *password)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    nvs_set_str(h, "ssid",     ssid);
    nvs_set_str(h, "password", password);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t nvs_config_set_hostname(const char *hostname)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    nvs_set_str(h, "hostname", hostname);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}

esp_err_t nvs_config_set_port(uint16_t port)
{
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    nvs_set_u16(h, "port", port);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err;
}
