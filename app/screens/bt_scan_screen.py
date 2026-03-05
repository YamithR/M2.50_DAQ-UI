"""
bt_scan_screen.py — Screen 1: BLE device scanner.

Lists M2-DAQ ESP32 devices found by bleak and lets the user tap to connect.
On successful connect, transitions to DashboardScreen.
"""

import asyncio
import threading
import logging

from kivy.app import App
from kivy.uix.screen import Screen
from kivy.clock import Clock, mainthread

from services.ble_service import scan_for_m2_devices

log = logging.getLogger(__name__)


class BtScanScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scan_thread = None

    # ── Called from KV button ────────────────────────────────────────── #
    def do_scan(self):
        self.ids.rv.data = []
        self.ids.btn_scan.text    = "ESCANEANDO..."
        self.ids.btn_scan.disabled = True
        self._scan_thread = threading.Thread(
            target=self._run_scan, daemon=True
        )
        self._scan_thread.start()

    def _run_scan(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            devices = loop.run_until_complete(scan_for_m2_devices(timeout=5.0))
            self._on_scan_done(devices)
        except Exception as e:
            log.warning("Scan error: %s", e)
            self._on_scan_done([])
        finally:
            loop.close()

    @mainthread
    def _on_scan_done(self, devices):
        self.ids.btn_scan.text     = "ESCANEAR"
        self.ids.btn_scan.disabled = False

        if not devices:
            self.ids.rv.data = [{"device_name": "No se encontraron dispositivos M2-DAQ",
                                  "device_rssi": "",
                                  "address": ""}]
            return

        self.ids.rv.data = [
            {
                "device_name": d.name or "Desconocido",
                "device_rssi": "{} dBm".format(getattr(d, 'rssi', '?')),
                "address":     d.address,
            }
            for d in devices
        ]

    # ── Called from KV RecycleView item button ───────────────────────── #
    def connect_to(self, address: str):
        if not address:
            return
        app = App.get_running_app()
        app.ble_address = address
        log.info("Connecting to %s", address)
        self.manager.current = "dashboard"
