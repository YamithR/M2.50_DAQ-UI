#!/usr/bin/env bash
# deploy.sh — Despliega el simulador MicroPython al ESP32
#
# Prerequisitos:
#   pip install mpremote
#   ESP32 con MicroPython v1.22+ conectado por USB
#
# Uso:
#   ./firmware_mp/deploy.sh [puerto]          (default: /dev/ttyUSB0)
#   ./firmware_mp/deploy.sh /dev/ttyACM0
#   ./firmware_mp/deploy.sh COM5              (Windows con WSL)
#
# El script sube:
#   1. Archivos Python del simulador
#   2. web_ui/ completo → /web/ en el filesystem del ESP32
#
# Antes de ejecutar editar firmware_mp/config.py con:
#   WIFI_SSID, WIFI_PASSWORD, y opcionalmente SIMULATE_SENSORS

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PORT="${1:-/dev/ttyUSB0}"
WEB_SRC="$ROOT/web_ui"

echo "======================================================"
echo " M2.50 DAQ — Despliegue MicroPython"
echo " Puerto    : $PORT"
echo " Web fuente: $WEB_SRC"
echo "======================================================"

# Verificar que mpremote está instalado
if ! command -v mpremote &>/dev/null; then
    echo "[ERROR] mpremote no está instalado. Ejecutar:"
    echo "  pip install mpremote"
    exit 1
fi

# Verificar que el directorio web_ui existe
if [ ! -d "$WEB_SRC" ]; then
    echo "[ERROR] No se encontró $WEB_SRC"
    exit 1
fi

echo ""
echo "[1/3] Subiendo archivos Python del simulador..."
for f in boot.py config.py main.py server.py sensors.py mpu6050_driver.py; do
    echo "  → $f"
    mpremote connect "$PORT" cp "$SCRIPT_DIR/$f" ":$f"
done

echo ""
echo "[2/3] Creando directorios en el ESP32..."
mpremote connect "$PORT" fs mkdir :web       2>/dev/null || true
mpremote connect "$PORT" fs mkdir :web/js    2>/dev/null || true
mpremote connect "$PORT" fs mkdir :web/vendor 2>/dev/null || true

echo ""
echo "[3/3] Subiendo web_ui/..."
echo "  → index.html"
mpremote connect "$PORT" cp "$WEB_SRC/index.html" :web/index.html

for js_file in ws_client.js svg_bolt.js gauges.js encoders.js charts.js bt_toggle.js; do
    echo "  → js/$js_file"
    mpremote connect "$PORT" cp "$WEB_SRC/js/$js_file" ":web/js/$js_file"
done

echo "  → vendor/uplot.min.js  (52 KB — puede tardar unos segundos)"
mpremote connect "$PORT" cp "$WEB_SRC/vendor/uplot.min.js" :web/vendor/uplot.min.js

echo ""
echo "======================================================"
echo " Despliegue completado."
echo " Reiniciar el dispositivo con:"
echo "   mpremote connect $PORT reset"
echo ""
echo " Luego abrir el monitor serie para ver la IP:"
echo "   mpremote connect $PORT repl"
echo "======================================================"
