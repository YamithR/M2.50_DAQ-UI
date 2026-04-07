/**
 * ws_client.js — Cliente WebSocket con simulación local integrada.
 *
 * Comportamiento:
 *  - La simulación local arranca inmediatamente al cargar la página (modo offline).
 *  - Al recibir el primer paquete real del firmware, la simulación se detiene.
 *  - Si la conexión WS cae, la simulación local se reactiva automáticamente.
 *  - Reconexión con backoff exponencial: 1 s → 2 s → 4 s → … → 30 s máx.
 *  - Un único requestAnimationFrame loop maneja toda la UI (sin setInterval).
 *
 * Parámetros de simulación IDÉNTICOS a firmware/config.py y firmware/sensors.py.
 */

(function () {
  'use strict';

  // ── Parámetros de simulación (deben coincidir con config.py) ───────────────
  const SIM_ROLL_AMP      = 10.0;   // grados ±
  const SIM_PITCH_AMP     =  8.0;   // grados ±
  const SIM_YAW_DRIFT_HZ  =  0.04;  // Hz
  const SIM_FIRE_CYCLE_MS =  6000;  // ms
  const BROADCAST_HZ      = 50;
  const PERIOD_MS         = 1000 / BROADCAST_HZ;   // 20 ms

  const SIM_DT        = PERIOD_MS / 1000.0;
  const SIM_YAW_OMEGA = SIM_YAW_DRIFT_HZ * 2 * Math.PI;

  // ── Estado de simulación ───────────────────────────────────────────────────
  let simT       = 0.0;
  let simYaw     = 0.0;
  let simEncH    = 0;
  let simEncV    = 0;
  let simEncHVel = 0;
  let simEncVVel = 0;

  // ── Estado de conexión ─────────────────────────────────────────────────────
  let ws            = null;
  let liveMode      = false;   // true = recibiendo datos reales
  let retryDelay    = 1000;
  let retryTimer    = null;
  let lastRafTs     = null;
  let simAccum      = 0;       // acumulador de tiempo para sub-muestreo a 50 Hz
  let frameHz       = 0;
  let frameCount    = 0;
  let fpsTimer      = 0;

  // ── Elementos DOM de estado ────────────────────────────────────────────────
  const dot       = document.getElementById('ws-dot');
  const wsText    = document.getElementById('ws-text');
  const wsFreq    = document.getElementById('ws-freq');
  const simToggle = document.getElementById('sim-toggle');

  // forceSim = true → ignora datos WS y corre simulación local
  let forceSim = false;

  function setForceSim(val) {
    forceSim = val;
    if (simToggle) {
      simToggle.textContent = forceSim ? 'SIM' : 'LIVE';
      simToggle.classList.toggle('mode-live', !forceSim);
      simToggle.title = forceSim
        ? 'Modo simulación local activo — clic para cambiar a LIVE'
        : 'Modo live activo — clic para forzar simulación';
    }
    if (forceSim) {
      liveMode  = false;
      simAccum  = 0;
      lastRafTs = null;
      setStatus('simulating', 'Simulación local (forzada)');
    } else {
      // Reconectar si el WS está cerrado
      if (!ws || ws.readyState > 1) {
        if (!retryTimer) connect();
      }
    }
  }

  if (simToggle) {
    simToggle.addEventListener('click', () => setForceSim(!forceSim));
  }

  // ── Función de despacho a todos los módulos ────────────────────────────────
  function dispatch(d) {
    if (window.svgBolt)    svgBolt.update(d);
    if (window.gauges)     gauges.update(d);
    if (window.encoders)   encoders.update(d);
    if (window.charts)     charts.push(d);

    // Actualizar tabla de sensores
    _updateTable(d);

    // Frecuencímetro
    frameCount++;
  }

  function _updateTable(d) {
    const set = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = v;
    };
    set('tbl-s1',    d.s1    ? 'ACTIVO' : 'inact.');
    set('tbl-s2',    d.s2    ? 'ACTIVO' : 'inact.');
    set('tbl-s3',    d.s3    ? 'ACTIVO' : 'inact.');
    set('tbl-roll',  d.roll.toFixed(1));
    set('tbl-pitch', d.pitch.toFixed(1));
    set('tbl-yaw',   d.yaw.toFixed(1));
    set('tbl-enc-h', d.enc_h);
    set('tbl-enc-v', d.enc_v);
    set('tbl-ts',    d.ts);
  }

  // ── Generador de paquete simulado ──────────────────────────────────────────
  function simPacket() {
    const t = simT;

    const roll  = SIM_ROLL_AMP  * Math.cos(t * 0.35);
    const pitch = SIM_PITCH_AMP * Math.sin(t * 0.40);
    simYaw = (simYaw + 2.0 * Math.sin(t * SIM_YAW_OMEGA) * SIM_DT + 360) % 360;

    if (Math.random() < 0.03) simEncHVel = Math.round(Math.random() * 6 - 3);
    if (Math.random() < 0.03) simEncVVel = Math.round(Math.random() * 6 - 3);
    simEncH += simEncHVel;
    simEncV += simEncVVel;

    const phase = (performance.now() % SIM_FIRE_CYCLE_MS) / SIM_FIRE_CYCLE_MS;
    let s1, s2, s3;
    if      (phase < 0.30) { s1 = true;  s2 = false; s3 = false; }
    else if (phase < 0.60) { s1 = false; s2 = true;  s3 = false; }
    else if (phase < 0.65) { s1 = false; s2 = false; s3 = true;  }
    else                   { s1 = false; s2 = false; s3 = false; }

    simT += SIM_DT;

    return {
      s1, s2, s3,
      gas_valve: s3,
      roll:         +roll.toFixed(2),
      pitch:        +pitch.toFixed(2),
      yaw:          +simYaw.toFixed(2),
      yaw_signed:   +(((simYaw + 180) % 360) - 180).toFixed(2),
      enc_h:        simEncH,
      enc_v:        simEncV,
      ts:           Math.round(performance.now()),
    };
  }

  // ── Loop principal rAF ─────────────────────────────────────────────────────
  function rafLoop(ts) {
    requestAnimationFrame(rafLoop);

    // Frecuencímetro (actualiza cada segundo)
    if (ts - fpsTimer >= 1000) {
      frameHz   = frameCount;
      frameCount = 0;
      fpsTimer  = ts;
      if (wsFreq) wsFreq.textContent = `${frameHz} Hz`;
    }

    if (!liveMode) {
      // Acumular tiempo y emitir paquetes a 50 Hz
      if (lastRafTs !== null) {
        simAccum += ts - lastRafTs;
      }
      lastRafTs = ts;

      while (simAccum >= PERIOD_MS) {
        dispatch(simPacket());
        simAccum -= PERIOD_MS;
      }
    }
  }

  // ── Estado UI de conexión ──────────────────────────────────────────────────
  function setStatus(state, msg) {
    dot.className   = state;   // 'simulating' | 'connected' | ''
    wsText.textContent = msg;
  }

  // ── WebSocket ──────────────────────────────────────────────────────────────
  function connect() {
    const url = `ws://${location.host}/ws`;
    setStatus('simulating', `Simulación local — conectando a ${url} …`);

    try {
      ws = new WebSocket(url);
    } catch (e) {
      scheduleRetry();
      return;
    }

    ws.onopen = () => {
      retryDelay = 1000;
      setStatus('connected', `Conectado a ${url}`);
    };

    ws.onmessage = (ev) => {
      if (forceSim) return;   // toggle en SIM → descartar datos reales
      if (!liveMode) {
        liveMode     = true;
        simAccum     = 0;
        lastRafTs    = null;
        setStatus('connected', `Live @ ${url}`);
      }
      try {
        dispatch(JSON.parse(ev.data));
      } catch (_) { /* ignorar frames malformados */ }
    };

    ws.onclose  = ws.onerror = () => {
      if (liveMode) {
        liveMode  = true;   // marcamos false para que la sim vuelva a correr
        liveMode  = false;
        setStatus('simulating', 'Conexión perdida — simulación local activa — reconectando…');
      }
      ws = null;
      scheduleRetry();
    };
  }

  function scheduleRetry() {
    if (retryTimer) return;
    retryTimer = setTimeout(() => {
      retryTimer = null;
      retryDelay = Math.min(retryDelay * 2, 30000);
      connect();
    }, retryDelay);
  }

  // ── Arranque ───────────────────────────────────────────────────────────────
  // La simulación local empieza en el primer rAF (sin esperar al WS)
  requestAnimationFrame(rafLoop);
  connect();

  // Exponer reset de encoders local (para el botón de UI)
  window.resetEncoders = function () {
    simEncH = simEncV = simEncHVel = simEncVVel = 0;
  };

})();
