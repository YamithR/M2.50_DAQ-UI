/**
 * encoders.js — Contadores ENC_H / ENC_V + brújula SVG y elevación SVG.
 *
 * ── CONFIGURACIÓN DE ESCALA ─────────────────────────────────────────────────
 * Edita únicamente los 8 valores marcados como CONFIGURABLE para adaptar
 * el instrumento al rango físico real del sistema:
 *
 *   ENC_H_CNT_MIN / MAX → cuentas mínima / máxima del encoder horizontal
 *   ENC_H_ANG_MIN / MAX → azimut [°] correspondiente (0° = apunta al norte)
 *   ENC_V_CNT_MIN / MAX → cuentas mínima / máxima del encoder vertical
 *   ENC_V_ANG_MIN / MAX → elevación [°] (+ = elevado, - = deprimido)
 */

window.encoders = (function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // CONFIGURABLE — encoder horizontal  →  azimut [°]
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  let ENC_H_CNT_MIN = -1000;  // sobrescrito desde /api/config al cargar
  let ENC_H_CNT_MAX =  1000;
  let ENC_H_ANG_MIN = -180;
  let ENC_H_ANG_MAX =  180;

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // CONFIGURABLE — encoder vertical  →  elevación [°]
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  let ENC_V_CNT_MIN = -500;
  let ENC_V_CNT_MAX =  500;
  let ENC_V_ANG_MIN = -45;
  let ENC_V_ANG_MAX =  45;

  // ── Referencias DOM ────────────────────────────────────────────────────────
  let elH = null, elV = null;
  let needleH   = null;   // <g> que rota en la brújula
  let needleV   = null;   // <g> que rota en el indicador de elevación
  let degTextH  = null;
  let degTextV  = null;
  let _initialized = false;

  // ── Helpers SVG ────────────────────────────────────────────────────────────
  function mk(tag, attrs) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    return e;
  }
  function mkSVG(w, h) {
    return mk('svg', {
      width: w, height: h, viewBox: `0 0 ${w} ${h}`,
      style: 'display:block;background:#0d0f10;border-radius:4px;border:1px solid #3a3f45',
    });
  }

  // Mapeo lineal con saturación: cuentas → grados
  function mapCnt(cnt, cntMin, cntMax, angMin, angMax) {
    const t = Math.max(0, Math.min(1, (cnt - cntMin) / (cntMax - cntMin)));
    return angMin + t * (angMax - angMin);
  }

  // ── Brújula ENC_H (158×168) ───────────────────────────────────────────────
  // Aguja = silueta M2 .50 vista desde arriba; barril apunta al NORTE (−Y).
  // rotate(ang) = giro horario → este = positivo, coherente con azimut.
  function buildCompassH(container) {
    const W = 158, H = 168, cx = 79, cy = 78, R = 70;
    const svg = mkSVG(W, H);

    // Fondo del disco
    svg.appendChild(mk('circle', { cx, cy, r: R, fill: '#0a0c12' }));

    // Marcas angulares (10°; mayores en 30°)
    for (let d = 0; d < 360; d += 10) {
      const big = d % 30 === 0;
      const rad = (d - 90) * Math.PI / 180;   // -90°: norste SVG = norte
      const ro = R, ri = big ? R - 9 : R - 5;
      svg.appendChild(mk('line', {
        x1: (cx + ro * Math.cos(rad)).toFixed(1), y1: (cy + ro * Math.sin(rad)).toFixed(1),
        x2: (cx + ri * Math.cos(rad)).toFixed(1), y2: (cy + ri * Math.sin(rad)).toFixed(1),
        stroke: big ? '#6a7060' : '#303838', 'stroke-width': big ? 1.5 : 1,
      }));
    }

    // Etiquetas cardinales y semicardinales
    const CARD = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SO: 225, O: 270, NO: 315 };
    for (const [lbl, deg] of Object.entries(CARD)) {
      const major = lbl.length === 1;
      const rad   = (deg - 90) * Math.PI / 180;
      const rr    = R - (major ? 16 : 20);
      const t = mk('text', {
        x: (cx + rr * Math.cos(rad)).toFixed(1),
        y: (cy + rr * Math.sin(rad) + 4).toFixed(1),
        'text-anchor': 'middle',
        fill: lbl === 'N' ? '#ff4444' : major ? '#ffa000' : '#556070',
        'font-size': major ? 11 : 8,
        'font-family': 'monospace',
        'font-weight': major ? 'bold' : 'normal',
      });
      t.textContent = lbl;
      svg.appendChild(t);
    }

    // Borde y cruz de referencia
    svg.appendChild(mk('circle', { cx, cy, r: R, fill: 'none', stroke: '#4b5320', 'stroke-width': 1.5 }));
    svg.appendChild(mk('line', { x1: cx - R + 4, y1: cy, x2: cx + R - 4, y2: cy, stroke: '#1e2430', 'stroke-width': 1 }));
    svg.appendChild(mk('line', { x1: cx, y1: cy - R + 4, x2: cx, y2: cy + R - 4, stroke: '#1e2430', 'stroke-width': 1 }));

    // ── Aguja: silueta M2 .50 vista DESDE ARRIBA ────────────────────────────
    // Dibujada con (0,0) en el pivote; barril apuntando hacia −Y (norte).
    // transform="translate(cx,cy) rotate(0)":
    //   1. rotate(ang) gira alrededor de (0,0) local  →  barril rota
    //   2. translate(cx,cy) mueve al centro del disco  ✓
    const needle = mk('g', { transform: `translate(${cx},${cy}) rotate(0)` });

    // Freno de boca (triángulo en la punta del cañón)
    needle.appendChild(mk('polygon', { points: '-3.5,-68 0,-77 3.5,-68', fill: '#ffdd00' }));
    // Compensador (rectángulo en el extremo del cañón)
    needle.appendChild(mk('rect',    { x: -3, y: -70, width: 6, height: 5, rx: 1, fill: '#ccaa00' }));
    // Cañón (largo y fino)
    needle.appendChild(mk('rect',    { x: -2, y: -65, width: 4, height: 46, rx: 1, fill: '#ffa000' }));
    // Jacket / cubierta del barril (sección central más ancha)
    needle.appendChild(mk('rect',    { x: -4.5, y: -34, width: 9, height: 22, rx: 1, fill: '#cc7700' }));
    // Receptor / cuerpo del arma
    needle.appendChild(mk('rect',    { x: -6.5, y: -12, width: 13, height: 15, rx: 2, fill: '#aa5500' }));
    // Palanca de armado (nub lateral derecho)
    needle.appendChild(mk('rect',    { x: 6.5, y: -10, width: 8, height: 4, rx: 1, fill: '#886622' }));
    // Backplate / área de empuñadura (espadines)
    needle.appendChild(mk('rect',    { x: -5, y: 3, width: 10, height: 15, rx: 2, fill: '#774400' }));
    // Centro / pivote
    needle.appendChild(mk('circle',  { cx: 0, cy: 0, r: 3, fill: '#ffffffbb' }));

    svg.appendChild(needle);
    needleH = needle;

    // Texto de ángulo bajo el disco
    const dt = mk('text', {
      x: cx, y: H - 4,
      'text-anchor': 'middle', fill: '#ffa000',
      'font-size': 10, 'font-family': 'monospace',
    });
    dt.textContent = '0.0°';
    svg.appendChild(dt);
    degTextH = dt;

    container.appendChild(svg);
  }

  // ── Indicador de elevación ENC_V (180×138) ────────────────────────────────
  // Aguja = silueta M2 .50 en perfil (vista lateral); barril apunta a la DERECHA.
  // rotate(−ang): elevación positiva → rotación CCW en SVG (barril sube).
  function buildElevV(container) {
    const W = 180, H = 138;
    const px = 54, py = 82;          // pivote en coords SVG
    const R  = 58;                   // radio del arco de referencia
    const AMIN = ENC_V_ANG_MIN, AMAX = ENC_V_ANG_MAX;
    const svg = mkSVG(W, H);

    // Funciones de posición en el arco.
    // Convenio: 0°=derecha, +°=arriba (−sin en SVG porque Y↓).
    const ax = a => px + R * Math.cos(a * Math.PI / 180);
    const ay = a => py - R * Math.sin(a * Math.PI / 180);

    // Sector de fondo (relleno)
    let dSec = `M ${px},${py} L ${ax(AMIN).toFixed(1)},${ay(AMIN).toFixed(1)}`;
    for (let i = 1; i <= 48; i++) {
      const a = AMIN + (AMAX - AMIN) * i / 48;
      dSec += ` L ${ax(a).toFixed(1)},${ay(a).toFixed(1)}`;
    }
    dSec += ' Z';
    svg.appendChild(mk('path', { d: dSec, fill: '#0a1a30' }));

    // Borde del arco
    let dArc = `M ${ax(AMIN).toFixed(1)},${ay(AMIN).toFixed(1)}`;
    for (let i = 1; i <= 48; i++) {
      const a = AMIN + (AMAX - AMIN) * i / 48;
      dArc += ` L ${ax(a).toFixed(1)},${ay(a).toFixed(1)}`;
    }
    svg.appendChild(mk('path', { d: dArc, fill: 'none', stroke: '#4b5320', 'stroke-width': 1.5 }));

    // Marcas de escala
    for (let a = Math.ceil(AMIN / 5) * 5; a <= Math.floor(AMAX / 5) * 5; a += 5) {
      const big = a % 15 === 0;
      const ro = R, ri = big ? R - 10 : R - 5;
      const rad = a * Math.PI / 180;
      svg.appendChild(mk('line', {
        x1: (px + ro * Math.cos(rad)).toFixed(1), y1: (py - ro * Math.sin(rad)).toFixed(1),
        x2: (px + ri * Math.cos(rad)).toFixed(1), y2: (py - ri * Math.sin(rad)).toFixed(1),
        stroke: big ? '#6a7060' : '#303838', 'stroke-width': big ? 1.5 : 1,
      }));
      if (big) {
        const rr = ri - 9;
        const t = mk('text', {
          x: (px + rr * Math.cos(rad)).toFixed(1),
          y: (py - rr * Math.sin(rad) + 4).toFixed(1),
          'text-anchor': 'middle',
          fill: a === 0 ? '#ffa000' : '#556070',
          'font-size': 8, 'font-family': 'monospace',
        });
        t.textContent = (a > 0 ? '+' : '') + a + '°';
        svg.appendChild(t);
      }
    }

    // Línea datum horizontal (0°, fija)
    svg.appendChild(mk('line', {
      x1: px, y1: py, x2: px + R + 10, y2: py,
      stroke: '#ffa00028', 'stroke-width': 1.5,
    }));

    // ── Aguja: silueta M2 .50 en perfil lateral ───────────────────────────
    // Dibujada con (0,0) en el pivote (receptor); barril apuntando a +X.
    // transform="translate(px,py) rotate(0)":
    //   1. rotate(−ang) gira alrededor de (0,0) local  →  barril sube/baja
    //   2. translate(px,py) mueve al pivote en el SVG  ✓
    const needle = mk('g', { transform: `translate(${px},${py}) rotate(0)` });

    // Cañón (largo, hacia la derecha)
    needle.appendChild(mk('rect',    { x: 0, y: -3, width: 82, height: 6, rx: 1, fill: '#ffa000' }));
    // Freno / compensador de boca
    needle.appendChild(mk('rect',    { x: 82, y: -8, width: 5, height: 16, rx: 1, fill: '#ffdd00' }));
    // Jacket / cubierta del barril (sección intermedia, algo más gruesa)
    needle.appendChild(mk('rect',    { x: 18, y: -5.5, width: 44, height: 11, rx: 2, fill: '#cc7700' }));
    // Receptor / cuerpo
    needle.appendChild(mk('rect',    { x: -18, y: -10, width: 20, height: 22, rx: 2, fill: '#aa5500' }));
    // Empuñadura (grip, hacia abajo)
    needle.appendChild(mk('rect',    { x: -14, y: 11, width: 8, height: 22, rx: 2, fill: '#774400' }));
    // Bípode — pata delantera
    needle.appendChild(mk('line',    { x1: 28, y1: 5, x2: 20, y2: 22, stroke: '#606040', 'stroke-width': 2 }));
    // Bípode — pata trasera
    needle.appendChild(mk('line',    { x1: 38, y1: 5, x2: 46, y2: 22, stroke: '#606040', 'stroke-width': 2 }));
    // Centro / pivote
    needle.appendChild(mk('circle',  { cx: 0, cy: 0, r: 3, fill: '#ffffffbb' }));

    svg.appendChild(needle);
    needleV = needle;

    // Texto de ángulo (derecha del SVG)
    const dt = mk('text', {
      x: W - 6, y: py + 4,
      'text-anchor': 'end', fill: '#ffa000',
      'font-size': 10, 'font-family': 'monospace',
    });
    dt.textContent = '0.0°';
    svg.appendChild(dt);
    degTextV = dt;

    container.appendChild(svg);
  }

  // ── Inicialización ─────────────────────────────────────────────────────────
  function init() {
    if (_initialized) return;
    _initialized = true;
    elH = document.getElementById('enc-h');
    elV = document.getElementById('enc-v');
    const cH = document.getElementById('compass-h');
    const cV = document.getElementById('compass-v');
    if (cH) buildCompassH(cH);
    if (cV) buildElevV(cV);
  }

  // ── Update (llamado a 50 Hz desde ws_client.js) ───────────────────────────
  function update(d) {
    if (!_initialized) init();

    // Contadores numéricos
    if (elH) elH.textContent = _fmt(d.enc_h);
    if (elV) elV.textContent = _fmt(d.enc_v);
    const tH = document.getElementById('tbl-enc-h');
    const tV = document.getElementById('tbl-enc-v');
    if (tH) tH.textContent = _fmt(d.enc_h);
    if (tV) tV.textContent = _fmt(d.enc_v);

    // Brújula ENC_H
    if (needleH) {
      const ang = mapCnt(d.enc_h, ENC_H_CNT_MIN, ENC_H_CNT_MAX, ENC_H_ANG_MIN, ENC_H_ANG_MAX);
      needleH.setAttribute('transform', `translate(79,78) rotate(${ang.toFixed(2)})`);
      if (degTextH) degTextH.textContent = ang.toFixed(1) + '°';
    }

    // Indicador elevación ENC_V
    if (needleV) {
      const ang = mapCnt(d.enc_v, ENC_V_CNT_MIN, ENC_V_CNT_MAX, ENC_V_ANG_MIN, ENC_V_ANG_MAX);
      // −ang porque elevación positiva = CCW en SVG (barril sube)
      needleV.setAttribute('transform', `translate(54,82) rotate(${(-ang).toFixed(2)})`);
      if (degTextV) degTextV.textContent = ang.toFixed(1) + '°';
    }
  }

  function _fmt(n) {
    if (n > 0) return '+' + n;
    if (n < 0) return String(n);
    return '0';
  }

  return { update };

})();
