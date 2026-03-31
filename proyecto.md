# M2.50 DAQ-UI

> Sistema de adquisición de datos para el estudio del simulador de combate con réplica
> neumática del arma Browning M2 .50 Cal.  El firmware corre en un ESP32-S3 bajo
> MicroPython y expone un dashboard web en tiempo real a 50 Hz vía WebSocket.

---

## Tabla de Contenidos

1. [Descripción del sistema](#1-descripción-del-sistema)
2. [Hardware requerido](#2-hardware-requerido)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Arquitectura de software](#4-arquitectura-de-software)
5. [Firmware — detalle de cada módulo](#5-firmware--detalle-de-cada-módulo)
6. [Web UI — detalle de cada módulo](#6-web-ui--detalle-de-cada-módulo)
7. [Protocolo WebSocket / paquete de datos](#7-protocolo-websocket--paquete-de-datos)
8. [REST API](#8-rest-api)
9. [Configuración (`config.py`)](#9-configuración-configpy)
10. [Mapa de pines GPIO](#10-mapa-de-pines-gpio)
11. [Driver IMU ISM330DHCX](#11-driver-imu-ism330dhcx)
12. [Modo simulación](#12-modo-simulación)
13. [Despliegue al ESP32](#13-despliegue-al-esp32)
14. [Flujo de arranque completo](#14-flujo-de-arranque-completo)
15. [Dependencias externas](#15-dependencias-externas)

---

## 1. Descripción del sistema

El sistema captura los siguientes datos del simulador a **50 Hz**:

| Canal | Tipo | Descripción |
|---|---|---|
| **S1 — BLOQUEADO** | Digital activo-bajo | Cerrojo en posición de bloqueo |
| **S2 — RETENEDOR** | Digital activo-bajo | Cerrojo amartillado y retenido |
| **S3 — VÁLVULA** | Digital activo-bajo | Válvula de gas abierta (= disparo) |
| **ROLL** | IMU analógico | Eje longitudinal (°) |
| **PITCH** | IMU analógico | Eje transversal (°) |
| **YAW** | IMU integrado | Rumbo acumulado 0–360° |
| **ENC_H** | Encoder cuadratura | Posición horizontal (cuentas) |
| **ENC_V** | Encoder cuadratura | Posición vertical (cuentas) |

Los datos se transmiten por **WiFi WebSocket** a un navegador web que muestra:
- Animación SVG del mecanismo de cerrojo del M2.50
- Indicadores IMU estilo aviación (roll, pitch, yaw)
- Contadores de encoders
- Cuatro gráficas en tiempo real (cadencia de fuego, sensores digitales, IMU, encoders)

---

## 2. Hardware requerido

| Componente | Especificación |
|---|---|
| Microcontrolador | **ESP32-S3 DevKitC-1 v1.1, N16R8** (16 MB Flash, 8 MB PSRAM) |
| IMU | **ISM330DHCX** (SparkFun Qwiic) — dirección I2C `0x6B` (SDO=VCC) |
| Encoder horizontal | Encoder incremental cuadratura (fases A+B) |
| Encoder vertical | Encoder incremental cuadratura (fases A+B) |
| S1 / S2 / S3 | Switches o sensores activo-bajo (se usa pull-up interno) |
| Cable USB | Para flashing y acceso REPL |

> **Nota:** El firmware tiene un modo simulado completo (`SIMULATE_SENSORS = True` en
> `config.py`) que no requiere ningún hardware externo más allá del ESP32.

---

## 3. Estructura del repositorio

```
M2.50_DAQ-UI/
├── firmware/
│   ├── boot.py               # Configura CPU 240 MHz, silencia osdebug, llama main
│   ├── config.py             # ÚNICA fuente de verdad de todos los parámetros
│   ├── main.py               # Conecta WiFi (STA o AP fallback), lanza asyncio
│   ├── sensors.py            # Abstracción dual: simulado / hardware real
│   ├── server.py             # Servidor HTTP + WebSocket RFC 6455 + REST API
│   └── ism330dhcx_driver.py  # Driver I2C nativo para ISM330DHCX + filtro complementario
│
├── web/
│   ├── index.html            # Dashboard principal (HTML5, sin framework)
│   ├── js/
│   │   ├── ws_client.js      # Cliente WS con simulación local y reconexión expo.
│   │   ├── svg_bolt.js       # Animación SVG del cerrojo
│   │   ├── gauges.js         # Indicadores IMU SVG puros (roll, pitch, yaw)
│   │   ├── encoders.js       # Actualiza contadores ENC_H / ENC_V
│   │   ├── charts.js         # Gráficas rolling con uPlot (4 paneles)
│   │   └── bt_toggle.js      # Botones de calibración yaw/pitch/roll
│   └── vendor/
│       └── uplot.min.js      # Librería de gráficas (~52 KB, sin dependencias)
│
├── deploy.sh                 # Script bash — sube todo vía mpremote
├── deploy_raw.py             # Script Python — sube todo vía pyserial raw REPL
├── PLAN.md                   # Plan de arquitectura (incluye BLE y HID futuros)
└── README.md                 # Descripción mínima del proyecto
```

---

## 4. Arquitectura de software

```
┌─────────────────────────────────────────────────────────┐
│                    ESP32-S3 (MicroPython)               │
│                                                         │
│  boot.py                                                │
│    └─▶ main.py                                          │
│          ├─ connect_wifi()   STA → AP fallback          │
│          └─ asyncio.run(main())                         │
│                ├─ start_server()                        │
│                │     ├─ asyncio.start_server()          │
│                │     │     └─ _handle_client() por TCP  │
│                │     │           ├─ /ws  → WS upgrade   │
│                │     │           ├─ /api/* → REST stub   │
│                │     │           └─ /* → static files   │
│                │     └─ _broadcast_loop()  50 Hz        │
│                │           ├─ sensors.read()            │
│                │           └─ WS frame → _ws_writers[]  │
│                └─ sensors.init()                        │
│                      ├─ SIMULATE=True → parámetros sim  │
│                      └─ SIMULATE=False → ISM330DHCX     │
│                                         encoders IRQ    │
│                                         pines S1/S2/S3  │
└─────────────────────────────────────────────────────────┘
             │ WiFi 802.11 │
             ▼
┌─────────────────────────────────────────────────────────┐
│                  Navegador web (cualquier dispositivo)  │
│                                                         │
│  index.html                                             │
│    ├─ ws_client.js  →  WebSocket ws://<IP>/ws           │
│    │    └─ dispatch(paquete) → todos los módulos        │
│    ├─ svg_bolt.js   →  animación cerrojo M2.50          │
│    ├─ gauges.js     →  roll / pitch / yaw SVG           │
│    ├─ encoders.js   →  contadores ENC_H / ENC_V         │
│    ├─ charts.js     →  4 gráficas uPlot en tiempo real  │
│    └─ bt_toggle.js  →  POST /api/calibrate/*            │
└─────────────────────────────────────────────────────────┘
```

### Concurrencia

El servidor usa **asyncio** de MicroPython. Dos coroutines principales corren en
el mismo event loop:

- `asyncio.start_server(_handle_client, ...)` — acepta conexiones TCP entrantes.
- `_broadcast_loop()` — corre al ritmo de `PERIOD_MS` (20 ms = 50 Hz), lee
  sensores y hace `writer.write()` a todos los WebSocket activos en `_ws_writers`.

Cada cliente WebSocket tiene además su propia tarea `_ws_client_task` que lee
frames entrantes (Close, Ping) sin bloquear el broadcast.

---

## 5. Firmware — detalle de cada módulo

### `boot.py`

```
Tareas:
  - Establece frecuencia de CPU a 240 MHz
  - Silencia mensajes internos del SO (esp.osdebug(None))
  - Desactiva ambas interfaces WiFi (el main.py las activará selectivamente)
  - Importa main (con captura de excepciones para no quedar atrapado en el arranque)
```

### `config.py`

Fuente única de verdad. Se edita antes de desplegar. Ver [sección 9](#9-configuración-configpy).

### `main.py`

```
Función connect_wifi():
  1. Activa interfaz STA
  2. Si ya está conectado (warm boot) → usa la IP existente
  3. Si no → llama wlan.connect() y espera hasta WIFI_TIMEOUT_S segundos
  4. Si timeout → llama _start_ap_fallback() (levanta AP_SSID con WPA2)

Coroutine main():
  1. connect_wifi()
  2. await start_server()   ← no retorna nunca

Ventana de interrupción:
  time.sleep_ms(3000) al inicio permite Ctrl+C antes de que asyncio bloquee el REPL
```

### `sensors.py`

Expone la interfaz pública independiente del modo:

| Función | Descripción |
|---|---|
| `init()` | Inicializa hardware o parámetros de simulación |
| `read() → dict` | Devuelve el paquete canónico de datos |
| `reset_yaw()` | Reinicia integrador yaw a 0° |
| `reset_pitch()` | Calibra pitch (referencia cero = posición actual) |
| `reset_roll()` | Calibra roll (referencia cero = posición actual) |

**Modo hardware real:**
- ISM330DHCX inicializado vía `ism330dhcx_driver.ISM330DHCX(PIN_SDA, PIN_SCL)`
- Encoders: IRQ en fase A (`IRQ_RISING | IRQ_FALLING`), dirección por estado de fase B
- S1/S2/S3: `Pin.IN, Pin.PULL_UP` — lógica invertida (GPIO=0 → sensor activo)
- Fallo de IMU es **no fatal**: encoders y digitales siguen operando; roll/pitch/yaw = 0

**Modo simulado:**
- roll: `SIM_ROLL_AMP × cos(t × 0.35)`
- pitch: `SIM_PITCH_AMP × sin(t × 0.40)`
- yaw: integración de `2 × sin(t × SIM_YAW_DRIFT_HZ × 2π)` × DT (deriva de giróscopo)
- encoders: random walk con inercia (~3% probabilidad de cambiar velocidad por tick)
- S1/S2/S3: máquina de estados de 4 fases con período `SIM_FIRE_CYCLE_MS`

**Máquina de estados del ciclo de disparo simulado:**

```
Fase  | Fracción  | S1    | S2    | S3    | Descripción
------|-----------|-------|-------|-------|---------------------------
  1   |  0–30%    | True  | False | False | Cerrojo bloqueado
  2   | 30–60%    | True  | True  | False | Retenedor enganchado
  3   | 60–65%    | False | False | True  | Válvula de gas (disparo)
  4   | 65–100%   | False | False | False | Retorno / reposo
```

### `server.py`

```
Constantes:
  _WS_MAGIC   = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'  (RFC 6455)
  _FILE_CHUNK = 512 bytes  (chunks para servir archivos grandes sin agotar heap)
  MAX_WS_CLIENTS = 8 (lista _ws_writers — sin límite explícito, limit implícito en RAM)

Funciones internas clave:
  _ws_accept_key(key)     → BASE64(SHA1(key + WS_MAGIC))
  _ws_encode_text(bytes)  → frame WS texto FIN=1, opcode=0x01, sin masking
  _ws_read_frame(reader)  → (opcode, payload), desenmascara frames de cliente
  _handle_ws_upgrade()    → handshake 101, lanza _ws_client_task
  _ws_client_task()       → lee Close/Ping del cliente, elimina writer al cerrar
  _handle_static()        → sirve desde WEB_ROOT en chunks, MIME por extensión
  _handle_api()           → endpoints REST (ver sección 8)
  _handle_client()        → router: /ws → WS | /api/* → REST | /* → static
  _broadcast_loop()       → loop 50 Hz: lee sensores → construye JSON → envía a _ws_writers
  start_server()          → sensors.init() + asyncio.start_server() + asyncio.create_task(_broadcast_loop)
```

**Formato JSON del broadcast** (construido manualmente, campo a campo):

```json
{
  "s1": true/false,
  "s2": true/false,
  "s3": true/false,
  "gas_valve": true/false,
  "roll": -10.00,
  "pitch": 3.45,
  "yaw": 180.0,
  "yaw_signed": -180.0,
  "enc_h": 42,
  "enc_v": -7,
  "ts": 12345
}
```

### `ism330dhcx_driver.py`

Driver I2C nativo — sin dependencias SparkFun.

**Configuración del sensor:**

| Registro | Valor | Descripción |
|---|---|---|
| `CTRL3_C` (0x12) | `0x44` | BDU + IF_INC |
| `CTRL1_XL` (0x10) | `0x48` | Acelerómetro 104 Hz, FS ±4g |
| `CTRL2_G` (0x11) | `0x44` | Giróscopo 104 Hz, FS ±500 dps |

**Sensibilidades:**
- Acelerómetro: `0.122e-3 g/LSB` (±4g, 16-bit)
- Giróscopo: `17.5e-3 dps/LSB` (±500 dps, 16-bit)

**Filtro complementario (α = 0.98, DT = 0.02 s):**

```
pitch(t) = 0.98 × (pitch(t-1) + gy × DT) + 0.02 × atan2(ay, az)
roll(t)  = 0.98 × (roll(t-1)  + gx × DT) + 0.02 × atan2(-ax, az)
yaw(t)   = (yaw(t-1) + gz × DT) mod 360
```

**Dirección I2C:** `0x6B` (SDO = VCC, jumper JP1 abierto en SparkFun Qwiic).
Usar `0x6A` si SDO = GND.

---

## 6. Web UI — detalle de cada módulo

### `index.html`

Dashboard monopágina en HTML5 puro. Paleta de colores:

```css
--gunmetal:  #2a2d30
--army-green: #4b5320
--danger:    #d32f2f
--safe:      #388e3c
```

Estructura visual:

```
[ ws-status ]  barra de estado conexión
[ .container ] panel principal
    ├─ SVG bolt animation (800×300 viewBox)
    ├─ Botones S1/S2/S3 (read-only indicators)
    ├─ Status box (estado del cerrojo)
    ├─ HUD con LEDs S1/S2/S3 + texto válvula
    └─ Tabla de sensores
[ .panel-row ]
    ├─ Panel IMU (roll/pitch/yaw + indicadores SVG gauges.js)
    └─ Panel Encoders (ENC_H/ENC_V + botones calibración)
[ .chart-container ]
    ├─ Cadencia de fuego (60 s)
    ├─ Historial sensores digitales (6 s)
    ├─ Historial IMU (6 s)
    └─ Historial encoders (6 s)
```

Scripts cargados al final del body (en orden):
1. `vendor/uplot.min.js`
2. `js/ws_client.js`
3. `js/svg_bolt.js`
4. `js/gauges.js`
5. `js/encoders.js`
6. `js/charts.js`
7. `js/bt_toggle.js`

### `ws_client.js`

- **Modo offline:** Simulación local arranca **inmediatamente** al cargar la página
  (sin esperar WS) para que los indicadores animen desde el primer frame.
- **Modo live:** Al recibir el primer paquete real, para la simulación local;
  si la conexión cae, reinicia la simulación automáticamente.
- **Reconexión:** backoff exponencial `1 s → 2 s → 4 s → … → 30 s máx`.
- **Despacho:** `dispatch(d)` llama a `svgBolt.update(d)`, `gauges.update(d)`,
  `encoders.update(d)` y `charts.push(d)`.
- Los parámetros de simulación son **idénticos** a `config.py` y `sensors.py`
  para que la UI local y el firmware produzcan exactamente la misma señal.

### `svg_bolt.js`

Mapeo sensor → posición X del grupo SVG `#bolt-group`:

| Estado | Posición X |
|---|---|
| S1 activo | 100 |
| S2 activo | 310 |
| S3 activo | 600 |
| Ninguno | última posición conocida |

También actualiza: spring width, opacidad del "air-blast" (chorro azul),
animación CSS `recoil-active` (vibración al disparar), LEDs, texto de estado.

### `gauges.js`

Tres instrumentos SVG puros (sin dependencias):

| Instrumento | Tamaño | Descripción |
|---|---|---|
| Roll indicator | 220×110 px | Símbolo de avión rota ±60° según roll |
| Pitch indicator | 120×190 px | Barra horizontal desliza vert. ±30° según pitch |
| Yaw slider | 220×60 px | Marcador ámbar desliza horiz. −180°…+180° |

### `charts.js`

Cuatro gráficas con `uPlot`:

| ID | Buffers | Ventana | Descripción |
|---|---|---|---|
| `chart-cadencia` | ts, disp/min | 60 s (3 000 muestras) | Cadencia de fuego detectada por flanco S3 ↑ |
| `chart-sensors` | ts, S1, S2, S3 | 6 s (300 muestras) | Estados digitales 0/1 |
| `chart-imu` | ts, roll, pitch, yaw | 6 s (300 muestras) | Orientación en grados |
| `chart-enc` | ts, enc_h, enc_v | 6 s (300 muestras) | Posición de encoders |

### `encoders.js`

Actualiza los elementos `#enc-h` y `#enc-v` con el valor firmado (con signo `+`/`-`).

### `bt_toggle.js`

Expone `calibrateYaw()`, `calibratePitch()` y `calibrateRoll()` al `window` global.
Cada función hace `POST` al endpoint correspondiente y muestra feedback visual
temporal en el botón (1 500 ms).

---

## 7. Protocolo WebSocket / paquete de datos

- **Endpoint:** `ws://<IP>/ws`
- **Dirección:** servidor → cliente (broadcast), cliente → servidor (solo Close/Ping)
- **Frecuencia:** 50 Hz (cada 20 ms)
- **Frame:** texto UTF-8 (opcode 0x01), FIN=1, sin masking (servidor → cliente)
- **Payload:** JSON (ver formato en sección 5 / `server.py`)

Campos del paquete:

| Campo | Tipo | Rango | Descripción |
|---|---|---|---|
| `s1` | bool | | S1 activo |
| `s2` | bool | | S2 activo |
| `s3` | bool | | S3 activo |
| `gas_valve` | bool | | Alias de `s3` |
| `roll` | float | ±90° | Roll con offset de calibración |
| `pitch` | float | ±90° | Pitch con offset de calibración |
| `yaw` | float | 0–360° | Yaw acumulado |
| `yaw_signed` | float | −180–+180° | `((yaw+180) % 360) - 180` |
| `enc_h` | int | ilimitado | Cuentas encoder horizontal |
| `enc_v` | int | ilimitado | Cuentas encoder vertical |
| `ts` | int | ms | `time.ticks_ms()` desde boot |

---

## 8. REST API

| Método | Endpoint | Acción |
|---|---|---|
| `GET` | `/api/config` | Devuelve JSON con SSID, hostname, port, simulate |
| `POST` | `/api/config` | Aceptado (no aplica cambios) |
| `POST` | `/api/calibrate` | `sensors.reset_yaw()` |
| `POST` | `/api/calibrate/pitch` | `sensors.reset_pitch()` |
| `POST` | `/api/calibrate/roll` | `sensors.reset_roll()` |

Todas las respuestas POST exitosas devuelven `{"ok":true}`.

---

## 9. Configuración (`config.py`)

```python
# WiFi STA
WIFI_SSID      = "Oniris_G5-ID"
WIFI_PASSWORD  = "Oniri$2025"
WIFI_TIMEOUT_S = 15              # segundos antes de AP fallback

# AP fallback
AP_SSID        = "M2-DAQ-SIM"
AP_PASSWORD    = "m2daq1234"     # mín. 8 caracteres WPA2

# Servidor
HOSTNAME       = "m2-daq-sim"   # nombre mDNS (sin .local)
PORT           = 80
WEB_ROOT       = "/web"          # ruta en filesystem del ESP32

# Modo sensor
SIMULATE_SENSORS = False         # True = sin hardware externo

# Temporización
BROADCAST_HZ   = 50
PERIOD_MS      = 20              # 1000 // BROADCAST_HZ

# Parámetros de simulación
SIM_ROLL_AMP       = 10.0        # grados ±
SIM_PITCH_AMP      =  8.0        # grados ±
SIM_YAW_DRIFT_HZ   =  0.04       # Hz deriva de yaw
SIM_FIRE_CYCLE_MS  =  6000       # ms ciclo completo de disparo
```

---

## 10. Mapa de pines GPIO

**Placa:** ESP32-S3 DevKitC-1 v1.1, N16R8

> GPIO 35/36/37 reservados para Flash/PSRAM — **no usar**.

| Pin GPIO | Señal | Descripción |
|---|---|---|
| 8 | PIN_SDA | I2C SDA → ISM330DHCX (SparkFun Qwiic) |
| 9 | PIN_SCL | I2C SCL → ISM330DHCX |
| 4 | PIN_ENC_H_A | Encoder horizontal fase A (IRQ) |
| 5 | PIN_ENC_H_B | Encoder horizontal fase B (lectura en ISR) |
| 6 | PIN_ENC_V_A | Encoder vertical fase A (IRQ) |
| 7 | PIN_ENC_V_B | Encoder vertical fase B (lectura en ISR) |
| 15 | PIN_S1 | S1_BLOQUEADO (activo-bajo, pull-up interno) |
| 16 | PIN_S2 | S2_RETENEDOR (activo-bajo, pull-up interno) |
| 17 | PIN_S3 | S3_VÁLVULA (activo-bajo, pull-up interno) |

Referencia oficial de la placa:
https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html

**I2C:** frecuencia 400 kHz (`freq=400_000`), instancia `I2C(0, ...)`.

---

## 11. Driver IMU ISM330DHCX

Registro de identidad verificado al inicio: `WHO_AM_I` (0x0F) debe retornar `0x6B`.

**Secuencia de inicialización:**

```
1. Escribir 0x01 en CTRL3_C → SW_RESET
2. Esperar 15 ms
3. Escribir 0x44 en CTRL3_C → BDU + IF_INC
4. Escribir 0x48 en CTRL1_XL → ODR 104 Hz, FS ±4g
5. Escribir 0x44 en CTRL2_G  → ODR 104 Hz, FS ±500 dps
```

**Lectura:** espera hasta 20 ms a que `STATUS_REG` (0x1E) tenga bits GDA+XLDA
(`& 0x03 == 0x03`). Si timeout, retorna los últimos ángulos calculados.

**Registros de datos:**
- Giróscopo: `OUTX_L_G` (0x22), 6 bytes little-endian (X lo, X hi, Y lo, Y hi, Z lo, Z hi)
- Acelerómetro: `OUTX_L_A` (0x28), 6 bytes little-endian

---

## 12. Modo simulación

Activar con `SIMULATE_SENSORS = True` en `config.py`.

La simulación es **idéntica** tanto en el firmware (Python) como en el navegador
(JavaScript, `ws_client.js`), garantizando que la UI animada en modo offline sea
fiel al comportamiento del hardware.

**Sin hardware externo requerido:** solo el ESP32 conectado a WiFi.

---

## 13. Despliegue al ESP32

### Prerrequisitos

```bash
pip install mpremote       # para deploy.sh
pip install pyserial       # para deploy_raw.py
```

### Opción A — `deploy.sh` (recomendado si el REPL está disponible)

```bash
# Detección automática de puerto:
./deploy.sh

# Puerto explícito:
./deploy.sh /dev/ttyUSB0
```

El script:
1. Sube los 6 archivos de firmware al raíz del ESP32
2. Crea `/web`, `/web/js`, `/web/vendor` en el filesystem
3. Sube `index.html`, los 6 JS y `uplot.min.js`
4. Ejecuta `mpremote reset`

### Opción B — `deploy_raw.py` (cuando asyncio bloquea el REPL normal)

```bash
python3 deploy_raw.py /dev/ttyACM0
```

Usa raw REPL vía pyserial:
- Envía `Ctrl+C × 2` para interrumpir el programa en curso
- Entra en raw REPL (`Ctrl+A`)
- Sube cada archivo en chunks de 128 bytes codificados en binascii

### Filesystem del ESP32 tras el deploy

```
/boot.py
/main.py
/config.py
/server.py
/sensors.py
/ism330dhcx_driver.py
/web/
    index.html
    js/
        ws_client.js
        svg_bolt.js
        gauges.js
        encoders.js
        charts.js
        bt_toggle.js
    vendor/
        uplot.min.js
```

---

## 14. Flujo de arranque completo

```
Power-on / Reset
      │
      ▼
  boot.py
    ├─ machine.freq(240_000_000)
    ├─ esp.osdebug(None)
    ├─ WLAN STA + AP → active(False)
    └─ import main
           │
           ▼ (3 segundos de ventana Ctrl+C)
      main.py
        ├─ connect_wifi()
        │     ├─ STA connect → espera WIFI_TIMEOUT_S s
        │     │     ├─ OK  → IP STA, AP desactivado
        │     │     └─ FAIL → AP fallback 192.168.4.1
        │     └─ retorna True/False
        └─ asyncio.run(main())
               └─ await start_server()
                     ├─ sensors.init()
                     │     ├─ SIMULATE=True → print OK
                     │     └─ SIMULATE=False
                     │           ├─ ISM330DHCX.__init__()
                     │           ├─ encoders IRQ (fases A+B)
                     │           └─ S1/S2/S3 Pin.IN PULL_UP
                     ├─ asyncio.start_server(_handle_client, '0.0.0.0', 80)
                     └─ asyncio.create_task(_broadcast_loop())

Loop en ejecución:
  ├─ _broadcast_loop: cada 20 ms → sensors.read() → JSON → WS broadcast
  └─ _handle_client: por cada conexión TCP
        ├─ /ws       → WS handshake → _ws_client_task
        ├─ /api/*    → REST stubs
        └─ /*        → archivos estáticos desde /web
```

---

## 15. Dependencias externas

### Firmware (MicroPython)

| Módulo | Fuente | Notas |
|---|---|---|
| `asyncio` | MicroPython stdlib | v1.22+ (`asyncio.run()`) |
| `network` | MicroPython stdlib | WiFi STA + AP |
| `machine` | MicroPython stdlib | I2C, Pin, IRQ, freq |
| `hashlib` | MicroPython stdlib | SHA1 para WS handshake |
| `binascii` | MicroPython stdlib | Base64 encode |
| `random` | MicroPython stdlib | Simulación (urandom en versiones antiguas) |

No se requiere ninguna librería de terceros en el firmware.

### Web UI

| Librería | Versión | Archivo | Motivo |
|---|---|---|---|
| **uPlot** | Última disponible | `vendor/uplot.min.js` | Gráficas de series temporales de alto rendimiento |

Todo lo demás es HTML5 + JavaScript vanilla + SVG puro.

### Herramientas de desarrollo

| Herramienta | Uso |
|---|---|
| `mpremote` | Subida de archivos y reset del ESP32 |
| `pyserial` | Raw REPL para deploy cuando asyncio bloquea |

---

*Documento generado el 27/03/2026 — M2.50 DAQ-UI*
