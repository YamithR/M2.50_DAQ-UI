#include "ble_stream.h"
#include "sensor_task.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/portmacro.h"

/* NimBLE headers */
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include <stdio.h>
#include <string.h>

static const char *TAG = "ble_stream";

/* Runtime state */
static bool     s_enabled       = false;
static uint16_t s_notify_handle = 0;           /* GATT characteristic value handle */
static uint16_t s_conn_handle   = BLE_HS_CONN_HANDLE_NONE;
static char     s_device_name[48];

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

/* ------------------------------------------------------------------ */
/*  128-bit UUIDs (BLE spec little-endian byte order)                   */
/* ------------------------------------------------------------------ */
/* Service:       12345678-1234-1234-1234-000000000001 */
static const ble_uuid128_t svc_uuid = BLE_UUID128_INIT(
    0x01,0x00,0x00,0x00,0x00,0x00,
    0x34,0x12,0x34,0x12,0x34,0x12,
    0x78,0x56,0x34,0x12
);

/* Sensor notify char: 12345678-1234-1234-1234-000000000002 */
static const ble_uuid128_t char_sensor_uuid = BLE_UUID128_INIT(
    0x02,0x00,0x00,0x00,0x00,0x00,
    0x34,0x12,0x34,0x12,0x34,0x12,
    0x78,0x56,0x34,0x12
);

/* Control write char: 12345678-1234-1234-1234-000000000003 */
static const ble_uuid128_t char_ctrl_uuid = BLE_UUID128_INIT(
    0x03,0x00,0x00,0x00,0x00,0x00,
    0x34,0x12,0x34,0x12,0x34,0x12,
    0x78,0x56,0x34,0x12
);

/* ------------------------------------------------------------------ */
/*  GATT characteristic access callbacks                                */
/* ------------------------------------------------------------------ */
static int sensor_char_access(uint16_t conn_handle, uint16_t attr_handle,
                               struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    /* Read: return empty (data is pushed via notify) */
    return BLE_ATT_ERR_READ_NOT_PERMITTED;
}

static int ctrl_char_access(uint16_t conn_handle, uint16_t attr_handle,
                             struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;

    char buf[64] = { 0 };
    int len = MIN(ctxt->om->om_len, (int)sizeof(buf) - 1);
    memcpy(buf, ctxt->om->om_data, len);

    /* Simple text commands: "bt:on", "bt:off", "calibrate" */
    if (strcmp(buf, "bt:off") == 0) {
        ble_stream_set_enabled(false);
    } else if (strcmp(buf, "bt:on") == 0) {
        ble_stream_set_enabled(true);
    } else if (strcmp(buf, "calibrate") == 0) {
        extern void mpu6050_reset_yaw(void);
        mpu6050_reset_yaw();
    }
    return 0;
}

/* GATT service table */
static const struct ble_gatt_svc_def gatt_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &svc_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]){
            {
                .uuid       = &char_sensor_uuid.u,
                .access_cb  = sensor_char_access,
                .val_handle = &s_notify_handle,
                .flags      = BLE_GATT_CHR_F_NOTIFY,
            },
            {
                .uuid      = &char_ctrl_uuid.u,
                .access_cb = ctrl_char_access,
                .flags     = BLE_GATT_CHR_F_WRITE | BLE_GATT_CHR_F_WRITE_NO_RSP,
            },
            { 0 },  /* Terminator */
        },
    },
    { 0 },  /* Terminator */
};

/* ------------------------------------------------------------------ */
/*  GAP event handler                                                   */
/* ------------------------------------------------------------------ */
static int gap_event_handler(struct ble_gap_event *event, void *arg)
{
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            s_conn_handle = event->connect.conn_handle;
            ESP_LOGI(TAG, "BLE client connected, handle=%u", s_conn_handle);
        } else {
            s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
        }
        break;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "BLE client disconnected, reason=%d", event->disconnect.reason);
        s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
        /* Restart advertising */
        if (s_enabled) {
            ble_stream_set_enabled(true);
        }
        break;

    default:
        break;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
static void start_advertising(void)
{
    struct ble_hs_adv_fields fields = { 0 };
    fields.flags                 = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name                  = (const uint8_t *)s_device_name;
    fields.name_len              = strlen(s_device_name);
    fields.name_is_complete      = 1;

    ble_gap_adv_set_fields(&fields);

    struct ble_gap_adv_params adv_params = { 0 };
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;

    int rc = ble_gap_adv_start(BLE_OWN_ADDR_PUBLIC, NULL, BLE_HS_FOREVER,
                                &adv_params, gap_event_handler, NULL);
    if (rc == 0) {
        ESP_LOGI(TAG, "BLE advertising as \"%s\"", s_device_name);
    } else if (rc != BLE_HS_EALREADY) {
        ESP_LOGE(TAG, "ble_gap_adv_start failed: %d", rc);
    }
}

static void on_sync(void)
{
    ble_hs_util_ensure_addr(0);
    if (s_enabled) start_advertising();
}

static void nimble_host_task(void *param)
{
    nimble_port_run();  /* Blocks until nimble_port_stop() */
    nimble_port_freertos_deinit();
}

/* ------------------------------------------------------------------ */
esp_err_t ble_stream_start(bool enabled, const char *hostname)
{
    snprintf(s_device_name, sizeof(s_device_name), "%s-BLE", hostname);
    s_enabled = enabled;

    nimble_port_init();

    ble_hs_cfg.sync_cb  = on_sync;
    ble_hs_cfg.reset_cb = NULL;

    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_svc_gap_device_name_set(s_device_name);

    int rc = ble_gatts_count_cfg(gatt_svcs);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gatts_count_cfg failed: %d", rc);
        return ESP_FAIL;
    }
    rc = ble_gatts_add_svcs(gatt_svcs);
    if (rc != 0) {
        ESP_LOGE(TAG, "ble_gatts_add_svcs failed: %d", rc);
        return ESP_FAIL;
    }

    nimble_port_freertos_init(nimble_host_task);

    /* Register sensor callback */
    sensor_task_register_callback(ble_stream_notify, NULL);

    ESP_LOGI(TAG, "BLE stream ready, advertising=%s", enabled ? "ON" : "OFF");
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
void ble_stream_notify(const sensor_data_t *d, void *ctx)
{
    portENTER_CRITICAL(&s_mux);
    bool enabled     = s_enabled;
    uint16_t conn_h  = s_conn_handle;
    uint16_t val_h   = s_notify_handle;
    portEXIT_CRITICAL(&s_mux);

    if (!enabled || conn_h == BLE_HS_CONN_HANDLE_NONE || val_h == 0) return;

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

    struct os_mbuf *om = ble_hs_mbuf_from_flat(buf, len);
    if (!om) return;

    ble_gattc_notify_custom(conn_h, val_h, om);
}

/* ------------------------------------------------------------------ */
void ble_stream_set_enabled(bool enabled)
{
    portENTER_CRITICAL(&s_mux);
    s_enabled = enabled;
    portEXIT_CRITICAL(&s_mux);

    if (enabled) {
        start_advertising();
    } else {
        ble_gap_adv_stop();
        ESP_LOGI(TAG, "BLE advertising stopped");
    }
}
