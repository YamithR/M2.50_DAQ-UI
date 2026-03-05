"""
dashboard_screen.py — Screen 2: Main DAQ dashboard with WebView + BLE bridge.
"""

import logging
import os

from kivy.app import App
from kivy.uix.screen import Screen
from kivy.clock import Clock

from services.ble_service import BleService
from services.js_bridge import JsBridge

log = logging.getLogger(__name__)

# Path to the local copy of web_ui/index.html (bundled with the app)
WEB_UI_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "web_ui")


class DashboardScreen(Screen):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._ble  = None
        self._bridge = None

    # ── Kivy lifecycle ──────────────────────────────────────────────── #
    def on_enter(self):
        app = App.get_running_app()
        address = getattr(app, "ble_address", None)

        wv = self.ids.get("webview_widget")
        if wv is None:
            log.error("webview_widget id not found in DashboardScreen kv layout")
            return

        self._bridge = JsBridge(wv)

        # Inject __KIVY_MODE__ before loading the page so ws_client.js
        # skips WebSocket and activates the BT data path.
        self._load_webview(wv)

        if address:
            log.info("Starting BLE service for %s", address)
            self._ble = BleService(address, self._bridge.on_data)
            self._ble.start()
            self.ids.status_bar.text = "BLE: conectando a " + address
        else:
            self.ids.status_bar.text = "Sin dispositivo BLE — modo demostración"

    def on_leave(self):
        if self._ble:
            self._ble.stop()
            self._ble = None

    # ── WebView loading ─────────────────────────────────────────────── #
    def _load_webview(self, wv):
        """Build the local file URL and load it in the WebView."""
        index_path = os.path.join(WEB_UI_DIR, "index.html")
        index_path = os.path.abspath(index_path)

        # Android: content must be placed under assets/ and loaded via file://
        # The buildozer.spec copies web_ui/ to assets/web_ui/.
        if os.name == "posix" and "ANDROID_ARGUMENT" in os.environ:
            url = "file:///android_asset/web_ui/index.html"
        else:
            # Windows / Linux desktop: use file:// absolute path
            url = "file:///" + index_path.replace("\\", "/")

        log.info("Loading WebView: %s", url)

        # Inject KIVY_MODE flag via a data: URL that sets the flag then redirects
        # Most Kivy WebView wrappers support .load_url() or .url property
        if hasattr(wv, "url"):
            wv.url = url
        elif hasattr(wv, "load_url"):
            wv.load_url(url)
        else:
            log.warning("WebView widget has no recognized load method")

    # ── Status bar update (called from main thread) ─────────────────── #
    def set_status(self, text: str):
        if hasattr(self.ids, "status_bar"):
            self.ids.status_bar.text = text
