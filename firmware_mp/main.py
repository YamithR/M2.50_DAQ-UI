import network
import asyncio
import time
import config
from server import start_server


def _start_ap_fallback():
    """Levanta un AP WiFi si la conexión STA falla."""
    # Asegurar que STA está desactivado antes de AP
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    
    ap = network.WLAN(network.AP_IF)
    ap.active(False)  # Reset antes de reconfigurar
    ap.active(True)
    ap.config(
        essid=config.AP_SSID,
        password=config.AP_PASSWORD,
        authmode=network.AUTH_WPA2_PSK,
    )
    # Espera a que el AP esté activo
    deadline = time.time() + 5
    while not ap.active() and time.time() < deadline:
        time.sleep_ms(100)
    ip = ap.ifconfig()[0]
    print("AP activo: SSID={!r}  IP={}".format(config.AP_SSID, ip))
    print("Abrir en navegador: http://{}/".format(ip))


def connect_wifi():
    """
    Intenta conectar como STA.
    Si no obtiene IP en WIFI_TIMEOUT_S segundos, levanta AP fallback.
    Retorna True si STA OK, False si se usó AP fallback.
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        # Ya estaba conectado (warm boot)
        ip = wlan.ifconfig()[0]
        print("WiFi ya conectado: IP={}".format(ip))
        return True

    print("Conectando WiFi a {!r} ...".format(config.WIFI_SSID))
    wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

    deadline = time.time() + config.WIFI_TIMEOUT_S
    while not wlan.isconnected() and time.time() < deadline:
        time.sleep_ms(200)

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("WiFi OK: IP={}".format(ip))
        print("Abrir en navegador: http://{}/".format(ip))
        return True

    print("WiFi falló (timeout {}s) — iniciando AP fallback".format(
        config.WIFI_TIMEOUT_S))
    _start_ap_fallback()
    return False


async def main():
    connect_wifi()
    # start_server() no retorna — mantiene el loop del servidor y el broadcast 50 Hz
    await start_server()


# Crear la tarea y ejecutar el loop
try:
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(main())
except Exception as e:
    print("❌ ERROR en main:", e)
    import sys
    sys.print_exception(e)
