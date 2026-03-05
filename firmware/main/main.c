#include "nvs_config.h"
#include "sensor_task.h"
#include "ws_server.h"
#include "hid_mouse.h"
#include "ble_stream.h"
#include "sdkconfig.h"

#include "esp_log.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "mdns.h"
#include <string.h>

static const char *TAG = "main";

/* WiFi event group bits */
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1
#define WIFI_MAX_RETRIES   5

static EventGroupHandle_t s_wifi_event_group;
static int s_wifi_retries = 0;

/* ------------------------------------------------------------------ */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_wifi_retries < WIFI_MAX_RETRIES) {
            esp_wifi_connect();
            s_wifi_retries++;
            ESP_LOGW(TAG, "WiFi reconnect attempt %d/%d", s_wifi_retries, WIFI_MAX_RETRIES);
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
            ESP_LOGE(TAG, "WiFi connection failed after %d retries", WIFI_MAX_RETRIES);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&ev->ip_info.ip));
        s_wifi_retries = 0;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static esp_err_t wifi_connect(const char *ssid, const char *password)
{
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t inst_any, inst_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, &inst_any));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, &inst_got_ip));

    wifi_config_t wifi_cfg = { 0 };
    strlcpy((char *)wifi_cfg.sta.ssid,     ssid,     sizeof(wifi_cfg.sta.ssid));
    strlcpy((char *)wifi_cfg.sta.password, password, sizeof(wifi_cfg.sta.password));
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_OPEN;  /* Allow open networks */

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "Connecting to SSID: %s", ssid);

    /* Wait for connection or failure */
    EventBits_t bits = xEventGroupWaitBits(
        s_wifi_event_group,
        WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
        pdFALSE, pdFALSE,
        pdMS_TO_TICKS(15000)
    );

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "WiFi connected");
        return ESP_OK;
    }

    /* Not connected — start AP mode as fallback so the user can reconfigure */
    ESP_LOGW(TAG, "Starting AP fallback: SSID=M2-DAQ-SETUP");
    esp_netif_create_default_wifi_ap();
    wifi_config_t ap_cfg = {
        .ap = {
            .ssid           = "M2-DAQ-SETUP",
            .ssid_len       = 0,
            .password       = "m2daq1234",
            .max_connection = 2,
            .authmode       = WIFI_AUTH_WPA2_PSK,
        }
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_cfg));
    return ESP_ERR_WIFI_NOT_CONNECT;
}

static void mdns_setup(const char *hostname)
{
    ESP_ERROR_CHECK(mdns_init());
    ESP_ERROR_CHECK(mdns_hostname_set(hostname));
    mdns_service_add(NULL, "_http", "_tcp", 80, NULL, 0);
    ESP_LOGI(TAG, "mDNS: http://%s.local/", hostname);
}

/* ================================================================== */
void app_main(void)
{
    ESP_LOGI(TAG, "M2.50 DAQ starting...");

    /* 1. Persistent configuration */
    ESP_ERROR_CHECK(nvs_config_init());
    m2_config_t cfg;
    ESP_ERROR_CHECK(nvs_config_load(&cfg));

    /* 2. TinyUSB HID mouse (must start before WiFi to claim USB device) */
    ESP_ERROR_CHECK(hid_mouse_start(&cfg));

    /* 3. WiFi + mDNS */
    wifi_connect(cfg.ssid, cfg.password);
    mdns_setup(cfg.hostname);

    /* 4. HTTP + WebSocket server (serves SPIFFS web files) */
    ESP_ERROR_CHECK(ws_server_start(cfg.port));

    /* 5. BLE GATT streaming (coexists with WiFi on ESP32-S3) */
    ESP_ERROR_CHECK(ble_stream_start(cfg.bt_enabled, cfg.hostname));

    /* 6. Sensor task (last — begins broadcasting to all consumers at 50 Hz) */
    ESP_ERROR_CHECK(sensor_task_start());

    ESP_LOGI(TAG, "System ready — http://%s.local/ | BT: %s",
             cfg.hostname, cfg.bt_enabled ? "ON" : "OFF");
}
