#include "ws_server.h"
#include "nvs_config.h"
#include "sensor_task.h"
#include "esp_http_server.h"
#include "esp_spiffs.h"
#include "esp_log.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "ws_server";

/* WebSocket client file descriptor list */
#define MAX_WS_CLIENTS 4
static int s_ws_fds[MAX_WS_CLIENTS];
static int s_ws_count = 0;
static httpd_handle_t s_server = NULL;
static portMUX_TYPE  s_fd_mux  = portMUX_INITIALIZER_UNLOCKED;

/* ------------------------------------------------------------------ */
/*  SPIFFS static file serving                                          */
/* ------------------------------------------------------------------ */
#define SPIFFS_BASE "/spiffs"

static esp_err_t static_file_handler(httpd_req_t *req)
{
    char path[128];
    const char *uri = req->uri;

    /* Map "/" to "/index.html" */
    if (strcmp(uri, "/") == 0) {
        uri = "/index.html";
    }
    snprintf(path, sizeof(path), "%s%s", SPIFFS_BASE, uri);

    /* Determine Content-Type */
    const char *ct = "application/octet-stream";
    if (strstr(path, ".html")) ct = "text/html";
    else if (strstr(path, ".css"))  ct = "text/css";
    else if (strstr(path, ".js"))   ct = "application/javascript";
    else if (strstr(path, ".json")) ct = "application/json";
    else if (strstr(path, ".ico"))  ct = "image/x-icon";
    else if (strstr(path, ".png"))  ct = "image/png";

    FILE *f = fopen(path, "r");
    if (!f) {
        ESP_LOGW(TAG, "File not found: %s", path);
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND, "File Not Found");
        return ESP_FAIL;
    }

    httpd_resp_set_type(req, ct);
    /* Cache static assets for 1 hour, never cache index.html */
    if (strstr(path, "index.html")) {
        httpd_resp_set_hdr(req, "Cache-Control", "no-cache");
    } else {
        httpd_resp_set_hdr(req, "Cache-Control", "max-age=3600");
    }

    char buf[512];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), f)) > 0) {
        httpd_resp_send_chunk(req, buf, n);
    }
    fclose(f);
    httpd_resp_send_chunk(req, NULL, 0);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/*  WebSocket handler                                                   */
/* ------------------------------------------------------------------ */
static esp_err_t ws_handler(httpd_req_t *req)
{
    if (req->method == HTTP_GET) {
        /* WebSocket handshake — store the fd */
        int fd = httpd_req_to_sockfd(req);
        portENTER_CRITICAL(&s_fd_mux);
        if (s_ws_count < MAX_WS_CLIENTS) {
            s_ws_fds[s_ws_count++] = fd;
            ESP_LOGI(TAG, "WS client connected: fd=%d (%d total)", fd, s_ws_count);
        }
        portEXIT_CRITICAL(&s_fd_mux);
        return ESP_OK;
    }

    /* Receive frame (handle pings, close) */
    httpd_ws_frame_t pkt = { .type = HTTPD_WS_TYPE_TEXT };
    esp_err_t ret = httpd_ws_recv_frame(req, &pkt, 0);
    if (ret != ESP_OK) return ret;
    if (pkt.len == 0) return ESP_OK;

    pkt.payload = malloc(pkt.len + 1);
    if (!pkt.payload) return ESP_ERR_NO_MEM;
    ret = httpd_ws_recv_frame(req, &pkt, pkt.len);
    free(pkt.payload);
    return ret;
}

/* Called by esp_http_server when a socket is closed */
static void ws_close_fn(httpd_handle_t hd, int sockfd)
{
    portENTER_CRITICAL(&s_fd_mux);
    for (int i = 0; i < s_ws_count; i++) {
        if (s_ws_fds[i] == sockfd) {
            s_ws_fds[i] = s_ws_fds[--s_ws_count];
            ESP_LOGI(TAG, "WS client disconnected: fd=%d (%d remain)", sockfd, s_ws_count);
            break;
        }
    }
    portEXIT_CRITICAL(&s_fd_mux);
    close(sockfd);
}

