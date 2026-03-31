/**
 * bt_toggle.js — Botones de calibración IMU y reset de encoders.
 *
 * Expone las siguientes funciones al scope global (window):
 *   calibrateYaw()    → POST /api/calibrate/yaw
 *   calibratePitch()  → POST /api/calibrate/pitch
 *   calibrateRoll()   → POST /api/calibrate/roll
 *
 * Al llamar a cada función:
 *  1. Hace POST al endpoint correspondiente del firmware.
 *  2. Muestra feedback visual en el botón durante 1 500 ms.
 *  3. En caso de error (sin conexión live), aplica el reset localmente
 *     en el estado de la simulación (ws_client.js expone resetEncoders).
 */

(function () {
  'use strict';

  function postCalibrate(endpoint, btnEl) {
    // Feedback visual inmediato
    if (btnEl) {
      btnEl.disabled = true;
      const origText = btnEl.textContent;
      btnEl.textContent = '✓ OK';
      btnEl.classList.add('ok');
      setTimeout(() => {
        btnEl.textContent = origText;
        btnEl.classList.remove('ok');
        btnEl.disabled = false;
      }, 1500);
    }

    // POST al firmware (falla silenciosamente si no hay conexión)
    fetch(endpoint, { method: 'POST' })
      .then(r => r.json())
      .catch(() => { /* sin conexión — feedback ya mostrado */ });
  }

  // Encuentra el botón más cercano al caller (por proximidad de onclick)
  function callerBtn(name) {
    return document.querySelector(`[onclick="${name}()"]`);
  }

  window.calibrateYaw   = () => postCalibrate('/api/calibrate/yaw',   callerBtn('calibrateYaw'));
  window.calibratePitch = () => postCalibrate('/api/calibrate/pitch', callerBtn('calibratePitch'));
  window.calibrateRoll  = () => postCalibrate('/api/calibrate/roll',  callerBtn('calibrateRoll'));

  // Sobreescribe el resetEncoders de ws_client.js para añadir:
  //   1. Visual feedback en el botón
  //   2. POST al endpoint de hardware
  //   3. Llamada al reset local de simulación (original)
  const _origResetEncoders = window.resetEncoders || null;
  window.resetEncoders = function () {
    // Reset estado de simulación local
    if (_origResetEncoders) _origResetEncoders();

    // Feedback visual
    const btn = callerBtn('resetEncoders');
    if (btn) {
      btn.disabled = true;
      const origText = btn.textContent;
      btn.textContent = '✓ OK';
      btn.classList.add('ok');
      setTimeout(() => {
        btn.textContent = origText;
        btn.classList.remove('ok');
        btn.disabled = false;
      }, 1500);
    }

    // POST al firmware (falla silenciosamente si no hay conexión)
    fetch('/api/calibrate/encoders', { method: 'POST' })
      .then(r => r.json())
      .catch(() => { /* sin conexión — sim ya reseteada */ });
  };

})();
