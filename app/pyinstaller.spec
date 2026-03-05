# pyinstaller.spec — Windows EXE build configuration
#
# Build command (from app/ directory, Windows):
#   pyinstaller pyinstaller.spec
#
# Output:  app/dist/M2_DAQ_UI/M2_DAQ_UI.exe  (folder distribution)

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect Kivy data files (fonts, shaders, images)
kivy_datas = collect_data_files("kivy")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Kivy framework data
        *kivy_datas,
        # Application assets
        ("assets/web_ui",   "assets/web_ui"),
        ("kv",              "kv"),
    ],
    hiddenimports=[
        "bleak",
        "bleak.backends.winrt.client",
        "bleak.backends.winrt.scanner",
        "kivy",
        "kivy.core.window",
        "kivy.core.window.window_sdl2",
        "kivy.core.text.text_sdl2",
        "kivy.core.audio.audio_sdl2",
        "kivy.core.image",
        "kivy.uix.recycleview",
        "kivy.uix.recycleboxlayout",
        "screens.bt_scan_screen",
        "screens.dashboard_screen",
        "services.ble_service",
        "services.js_bridge",
        "widgets.ble_device_item",
    ],
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="M2_DAQ_UI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,      # Set True for debug output window
    icon=None,          # Optional: path to .ico file
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="M2_DAQ_UI",
)