/* ------------------------------------------------------------------ */
/*  Sensor broadcast (registered as sensor_task callback)              */
/* ------------------------------------------------------------------ */
void ws_server_broadcast(const sensor_data_t *d, void *ctx)
{
    if (!s_server || s_ws_count == 0) return;

    char buf[256];
    int len = snprintf(buf, sizeof(buf),
        "{\"s1\":%s,\"s2\":%s,\"s3\":%s,"
        "\"gas_valve\":%s,"
        "\"pitch\":%.2f,\"roll\":%.2f,\"yaw\":%.1f,"
        "\"enc_h\":%lld,\"enc_v\":%lld,"
        "\"ts\":%llu}",
        d->s1 ? "true" : "false",
        d->s2 ? "true" : "false",
        d->s3 ? "true" : "false",
        d->gas_valve ? "true" : "false",
        d->pitch, d->roll, d->yaw,
        (long long)d->enc_h, (long long)d->enc_v,
        (unsigned long long)d->ts
    );

    httpd_ws_frame_t pkt = {
        .type    = HTTPD_WS_TYPE_TEXT,
        .payload = (uint8_t *)buf,
        .len     = len,
    };

    portENTER_CRITICAL(&s_fd_mux);
    for (int i = s_ws_count - 1; i >= 0; i--) {
        esp_err_t ret = httpd_ws_send_frame_async(s_server, s_ws_fds[i], &pkt);
        if (ret != ESP_OK) {
            ESP_LOGD(TAG, "Dead WS client fd=%d removed", s_ws_fds[i]);
            s_ws_fds[i] = s_ws_fds[--s_ws_count];
        }
    }
    portEXIT_CRITICAL(&s_fd_mux);
}

/* ------------------------------------------------------------------ */
/*  REST API: GET /api/config                                           */
/* ------------------------------------------------------------------ */
static esp_err_t api_config_get(httpd_req_t *req)
{
    m2_config_t cfg;
    nvs_config_load(&cfg);

    char body[256];
    snprintf(body, sizeof(body),
        "{\"ssid\":\"%s\",\"hostname\":\"%s\","
        "\"port\":%u,\"bt_enabled\":%s,"
        "\"hid_sens_x\":%.3f,\"hid_sens_y\":%.3f}",
        cfg.ssid, cfg.hostname, cfg.port,
        cfg.bt_enabled ? "true" : "false",
        cfg.hid_sens_x, cfg.hid_sens_y
    );
    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, body);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/*  REST API: POST /api/config                                          */
