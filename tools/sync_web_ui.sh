#!/usr/bin/env bash
# sync_web_ui.sh — Sync web_ui/ into app/assets/web_ui/
#
# Run this after changing any web_ui file to keep the Kivy app's local
# copy in sync with the files that will be served by the ESP32 SPIFFS.
#
# Usage (from project root):
#   ./tools/sync_web_ui.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

SRC="$ROOT/web_ui/"
DST="$ROOT/app/assets/web_ui/"

echo "[sync_web_ui] $SRC → $DST"
mkdir -p "$DST"
rsync -av --delete "$SRC" "$DST"
echo "[sync_web_ui] Done."
