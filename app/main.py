"""
main.py — M2.50 DAQ Kivy Application entry point.

Screens:
    scan      → BtScanScreen  (BLE device discovery)
    dashboard → DashboardScreen (WebView + BLE data bridge)
"""

import os
import logging

# Suppress Kivy console banner before importing
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, SlideTransition
from kivy.lang import Builder

from screens.bt_scan_screen  import BtScanScreen
from screens.dashboard_screen import DashboardScreen

log = logging.getLogger(__name__)

# Load KV layout files
KV_DIR = os.path.join(os.path.dirname(__file__), "kv")
Builder.load_file(os.path.join(KV_DIR, "bt_scan.kv"))
Builder.load_file(os.path.join(KV_DIR, "dashboard.kv"))


class M2DaqApp(App):

    # Shared state set by BtScanScreen, read by DashboardScreen
    ble_address: str = ""

    def build(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(BtScanScreen(name="scan"))
        sm.add_widget(DashboardScreen(name="dashboard"))
        return sm

    def on_start(self):
        log.info("M2.50 DAQ started")

    def on_stop(self):
        # Ensure BLE service is stopped on exit
        try:
            ds = self.root.get_screen("dashboard")
            if ds._ble:
                ds._ble.stop()
        except Exception:
            pass


if __name__ == "__main__":
    M2DaqApp().run()