/* ------------------------------------------------------------------ */
static esp_err_t api_config_post(httpd_req_t *req)
{
    char body[256] = { 0 };
    int len = MIN((int)req->content_len, (int)sizeof(body) - 1);
    if (httpd_req_recv(req, body, len) != len) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Bad body");
        return ESP_FAIL;
    }

    cJSON *root = cJSON_Parse(body);
    if (!root) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    m2_config_t cfg;
    nvs_config_load(&cfg);

    cJSON *v;
    if ((v = cJSON_GetObjectItem(root, "ssid"))     && cJSON_IsString(v)) strlcpy(cfg.ssid,     v->valuestring, sizeof(cfg.ssid));
    if ((v = cJSON_GetObjectItem(root, "password")) && cJSON_IsString(v)) strlcpy(cfg.password, v->valuestring, sizeof(cfg.password));
    if ((v = cJSON_GetObjectItem(root, "hostname")) && cJSON_IsString(v)) strlcpy(cfg.hostname, v->valuestring, sizeof(cfg.hostname));
    if ((v = cJSON_GetObjectItem(root, "port"))     && cJSON_IsNumber(v)) cfg.port       = (uint16_t)v->valueint;
    if ((v = cJSON_GetObjectItem(root, "hid_sens_x")) && cJSON_IsNumber(v)) cfg.hid_sens_x = (float)v->valuedouble;
    if ((v = cJSON_GetObjectItem(root, "hid_sens_y")) && cJSON_IsNumber(v)) cfg.hid_sens_y = (float)v->valuedouble;

    nvs_config_save(&cfg);
    cJSON_Delete(root);

    httpd_resp_sendstr(req, "{\"ok\":true}");
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/*  REST API: POST /api/config/bluetooth                                */
/* ------------------------------------------------------------------ */
static esp_err_t api_bt_post(httpd_req_t *req)
{
    char body[64] = { 0 };
    int len = MIN((int)req->content_len, (int)sizeof(body) - 1);
    httpd_req_recv(req, body, len);

    cJSON *root = cJSON_Parse(body);
    if (!root) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    cJSON *v = cJSON_GetObjectItem(root, "enabled");
    bool enabled = cJSON_IsTrue(v);
    cJSON_Delete(root);

    nvs_config_set_bt_enabled(enabled);

    /* Notify ble_stream at runtime */
    extern void ble_stream_set_enabled(bool);
    ble_stream_set_enabled(enabled);

    httpd_resp_sendstr(req, "{\"ok\":true}");
    ESP_LOGI(TAG, "BT mode set to %s", enabled ? "ON" : "OFF");
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/*  REST API: POST /api/calibrate  (reset yaw integrator)              */
/* ------------------------------------------------------------------ */
static esp_err_t api_calibrate_post(httpd_req_t *req)
{
    extern void mpu6050_reset_yaw(void);
    mpu6050_reset_yaw();
    httpd_resp_sendstr(req, "{\"ok\":true}");
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
/*  Server startup                                                      */
/* ------------------------------------------------------------------ */
esp_err_t ws_server_start(uint16_t port)
{
    /* Mount SPIFFS */
    esp_vfs_spiffs_conf_t spiffs_cfg = {
        .base_path              = SPIFFS_BASE,
        .partition_label        = "storage",
        .max_files              = 8,
        .format_if_mount_failed = false,
    };
    esp_err_t ret = esp_vfs_spiffs_register(&spiffs_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "SPIFFS mount failed: %s", esp_err_to_name(ret));
        return ret;
    }

    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port      = port;
    cfg.max_open_sockets = MAX_WS_CLIENTS + 4;
    cfg.lru_purge_enable = true;
    cfg.close_fn         = ws_close_fn;
    cfg.uri_match_fn     = httpd_uri_match_wildcard;

    ESP_ERROR_CHECK(httpd_start(&s_server, &cfg));

    /* WebSocket */
    httpd_uri_t ws_uri = {
        .uri          = "/ws",
        .method       = HTTP_GET,
        .handler      = ws_handler,
        .is_websocket = true,
    };
    httpd_register_uri_handler(s_server, &ws_uri);

    /* REST */
    httpd_uri_t api_cfg_get  = { .uri="/api/config",           .method=HTTP_GET,  .handler=api_config_get  };
    httpd_uri_t api_cfg_post = { .uri="/api/config",           .method=HTTP_POST, .handler=api_config_post };
    httpd_uri_t api_bt_uri   = { .uri="/api/config/bluetooth", .method=HTTP_POST, .handler=api_bt_post     };
    httpd_uri_t api_cal_uri  = { .uri="/api/calibrate",        .method=HTTP_POST, .handler=api_calibrate_post };
    httpd_register_uri_handler(s_server, &api_cfg_get);
    httpd_register_uri_handler(s_server, &api_cfg_post);
    httpd_register_uri_handler(s_server, &api_bt_uri);
    httpd_register_uri_handler(s_server, &api_cal_uri);

    /* Static files — wildcard catch-all (must be last) */
    httpd_uri_t static_uri = { .uri="/*", .method=HTTP_GET, .handler=static_file_handler };
    httpd_register_uri_handler(s_server, &static_uri);

    /* Register broadcast callback with sensor_task */
    sensor_task_register_callback(ws_server_broadcast, NULL);

    ESP_LOGI(TAG, "HTTP server started on port %u, SPIFFS mounted", port);
    return ESP_OK;
}
