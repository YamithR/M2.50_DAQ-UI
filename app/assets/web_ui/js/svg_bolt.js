/**
 * svg_bolt.js — Drives the Browning M2.50 bolt SVG using real sensor states.
 *
 * Sensor → SVG position mapping:
 *   S1 active → bolt at x = 100 (fully retracted, locked)
 *   S2 active → bolt at x = 310 (held by retainer, cocked)
 *   S3 active → bolt at x = 600 (forward, gas valve open)
 *   None      → bolt stays at last known position
 *
 * All SVG element IDs are preserved from the original 2D.html simulation.
 */
window.svgBolt = (function () {
    'use strict';

    const S1_X = 100, S2_X = 310, S3_X = 600;

    const boltEl    = document.getElementById('bolt-group');
    const springEl  = document.getElementById('spring');
    const airEl     = document.getElementById('air-blast');
    const titleEl   = document.getElementById('state-title');
    const descEl    = document.getElementById('state-desc');
    const canvasEl  = document.getElementById('sim-canvas');

    const ledS1 = document.getElementById('led-s1');
    const ledS2 = document.getElementById('led-s2');
    const ledS3 = document.getElementById('led-s3');
    const txtGas = document.getElementById('txt-gas');

    const btnSafe    = document.getElementById('btn-safe');
    const btnTrigger = document.getElementById('btn-trigger');

    let lastPos = S1_X;

    function update(d) {
        /* ── Bolt position: highest-priority sensor wins ── */
        let pos = lastPos;
        if (d.s3)       pos = S3_X;
        else if (d.s2)  pos = S2_X;
        else if (d.s1)  pos = S1_X;
        lastPos = pos;

        /* ── SVG transforms ── */
        boltEl.setAttribute('transform', 'translate(' + pos + ', 0)');

        var sStart = pos + 130;
        springEl.setAttribute('x', sStart);
        springEl.setAttribute('width', Math.max(0, 760 - sStart));

        airEl.setAttribute('opacity', d.gas_valve ? '1' : '0');

        /* ── Recoil shake on gas valve opening ── */
        if (d.gas_valve) {
            canvasEl.classList.add('recoil-active');
        } else {
            canvasEl.classList.remove('recoil-active');
        }

        /* ── LED indicators ── */
        ledS1.className = 'sensor-dot' + (d.s1 ? ' on' : '');
        ledS2.className = 'sensor-dot' + (d.s2 ? ' on' : '');
        ledS3.className = 'sensor-dot' + (d.s3 ? ' on' : '');

        /* ── Gas valve text ── */
        txtGas.textContent  = d.gas_valve ? 'Abierta' : 'Cerrada';
        txtGas.style.color  = d.gas_valve ? '#0f0'    : '#777';

        /* ── Status box ── */
        var title = 'SISTEMA_OK';
        var desc  = 'Esperando activación mecánica.';

        if (d.s1 && !d.s2 && !d.s3) {
            title = '0. BLOQUEADO (S1)';
            desc  = 'Cerrojo en posición de bloqueo S1. Seguro mecánico activo.';
        } else if (!d.s1 && d.s2 && !d.s3) {
            title = '1. RETENIDO (S2)';
            desc  = 'Cerrojo amartillado — retenedor activo en S2. Listo para disparar.';
        } else if (!d.s1 && !d.s2 && d.s3) {
            title = '3. VÁLVULA ACTIVA (S3)';
            desc  = 'Cerrojo en S3 — gas liberado. Ciclo automático en progreso.';
        } else if (d.s1 && d.s2) {
            title = 'TRANSICIÓN S1→S2';
            desc  = 'Cerrojo en recorrido de armado.';
        } else if (d.s2 && d.s3) {
            title = 'TRANSICIÓN S2→S3';
            desc  = 'Disparo: cerrojo avanzando hacia válvula.';
        } else if (!d.s1 && !d.s2 && !d.s3) {
            title = 'EN TRÁNSITO';
            desc  = 'Cerrojo entre posiciones de referencia.';
        }

        titleEl.textContent = 'Estado: ' + title;
        descEl.textContent  = desc;

        /* ── Safety / Trigger button labels (read-only indicators) ── */
        /* These buttons are disabled — they serve as status indicators only */
    }

    return { update: update };
})();
