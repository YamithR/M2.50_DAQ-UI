# M2.50 DAQ-UI — Instrucciones de Ejecución

Guía paso a paso para configurar, compilar y ejecutar cada componente del sistema.

---

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Firmware ESP32-S3 (producción)](#2-firmware-esp32-s3-producción)
3. [Simulador MicroPython (prueba)](#3-simulador-micropython-prueba)
4. [Web UI en navegador](#4-web-ui-en-navegador)
5. [App Kivy — Android APK](#5-app-kivy--android-apk)
6. [App Kivy — Windows EXE](#6-app-kivy--windows-exe)
7. [Sincronizar web_ui con la app](#7-sincronizar-web_ui-con-la-app)
8. [Flujo de desarrollo](#8-flujo-de-desarrollo)
9. [Resolución de problemas](#9-resolución-de-problemas)

---

## 1. Requisitos previos

### Herramientas comunes

| Herramienta | Versión mínima | Instalación |
|---|---|---|
| Git | cualquiera | `apt install git` / brew / winget |
| Python | 3.10+ | python.org |
| pip | 23+ | `pip install --upgrade pip` |

### Para firmware ESP32-S3

- **ESP-IDF v5.2+** instalado y configurado
  ```bash
  # Instalar ESP-IDF (Linux/macOS)
  mkdir -p ~/esp && cd ~/esp
  git clone --recursive https://github.com/espressif/esp-idf.git
  cd esp-idf && git checkout v5.2
  ./install.sh esp32s3
  ```
- Exportar variables de entorno **en cada sesión de terminal**:
  ```bash
  . ~/esp/esp-idf/export.sh
  ```
- **ESP32-S3** DevKitC-1 conectado por USB-C

### Para simulador MicroPython

- **MicroPython v1.22+** para ESP32 genérico:
  - Descargar desde https://micropython.org/download/ESP32_GENERIC/
  - La build estándar incluye `hashlib`, `binascii`, `asyncio`
- **mpremote** para despliegue:
  ```bash
  pip install mpremote
  ```

### Para app Kivy

- Python 3.10+ con pip
- Dependencias de la app:
  ```bash
  pip install -r app/requirements.txt
  ```
- Android: Linux o WSL (recomendado Ubuntu 22.04), Java JDK 17
- Windows EXE: Windows 10/11 con Python 3.10+

---

## 2. Firmware ESP32-S3 (producción)

Este firmware es la implementación completa: WiFi, BLE GATT, USB HID mouse, 50 Hz.

### 2.1 Configuración WiFi

El ESP32-S3 levanta su propio AP en el primer arranque con SSID `M2-DAQ_AP`.
Para conectarlo a una red existente, usar la API REST desde la web:
```
POST http://m2daq.local/api/config
{"ssid":"MiRed","password":"contraseña","hostname":"m2daq","port":80}
```
El dispositivo se reiniciará en modo STA. Si la conexión falla, regresa al AP.

### 2.2 Build y flash completo

```bash
# Desde la raíz del proyecto
. ~/esp/esp-idf/export.sh

# Build + flash de firmware + SPIFFS (web_ui incluido)
./tools/flash_all.sh /dev/ttyUSB0

# Monitor serie
idf.py -p /dev/ttyUSB0 monitor
```

El script `flash_all.sh`:
1. Sincroniza `web_ui/` → `app/assets/web_ui/`
2. Compila el firmware completo (`idf.py build`)
3. Flashea firmware + imagen SPIFFS a 460800 baud

### 2.3 Solo refrescar web UI (sin recompilar firmware)

```bash
cd firmware
idf.py -p /dev/ttyUSB0 spiffs-flash
```

### 2.4 Acceso a la interfaz

Una vez flasheado y conectado a red:

| URL | Descripción |
|---|---|
| `http://m2daq.local/` | Interfaz web vía mDNS |
| `http://<ip>/` | Interfaz web vía IP directa |
| `ws://m2daq.local/ws` | WebSocket de datos (50 Hz) |

En modo AP el ESP32 usa la IP `192.168.4.1`.

### 2.5 Configurar sensibilidad HID (ratón USB)

```
POST http://m2daq.local/api/config
{"hid_sens_x": 2.0, "hid_sens_y": 2.0}
```

- `hid_sens_x/y`: cuentas de encoder por píxel. Valores mayores = movimientos más lentos.
- Sensibilidad por defecto: 1.0 (1 cuenta = 1 píxel)

### 2.6 Activar modo Bluetooth

Desde la web UI, pulsar el botón **BLUETOOTH** o usar la API:
```
POST http://m2daq.local/api/config/bluetooth
{"enabled": true}
```

Una vez activado, el dispositivo BLE se publicita como `m2daq-BLE`.
Para volver a WiFi, conectarse vía BLE y enviar el comando `bt:off`.

---

## 3. Simulador MicroPython (prueba)

Permite probar el sistema completo con cualquier ESP32 convencional (no S3)
sin necesidad del hardware de producción. Sin BLE ni USB HID.

### 3.1 Instalar MicroPython en el ESP32

```bash
# Instalar esptool
pip install esptool

# Borrar flash
esptool.py --port /dev/ttyUSB0 erase_flash

# Flashear MicroPython (ajustar nombre del archivo descargado)
esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash \
    -z 0x1000 ESP32_GENERIC-20240602-v1.23.0.bin
```

> Descargar el binario desde: https://micropython.org/download/ESP32_GENERIC/

### 3.2 Configurar credenciales WiFi

Editar `firmware_mp/config.py`:

```python
WIFI_SSID      = "NombreDeTuRed"
WIFI_PASSWORD  = "TuContraseña"
SIMULATE_SENSORS = True    # True = datos simulados, False = hardware real
```

### 3.3 Desplegar al ESP32

```bash
# Desde la raíz del proyecto
./firmware_mp/deploy.sh /dev/ttyUSB0
```

El script sube todos los archivos Python y el directorio `web/web_ui/`.
Al finalizar, reiniciar el dispositivo:

```bash
mpremote connect /dev/ttyUSB0 reset
```

### 3.4 Ver IP asignada (monitor serie)

```bash
mpremote connect /dev/ttyUSB0 repl
```

Salida esperada:
```
Conectando WiFi a 'MiRed' ...
WiFi OK: IP=192.168.1.42
Abrir en navegador: http://192.168.1.42/
Sensores: modo SIMULADO
Servidor HTTP+WS en puerto 80
WebSocket: ws://192.168.1.42/ws
```

Si WiFi falla, el ESP32 levanta el AP `M2-DAQ-SIM` (contraseña: `m2daq1234`) con IP `192.168.4.1`.

### 3.5 Usar hardware real en el simulador

Conectar:
- MPU-6050: SDA→GPIO8, SCL→GPIO9
- Encoder H: faseA→GPIO1, faseB→GPIO2
- Encoder V: faseA→GPIO3, faseB→GPIO4
- S1→GPIO5, S2→GPIO6, S3→GPIO7 (activo-bajo, pull-up interno activo)

Cambiar en `config.py`:
```python
SIMULATE_SENSORS = False
```

Y re-desplegar con `deploy.sh`.

---

## 4. Web UI en navegador

La interfaz web es idéntica tanto para el firmware ESP32-S3 como para el simulador MicroPython.

### Acceso

| Caso | URL |
|---|---|
| ESP32-S3 en red local | `http://m2daq.local/` |
| ESP32-S3 en modo AP | `http://192.168.4.1/` |
| Simulador MicroPython | `http://<ip-mostrada-en-serial>/` |

**Navegadores compatibles**: Chrome 90+, Firefox 88+, Edge 90+, Safari 14+.

### Controles de la interfaz

| Elemento | Función |
|---|---|
| Animación SVG (cerrojo) | Muestra posición del cerrojo según S1/S2/S3 |
| LEDs S1/S2/S3 | Indicadores de estado en tiempo real |
| Rosa de los vientos | Orientación yaw del arma |
| Pitch / Roll / Yaw | Valores numéricos del IMU en grados |
| Enc H / Enc V | Cuentas acumuladas de los encoders |
| Gráficas (3 paneles) | Historia 6s: estados, IMU, encoders |
| Botón BLUETOOTH | Activa/desactiva BLE advertising (solo ESP32-S3) |
| Botón CALIBRAR YAW | Reinicia el integrador de yaw a 0° |
| Indicador ⬤ | Estado de la conexión WebSocket |

### Indicador de conexión

- `⬤ CONECTADO` (verde) — datos fluyendo a 50 Hz
- `⬌ RECONECTANDO` — intento de reconexión (backoff exponencial 1s→30s)
- `⬌ DESCONECTADO` — sin conexión

---

## 5. App Kivy — Android APK

### 5.1 Preparar entorno (Linux / WSL Ubuntu 22.04)

```bash
# Dependencias del sistema
sudo apt update && sudo apt install -y \
    python3-pip python3-venv git zip unzip \
    openjdk-17-jdk build-essential libssl-dev \
    libffi-dev autoconf libtool

# Clonar e instalar buildozer
pip install buildozer cython

# Sincronizar web_ui antes de compilar
./tools/sync_web_ui.sh
```

### 5.2 Compilar APK (debug)

```bash
cd app
buildozer android debug
```

El primer build descarga el NDK/SDK de Android automáticamente (~1.5 GB).
Las compilaciones posteriores son significativamente más rápidas.

El APK se genera en:
```
app/bin/m2daqui-0.1.0-arm64-v8a-debug.apk
```

### 5.3 Instalar y ejecutar en dispositivo Android

```bash
# Compilar + desplegar + ejecutar en dispositivo conectado por USB
buildozer android debug deploy run

# Solo ver logs
buildozer android logcat
```

**Permisos requeridos** (el sistema los solicitará al primer uso):
- Bluetooth (SCAN + CONNECT)
- Ubicación (requerida por Android para BLE scan)

### 5.4 Uso de la app

1. Asegurarse de que el ESP32-S3 tiene BLE activo (`POST /api/config/bluetooth`)
2. Abrir la app → pantalla **BLUETOOTH SCAN**
3. Pulsar **ESCANEAR** → aparecerá el dispositivo `m2daq-BLE`
4. Pulsar **CONECTAR** → carga el dashboard en WebView
5. Los datos llegan vía BLE y se muestran en la misma interfaz que la web

---

## 6. App Kivy — Windows EXE

### 6.1 Preparar entorno (Windows 10/11)

```powershell
# Instalar dependencias
pip install -r app/requirements.txt
pip install pyinstaller pyinstaller-hooks-contrib

# Sincronizar web_ui
bash tools/sync_web_ui.sh   # (en Git Bash / WSL)
# o en PowerShell:
# robocopy web_ui app\assets\web_ui /MIR
```

### 6.2 Compilar EXE

```powershell
cd app
pyinstaller pyinstaller.spec
```

El ejecutable se genera en:
```
app\dist\M2_DAQ_UI\M2_DAQ_UI.exe
```

### 6.3 Distribuir

Comprimir y distribuir la carpeta completa `dist\M2_DAQ_UI\`.
No requiere Python instalado en el sistema destino.

### 6.4 Modo demo (sin hardware)

Si se ejecuta sin ESP32 disponible, la app arranca en modo demo:
- El WebView carga la interfaz normalmente
- No hay datos BLE — los charts y gauges permanecen estáticos
- Útil para verificar la instalación

---

## 7. Sincronizar web_ui con la app

El directorio `web_ui/` es la fuente canónica de la interfaz web.
La app Kivy necesita una copia en `app/assets/web_ui/`.

```bash
# Sincronización manual
./tools/sync_web_ui.sh

# La sincronización también ocurre automáticamente al ejecutar:
./tools/flash_all.sh
```

> Siempre sincronizar antes de compilar el APK o EXE si se modificó `web_ui/`.

---

## 8. Flujo de desarrollo

### Modificar la interfaz web

```bash
# Editar archivos en web_ui/
# Refrescar solo la partición SPIFFS (sin recompilar firmware)
cd firmware
idf.py -p /dev/ttyUSB0 spiffs-flash

# O probar con el simulador MicroPython (más rápido):
./firmware_mp/deploy.sh /dev/ttyUSB0
```

### Monitor serie

```bash
# ESP32-S3 (ESP-IDF)
idf.py -p /dev/ttyUSB0 monitor

# Simulador MicroPython
mpremote connect /dev/ttyUSB0 repl

# Salir del monitor: Ctrl+]  (IDF) / Ctrl+X (mpremote)
```

### Solo refrescar archivos Python en el simulador

```bash
# Un archivo específico
mpremote connect /dev/ttyUSB0 cp firmware_mp/sensors.py :sensors.py

# Reiniciar
mpremote connect /dev/ttyUSB0 reset
```

### Listar archivos en el ESP32 (MicroPython)

```bash
mpremote connect /dev/ttyUSB0 ls :
mpremote connect /dev/ttyUSB0 ls :web/js
```

### Verificar espacio en flash (MicroPython)

```python
# En el REPL:
import os; s = os.statvfs('/'); print("Libre:", s[0]*s[3]//1024, "KB")
```

---

## 9. Resolución de problemas

### El ESP32-S3 no aparece en `/dev/ttyUSB*`

- En ESP32-S3 DevKitC-1, el puerto USB OTG está en el conector UART (no OTG)
- Verificar con `lsusb` que el dispositivo aparece
- Añadir usuario al grupo dialout: `sudo usermod -a -G dialout $USER` (requiere cerrar sesión)

### `idf.py: command not found`

```bash
. ~/esp/esp-idf/export.sh
```

### `hashlib` no disponible en MicroPython

El servidor WebSocket usa `hashlib.sha1`. Verificar con:
```python
import hashlib; hashlib.sha1(b'test').digest()
```
Si falla, usar una build MicroPython que incluya `hashlib` (build estándar v1.22+ para ESP32).

### `asyncio.wait_for` no disponible

Verificar la versión de MicroPython:
```python
import sys; print(sys.version)
```
Requiere MicroPython v1.22.0 o superior.

### La web UI no carga en el simulador (404)

Verificar que los archivos están en el ESP32:
```bash
mpremote connect /dev/ttyUSB0 ls :web
```
Si no hay archivos, re-ejecutar `./firmware_mp/deploy.sh`.

### Los charts no se actualizan (WebSocket desconectado)

- Verificar que el indicador `⬤` muestra CONECTADO
- Confirmar que el navegador está en la misma red que el ESP32
- Deshabilitar VPN si está activa
- Probar en Chrome (mejor compatibilidad WebSocket)

### buildozer falla en primer build

```bash
# Limpiar y reintentar
buildozer android clean
buildozer android debug
```

### El EXE de Windows no encuentra `web_ui`

- Ejecutar el EXE desde su propia carpeta `dist\M2_DAQ_UI\`
- No mover solo el `.exe` sin el resto de la carpeta

### Bluetooth no encontrado en la app

- Verificar que el ESP32-S3 tiene BLE activo: `POST /api/config/bluetooth {"enabled":true}`
- El dispositivo se publicita como `m2daq-BLE` (o `<hostname>-BLE` si se cambió el hostname)
- En Android, aceptar el permiso de Ubicación cuando se solicite (requerido por el SO para BLE scan)
