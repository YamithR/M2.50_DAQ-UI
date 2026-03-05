#include "encoder.h"
#include "driver/pulse_cnt.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/portmacro.h"
#include <stdlib.h>

static const char *TAG = "encoder";

/* ------------------------------------------------------------------ */
struct encoder_s {
    pcnt_unit_handle_t   unit;
    int                  last_raw;    /* last raw PCNT reading */
    int64_t              accumulator; /* unbounded signed count */
    portMUX_TYPE         mux;
};

/* ------------------------------------------------------------------ */
esp_err_t encoder_init(int gpio_a, int gpio_b, encoder_handle_t *handle)
{
    struct encoder_s *enc = calloc(1, sizeof(*enc));
    if (!enc) return ESP_ERR_NO_MEM;
    enc->mux = (portMUX_TYPE)portMUX_INITIALIZER_UNLOCKED;

    /* PCNT unit */
    pcnt_unit_config_t unit_cfg = {
        .high_limit = ENCODER_PCNT_HIGH_LIMIT,
        .low_limit  = ENCODER_PCNT_LOW_LIMIT,
    };
    ESP_ERROR_CHECK(pcnt_new_unit(&unit_cfg, &enc->unit));

    /* Channel A — counts on phase A edges, level determined by phase B */
    pcnt_chan_config_t chan_a_cfg = {
        .edge_gpio_num  = gpio_a,
        .level_gpio_num = gpio_b,
    };
    pcnt_channel_handle_t chan_a;
    ESP_ERROR_CHECK(pcnt_new_channel(enc->unit, &chan_a_cfg, &chan_a));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(
        chan_a,
        PCNT_CHANNEL_EDGE_ACTION_DECREASE,  /* falling edge */
        PCNT_CHANNEL_EDGE_ACTION_INCREASE   /* rising edge  */
    ));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(
        chan_a,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,     /* B high → keep direction */
        PCNT_CHANNEL_LEVEL_ACTION_INVERSE   /* B low  → invert direction */
    ));

    /* Channel B — mirror for full quadrature (4× resolution) */
    pcnt_chan_config_t chan_b_cfg = {
        .edge_gpio_num  = gpio_b,
        .level_gpio_num = gpio_a,
    };
    pcnt_channel_handle_t chan_b;
    ESP_ERROR_CHECK(pcnt_new_channel(enc->unit, &chan_b_cfg, &chan_b));
    ESP_ERROR_CHECK(pcnt_channel_set_edge_action(
        chan_b,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE,
        PCNT_CHANNEL_EDGE_ACTION_DECREASE
    ));
    ESP_ERROR_CHECK(pcnt_channel_set_level_action(
        chan_b,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,
        PCNT_CHANNEL_LEVEL_ACTION_INVERSE
    ));

    /* Glitch filter: ignore pulses < 1 µs */
    pcnt_glitch_filter_config_t filter = { .max_glitch_ns = 1000 };
    ESP_ERROR_CHECK(pcnt_unit_set_glitch_filter(enc->unit, &filter));

    ESP_ERROR_CHECK(pcnt_unit_enable(enc->unit));
    ESP_ERROR_CHECK(pcnt_unit_clear_count(enc->unit));
    ESP_ERROR_CHECK(pcnt_unit_start(enc->unit));

    *handle = enc;
    ESP_LOGI(TAG, "Encoder initialised: A=GPIO%d B=GPIO%d", gpio_a, gpio_b);
    return ESP_OK;
}

/* ------------------------------------------------------------------ */
esp_err_t encoder_get_count(encoder_handle_t handle, int64_t *count)
{
    int raw;
    ESP_ERROR_CHECK(pcnt_unit_get_count(handle->unit, &raw));

    portENTER_CRITICAL(&handle->mux);
    int delta = raw - handle->last_raw;

    /* Overflow correction: if delta jumps more than half the range,
       the hardware counter wrapped around.                           */
    if (delta >  ENCODER_OVERFLOW_THRESH) delta -= (ENCODER_PCNT_HIGH_LIMIT - ENCODER_PCNT_LOW_LIMIT + 1);
    if (delta < -ENCODER_OVERFLOW_THRESH) delta += (ENCODER_PCNT_HIGH_LIMIT - ENCODER_PCNT_LOW_LIMIT + 1);

    handle->accumulator += delta;
    handle->last_raw     = raw;
    *count = handle->accumulator;
    portEXIT_CRITICAL(&handle->mux);

    return ESP_OK;
}

/* ------------------------------------------------------------------ */
esp_err_t encoder_reset(encoder_handle_t handle)
{
    portENTER_CRITICAL(&handle->mux);
    handle->accumulator = 0;
    handle->last_raw    = 0;
    portEXIT_CRITICAL(&handle->mux);
    return pcnt_unit_clear_count(handle->unit);
}
