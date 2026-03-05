#!/usr/bin/env bash
# flash_all.sh — Build firmware + SPIFFS and flash everything to ESP32-S3
#
# Prerequisites:
#   - ESP-IDF v5.2 installed and sourced: . ~/esp/esp-idf/export.sh
#   - ESP32-S3 connected via USB-C (USB OTG or UART port)
#
# Usage:
#   ./tools/flash_all.sh [port]   (default port: /dev/ttyUSB0)
#
# Examples:
#   ./tools/flash_all.sh
#   ./tools/flash_all.sh /dev/ttyACM0
#   ./tools/flash_all.sh COM3       # Windows (use in WSL or cmd)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
FW_DIR="$ROOT/firmware"
PORT="${1:-/dev/ttyUSB0}"

echo "======================================================"
echo " M2.50 DAQ — Full Build & Flash"
echo " Firmware dir : $FW_DIR"
echo " Flash port   : $PORT"
echo "======================================================"

# 1. Verify IDF is sourced
if [ -z "${IDF_PATH:-}" ]; then
    echo "[ERROR] IDF_PATH is not set. Source IDF first:"
    echo "  . ~/esp/esp-idf/export.sh"
    exit 1
fi

# 2. Sync web_ui → app/assets/web_ui (keeps Kivy app in sync)
echo ""
echo "[1/3] Syncing web_ui to app assets..."
bash "$SCRIPT_DIR/sync_web_ui.sh"

# 3. Build firmware (includes SPIFFS image generation via CMakeLists.txt)
echo ""
echo "[2/3] Building firmware..."
cd "$FW_DIR"
idf.py build

# 4. Flash firmware + SPIFFS (idf.py flash covers all partitions)
echo ""
echo "[3/3] Flashing to $PORT ..."
idf.py -p "$PORT" -b 460800 flash

echo ""
echo "======================================================"
echo " Flash complete. Start monitor with:"
echo "   idf.py -p $PORT monitor"
echo " Web UI will be available at http://m2daq.local/"
echo "======================================================"
