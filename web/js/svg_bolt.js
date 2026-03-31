/**
 * svg_bolt.js — Animación SVG del mecanismo de cerrojo M2.50.
 *
 * Mapeo sensor → posición X del #bolt-group (translateX):
 *   S1 activo (BLOQUEADO)  → X = 100
 *   S2 activo (RETENEDOR)  → X = 310
 *   S3 activo (VÁLVULA)    → X = 600
 *   Ninguno activo         → última posición conocida
 *
 * El muelle (#spring-path) se dibuja entre la pared trasera (x=38) y la
 * cara izquierda del bolt-group (X actual del grupo).
 */

window.svgBolt = (function () {
  'use strict';

  // ── Posiciones canónicas del cerrojo ───────────────────────────────────────
  const POS = { S1: 100, S2: 310, S3: 600 };
  const SPRING_WALL_X  = 788;   // x fijo — pared interior derecha del receptor
  const SPRING_BOLT_DX = 200;   // borde derecho del cuerpo del cerrojo (coords locales)
  const SPRING_Y       = 150;   // y central del muelle
  const SPRING_AMP     = 18;    // amplitud del zigzag en px
  const SPRING_SEGS    = 12;    // número de segmentos del zigzag

  // ── Cache de elementos SVG ─────────────────────────────────────────────────
  let boltGroup   = null;
  let springPath  = null;
  let airBlast    = null;
  let ledS1       = null;
  let ledS2       = null;
  let ledS3       = null;
  let statusText  = null;
  let valveText   = null;
  let svgWrapper  = null;

  let currentX     = POS.S1;
  let targetX      = POS.S1;
  let prevS3       = false;

  // ── Inicialización ─────────────────────────────────────────────────────────
  function init() {
    boltGroup  = document.getElementById('bolt-group');
    springPath = document.getElementById('spring-path');
    airBlast   = document.getElementById('air-blast');
    ledS1      = document.getElementById('led-s1');
    ledS2      = document.getElementById('led-s2');
    ledS3      = document.getElementById('led-s3');
    statusText = document.getElementById('bolt-status-text');
    valveText  = document.getElementById('valve-text');
    svgWrapper = document.getElementById('bolt-svg-wrapper');

    // Posición inicial
    _applyPosition(currentX);
  }

  // ── Función principal: actualizar desde paquete de datos ───────────────────
  function update(d) {
    if (!boltGroup) init();

    // Determinar nueva posición objetivo
    if      (d.s3) targetX = POS.S3;
    else if (d.s2) targetX = POS.S2;
    else if (d.s1) targetX = POS.S1;
    // Si ninguno: mantener última posición conocida

    // Interpolación suave (80% del camino por frame a ~50 Hz → transición ~60 ms)
    currentX += (targetX - currentX) * 0.4;
    if (Math.abs(targetX - currentX) < 0.5) currentX = targetX;

    _applyPosition(currentX);
    _updateSpring(currentX);
    _updateAirBlast(d.s3);
    _updateLEDs(d);
    _updateStatus(d);

    // Recoil: flanco ascendente de S3
    if (d.s3 && !prevS3 && svgWrapper) {
      svgWrapper.classList.remove('recoil-active');
      // Force reflow para reiniciar animación CSS
      void svgWrapper.offsetWidth;
      svgWrapper.classList.add('recoil-active');
    }
    prevS3 = d.s3;
  }

  // ── Helpers internos ───────────────────────────────────────────────────────
  function _applyPosition(x) {
    boltGroup.setAttribute('transform', `translate(${x.toFixed(1)},0)`);
  }

  function _updateSpring(boltX) {
    // El muelle va desde la cara derecha del cuerpo del cerrojo hasta la
    // pared interior derecha del receptor. Cuando el cerrojo avanza hasta
    // S3, el cuerpo llega a la cámara y el resorte queda completamente
    // comprimido (longitud ≤ 0 → no se dibuja).
    const x1 = boltX + SPRING_BOLT_DX;   // borde derecho del cerrojo
    const x2 = SPRING_WALL_X;            // pared derecha (fija)
    if (x2 - x1 < 4) {
      springPath.setAttribute('d', '');
      return;
    }
    springPath.setAttribute('d', _zigzag(x1, x2, SPRING_Y, SPRING_AMP, SPRING_SEGS));
  }

  function _zigzag(x1, x2, y, amp, segs) {
    if (x2 <= x1) return '';
    const dx = (x2 - x1) / segs;
    let d = `M ${x1.toFixed(1)},${y}`;
    for (let i = 0; i < segs; i++) {
      const xa = (x1 + i * dx + dx * 0.25).toFixed(1);
      const xb = (x1 + i * dx + dx * 0.75).toFixed(1);
      const ya = (y + (i % 2 === 0 ? -amp : amp)).toFixed(1);
      const yb = (y + (i % 2 === 0 ?  amp : -amp)).toFixed(1);
      d += ` L ${xa},${ya} L ${xb},${yb}`;
    }
    d += ` L ${x2.toFixed(1)},${y}`;
    return d;
  }

  function _updateAirBlast(s3Active) {
    airBlast.setAttribute('opacity', s3Active ? '1' : '0');
  }

  function _updateLEDs(d) {
    _setLed(ledS1, d.s1, 'active-s1');
    _setLed(ledS2, d.s2, 'active-s2');
    _setLed(ledS3, d.s3, 'active-s3');
  }

  function _setLed(el, active, cls) {
    if (!el) return;
    if (active) el.classList.add(cls);
    else        el.classList.remove(cls);
  }

  function _updateStatus(d) {
    let estado, valve;
    if (d.s3)       { estado = 'DISPARO — Válvula gas abierta'; valve = true;  }
    else if (d.s2)  { estado = 'Cerrojo amartillado y retenido'; valve = false; }
    else if (d.s1)  { estado = 'Cerrojo en posición de bloqueo'; valve = false; }
    else            { estado = 'Retorno / reposo';               valve = false; }

    if (statusText) statusText.textContent = estado;

    if (valveText) {
      valveText.textContent = valve ? '⚡ VÁLVULA ABIERTA' : 'VÁLVULA CERRADA';
      if (valve) valveText.classList.add('firing');
      else       valveText.classList.remove('firing');
    }
  }

  return { update };

})();
