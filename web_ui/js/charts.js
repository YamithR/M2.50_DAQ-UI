/**
 * charts.js — Rolling time-series charts using uPlot.
 *
 * Three charts with a 300-sample (6 s at 50 Hz) rolling window:
 *   1. Sensors (S1, S2, S3) — discrete 0/1
 *   2. IMU (pitch, roll, yaw)
 *   3. Encoders (enc_h, enc_v)
 */
window.charts = (function () {
    'use strict';

    var MAX_SAMPLES = 300;

    /* ── Shared dark theme ─────────────────────────────────────────── */
    var AXES_OPTS = {
        stroke: '#555',
        ticks:  { stroke: '#333' },
        grid:   { stroke: '#1a1a1a' },
    };
    var LABEL_STYLE = { fill: '#4b5320', font: '11px Courier New' };

    /* ── Buffer helpers ─────────────────────────────────────────────── */
    function makeBuffers(n) {
        var arr = [];
        for (var i = 0; i < n; i++) arr.push([]);
        return arr;
    }
    function pushRolling(buf, val, max) {
        buf.push(val);
        if (buf.length > max) buf.shift();
    }

    /* ── Sensor chart ──────────────────────────────────────────────── */
    var sBufs = makeBuffers(4); /* ts, s1, s2, s3 */

    var sOpts = {
        width:  document.getElementById('chart-sensors').offsetWidth || 800,
        height: 120,
        padding: [8, 8, 8, 8],
        cursor: { show: false },
        legend: { show: true },
        axes:   [
            Object.assign({}, AXES_OPTS, { label: 'Tiempo (ms)', ...LABEL_STYLE }),
            Object.assign({}, AXES_OPTS, { label: 'Estado', min: -0.1, max: 1.1, ...LABEL_STYLE }),
        ],
        series: [
            {},
            { label: 'S1', stroke: '#d32f2f', width: 1.5, fill: 'rgba(211,47,47,0.1)' },
            { label: 'S2', stroke: '#ffa000', width: 1.5, fill: 'rgba(255,160,0,0.1)' },
            { label: 'S3', stroke: '#0f0',    width: 1.5, fill: 'rgba(0,255,0,0.1)'   },
        ],
    };
    var sChart = new uPlot(sOpts, [[], [], [], []], document.getElementById('chart-sensors'));

    /* ── IMU chart ─────────────────────────────────────────────────── */
    var imuBufs = makeBuffers(4); /* ts, pitch, roll, yaw */

    var imuOpts = {
        width:  document.getElementById('chart-imu').offsetWidth || 800,
        height: 140,
        padding: [8, 8, 8, 8],
        cursor: { show: false },
        legend: { show: true },
        axes:   [
            Object.assign({}, AXES_OPTS, { label: 'Tiempo (ms)', ...LABEL_STYLE }),
            Object.assign({}, AXES_OPTS, { label: 'Grados (°)',  ...LABEL_STYLE }),
        ],
        series: [
            {},
            { label: 'Pitch', stroke: '#29B6F6', width: 1.5 },
            { label: 'Roll',  stroke: '#ab47bc', width: 1.5 },
            { label: 'Yaw',   stroke: '#ffa000', width: 1.5 },
        ],
    };
    var imuChart = new uPlot(imuOpts, [[], [], [], []], document.getElementById('chart-imu'));

    /* ── Encoder chart ─────────────────────────────────────────────── */
    var encBufs = makeBuffers(3); /* ts, enc_h, enc_v */

    var encOpts = {
        width:  document.getElementById('chart-enc').offsetWidth || 800,
        height: 120,
        padding: [8, 8, 8, 8],
        cursor: { show: false },
        legend: { show: true },
        axes:   [
            Object.assign({}, AXES_OPTS, { label: 'Tiempo (ms)', ...LABEL_STYLE }),
            Object.assign({}, AXES_OPTS, { label: 'Cuentas',     ...LABEL_STYLE }),
        ],
        series: [
            {},
            { label: 'ENC_H', stroke: '#0f0',    width: 1.5 },
            { label: 'ENC_V', stroke: '#29B6F6', width: 1.5 },
        ],
    };
    var encChart = new uPlot(encOpts, [[], [], []], document.getElementById('chart-enc'));

    /* ── Push a new data packet ─────────────────────────────────────── */
    function push(d) {
        var t = d.ts / 1000;  /* convert to seconds for uPlot time axis */

        /* Sensors */
        pushRolling(sBufs[0], t,              MAX_SAMPLES);
        pushRolling(sBufs[1], d.s1 ? 1 : 0,  MAX_SAMPLES);
        pushRolling(sBufs[2], d.s2 ? 1 : 0,  MAX_SAMPLES);
        pushRolling(sBufs[3], d.s3 ? 1 : 0,  MAX_SAMPLES);
        sChart.setData(sBufs);

        /* IMU */
        pushRolling(imuBufs[0], t,       MAX_SAMPLES);
        pushRolling(imuBufs[1], d.pitch, MAX_SAMPLES);
        pushRolling(imuBufs[2], d.roll,  MAX_SAMPLES);
        pushRolling(imuBufs[3], d.yaw,   MAX_SAMPLES);
        imuChart.setData(imuBufs);

        /* Encoders */
        pushRolling(encBufs[0], t,       MAX_SAMPLES);
        pushRolling(encBufs[1], d.enc_h, MAX_SAMPLES);
        pushRolling(encBufs[2], d.enc_v, MAX_SAMPLES);
        encChart.setData(encBufs);
    }

    /* ── Resize on window resize ────────────────────────────────────── */
    window.addEventListener('resize', function () {
        var w = document.getElementById('chart-sensors').offsetWidth || 800;
        sChart.setSize(  { width: w, height: 120 });
        imuChart.setSize({ width: w, height: 140 });
        encChart.setSize({ width: w, height: 120 });
    });

    return { push: push };
})();
