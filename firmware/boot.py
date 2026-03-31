# boot.py — Configuración de bajo nivel ejecutada por MicroPython al arrancar.
# Se ejecuta antes que main.py en cada power-on / reset.

import machine
import esp
import network

# Máxima frecuencia de CPU: 240 MHz
machine.freq(240_000_000)

# Silenciar mensajes internos del SO (reduce ruido en la UART serie)
esp.osdebug(None)

# Desactivar ambas interfaces WiFi; main.py las activará selectivamente
network.WLAN(network.STA_IF).active(False)
network.WLAN(network.AP_IF).active(False)

# Importar el programa principal.
# El try/except evita que el ESP32 quede atrapado en un bucle de reset si
# main.py tiene un error de importación.
try:
    import main
except Exception as e:
    print("[boot] ERROR al importar main:", e)
