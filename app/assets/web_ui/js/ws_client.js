/**
 * ws_client.js — WebSocket client with auto-reconnect.
 *
 * If window.__KIVY_MODE__ is set to true (injected by the Kivy WebView
 * before loading this page), the WebSocket is skipped and data is instead
 * delivered via window.onBTData() which the Kivy JS bridge calls.
 */
(function () {
    'use strict';

    const RECONNECT_BASE_MS = 1000;
    const RECONNECT_MAX_MS  = 30000;

    const wsStatusEl = document.getElementById('ws-status');

    function setStatus(text, cls) {
        wsStatusEl.textContent = text;
        wsStatusEl.className   = cls || '';
    }

    /** Dispatch a parsed sensor packet to every registered module. */
    function dispatch(d) {
        if (window.svgBolt)  window.svgBolt.update(d);
        if (window.gauges)   window.gauges.update(d);
        if (window.encoders) window.encoders.update(d);
        if (window.charts)   window.charts.push(d);
    }

    /* ── Kivy / BLE bridge mode ─────────────────────────────────── */
    if (window.__KIVY_MODE__) {
        setStatus('⬤ KIVY/BLE MODE', 'connected');
        /**
         * Called by Kivy JS bridge (js_bridge.py) with a JSON string
         * or pre-parsed object.
         */
        window.onBTData = function (payload) {
            const d = (typeof payload === 'string') ? JSON.parse(payload) : payload;
            dispatch(d);
        };
        return;
    }

    /* ── WebSocket mode ─────────────────────────────────────────── */
    const WS_URL = 'ws://' + location.host + '/ws';
    let ws;
    let reconnectDelay = RECONNECT_BASE_MS;

    function connect() {
        setStatus('⬤ CONECTANDO...', '');
        ws = new WebSocket(WS_URL);

        ws.onopen = function () {
            reconnectDelay = RECONNECT_BASE_MS;
            setStatus('⬤ CONECTADO — ' + location.host, 'connected');
        };

        ws.onmessage = function (ev) {
            try {
                dispatch(JSON.parse(ev.data));
            } catch (e) {
                console.warn('ws_client: bad JSON', e);
            }
        };

        ws.onerror = function () {
            setStatus('⬤ ERROR DE CONEXIÓN', 'error');
        };

        ws.onclose = function () {
            setStatus('⬤ DESCONECTADO — reintentando en ' + (reconnectDelay / 1000).toFixed(0) + 's', 'error');
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
        };
    }

    connect();
})();
