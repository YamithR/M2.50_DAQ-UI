/**
 * charts.js — Cinco gráficas en tiempo real con Plotly.js.
 *
 * Estrategia de rendimiento:
 *   · Los datos se acumulan en buffers locales a 50 Hz.
 *   · Plotly se actualiza cada UPDATE_EVERY frames (~10 Hz) usando
 *     extendTraces() con maxpoints para ventana deslizante automática.
 *   · El usuario puede cambiar la ventana de tiempo con los <select>.
 *
 * Gráficas:
 *   chart-cadencia  — Cadencia de fuego (disp/min)
 *   chart-s3state   — Estado digital S3 (0/1)
 *   chart-sensors   — S1, S2, S3 digitales
 *   chart-imu       — Roll, Pitch, Yaw (°)
 *   chart-enc       — ENC_H, ENC_V (cuentas)
 */

window.charts = (function () {
  'use strict';

  // ── Configuración ──────────────────────────────────────────────────────────
  const UPDATE_EVERY = 5;   // acumular N muestras antes de enviar a Plotly (~10 Hz)
  const HZ = 50;

  const C = {
    amber:  '#ffa000',
    green:  '#388e3c',
    red:    '#d32f2f',
    cyan:   '#0097a7',
    purple: '#7b1fa2',
    lime:   '#689f38',
    orange: '#e65100',
    bg:     '#0d0f10',
    grid:   'rgba(90,104,120,0.18)',
    tick:   '#5a6878',
  };

  // ── Estado ─────────────────────────────────────────────────────────────────
  let ready      = false;
  let frameCount = 0;
  let prevS3     = false;
  const s3Edges  = [];
  const CADEN_WIN = 60.0;

  // Buffer acumulador (se vierte a Plotly cada UPDATE_EVERY frames)
  let buf = _emptyBuf();

  function _emptyBuf() {
    return { t: [], cad: [], s3d: [], s1: [], s2: [], s3: [],
             roll: [], pitch: [], yaw: [], enc_h: [], enc_v: [] };
  }

  // ── Configuración base de Plotly ───────────────────────────────────────────
  const BASE_LAYOUT = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor:  C.bg,
    margin:   { l: 52, r: 8, t: 6, b: 26 },
    font:     { family: 'Courier New,monospace', size: 9, color: C.tick },
    xaxis:    { gridcolor: C.grid, tickfont: { size: 9 }, zeroline: false },
    yaxis:    { gridcolor: C.grid, tickfont: { size: 9 }, zeroline: false },
    legend:   { orientation: 'h', x: 0, y: 1.12, font: { size: 9 },
                bgcolor: 'rgba(0,0,0,0)', borderwidth: 0 },
    showlegend: false,
    hovermode: false,
  };

  const PLOT_CONFIG = { displayModeBar: false, responsive: true };

  function mkLayout(overrides, h) {
    return Object.assign({}, BASE_LAYOUT, { height: h || 130 }, overrides);
  }

  function mkTrace(color, name, extra) {
    return Object.assign({
      type: 'scatter', mode: 'lines', name,
      line: { color, width: 1.5 },
      x: [], y: [],
    }, extra || {});
  }

  // ── Selector de ventana (segundos → muestras) ──────────────────────────────
  function winSamples(selId) {
    const el = document.getElementById(selId);
    return ((el ? parseInt(el.value, 10) : 60)) * HZ;
  }

  // ── Construcción inicial de gráficas ───────────────────────────────────────
  function buildCadencia() {
    const el = document.getElementById('chart-cadencia');
    if (!el) return;
    Plotly.newPlot(el, [
      mkTrace(C.amber, 'Cadencia (disp/min)'),
    ], mkLayout({
      height: 150,
      yaxis: { ...BASE_LAYOUT.yaxis, range: [0, 700],
               title: { text: 'disp/min', font: { size: 9, color: C.amber } } },
    }), PLOT_CONFIG);
  }

  function buildS3State() {
    const el = document.getElementById('chart-s3state');
    if (!el) return;
    Plotly.newPlot(el, [
      mkTrace(C.red, 'S3 Válvula', { fill: 'tozeroy', fillcolor: C.red + '28' }),
    ], mkLayout({
      yaxis: { ...BASE_LAYOUT.yaxis, range: [-0.1, 1.2],
               tickvals: [0, 1], ticktext: ['Reposo', 'Disparo'],
               tickfont: { size: 8 } },
    }), PLOT_CONFIG);
  }

  function buildSensors() {
    const el = document.getElementById('chart-sensors');
    if (!el) return;
    Plotly.newPlot(el, [
      mkTrace(C.green,  'S1 Bloqueado'),
      mkTrace(C.amber,  'S2 Retenedor'),
      mkTrace(C.red,    'S3 Válvula'),
    ], mkLayout({
      showlegend: true,
      yaxis: { ...BASE_LAYOUT.yaxis, range: [-0.3, 1.3] },
    }), PLOT_CONFIG);
  }

  function buildIMU() {
    const el = document.getElementById('chart-imu');
    if (!el) return;
    Plotly.newPlot(el, [
      mkTrace(C.amber,  'Roll (°)'),
      mkTrace(C.cyan,   'Pitch (°)'),
      mkTrace(C.purple, 'Yaw (°)'),
    ], mkLayout({
      showlegend: true,
    }), PLOT_CONFIG);
  }

  function buildEncoders() {
    const el = document.getElementById('chart-enc');
    if (!el) return;
    Plotly.newPlot(el, [
      mkTrace(C.lime,   'ENC_H'),
      mkTrace(C.orange, 'ENC_V'),
    ], mkLayout({
      showlegend: true,
    }), PLOT_CONFIG);
  }

  // ── Volcado a Plotly ────────────────────────────────────────────────────────
  function flushToPlotly() {
    if (!buf.t.length) return;

    const maxCad = winSamples('win-cadencia');
    const maxS3  = winSamples('win-s3state');
    const maxSen = winSamples('win-sensors');
    const maxImu = winSamples('win-imu');
    const maxEnc = winSamples('win-enc');

    const t = buf.t;

    try { Plotly.extendTraces('chart-cadencia',
      { x: [t],         y: [buf.cad] }, [0], maxCad); } catch (_) {}
    try { Plotly.extendTraces('chart-s3state',
      { x: [t],         y: [buf.s3d] }, [0], maxS3);  } catch (_) {}
    try { Plotly.extendTraces('chart-sensors',
      { x: [t, t, t],   y: [buf.s1, buf.s2, buf.s3] }, [0, 1, 2], maxSen); } catch (_) {}
    try { Plotly.extendTraces('chart-imu',
      { x: [t, t, t],   y: [buf.roll, buf.pitch, buf.yaw] }, [0, 1, 2], maxImu); } catch (_) {}
    try { Plotly.extendTraces('chart-enc',
      { x: [t, t],      y: [buf.enc_h, buf.enc_v] }, [0, 1], maxEnc); } catch (_) {}

    buf = _emptyBuf();
  }

  // ── Inicialización diferida ────────────────────────────────────────────────
  function init() {
    if (typeof Plotly === 'undefined') {
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

  // ── API pública: push(d) ───────────────────────────────────────────────────
  function push(d) {
    if (!ready) return;

    const t = d.ts;   // ts ya viene en segundos desde firmware

    // Cadencia de fuego
    if (d.s3 && !prevS3) s3Edges.push(t);
    prevS3 = d.s3;
    while (s3Edges.length > 0 && t - s3Edges[0] > CADEN_WIN) s3Edges.shift();
    const winEff   = Math.min(t, CADEN_WIN);
    const cadencia = winEff > 0 ? (s3Edges.length / winEff) * 60 : 0;

    // Acumular en buffer
    buf.t.push(t);
    buf.cad.push(cadencia);
    buf.s3d.push(d.s3 ? 1 : 0);
    buf.s1.push(d.s1 ? 1 : 0);
    buf.s2.push(d.s2 ? 1 : 0);
    buf.s3.push(d.s3 ? 1 : 0);
    buf.roll.push(d.roll);
    buf.pitch.push(d.pitch);
    buf.yaw.push(d.yaw_signed);
    buf.enc_h.push(d.enc_h);
    buf.enc_v.push(d.enc_v);

    // Actualizar display de cadencia en tiempo real
    const livEl = document.getElementById('cad-live');
    if (livEl) livEl.textContent = Math.round(cadencia) + ' disp/min';

    // Volcar a Plotly cada UPDATE_EVERY frames
    frameCount++;
    if (frameCount >= UPDATE_EVERY) {
      frameCount = 0;
      flushToPlotly();
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
