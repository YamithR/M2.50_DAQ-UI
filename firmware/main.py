# main.py — Punto de entrada principal del firmware M2.50 DAQ-UI.
# Gestiona la conexión WiFi (STA → AP fallback) y lanza el event loop asyncio.

import time
import network
import asyncio
import config

# ---------------------------------------------------------------------------
# Conexión WiFi
# ---------------------------------------------------------------------------
def connect_wifi() -> bool:
    """Intenta conectar en modo STA. Si falla, activa el AP fallback.
    Retorna True si hay conectividad (STA o AP).
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Warm boot: ya conectado desde el ciclo anterior
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"[wifi] Ya conectado — IP: {ip}")
        network.WLAN(network.AP_IF).active(False)
        return True

    print(f"[wifi] Conectando a '{config.WIFI_SSID}' …")
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    t0 = time.time()
    while not wlan.isconnected():
        if time.time() - t0 >= config.WIFI_TIMEOUT_S:
            wlan.active(False)
            print(f"[wifi] Timeout ({config.WIFI_TIMEOUT_S}s) — activando AP fallback")
            return _start_ap_fallback()
        time.sleep_ms(200)

    ip = wlan.ifconfig()[0]
    print(f"[wifi] Conectado en modo STA — IP: {ip}")
    network.WLAN(network.AP_IF).active(False)
    return True


def _start_ap_fallback() -> bool:
    """Levanta el punto de acceso WiFi de emergencia."""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(
        ssid     = config.AP_SSID,
        password = config.AP_PASSWORD,
        authmode = network.AUTH_WPA_WPA2_PSK,
    )

    t0 = time.time()
    while not ap.active():
        if time.time() - t0 > 10:
            print("[wifi] ERROR — no se pudo activar el AP.")
            return False
        time.sleep_ms(100)

    ip = ap.ifconfig()[0]
    print(f"[wifi] AP activo — SSID: '{config.AP_SSID}' — IP: {ip}")
    return True


# ---------------------------------------------------------------------------
# Coroutine principal
# ---------------------------------------------------------------------------
async def main():
    from server import start_server
    await start_server()


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
# Ventana de interrupción: 3 s para que Ctrl+C pueda detener el programa
# antes de que asyncio bloquee el REPL.
time.sleep_ms(3000)

connect_wifi()
asyncio.run(main())
