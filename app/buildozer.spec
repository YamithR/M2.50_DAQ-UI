[app]
title = M2 DAQ UI
package.name = m2daqui
package.domain = org.m250daq
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,html,css,js,json,min.js
source.include_patterns = assets/web_ui/**,kv/**
source.exclude_dirs = .venv,__pycache__,dist,build,.git

version = 0.1.0

requirements = python3,kivy==2.3.0,bleak,android,pyjnius

# Garden: webview for Android WebView widget
garden_requirements = webview

orientation = portrait,landscape

# Android
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a
android.allow_backup = True

# Place web_ui assets inside Android assets/ directory so they are accessible
# via file:///android_asset/web_ui/index.html
android.add_src = assets/web_ui:assets/web_ui

[buildozer]
log_level = 2
warn_on_root = 1
