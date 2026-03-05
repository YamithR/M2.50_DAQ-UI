"""
ble_device_item.py — RecycleView row widget for BLE scan results.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty


class BleDeviceItem(BoxLayout):
    """Row in the BLE device scan list.

    Bound to:
        device_name : str  — Advertised BLE device name
        device_rssi : str  — Signal strength (e.g. "-72 dBm")
        address     : str  — BLE MAC address (used to connect)
    """
    device_name = StringProperty("")
    device_rssi = StringProperty("")
    address     = StringProperty("")
