/**
 * gauges.js — Instrumentos IMU SVG puros (sin dependencias externas).
 *
 * Correcciones arquitectónicas:
 *   ROLL  — El clip-path está en el wrapper EXTERNO (fijo). El grupo interno
 *            rota con rotate(ángulo, cx, cy) — forma de 3 argumentos que
 *            especifica el punto de pivote directamente. Sin mezcla
 *            translate+rotate en el mismo elemento que tiene clip-path.
 *   PITCH — Se actualiza el atributo `y` de un <rect> directamente.
 *            Sin grupos con clip-path, sin transforms ambiguos.
 *   YAW   — Translación simple, funciona correctamente.
 *
 * Escala visual 1:1 con los datos (sin ganancia artificial):
 *   Roll  — el horizonte rota exactamente d.roll grados (como un ADI real)
 *   Pitch — la barra usa la escala natural de la pista: 80 px / 30° ≈ 2.667 px/°
 *   Yaw   — marcador mapeado a la pista completa ±180°
 */

window.gauges = (function () {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';

  // ── Escala pitch: la pista cubre ±30° en 80 px → 80/30 px/° ────────────────
  const PITCH_PX_PER_DEG = 80 / 30;   // ≈ 2.667 px/° — consistente con las marcas dibujadas

  // ── Utilidades ─────────────────────────────────────────────────────────────
  function svgEl(tag, attrs) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  function mkSVG(w, h) {
    return svgEl('svg', {
      width: w, height: h,
      viewBox: `0 0 ${w} ${h}`,
      style: 'display:block;background:#0d0f10;border-radius:4px;border:1px solid #3a3f45',
    });
  }

  // ── Referencias a elementos animados ──────────────────────────────────────
  let rollHorizon = null;   // <g> que rota — DENTRO del wrapper con clip-path
  let pitchBarEl  = null;   // <rect> cuyo atributo `y` se actualiza directamente
  let yawMarker   = null;   // <g> que se translada horizontalmente
  let _initialized = false;

  // ── Roll Indicator (220×110) ───────────────────────────────────────────────
  function buildRoll(container) {
    const svg = mkSVG(220, 110);
    const cx = 110, cy = 55, r = 48;

    // ── Definición del clip circular ──────────────────────────────────────
    const defs = svgEl('defs', {});
    const clip = svgEl('clipPath', { id: 'roll-clip' });
    clip.appendChild(svgEl('circle', { cx, cy, r }));
    defs.appendChild(clip);
    svg.appendChild(defs);

    // ── Fondo oscuro del círculo ──────────────────────────────────────────
    svg.appendChild(svgEl('circle', { cx, cy, r, fill: '#0a0c12' }));

    // ── Wrapper con clip (FIJO — no rota nunca) ───────────────────────────
    //    El clip-path solo está en este wrapper, NO en el grupo que anima.
    const clipWrapper = svgEl('g', { 'clip-path': 'url(#roll-clip)' });

    // ── Grupo que rota (INTERIOR — sin clip-path) ─────────────────────────
    //    Usa rotate(angle, cx, cy): forma de 3 args SVG que especifica el
    //    punto de pivote en coordenadas del PADRE → no hay ambigüedad.
    const horizon = svgEl('g', {});

    // Cielo (mitad superior centrada en (cx,cy) en coords SVG absolutas)
    horizon.appendChild(svgEl('rect', {
      x: cx - r - 5, y: cy - r - 5,
      width: (r + 5) * 2, height: r + 5,
      fill: '#1a3a6e',
    }));
    // Tierra (mitad inferior)
    horizon.appendChild(svgEl('rect', {
      x: cx - r - 5, y: cy,
      width: (r + 5) * 2, height: r + 5,
      fill: '#5d3a1a',
    }));
    // Línea de horizonte
    horizon.appendChild(svgEl('line', {
      x1: cx - r - 5, y1: cy, x2: cx + r + 5, y2: cy,
      stroke: '#ffffff', 'stroke-width': 2,
    }));
    // Marcas de pitch en el horizonte (±12 px, ±24 px)
    for (const off of [-24, -12, 12, 24]) {
      const hw = Math.abs(off) > 15 ? 12 : 18;
      horizon.appendChild(svgEl('line', {
        x1: cx - hw, y1: cy + off, x2: cx + hw, y2: cy + off,
        stroke: '#ffffff88', 'stroke-width': 1,
      }));
    }

    clipWrapper.appendChild(horizon);
    svg.appendChild(clipWrapper);
    rollHorizon = horizon;   // ← cacheamos el INTERIOR

    // ── Borde del círculo (fijo, encima del contenido rotado) ─────────────
    svg.appendChild(svgEl('circle', {
      cx, cy, r, fill: 'none', stroke: '#4b5320', 'stroke-width': 2,
    }));

    // ── Marcas de grados en el borde ──────────────────────────────────────
    for (const deg of [-60, -45, -30, -15, 0, 15, 30, 45, 60]) {
      const rad = (deg - 90) * Math.PI / 180;
      const len = deg % 30 === 0 ? 7 : 4;
      svg.appendChild(svgEl('line', {
        x1: cx + (r - len) * Math.cos(rad), y1: cy + (r - len) * Math.sin(rad),
        x2: cx + r * Math.cos(rad),         y2: cy + r * Math.sin(rad),
        stroke: '#8a9060', 'stroke-width': deg % 30 === 0 ? 1.5 : 1,
      }));
    }

    // ── Triángulo puntero en 0° (cima, fijo) ──────────────────────────────
    svg.appendChild(svgEl('polygon', {
      points: `${cx},${cy - r + 1} ${cx - 5},${cy - r + 10} ${cx + 5},${cy - r + 10}`,
      fill: '#ffa000',
    }));

    // ── Símbolo de avión (fijo, centrado en (cx,cy)) ──────────────────────
    svg.appendChild(svgEl('rect', { x: cx-2,  y: cy-12, width: 4,  height: 16, rx: 2, fill: '#ffa000' }));
    svg.appendChild(svgEl('rect', { x: cx-18, y: cy-3,  width: 36, height: 5,  rx: 2, fill: '#ffa000' }));
    svg.appendChild(svgEl('rect', { x: cx-7,  y: cy+2,  width: 14, height: 3,  rx: 1, fill: '#ffa000' }));

    container.appendChild(svg);
  }

  // ── Pitch Indicator (120×190) ──────────────────────────────────────────────
  function buildPitch(container) {
    const svg = mkSVG(120, 190);
    const cx = 60;
    const TOP = 15, BOT = 175;
    const MID = (TOP + BOT) / 2;   // 95
    const HALF = (BOT - TOP) / 2;  // 80

    // Fondo del track
    svg.appendChild(svgEl('rect', {
      x: 20, y: TOP, width: 80, height: BOT - TOP,
      rx: 3, fill: '#0a1a30', stroke: '#3a4050', 'stroke-width': 1,
    }));

    // Marcas de escala (estáticas)
    for (let deg = -30; deg <= 30; deg += 5) {
      const y = MID - (deg / 30) * HALF;
      const hw = deg % 10 === 0 ? 18 : 10;
      svg.appendChild(svgEl('line', {
        x1: cx - hw, y1: y, x2: cx + hw, y2: y,
        stroke: deg === 0 ? '#ffa00030' : '#3a4060',
        'stroke-width': deg % 10 === 0 ? 1.5 : 1,
      }));
      if (deg % 10 === 0 && deg !== 0) {
        const t = svgEl('text', {
          x: cx + 22, y: y + 4,
          fill: '#5a6878', 'font-size': 8, 'font-family': 'monospace',
        });
        t.textContent = (deg > 0 ? '+' : '') + deg;
        svg.appendChild(t);
      }
    }

    // ── Barra animada de pitch ────────────────────────────────────────────
    //    Es un <rect> simple — se actualiza su atributo `y` directamente.
    //    Sin transforms, sin clip-path sobre el elemento animado.
    const barBg = svgEl('rect', {
      x: 22, y: MID - 7,
      width: 76, height: 14, rx: 3,
      fill: '#ffa000', opacity: '0.25',
    });
    svg.appendChild(barBg);
    pitchBarEl = barBg;   // ← actualizamos este rect directamente

    const barLine = svgEl('rect', {
      x: 22, y: MID - 1,
      width: 76, height: 2,
      fill: '#ffa000', opacity: '0.9',
    });
    svg.appendChild(barLine);
    // También acumulamos la línea en el mismo closure para actualizar junto:
    pitchBarEl._line = barLine;

    // Cruz de referencia central (fija)
    svg.appendChild(svgEl('line', { x1: cx-14, y1: MID, x2: cx+14, y2: MID, stroke: '#ffa000', 'stroke-width': 2 }));
    svg.appendChild(svgEl('line', { x1: cx, y1: MID-7, x2: cx, y2: MID+7, stroke: '#ffa000', 'stroke-width': 2 }));

    // Borde del track
    svg.appendChild(svgEl('rect', {
      x: 20, y: TOP, width: 80, height: BOT - TOP,
      rx: 3, fill: 'none', stroke: '#4b5320', 'stroke-width': 1.5,
    }));

    container.appendChild(svg);
  }

  // ── Yaw Slider (220×60) ────────────────────────────────────────────────────
  function buildYaw(container) {
    const svg = mkSVG(220, 60);
    const cy = 30;
    const trackX = 15, trackW = 190;

    svg.appendChild(svgEl('rect', {
      x: trackX, y: cy - 6, width: trackW, height: 12,
      rx: 3, fill: '#0a1a30', stroke: '#3a4050', 'stroke-width': 1,
    }));

    for (const [deg, label] of [[-180,'-180'],[-90,'-90'],[0,'N'],[90,'+90'],[180,'+180']]) {
      const x = trackX + (deg + 180) / 360 * trackW;
      svg.appendChild(svgEl('line', { x1: x, y1: cy-8, x2: x, y2: cy+8, stroke: '#4a5568', 'stroke-width': 1 }));
      const t = svgEl('text', {
        x, y: cy + 20, 'text-anchor': 'middle',
        fill: deg === 0 ? '#ffa000' : '#5a6878', 'font-size': 8, 'font-family': 'monospace',
      });
      t.textContent = label;
      svg.appendChild(t);
    }

    const xN = trackX + trackW / 2;
    svg.appendChild(svgEl('line', { x1: xN, y1: cy-10, x2: xN, y2: cy+10, stroke: '#ffa000', 'stroke-width': 1.5, opacity: '0.3' }));

    const marker = svgEl('g', { transform: `translate(${xN},${cy})` });
    marker.appendChild(svgEl('polygon', { points: '0,-9 5,3 -5,3', fill: '#ffa000' }));
    marker.appendChild(svgEl('polygon', { points: '0,9 5,-3 -5,-3', fill: '#ffa00040' }));
    svg.appendChild(marker);
    yawMarker = marker;

    svg.appendChild(svgEl('rect', {
      x: trackX, y: cy - 6, width: trackW, height: 12,
      rx: 3, fill: 'none', stroke: '#4b5320', 'stroke-width': 1.5,
    }));

    container.appendChild(svg);
  }

  // ── Inicialización ─────────────────────────────────────────────────────────
  function init() {
    if (_initialized) return;
    _initialized = true;
    const cRoll  = document.getElementById('gauge-roll');
    const cPitch = document.getElementById('gauge-pitch');
    const cYaw   = document.getElementById('gauge-yaw');
    if (cRoll)  buildRoll(cRoll);
    if (cPitch) buildPitch(cPitch);
    if (cYaw)   buildYaw(cYaw);
  }

  // ── Función pública: update(d) ─────────────────────────────────────────────
  function update(d) {
    if (!_initialized) init();

    // ── Roll ──────────────────────────────────────────────────────────────
    // rotate(angle, cx, cy) : SVG 3-arg rotate — pivota en las coords del padre.
    // No hay translación en el mismo elemento → sin ambigüedad de sistema de coords.
    if (rollHorizon) {
      const angle = -(d.roll);   // 1:1 — el horizonte rota el ángulo real
      rollHorizon.setAttribute('transform', `rotate(${angle.toFixed(2)}, 110, 55)`);
    }

    // ── Pitch ─────────────────────────────────────────────────────────────
    // Actualizamos `y` del <rect> directamente: fiable, sin transforms.
    if (pitchBarEl) {
      const TOP = 15, BOT = 175, MID = 95;
      // La pista dibujada cubre ±30° en 80 px → misma escala que las marcas
      const delta = -(d.pitch * PITCH_PX_PER_DEG);     // positivo = arriba
      const newY  = Math.max(TOP, Math.min(BOT - 14, MID + delta - 7));
      pitchBarEl.setAttribute('y', newY.toFixed(1));
      if (pitchBarEl._line) {
        pitchBarEl._line.setAttribute('y', (newY + 6).toFixed(1));
      }
    }

    // ── Yaw ───────────────────────────────────────────────────────────────
    if (yawMarker) {
      const trackX = 15, trackW = 190;
      const x = trackX + ((d.yaw_signed + 180) / 360) * trackW;
      yawMarker.setAttribute('transform', `translate(${x.toFixed(1)}, 30)`);
    }

    // ── Valores numéricos ─────────────────────────────────────────────────
    const setVal = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setVal('imu-roll-val',  d.roll.toFixed(1));
    setVal('imu-pitch-val', d.pitch.toFixed(1));
    setVal('imu-yaw-val',   d.yaw_signed.toFixed(1));
  }

  return { update };

})();
