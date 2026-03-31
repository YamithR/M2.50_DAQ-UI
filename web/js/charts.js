/**
 * charts.js — Cuatro gráficas en tiempo real con uPlot.
 *
 * Ring buffers pre-allocados con Float64Array para minimizar la presión
 * sobre el GC del navegador a 50 Hz sostenidos.
 *
 * Ventanas de tiempo:
 *   chart-cadencia → 60 s (3 000 muestras) — cadencia de fuego (disp/min)
 *   chart-sensors  →  6 s (  300 muestras) — estados S1, S2, S3 (0/1)
 *   chart-imu      →  6 s (  300 muestras) — roll, pitch, yaw (°)
 *   chart-enc      →  6 s (  300 muestras) — enc_h, enc_v (cuentas)
 *
 * La cadencia se calcula como la tasa de flancos ascendentes de S3 en una
 * ventana deslizante de 60 s, expresada en disparos/min.
 */

window.charts = (function () {
  'use strict';

  // ── Ring buffer con Float64Array ───────────────────────────────────────────
  class RingBuffer {
    constructor(cap) {
      this.data = new Float64Array(cap);
      this.cap  = cap;
      this.size = 0;
      this.head = 0;
    }
    push(val) {
      this.data[this.head] = val;
      this.head = (this.head + 1) % this.cap;
      if (this.size < this.cap) this.size++;
    }
    toArray() {
      const out = new Array(this.size);
      const start = this.size < this.cap ? 0 : this.head;
      for (let i = 0; i < this.size; i++) {
        out[i] = this.data[(start + i) % this.cap];
      }
      return out;
    }
  }

  // ── Capacidades ────────────────────────────────────────────────────────────
  const N_CADENCIA = 3000;   // 60 s × 50 Hz
  const N_SHORT    = 3000;   // 60 s × 50 Hz

  // ── Buffers ────────────────────────────────────────────────────────────────
  const bTs  = new RingBuffer(N_CADENCIA);
  const bCad = new RingBuffer(N_CADENCIA);   // disparos/min
  const bS3Cad = new RingBuffer(N_CADENCIA); // S3 digital (0/1) en escala cadencia
  const bS1  = new RingBuffer(N_SHORT);
  const bS2  = new RingBuffer(N_SHORT);
  const bS3  = new RingBuffer(N_SHORT);
  const bRoll  = new RingBuffer(N_SHORT);
  const bPitch = new RingBuffer(N_SHORT);
  const bYaw   = new RingBuffer(N_SHORT);
  const bEncH  = new RingBuffer(N_SHORT);
  const bEncV  = new RingBuffer(N_SHORT);

  // Timestamps de flancos S3↑ para el cálculo de cadencia
  const s3Edges  = [];          // timestamps en segundos
  const CADEN_WIN = 60.0;       // ventana de cadencia en segundos

  let prevS3   = false;
  let plots    = {};            // uPlot instances
  let ready    = false;

  // ── Opciones comunes de uPlot ──────────────────────────────────────────────
  function commonOpts(series, width) {
    return {
      width: width,
      height: 140,
      title: '',
      series,
      scales: { x: { time: false } },
      axes: [
        { stroke: '#5a6878', grid: { stroke: '#2a2d3020' }, ticks: { stroke: '#2a2d30' }, font: '10px monospace' },
        { stroke: '#5a6878', grid: { stroke: '#2a2d3040' }, ticks: { stroke: '#2a2d30' }, font: '10px monospace' },
      ],
      cursor: { show: false },
      legend: { show: false },
    };
  }

  // ── Ancho real del contenedor (deferido al repaint) ───────────────────────
  function panelWidth(id) {
    const el = document.getElementById(id);
    if (!el) return 300;
    const rect = el.getBoundingClientRect();
    const w = rect.width > 0 ? rect.width : el.clientWidth;
    return Math.max(200, Math.floor(w) - 4);
  }

  // ── ResizeObserver: reajusta el plot cuando el panel cambia de ancho ──────
  function attachResize(panelId, chartId, plotKey) {
    if (!window.ResizeObserver) return;
    const panel = document.getElementById(panelId);
    if (!panel) return;
    new ResizeObserver(() => {
      const p = plots[plotKey];
      const el = document.getElementById(chartId);
      if (!p || !el) return;
      const newW = Math.max(200, Math.floor(panel.getBoundingClientRect().width) - 20);
      if (Math.abs(newW - p.width) > 4) p.setSize({ width: newW, height: 140 });
    }).observe(panel);
  }

  // ── Leyenda HTML personalizada ─────────────────────────────────────────────
  function buildLegend(id, items) {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = items.map(({ color, label, dash }) => {
      const swatch = dash
        ? `<svg width="16" height="10" style="vertical-align:middle;margin-right:4px"><line x1="0" y1="5" x2="16" y2="5" stroke="${color}" stroke-width="2" stroke-dasharray="3,2"/></svg>`
        : `<svg width="10" height="10" style="vertical-align:middle;margin-right:4px"><circle cx="5" cy="5" r="4" fill="${color}"/></svg>`;
      return `<span class="chart-legend-item">${swatch}${label}</span>`;
    }).join('');
  }

  // ── Colores ────────────────────────────────────────────────────────────────
  const C = {
    amber:  '#ffa000',
    green:  '#388e3c',
    red:    '#d32f2f',
    blue:   '#1565c0',
    cyan:   '#0097a7',
    purple: '#7b1fa2',
    lime:   '#689f38',
    orange: '#e65100',
  };

  // ── Construcción de gráficas ───────────────────────────────────────────────
  function buildCadencia() {
    const w  = panelWidth('chart-cadencia');
    const el = document.getElementById('chart-cadencia');
    if (!el) return;
    const opts = commonOpts([
      {},
      { scale: 'y', stroke: C.amber, label: 'Disp/min', width: 2, fill: C.amber + '18' },
    ], w);
    opts.scales.y = { range: [0, 700] };
    opts.axes[1].stroke = C.amber;
    buildLegend('legend-cadencia', [
      { color: C.amber, label: 'Cadencia de fuego (disp/min)' },
    ]);
    plots.cadencia = new uPlot(opts, [[], []], el);
    attachResize('cpanel-cadencia', 'chart-cadencia', 'cadencia');
  }

  function buildS3State() {
    const w  = panelWidth('chart-s3state');
    const el = document.getElementById('chart-s3state');
    if (!el) return;
    const opts = commonOpts([
      {},
      { scale: 'y', stroke: C.red, label: 'Disparo', width: 2 },
    ], w);
    opts.scales.y = { range: [-0.15, 1.15] };
    opts.axes[1] = {
      stroke: C.red,
      grid: { stroke: '#2a2d3040' },
      ticks: { stroke: '#2a2d30' },
      font: '10px monospace',
      values: (u, vals) => vals.map(v => {
        if (Math.abs(v) < 0.1)     return 'Reposo';
        if (Math.abs(v - 1) < 0.1) return 'Disparo';
        return '';
      }),
      size: 58,
    };
    buildLegend('legend-s3state', [
      { color: C.red, label: 'Estado S3 — Válvula (0=Reposo / 1=Disparo)' },
    ]);
    plots.s3state = new uPlot(opts, [[], []], el);
    attachResize('cpanel-s3state', 'chart-s3state', 's3state');
  }

  function buildSensors() {
    const w  = panelWidth('chart-sensors');
    const el = document.getElementById('chart-sensors');
    if (!el) return;
    const opts = commonOpts([
      {},
      { stroke: C.green,  label: 'S1', width: 2 },
      { stroke: C.amber,  label: 'S2', width: 2 },
      { stroke: C.red,    label: 'S3', width: 2 },
    ], w);
    opts.scales.y = { range: [-0.3, 1.3] };
    buildLegend('legend-sensors', [
      { color: C.green, label: 'S1 — Bloqueado' },
      { color: C.amber, label: 'S2 — Retenedor' },
      { color: C.red,   label: 'S3 — Válvula' },
    ]);
    plots.sensors = new uPlot(opts, [[], [], [], []], el);
    attachResize('cpanel-sensors', 'chart-sensors', 'sensors');
  }

  function buildIMU() {
    const w  = panelWidth('chart-imu');
    const el = document.getElementById('chart-imu');
    if (!el) return;
    const opts = commonOpts([
      {},
      { stroke: C.amber,  label: 'Roll',  width: 1.5 },
      { stroke: C.cyan,   label: 'Pitch', width: 1.5 },
      { stroke: C.purple, label: 'Yaw',   width: 1.5 },
    ], w);
    buildLegend('legend-imu', [
      { color: C.amber,  label: 'Roll (°)' },
      { color: C.cyan,   label: 'Pitch (°)' },
      { color: C.purple, label: 'Yaw (°)' },
    ]);
    plots.imu = new uPlot(opts, [[], [], [], []], el);
    attachResize('cpanel-imu', 'chart-imu', 'imu');
  }

  function buildEncoders() {
    const w  = panelWidth('chart-enc');
    const el = document.getElementById('chart-enc');
    if (!el) return;
    const opts = commonOpts([
      {},
      { stroke: C.lime,   label: 'ENC_H', width: 1.5 },
      { stroke: C.orange, label: 'ENC_V', width: 1.5 },
    ], w);
    buildLegend('legend-enc', [
      { color: C.lime,   label: 'ENC_H — Horizontal (cnt)' },
      { color: C.orange, label: 'ENC_V — Vertical (cnt)' },
    ]);
    plots.enc = new uPlot(opts, [[], [], []], el);
    attachResize('cpanel-enc', 'chart-enc', 'enc');
  }

  function init() {
    // uPlot debe estar disponible antes de inicializar.
    // Se aplaza un frame extra para que el layout esté completo y
    // getBoundingClientRect() devuelva anchos reales.
    if (typeof uPlot === 'undefined') {
      setTimeout(init, 200);
      return;
    }
    requestAnimationFrame(() => {
      buildCadencia();
      buildS3State();
      buildSensors();
      buildIMU();
      buildEncoders();
      ready = true;
    });
  }

  // ── Función pública: push(d) ───────────────────────────────────────────────
  function push(d) {
    if (!ready) return;

    const tSec = d.ts / 1000.0;

    // ─ Cadencia ─
    // Detectar flanco ascendente de S3
    if (d.s3 && !prevS3) {
      s3Edges.push(tSec);
    }
    prevS3 = d.s3;

    // Eliminar flancos más antiguos que la ventana
    while (s3Edges.length > 0 && tSec - s3Edges[0] > CADEN_WIN) {
      s3Edges.shift();
    }

    // Cadencia instantánea = flancos en la ventana × (60 / ventana efectiva)
    const winEff   = Math.min(tSec, CADEN_WIN);
    const cadencia = winEff > 0 ? (s3Edges.length / winEff) * 60 : 0;

    bTs.push(tSec);
    bCad.push(cadencia);
    bS3Cad.push(d.s3 ? 1 : 0);
    bS1.push(d.s1 ? 1 : 0);
    bS2.push(d.s2 ? 1 : 0);
    bS3.push(d.s3 ? 1 : 0);
    bRoll.push(d.roll);
    bPitch.push(d.pitch);
    bYaw.push(d.yaw_signed);
    bEncH.push(d.enc_h);
    bEncV.push(d.enc_v);

    // Actualizar gráficas — cada una recorta su propia ventana según el selector
    const tsArr = bTs.toArray();

    // Devuelve el número de muestras visible según el <select> del panel dado
    function winSamples(selId) {
      const el = document.getElementById(selId);
      const secs = el ? parseInt(el.value, 10) : 60;
      return Math.round(secs * 50);   // 50 Hz
    }

    function sliceLast(arr, n) { return arr.length <= n ? arr : arr.slice(arr.length - n); }

    if (plots.cadencia) {
      const n   = winSamples('win-cadencia');
      const ts  = sliceLast(tsArr, n);
      const cad = sliceLast(bCad.toArray(), n);
      plots.cadencia.setData([ts, cad]);
      const livEl = document.getElementById('cad-live');
      if (livEl && cad.length) livEl.textContent = Math.round(cad[cad.length - 1]) + ' disp/min';
    }
    if (plots.s3state) {
      const n   = winSamples('win-s3state');
      const ts  = sliceLast(tsArr, n);
      const s3c = sliceLast(bS3Cad.toArray(), n);
      plots.s3state.setData([ts, s3c]);
    }
    if (plots.sensors) {
      const n = winSamples('win-sensors');
      plots.sensors.setData([sliceLast(tsArr, n), sliceLast(bS1.toArray(), n), sliceLast(bS2.toArray(), n), sliceLast(bS3.toArray(), n)]);
    }
    if (plots.imu) {
      const n = winSamples('win-imu');
      plots.imu.setData([sliceLast(tsArr, n), sliceLast(bRoll.toArray(), n), sliceLast(bPitch.toArray(), n), sliceLast(bYaw.toArray(), n)]);
    }
    if (plots.enc) {
      const n = winSamples('win-enc');
      plots.enc.setData([sliceLast(tsArr, n), sliceLast(bEncH.toArray(), n), sliceLast(bEncV.toArray(), n)]);
    }
  }

  // Inicializar cuando el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { push };

})();
