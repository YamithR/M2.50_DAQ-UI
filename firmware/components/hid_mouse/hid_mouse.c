#include "hid_mouse.h"
#include "sensor_task.h"
#include "nvs_config.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"

/* TinyUSB headers */
#include "tinyusb.h"
#include "class/hid/hid_device.h"

static const char *TAG = "hid_mouse";

/* Cached sensitivity (encoder counts per pixel) */
static float s_sens_x = 1.0f;
static float s_sens_y = 1.0f;

/* Previous encoder values to compute delta per HID report */
static int64_t s_last_enc_h = 0;
static int64_t s_last_enc_v = 0;

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

/* ------------------------------------------------------------------ */
/*  TinyUSB HID report descriptor — standard boot-protocol mouse       */
/* ------------------------------------------------------------------ */
static const uint8_t hid_report_descriptor[] = {
    TUD_HID_REPORT_DESC_MOUSE()
};

static const uint8_t *hid_descriptor_cb(uint8_t instance, uint16_t *size)
{
    *size = sizeof(hid_report_descriptor);
    return hid_report_descriptor;
}

/* TinyUSB device descriptor (USB 2.0 Full Speed, HID class) */
static const tusb_desc_device_t device_descriptor = {
    .bLength            = sizeof(tusb_desc_device_t),
    .bDescriptorType    = TUSB_DESC_DEVICE,
    .bcdUSB             = 0x0200,
    .bDeviceClass       = 0x00,        /* Class defined at interface level */
    .bDeviceSubClass    = 0x00,
    .bDeviceProtocol    = 0x00,
    .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor           = 0x303A,      /* Espressif VID */
    .idProduct          = 0x4004,
    .bcdDevice          = 0x0100,
    .iManufacturer      = 0x01,
    .iProduct           = 0x02,
    .iSerialNumber      = 0x03,
    .bNumConfigurations = 0x01,
};

/* ------------------------------------------------------------------ */
/*  Sensor callback — invoked at 50 Hz by sensor_task                   */
/* ------------------------------------------------------------------ */
static void hid_sensor_cb(const sensor_data_t *data, void *ctx)
{
    if (!tud_mounted()) return;

    portENTER_CRITICAL(&s_mux);
    int64_t delta_h = data->enc_h - s_last_enc_h;
    int64_t delta_v = data->enc_v - s_last_enc_v;
    s_last_enc_h = data->enc_h;
    s_last_enc_v = data->enc_v;
    float sx = s_sens_x;
    float sy = s_sens_y;
    portEXIT_CRITICAL(&s_mux);

    /* Scale and clamp to int8 range [-127, 127] */
    float fx = (float)delta_h / sx;
    float fy = (float)delta_v / sy;

    int16_t mx = (int16_t)(fx < -127.0f ? -127 : fx > 127.0f ? 127 : fx);
    int16_t my = (int16_t)(fy < -127.0f ? -127 : fy > 127.0f ? 127 : fy);

    if (mx == 0 && my == 0) return;  /* Skip zero-movement reports */

    /* tud_hid_mouse_report(report_id, buttons, x, y, scroll, pan) */
    tud_hid_mouse_report(0, 0x00, (int8_t)mx, (int8_t)my, 0, 0);
}

/* ------------------------------------------------------------------ */
esp_err_t hid_mouse_start(const m2_config_t *cfg)
{
    portENTER_CRITICAL(&s_mux);
    s_sens_x = cfg->hid_sens_x;
    s_sens_y = cfg->hid_sens_y;
    portEXIT_CRITICAL(&s_mux);

    /* TinyUSB driver config */
    const tinyusb_config_t tusb_cfg = {
        .device_descriptor = &device_descriptor,
        .string_descriptor = (const char *[]){
            [0] = (char[]){ 0x09, 0x04 },  /* LangID: English (US) */
            [1] = "Espressif",
            [2] = "M2-DAQ HID Mouse",
            [3] = "000001",
        },
        .string_descriptor_count = 4,
        .external_phy             = false,
        .configuration_descriptor = NULL,  /* Use TinyUSB auto-generated */
    };
    ESP_ERROR_CHECK(tinyusb_driver_install(&tusb_cfg));

    /* Wait for USB host to enumerate (up to 2 s) */
    int wait_ms = 2000;
    while (!tud_mounted() && wait_ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(50));
        wait_ms -= 50;
    }
    if (!tud_mounted()) {
        ESP_LOGW(TAG, "USB not mounted (no host connected) — HID reports ignored");
    } else {
        ESP_LOGI(TAG, "HID mouse enumerated by host");
    }

    /* Register 50 Hz callback */
    sensor_task_register_callback(hid_sensor_cb, NULL);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
void hid_mouse_set_sensitivity(float sx, float sy)
{
    portENTER_CRITICAL(&s_mux);
    s_sens_x = sx;
    s_sens_y = sy;
    portEXIT_CRITICAL(&s_mux);
    ESP_LOGI(TAG, "Sensitivity updated: X=%.3f Y=%.3f", sx, sy);
}

/* ------------------------------------------------------------------ */
/*  TinyUSB HID callbacks (required by TinyUSB — implementation stubs) */
/* ------------------------------------------------------------------ */
uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id,
                                hid_report_type_t report_type,
                                uint8_t *buffer, uint16_t reqlen)
{
    (void)instance; (void)report_id; (void)report_type;
    (void)buffer;   (void)reqlen;
    return 0;
}

void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id,
                            hid_report_type_t report_type,
                            const uint8_t *buffer, uint16_t bufsize)
{
    (void)instance; (void)report_id; (void)report_type;
    (void)buffer;   (void)bufsize;
}
