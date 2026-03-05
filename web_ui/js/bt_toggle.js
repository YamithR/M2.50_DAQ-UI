/**
 * bt_toggle.js — Toggle BLE advertisig mode via REST API.
 *
 * Sends POST /api/config/bluetooth with {"enabled": true/false}.
 * Button state updates optimistically; reverts on network error.
 *
 * calibrateYaw() exposes a global function called by the CALIBRAR YAW button.
 */
(function () {
    'use strict';

    var btEnabled = false;
    var btnBt = document.getElementById('btn-bt');

    // Inicializar estado del botón desde el servidor al cargar la página.
    // Compatible con el firmware ESP32-S3 y con el simulador MicroPython
    // (ambos responden {"bt_enabled": false/true} en GET /api/config).
    fetch('/api/config')
        .then(function (r) { return r.json(); })
        .then(function (cfg) {
            btEnabled = !!cfg.bt_enabled;
            btnBt.textContent = 'BLUETOOTH: ' + (btEnabled ? 'ON' : 'OFF');
            btnBt.className   = btEnabled ? 'bt-on' : '';
        })
        .catch(function () { /* silencioso — puede fallar en Kivy/modo BLE */ });

    window.btToggle = function () {
        var desired = !btEnabled;

        fetch('/api/config/bluetooth', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ enabled: desired }),
        })
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (json) {
            if (json.ok) {
                btEnabled = desired;
                btnBt.textContent = 'BLUETOOTH: ' + (btEnabled ? 'ON' : 'OFF');
                btnBt.className   = btEnabled ? 'bt-on' : '';
            }
        })
        .catch(function (err) {
            console.error('bt_toggle error:', err);
        });
    };

    window.calibrateYaw = function () {
        fetch('/api/calibrate', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    '{}',
        })
        .then(function (r) { return r.json(); })
        .then(function (json) {
            if (json.ok) {
                var btn = document.getElementById('btn-calibrate');
                var orig = btn.textContent;
                btn.textContent = 'YAW RESETEADO';
                setTimeout(function () { btn.textContent = orig; }, 1500);
            }
        })
        .catch(function (err) {
            console.error('calibrate error:', err);
        });
    };
})();
