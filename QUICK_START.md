# QUICK START — M2.50 DAQ-UI

Guía completa para poner en marcha el sistema desde cero.  
Tiempo estimado: **30–45 minutos** (sin hardware adicional: 10 minutos).

---

## Paso 0 — Requisitos previos

- PC con Linux, Windows 10+ o macOS
- Python 3.8 o superior instalado (`python3 --version`)
- Navegador web moderno (Chrome, Firefox, Edge)

---

## Paso 1 — Adquirir el hardware

| Componente | Modelo exacto | ¿Se puede omitir? |
|---|---|---|
| Microcontrolador | ESP32-S3 DevKitC-1 **v1.1 N16R8** (16 MB Flash, 8 MB PSRAM) | No |
| IMU | Módulo **GY-89** 10DOF (L3GD20 + LSM303D + BMP180) | Con modo simulado |
| Encoders | Cualquier encoder incremental cuadratura (A+B) ×2 | Con modo simulado |
| Switches | Micro-switch activo-bajo ×3 (S1, S2, S3) | Con modo simulado |
| Cable USB | USB-C o Micro-USB según placa | No |

> **Inicio rápido sin hardware:** si solo quieres ver el dashboard funcionando,
> salta al [Paso 3](#paso-3--instalar-micropython-en-el-esp32) y luego activa
> `SIMULATE_SENSORS = True` en el [Paso 5](#paso-5--configurar-configpy).
> No necesitas GY-89, encoders ni switches.

---

## Paso 2 — Instalar Thonny IDE (recomendado)

Thonny simplifica enormemente el trabajo con MicroPython.

1. Descargar desde **https://thonny.org**
2. Instalar (todo por defecto)
3. En Thonny: **Tools → Options → Interpreter**
4. Seleccionar: `MicroPython (ESP32)`
5. Puerto: elegir el COM / `/dev/ttyUSB0` / `/dev/ttyACM0` correspondiente al ESP32

> Alternativa en línea de comandos: `pip install mpremote` y usar `mpremote` (descrito en el [Paso 6](#paso-6--subir-archivos-al-esp32)).

---

## Paso 3 — Instalar MicroPython en el ESP32

### 3.1 Descargar el firmware

Ir a: **https://micropython.org/download/ESP32_GENERIC_S3/**

Descargar el `.bin` más reciente. Para usar la función USB HID (mouse), buscar la
variante con **"USB"** en el nombre, por ejemplo:
```
ESP32_GENERIC_S3-USB-20240602-v1.23.0.bin
```

> El firmware estándar (sin USB) también funciona para el dashboard web; solo
> deshabilita el mouse HID.

### 3.2 Flashear el firmware

**Con esptool (recomendado):**
```bash
pip install esptool

# 1. Borrar flash completamente:
esptool.py --chip esp32s3 --port /dev/ttyACM0 erase_flash

# 2. Escribir el firmware:
esptool.py --chip esp32s3 --port /dev/ttyACM0 \
           write_flash -z 0x0 firmware.bin
```
Reemplazar `/dev/ttyACM0` con el puerto de tu sistema y `firmware.bin` con el
nombre real del archivo descargado.

**En Windows:**
```
esptool.exe --chip esp32s3 --port COM5 erase_flash
esptool.exe --chip esp32s3 --port COM5 write_flash -z 0x0 firmware.bin
```

**Con Thonny (sin línea de comandos):**
1. Conectar el ESP32
2. Tools → Options → Interpreter → Install or update MicroPython
3. Seleccionar puerto y el archivo `.bin`

### 3.3 Verificar instalación

En Thonny, abrir Shell. Presionar Enter. Debe aparecer:
```
MicroPython ESP32-S3
>>>
```

---

## Paso 4 — Clonar / descargar el repositorio

```bash
git clone <URL-del-repo>
cd M2.50_DAQ-UI
```

O descargar el ZIP y descomprimir.

---

## Paso 5 — Configurar `config.py`

Abrir `firmware/config.py` con cualquier editor de texto.

### Parámetros a revisar antes del primer arranque

#### WiFi STA (red existente)

```python
WIFI_SSID      = "NombreDeTuRed"
WIFI_PASSWORD  = "ContraseñaWiFi"
WIFI_TIMEOUT_S = 15        # segundos antes de activar AP fallback
```

Si el ESP32 no logra conectarse a la red en `WIFI_TIMEOUT_S` segundos, crea
automáticamente su propia red WiFi (AP fallback).

#### AP fallback (red creada por el ESP32)

```python
AP_SSID     = "M2-DAQ-SIM"    # nombre de la red que crea el ESP32
AP_PASSWORD = "m2daq1234"      # contraseña de esa red
AP_IP       = "192.168.0.162"  # dirección del ESP32 en modo AP
```

#### Modo sensor

```python
SIMULATE_SENSORS = False   # → True para arrancar sin hardware externo
```

#### Pines GPIO

```python
PIN_SDA     = 8    # I2C SDA → GY-89
PIN_SCL     = 9    # I2C SCL → GY-89
PIN_ENC_H_A = 4    # Encoder horizontal fase A
PIN_ENC_H_B = 5    # Encoder horizontal fase B
PIN_ENC_V_A = 6    # Encoder vertical fase A
PIN_ENC_V_B = 7    # Encoder vertical fase B
PIN_S1      = 15   # Sensor S1 — BLOQUEADO
PIN_S2      = 16   # Sensor S2 — RETENEDOR
PIN_S3      = 17   # Sensor S3 — VÁLVULA
```

Ajustar según tu cableado. **No** usar GPIO 35, 36 ni 37 (reservados para Flash/PSRAM).

#### USB HID mouse

```python
HID_ENC_H_MIN = -1000  # cuentas encoder H que corresponden al borde izquierdo
HID_ENC_H_MAX =  1000  # cuentas encoder H que corresponden al borde derecho
HID_ENC_V_MIN = -500   # cuentas encoder V que corresponden a depresión máxima
HID_ENC_V_MAX =  500   # cuentas encoder V que corresponden a elevación máxima
HID_INVERT_Y  = True   # True: elevar el arma mueve cursor arriba
HID_CLICK_MS  = 60     # duración del clic izquierdo al disparar (ms)
```

#### Frecuencia de transmisión

```python
BROADCAST_HZ = 50   # Hz (no cambiar sin justificación)
PERIOD_MS    = 20   # ms (PERIOD_MS = 1000 / BROADCAST_HZ)
```

---

## Paso 6 — Subir archivos al ESP32

### Estructura de carpetas a crear en el ESP32

```
/ (raíz del ESP32)
├── boot.py
├── config.py
├── main.py
├── sensors.py
├── server.py
├── gy89_driver.py
├── hid_mouse.py
├── lib/
│   └── usb/
│       ├── __init__.py
│       └── device/
│           ├── __init__.py
│           ├── core.py
│           └── hid.py
└── web/
    ├── index.html
    └── js/
        ├── ws_client.js
        ├── svg_bolt.js
        ├── gauges.js
        ├── encoders.js
        ├── charts.js
        └── bt_toggle.js
```

### Opción A — Thonny (sin línea de comandos)

1. En Thonny: `View → Files` para ver el panel de archivos
2. En el panel izquierdo (PC), navegar a la carpeta `firmware/`
3. Para cada archivo `.py` de la raíz:
   - Clic derecho → `Upload to /`
4. Crear la carpeta `lib/usb/device/` en el ESP32:
   - Clic derecho en el panel derecho (ESP32) → `New directory` → `lib`
   - Repetir: `lib/usb`, luego `lib/usb/device`
5. Subir los 4 archivos de `firmware/lib/usb/` a su ubicación correspondiente
6. Crear carpetas `web/` y `web/js/` en el ESP32; subir `index.html` y todos los `.js`

### Opción B — mpremote (terminal)

```bash
pip install mpremote

# Archivos raíz del firmware
mpremote cp firmware/boot.py firmware/config.py firmware/main.py \
            firmware/sensors.py firmware/server.py \
            firmware/gy89_driver.py firmware/hid_mouse.py :

# Librería USB HID
mpremote mkdir :lib
mpremote mkdir :lib/usb
mpremote mkdir :lib/usb/device
mpremote cp firmware/lib/usb/__init__.py           :lib/usb/
mpremote cp firmware/lib/usb/device/__init__.py    :lib/usb/device/
mpremote cp firmware/lib/usb/device/core.py        :lib/usb/device/
mpremote cp firmware/lib/usb/device/hid.py         :lib/usb/device/

# Web
mpremote mkdir :web
mpremote mkdir :web/js
mpremote cp web/index.html :web/
mpremote cp web/js/ws_client.js web/js/svg_bolt.js web/js/gauges.js \
            web/js/encoders.js web/js/charts.js web/js/bt_toggle.js :web/js/

# Reiniciar
mpremote reset
```

---

## Paso 7 — Primer arranque y conexión al dashboard

### 7.1 Encender el ESP32

Conectar por USB (alimentación + datos) o mediante fuente externa de 5 V.  
Si usas Thonny, ver la consola Shell para seguir el arranque:

```
[BOOT] 240 MHz OK
[WIFI] Conectando a "NombreDeTuRed"...
[WIFI] IP: 192.168.1.45
[SERVER] HTTP + WS en puerto 80
```

Si la red no está disponible:
```
[WIFI] Timeout. Modo AP: M2-DAQ-SIM / 192.168.0.162
```

### 7.2 Conectar el navegador

| Situación | Qué hacer | URL del dashboard |
|---|---|---|
| ESP32 conectado a tu WiFi | Abre el navegador | `http://192.168.1.45` (IP del router) |
| ESP32 en modo AP | Conectarse a la red "M2-DAQ-SIM" | `http://192.168.0.162` |
| Solo probar el dashboard | Sin ESP32, abre `web/index.html` directamente | — (simulación local) |

### 7.3 Verificar que funciona

- La barra de estado dice **"Conectado"** (verde)
- Los indicadores IMU muestran movimiento (gira el ESP32 si tienes GY-89)
- Con `SIMULATE_SENSORS = True` todo animará automáticamente

---

## Paso 8 — Visión general del sistema

```
[ESP32-S3] ←─ I2C ─── GY-89 (L3GD20 + LSM303D)
              ←─ GPIO ─ Encoders H/V + S1/S2/S3
              ──WiFi→  Navegador web (50 Hz WS)
              ──USB──→  Mouse HID absoluto (PC/tablet)
```

**Lo que hace el sistema cada 20 ms (50 Hz):**

1. `sensors.read()` → obtiene roll/pitch/yaw + encH/encV + s1/s2/s3
2. `hid_mouse.update()` → convierte encoders → posición absoluta del cursor
3. `_broadcast_loop` → serializa a JSON y envía a todos los navegadores conectados
4. El navegador actualiza gauges SVG, gráficas Plotly, animación del cerrojo

---

## Paso 9 — Calibración

Con el sistema corriendo, la navbar del dashboard tiene botones de calibración:

| Botón | Acción |
|---|---|
| **Reset YAW** | Pone el yaw a 0° en la posición actual |
| **Cal PITCH** | Pone el pitch a 0° en la posición actual |
| **Cal ROLL** | Pone el roll a 0° en la posición actual |

Estos botones envían una petición `POST` a `/api/calibrate`, `/api/calibrate/pitch` y
`/api/calibrate/roll` respectivamente. El ESP32 ajusta el offset del filtro complementario.

---

## Resolución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| Dashboard no carga las gráficas | Sin acceso a internet (Plotly CDN) | Conectar a internet o usar modo offline |
| `[IMU] FALLO` en la consola | GY-89 no conectado o dirección I2C incorrecta | Verificar cableado / `SIMULATE_SENSORS=True` |
| Encoders no cuentan | Pines incorrectos | Revisar `PIN_ENC_H_A/B` y `PIN_ENC_V_A/B` en `config.py` |
| `[HID] fallback` en consola | Firmware sin soporte USB Device | Usar el `.bin` con "USB" en el nombre |
| No hay WiFi ni AP | `boot.py` deshabilita WiFi; `main.py` aún no llegó a `connect_wifi()` | Esperar 3–5 s al arranque |
| Barra de estado dice "Desconectado" | ESP32 apagado o IP cambiada | Actualizar la URL según la IP actual |
