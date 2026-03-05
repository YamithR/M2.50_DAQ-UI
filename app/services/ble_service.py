"""
ble_service.py — BLE Central client using bleak.

Connects to the ESP32's BLE GATT server and streams sensor JSON packets
to the registered callback via GATT notifications on the sensor characteristic.
Runs in a background thread with an asyncio event loop.
"""

import asyncio
import threading
import logging

from bleak import BleakClient, BleakScanner

log = logging.getLogger(__name__)

# UUIDs must match firmware ble_stream.h
SENSOR_CHAR_UUID = "12345678-1234-1234-1234-000000000002"
CTRL_CHAR_UUID   = "12345678-1234-1234-1234-000000000003"

RECONNECT_DELAY_S = 2.0


class BleService:
    """
    Manages a BLE connection to the M2-DAQ ESP32.

    Usage:
        svc = BleService(address="AA:BB:CC:DD:EE:FF", on_data=my_callback)
        svc.start()
        ...
        svc.stop()

    on_data(json_str: str) is called on successful notifications.
    """

    def __init__(self, address: str, on_data):
        self.address  = address
        self.on_data  = on_data       # callable(json_str: str)
        self._loop    = None
        self._thread  = None
        self._running = False

    # ------------------------------------------------------------------ #
    def start(self):
        self._running = True
        self._loop    = asyncio.new_event_loop()
        self._thread  = threading.Thread(
            target=self._run, name="ble-service", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ------------------------------------------------------------------ #
    def send_command(self, cmd: str):
        """Write a text command to the ESP32 control characteristic."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._write_ctrl(cmd), self._loop
            )

    async def _write_ctrl(self, cmd: str):
        # Client reference stored during connection loop
        if hasattr(self, '_client') and self._client and self._client.is_connected:
            try:
                await self._client.write_gatt_char(
                    CTRL_CHAR_UUID, cmd.encode(), response=False
                )
            except Exception as e:
                log.warning("ctrl write failed: %s", e)

    # ------------------------------------------------------------------ #
    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        self._client = None
        while self._running:
            log.info("BLE: connecting to %s", self.address)
            try:
                async with BleakClient(self.address) as client:
                    self._client = client
                    log.info("BLE: connected")
                    await client.start_notify(
                        SENSOR_CHAR_UUID, self._notification_handler
                    )
                    # Keep alive until disconnected or stopped
                    while self._running and client.is_connected:
                        await asyncio.sleep(0.5)
            except Exception as e:
                log.warning("BLE: connection error — %s", e)
            finally:
                self._client = None

            if self._running:
                log.info("BLE: reconnecting in %.1fs", RECONNECT_DELAY_S)
                await asyncio.sleep(RECONNECT_DELAY_S)

    def _notification_handler(self, sender, data: bytearray):
        try:
            json_str = data.decode("utf-8")
            self.on_data(json_str)
        except UnicodeDecodeError:
            log.warning("BLE: non-UTF8 notification ignored")


# ─────────────────────────────────────────────────────────────────────── #
# Scan helper (called from bt_scan_screen.py)
# ─────────────────────────────────────────────────────────────────────── #
async def scan_for_m2_devices(timeout: float = 5.0) -> list:
    """
    Scan for BLE advertisements and return devices whose name contains 'M2'.
    Returns a list of BLEDevice objects.
    """
    devices = await BleakScanner.discover(timeout=timeout)
    return [d for d in devices if d.name and "M2" in d.name.upper()]
