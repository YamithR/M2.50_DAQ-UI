# M2.50 DAQ-UI

> Sistema de adquisición de datos para el estudio del simulador de combate con réplica
> neumática del arma **Browning M2 .50 Cal.**
> Firmware MicroPython en **ESP32-S3** · Dashboard web a **50 Hz** vía WebSocket.

---

## Tabla de contenidos

1. [Descripción del sistema](#1-descripción-del-sistema)
2. [Hardware requerido](#2-hardware-requerido)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Arquitectura de software](#4-arquitectura-de-software)
5. [Firmware — detalle de módulos](#5-firmware--detalle-de-módulos)
6. [Web UI — detalle de módulos](#6-web-ui--detalle-de-módulos)
7. [Protocolo WebSocket](#7-protocolo-websocket)
8. [REST API](#8-rest-api)
9. [Configuración (`config.py`)](#9-configuración-configpy)
10. [Mapa de pines GPIO](#10-mapa-de-pines-gpio)
11. [Driver IMU GY-89](#11-driver-imu-gy-89)
12. [USB HID — mouse absoluto](#12-usb-hid--mouse-absoluto)
13. [Modo simulación](#13-modo-simulación)
14. [Despliegue al ESP32](#14-despliegue-al-esp32)
15. [Flujo de arranque completo](#15-flujo-de-arranque-completo)
16. [Dependencias externas](#16-dependencias-externas)

---

## 1. Descripción del sistema

El sistema captura a **50 Hz** los siguientes canales del simulador:

| Canal | Tipo | Descripción |
|---|---|---|
| **S1 — BLOQUEADO** | Digital activo‑bajo | Cerrojo en posición de bloqueo |
| **S2 — RETENEDOR** | Digital activo‑bajo | Cerrojo amartillado y retenido |
| **S3 — VÁLVULA** | Digital activo‑bajo | Válvula de gas abierta (= disparo) |
| **ROLL** | IMU analógico | Eje longitudinal (°) |
| **PITCH** | IMU analógico | Eje transversal (°) |
| **YAW** | IMU integrado | Rumbo acumulado 0–360° |
| **ENC_H** | Encoder cuadratura | Posición horizontal (cuentas) |
| **ENC_V** | Encoder cuadratura | Posición vertical (cuentas) |

Los datos se transmiten por **WiFi WebSocket** a un navegador web que muestra:

- Animación SVG del mecanismo de cerrojo del M2.50
- Indicadores IMU estilo aviación (roll, pitch, yaw) en SVG puro
- Contadores de encoders con visualización de brújula
- Cinco paneles de gráficas en tiempo real con Plotly.js (cadencia, estado S3,
  sensores digitales, IMU Roll/Pitch/Yaw, encoders H/V)
- Mouse USB HID absoluto: encoders → puntero de pantalla, S3 → clic izquierdo

---

## 2. Hardware requerido

| Componente | Especificación |
|---|---|
| Microcontrolador | **ESP32-S3 DevKitC-1 v1.1, N16R8** (16 MB Flash, 8 MB PSRAM) |
| IMU | **GY-89 10DOF** — L3GD20 (gyr., I2C `0x6B`) · LSM303D (accel.+mag., I2C `0x1E`) · BMP180 (barón., I2C `0x77`) |
| Encoder horizontal | Encoder incremental cuadratura (fases A+B) |
| Encoder vertical | Encoder incremental cuadratura (fases A+B) |
| S1 / S2 / S3 | Switches o sensores activo‑bajo (pull‑up interno) |
| Cable USB | Para flashing y acceso REPL |

> **Modo simulado:** `SIMULATE_SENSORS = True` en `config.py` no requiere hardware externo.

---

## 3. Estructura del repositorio

```
M2.50_DAQ-UI/
├── firmware/
│   ├── boot.py            # CPU 240 MHz, silencia osdebug, llama main
│   ├── config.py          # ÚNICA fuente de verdad de todos los parámetros
│   ├── main.py            # WiFi STA → AP fallback, lanza asyncio + USB HID
│   ├── sensors.py         # Abstracción dual: simulado / hardware real
│   ├── server.py          # Servidor HTTP + WebSocket RFC 6455 + REST API
│   ├── gy89_driver.py     # Driver I2C nativo GY-89 (L3GD20 + LSM303D + BMP180)
│   ├── hid_mouse.py       # USB HID mouse absoluto (encoder → puntero, S3 → clic)
│   └── lib/               # Librerías Python copiadas al ESP32
│       └── usb/
│           ├── __init__.py
│           └── device/
│               ├── __init__.py
│               ├── core.py        # micropython-lib usb-device
│               └── hid.py         # micropython-lib usb-device-hid
│
├── web/
│   ├── index.html         # Dashboard principal (HTML5, sin framework)
│   └── js/
│       ├── ws_client.js   # Cliente WS + simulación local + reconexión exponencial
│       ├── svg_bolt.js    # Animación SVG del cerrojo M2.50
│       ├── gauges.js      # Indicadores IMU SVG puros (roll, pitch, yaw)
│       ├── encoders.js    # Contadores ENC_H / ENC_V
│       ├── charts.js      # Gráficas Plotly.js (5 paneles rolling)
│       └── bt_toggle.js   # Botones de calibración yaw/pitch/roll
│
├── QUICK_START.md         # Guía de inicio rápido paso a paso
└── README.md              # Este archivo
```

---

## 4. Arquitectura de software

```
┌─────────────────────────────────────────────────────────────┐
│                    ESP32-S3 (MicroPython)                   │
│                                                             │
│  boot.py → 240 MHz, silencia log, import main              │
│                │                                            │
│  main.py       │                                            │
│    ├─ init_hid()       ← hid_mouse.py (USB HID absoluto)   │
│    ├─ connect_wifi()   STA → AP fallback (192.168.0.162)   │
│    └─ asyncio.run(main())                                   │
│          ├─ start_server()                                  │
│          │     ├─ sensors.init()                            │
│          │     │     └─ GY-89 (L3GD20+LSM303D) + encoders  │
│          │     ├─ asyncio.start_server()  → HTTP + WS       │
│          │     └─ _broadcast_loop()  50 Hz                  │
│          │           ├─ sensors.read()                      │
│          │           ├─ hid_mouse.update()  ← siempre       │
│          │           └─ WS JSON frame → _ws_writers[]       │
│          └─ (cada cliente WS: _ws_client_task)              │
└─────────────────────────────────────────────────────────────┘
                  │ WiFi 802.11 │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                  Navegador (cualquier dispositivo)          │
│                                                             │
│  index.html                                                 │
│    ├─ ws_client.js  →  ws://<IP>/ws  (50 Hz)               │
│    │    └─ dispatch(d) → todos los módulos                  │
│    ├─ svg_bolt.js   →  animación cerrojo M2.50              │
│    ├─ gauges.js     →  roll / pitch / yaw SVG               │
│    ├─ encoders.js   →  contadores ENC_H / ENC_V             │
│    ├─ charts.js     →  5 gráficas Plotly.js rolling         │
│    └─ bt_toggle.js  →  POST /api/calibrate/*                │
└─────────────────────────────────────────────────────────────┘
```

### Concurrencia

El servidor usa **asyncio** de MicroPython con dos coroutines principales:

- `asyncio.start_server(_handle_client)` — acepta conexiones TCP.
- `_broadcast_loop()` — corre a `PERIOD_MS` (20 ms), lee sensores,
  actualiza USB HID y hace `writer.write()` a todos los WebSocket activos.

Cada cliente WebSocket tiene su propia `_ws_client_task` (lee Close/Ping).

---

## 5. Firmware — detalle de módulos

### `boot.py`
- `machine.freq(240_000_000)` — CPU al máximo
- `esp.osdebug(None)` — silencia log interno
- Desactiva ambas interfaces WiFi (main.py las gestionará)

### `config.py`

Fuente única de verdad. Ver [sección 9](#9-configuración-configpy) para el detalle completo.

### `main.py`

```
init_hid()        → intenta activar USB HID antes de que WiFi tome el bus USB
connect_wifi()    → STA connect → espera WIFI_TIMEOUT_S → AP fallback 192.168.0.162
asyncio.run()     → lanza start_server() (no retorna)
```

### `sensors.py`

| Función | Descripción |
|---|---|
| `init()` | Inicializa hardware o parámetros de simulación |
| `read() → dict` | Devuelve el paquete canónico de datos |
| `reset_yaw()` | Reinicia integrador yaw a 0° |
| `reset_pitch()` | Calibra pitch (cero = posición actual) |
| `reset_roll()` | Calibra roll (cero = posición actual) |
| `reset_encoders()` | Pone a cero ambos contadores |

**Modo hardware:** GY-89 vía `gy89_driver.GY89()`, encoders con ISR, S1/S2/S3
con Pull-up. El fallo de IMU es **no fatal** (encoders y digitales siguen operando).

**Modo simulado:** señales sintéticas idénticas a las del JS (roll/pitch/yaw con
oscilaciones, random-walk de encoders, máquina de estados de disparo).

### `server.py`

Servidor HTTP sin frameworks sobre `asyncio.start_server()`.

| Función | Descripción |
|---|---|
| `_ws_accept_key()` | `BASE64(SHA1(key + WS_MAGIC))` RFC 6455 |
| `_ws_encode_frame()` | Frame texto FIN=1, opcode 0x01, sin masking |
| `_ws_read_frame()` | Lee y desenmascara frames de cliente |
| `_broadcast_loop()` | 50 Hz: lee sensores → JSON → WS broadcast + HID update |
| `_handle_client()` | Router: `/ws` → WS · `/api/*` → REST · `/*` → estático |

**JSON broadcast** (construido con `str.format()` por velocidad):
```json
{"s1":false,"s2":true,"s3":false,"gas_valve":false,
 "roll":-3.12,"pitch":1.45,"yaw":183.0,"yaw_signed":3.0,
 "enc_h":42,"enc_v":-7,"ts":12345}
```

### `gy89_driver.py`

Driver I2C nativo para el módulo GY-89 10DOF.

| Chip | Dirección | Parámetros |
|---|---|---|
| L3GD20 (gyr.) | `0x6B` | FS ±500 dps · 17.5 mdps/LSB · 95 Hz |
| LSM303D (accel.) | `0x1E` | FS ±2g · 0.061 mg/LSB |
| LSM303D (mag.) | `0x1E` | FS ±2 Gauss |

**Filtro complementario:**
```
pitch(t) = 0.98 × (pitch(t-1) + gy × DT) + 0.02 × atan2(ay, az)
roll(t)  = 0.98 × (roll(t-1)  + gx × DT) + 0.02 × atan2(-ax, az)
yaw(t)   = blend(yaw_gyro, yaw_mag, α=0.05)  ← tilt-compensated
```

### `hid_mouse.py`

Mouse USB HID absoluto vía USB OTG del ESP32-S3.

- **X/Y:** `[0, 32767]` — `ENC=0` → centro, sin deriva acumulada
- **Clic:** flanco ascendente de S3 → botón izquierdo durante `HID_CLICK_MS`
- **Descriptor HID:** 3 botones + X/Y absolutos 16-bit unsigned
- **Init en cascada:** prueba `usb.device.hid` → `mip install` → fallback con instrucciones

---

## 6. Web UI — detalle de módulos

### `index.html`

Dashboard responsive (max-width 980 px, breakpoints 768/480 px). Paleta militar:

```css
--gunmetal:   #2a2d30   --army-green: #4b5320
--danger:     #d32f2f   --safe:       #388e3c   --amber: #ffa000
```

Navbar sticky con 7 botones de toggle: **IMU · Encoders · Cadencia · S3 Estado ·
S1/S2/S3 · IMU R/P/Y · ENC H/V**.

Las gráficas usan **Plotly.js 2.35.2** cargado desde CDN — no es necesario ningún
archivo local de gráficas.

### `gauges.js`

Tres instrumentos SVG puros (sin dependencias):

| Instrumento | Tamaño | Descripción |
|---|---|---|
| Roll indicator | 220×110 px | Horizonte artificial rota ± según roll |
| Pitch indicator | 120×190 px | Barra desliza verticalmente ±30° |
| Yaw slider | 220×60 px | Marcador ámbar desliza −180°…+180° |

**Mosaico IMU:** Roll (arriba) + Yaw (abajo) en columna izquierda; Pitch ocupa
la altura completa en columna derecha.

### `charts.js`

Cinco gráficas Plotly.js con buffer de 5 frames (~10 Hz de actualización visual):

| Panel | Descripción | Ventana default |
|---|---|---|
| Cadencia de fuego | disp/min detectados por flanco S3↑ | 60 s |
| Estado S3 / Válvula | señal digital 0/1 | 60 s |
| Sensores S1/S2/S3 | tres trazas digitales | 60 s |
| IMU Roll/Pitch/Yaw | orientación en grados | 60 s |
| Encoders ENC_H/V | posición en cuentas | 60 s |

### `ws_client.js`

- Simulación local arranca **inmediatamente** (modo offline) — misma señal que el firmware.
- Al recibir el primer paquete real, la simulación se detiene.
- Reconexión con backoff exponencial: 1 s → 2 s → 4 s → … → 30 s máx.
- Loop único `requestAnimationFrame` maneja toda la UI sin `setInterval`.

---

## 7. Protocolo WebSocket

- **Endpoint:** `ws://<IP>/ws`
- **Dirección:** servidor → cliente (broadcast unidireccional); cliente → servidor solo Close/Ping
- **Frecuencia:** 50 Hz (20 ms/frame)
- **Frame:** texto UTF-8, opcode `0x01`, FIN=1, sin masking

| Campo | Tipo | Descripción |
|---|---|---|
| `s1`, `s2`, `s3` | bool | Estado sensores digitales |
| `gas_valve` | bool | Alias de `s3` |
| `roll` | float ±90° | Eje longitudinal con offset de calibración |
| `pitch` | float ±90° | Eje transversal con offset de calibración |
| `yaw` | float 0–360° | Rumbo acumulado |
| `yaw_signed` | float −180…+180° | `((yaw+180)%360)−180` |
| `enc_h` | int | Cuentas encoder horizontal |
| `enc_v` | int | Cuentas encoder vertical |
| `ts` | int ms | `time.ticks_ms()` desde boot |

---

## 8. REST API

| Método | Endpoint | Acción |
|---|---|---|
| `GET` | `/api/config` | JSON con SSID, hostname, port, simulate |
| `POST` | `/api/calibrate` | `sensors.reset_yaw()` |
| `POST` | `/api/calibrate/pitch` | `sensors.reset_pitch()` |
| `POST` | `/api/calibrate/roll` | `sensors.reset_roll()` |

Todas las respuestas POST exitosas devuelven `{"ok":true}`.

---

## 9. Configuración (`config.py`)

```python
# WiFi STA
WIFI_SSID       = "Oniris_G5-ID"
WIFI_PASSWORD   = "Oniri$2025"
WIFI_TIMEOUT_S  = 15              # s antes de AP fallback

# AP fallback
AP_SSID         = "M2-DAQ-SIM"
AP_PASSWORD     = "m2daq1234"
AP_IP           = "192.168.0.162"

# Servidor
HOSTNAME        = "m2-daq-sim"
PORT            = 80
WEB_ROOT        = "/web"

# Modo sensor: True = sin hardware · False = con GY-89 y encoders
SIMULATE_SENSORS = False

# Temporización
BROADCAST_HZ    = 50             # Hz
PERIOD_MS       = 20             # ms (pre-calculado)

# Pines GPIO — ESP32-S3 DevKitC-1 v1.1 N16R8
# (GPIO 35/36/37 reservados para Flash/PSRAM — NO USAR)
PIN_SDA         = 8              # I2C SDA → GY-89
PIN_SCL         = 9              # I2C SCL → GY-89
PIN_ENC_H_A     = 4              # Encoder H fase A (IRQ)
PIN_ENC_H_B     = 5              # Encoder H fase B (ISR)
PIN_ENC_V_A     = 6              # Encoder V fase A (IRQ)
PIN_ENC_V_B     = 7              # Encoder V fase B (ISR)
PIN_S1          = 15             # S1_BLOQUEADO
PIN_S2          = 16             # S2_RETENEDOR
PIN_S3          = 17             # S3_VÁLVULA

# IMU GY-89 10DOF
IMU_GYR_ADDR    = 0x6B           # L3GD20
IMU_ACC_ADDR    = 0x1E           # LSM303D
IMU_FREQ        = 400_000        # Hz bus I2C

# USB HID mouse absoluto
HID_ENC_H_MIN   = -1000   # cuentas extremo izquierdo
HID_ENC_H_MAX   =  1000   # cuentas extremo derecho
HID_ENC_V_MIN   = -500    # cuentas depresión
HID_ENC_V_MAX   =  500    # cuentas elevación
HID_INVERT_Y    = True    # elevación → cursor arriba
HID_CLICK_MS    = 60      # duración clic en ms

# Simulación (deben coincidir con ws_client.js)
SIM_ROLL_AMP      = 10.0         # grados ±
SIM_PITCH_AMP     =  8.0         # grados ±
SIM_YAW_DRIFT_HZ  =  0.04        # Hz
SIM_FIRE_CYCLE_MS =  6000        # ms
```

---

## 10. Mapa de pines GPIO

**Placa:** ESP32-S3 DevKitC-1 v1.1 N16R8
[Documentación oficial Espressif](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)

> GPIO 35/36/37 reservados para Flash/PSRAM — **no usar**.

| GPIO | Señal | Descripción |
|---|---|---|
| 8 | PIN_SDA | I2C SDA → GY-89 |
| 9 | PIN_SCL | I2C SCL → GY-89 |
| 4 | PIN_ENC_H_A | Encoder H fase A (IRQ) |
| 5 | PIN_ENC_H_B | Encoder H fase B (ISR dirección) |
| 6 | PIN_ENC_V_A | Encoder V fase A (IRQ) |
| 7 | PIN_ENC_V_B | Encoder V fase B (ISR dirección) |
| 15 | PIN_S1 | S1_BLOQUEADO (activo‑bajo, pull‑up) |
| 16 | PIN_S2 | S2_RETENEDOR (activo‑bajo, pull‑up) |
| 17 | PIN_S3 | S3_VÁLVULA (activo‑bajo, pull‑up) |

Bus I2C compartido: 400 kHz · `I2C(0, sda=8, scl=9, freq=400_000)`.

---

## 11. Driver IMU GY-89

`gy89_driver.py` implementa los tres chips del módulo GY-89 sin dependencias externas.

**L3GD20 (giróscopo):**
- `WHO_AM_I` verificado al init (0xD4 o 0xD7)
- FS ±500 dps · 17.5 mdps/LSB · auto-increment con `reg | 0x80`

**LSM303D (acelerómetro + magnetómetro):**
- FS ±2g / ±2 Gauss
- Lecturas de 6 bytes con auto-increment

**Filtro complementario (α = 0.98, DT = 0.02 s):**
```
pitch(t) = 0.98 × [pitch(t-1) + gy × DT] + 0.02 × atan2(ay, az)
roll(t)  = 0.98 × [roll(t-1)  + gx × DT] + 0.02 × atan2(-ax, az)
yaw(t)   = 0.95 × yaw_gyro + 0.05 × yaw_mag_tilt_comp
```

API pública: `read_angles()` → `(roll, pitch, yaw)` · `reset_yaw/pitch/roll()`.

---

## 12. USB HID — mouse absoluto

`hid_mouse.py` implementa un mouse USB HID con posición absoluta [0, 32767].

- **Encoders → pantalla:** `ENC=0` → centro exacto; sin deriva acumulada.
- **S3 → clic:** flanco ascendente → botón izquierdo durante `HID_CLICK_MS` ms.
- **Descriptor HID:** 5 bytes/reporte — 3 botones (5-bit pad) + X 16-bit + Y 16-bit.

### Requisito de firmware

Requiere MicroPython con soporte USB Device (TinyUSB). Las builds estándar **no** lo
incluyen. La librería `usb.device.hid` se incluye como código fuente en `firmware/lib/`.

| Condición | Resultado |
|---|---|
| Firmware con `machine.USBDevice` + `lib/usb/` subido | HID activo |
| Solo `machine.USBDevice`, sin `lib/usb/` | Intenta `mip install` |
| Sin `machine.USBDevice` | Fallback silencioso, sin HID |

Firmware con USB Device: [micropython.org/download/ESP32_GENERIC_S3/](https://micropython.org/download/ESP32_GENERIC_S3/)
(buscar el `.bin` con "USB" en el nombre).

---

## 13. Modo simulación

Activar con `SIMULATE_SENSORS = True` en `config.py`.

La simulación es **idéntica** en firmware (Python) y navegador (JavaScript),
garantizando que la UI animada en modo offline sea fiel al hardware.

**Máquina de estados del ciclo de disparo simulado:**

| Fase | Fracción | S1 | S2 | S3 | Descripción |
|---|---|---|---|---|---|
| 1 | 0–30% | ✓ | — | — | Cerrojo bloqueado |
| 2 | 30–60% | ✓ | ✓ | — | Retenedor enganchado |
| 3 | 60–65% | — | — | ✓ | Válvula de gas (disparo) |
| 4 | 65–100% | — | — | — | Retorno / reposo |

---

## 14. Despliegue al ESP32

### Prerrequisitos

```bash
pip install mpremote pyserial
```

### Archivos a subir

```
# Firmware (raíz del ESP32):
boot.py  config.py  main.py  sensors.py  server.py
gy89_driver.py  hid_mouse.py

# Librería USB HID (crear carpetas):
lib/usb/__init__.py
lib/usb/device/__init__.py
lib/usb/device/core.py
lib/usb/device/hid.py

# Web (crear carpetas):
web/index.html
web/js/ws_client.js  svg_bolt.js  gauges.js
web/js/encoders.js   charts.js    bt_toggle.js
```

### Con mpremote

```bash
# Subir firmware
mpremote cp firmware/boot.py firmware/config.py firmware/main.py \
            firmware/sensors.py firmware/server.py \
            firmware/gy89_driver.py firmware/hid_mouse.py :

# Crear estructura de directorios
mpremote mkdir :lib :lib/usb :lib/usb/device
mpremote cp -r firmware/lib/usb/ :lib/usb/

# Subir web
mpremote mkdir :web :web/js
mpremote cp web/index.html :web/
mpremote cp web/js/ :web/js/

mpremote reset
```

### Con Thonny

Guardar cada archivo con `File → Save copy… → MicroPython device`.

> Ver [QUICK_START.md](QUICK_START.md) para la guía completa paso a paso.

---

## 15. Flujo de arranque completo

```
Power-on / Reset
      │
  boot.py — 240 MHz · sin log · WiFi off
      │
  main.py
    ├─ 3 s ventana Ctrl+C (interrumpir antes de asyncio)
    ├─ init_hid()       → USB HID antes de WiFi
    ├─ connect_wifi()
    │     ├─ STA OK  → IP dinámica · AP off
    │     └─ Timeout → AP "M2-DAQ-SIM" · IP 192.168.0.162
    └─ asyncio.run(main())
           └─ start_server()
                 ├─ sensors.init()
                 │     ├─ SIMULATE=True  → parámetros sintéticos
                 │     └─ SIMULATE=False → GY-89 I2C · encoders IRQ · S1/S2/S3
                 ├─ asyncio.start_server('0.0.0.0', 80)
                 └─ create_task(_broadcast_loop)

Loop permanente 50 Hz:
  ├─ sensors.read()    → dict con roll/pitch/yaw/enc_h/enc_v/s1/s2/s3/ts
  ├─ hid_mouse.update() → reporte USB HID absoluto
  └─ _ws_writers[] → JSON frame a cada cliente WebSocket activo
```

---

## 16. Dependencias externas

### Firmware (MicroPython stdlib — sin instalación)

| Módulo | Uso |
|---|---|
| `asyncio` | Event loop (v1.22+) |
| `network` | WiFi STA + AP |
| `machine` | I2C, Pin, IRQ, freq |
| `hashlib` | SHA1 para WS handshake |
| `binascii` | Base64 encode |
| `random` | Simulación |

### Librería USB (incluida en `firmware/lib/`)

Fuente: [micropython-lib usb-device-hid](https://github.com/micropython/micropython-lib/tree/master/micropython/usb/usb-device-hid)

### Web UI

| Recurso | Cómo se carga |
|---|---|
| **Plotly.js 2.35.2** | CDN automático (el navegador necesita internet al abrir el dashboard) |

Todo lo demás es HTML5 + JavaScript vanilla + SVG puro. No hay bundler ni npm.
