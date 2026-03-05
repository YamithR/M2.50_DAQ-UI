import machine
import esp
import network
import time

# Máxima frecuencia CPU: mejora el headroom para el loop asyncio 50 Hz
machine.freq(240_000_000)

# Silencia mensajes internos del sistema operativo ESP32
# Los errores de Python siguen apareciendo en el REPL
esp.osdebug(None)

# IMPORTANTE: Desactivar STA por defecto para evitar conflictos WiFi
sta = network.WLAN(network.STA_IF)
sta.active(False)

# Activar AP inmediatamente (sin esperar a main.py)
print("="*50)
print("MicroPython M2.50 DAQ")
print("="*50)

import config
ap = network.WLAN(network.AP_IF)
ap.active(False)
time.sleep_ms(100)
ap.active(True)
ap.config(essid=config.AP_SSID, password=config.AP_PASSWORD, authmode=network.AUTH_WPA2_PSK)
time.sleep(1)
if ap.active():
    print("✓ AP activo: {}".format(config.AP_SSID))
    print("✓ IP: 192.168.4.1")
    print("✓ Contraseña: {}".format(config.AP_PASSWORD))

# Ejecutar main.py en background
print("\nIniciando servicios...")
try:
    import main
except Exception as e:
    print("ERROR en main:", e)
