"""
js_bridge.py — Injects sensor JSON from BLE into the Kivy WebView.

Works on Android (using kivy_garden.webview / Android WebView API)
and Windows (using pywebview).

The injected call is:
    window.onBTData(JSON.parse('<json_str>'))

The web_ui/js/ws_client.js handles this via the window.__KIVY_MODE__ branch.
"""

import logging
from kivy.clock import mainthread

log = logging.getLogger(__name__)


class JsBridge:
    """
    Forwards BLE sensor JSON to the WebView's JavaScript context.

    :param webview_widget: The Kivy widget that wraps the platform WebView.
                           Expected to expose evaluate_js(code: str) or
                           run_javascript(code: str).
    """

    def __init__(self, webview_widget):
        self._wv = webview_widget

    # ------------------------------------------------------------------ #
    @mainthread
    def on_data(self, json_str: str):
        """
        Called from BleService._notification_handler (background thread).
        @mainthread decorator marshals execution to the Kivy main thread
        before touching the WebView.
        """
        # Escape single quotes and backslashes to avoid breaking the JS string
        safe = json_str.replace("\\", "\\\\").replace("'", "\\'")
        js = "window.onBTData && window.onBTData(JSON.parse('{}'));".format(safe)
        self._run_js(js)

    # ------------------------------------------------------------------ #
    def _run_js(self, code: str):
        """Dispatch JS execution to whatever API the platform WebView exposes."""
        wv = self._wv
        # kivy_garden.webview (Android)
        if hasattr(wv, "evaluate_js"):
            try:
                wv.evaluate_js(code)
                return
            except Exception as e:
                log.debug("evaluate_js failed: %s", e)

        # pywebview (Windows)
        try:
            import webview  # noqa
            if webview.windows:
                webview.windows[0].evaluate_js(code)
                return
        except (ImportError, Exception) as e:
            log.debug("pywebview evaluate_js failed: %s", e)

        log.warning("JsBridge: no WebView handle available")
