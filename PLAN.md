# M2.50 DAQ-UI — Plan del Proyecto

## Descripción

Sistema de adquisición de datos para el estudio del uso del simulador de combate con réplica neumática de arma Browning M2.50. Captura orientación (IMU), posicionamiento (encoders) y estados del mecanismo de disparo (sensores digitales) a 50 Hz, y distribuye los datos simultáneamente a:

- Un navegador web vía WiFi WebSocket
- Un sistema de apuntado en PC vía USB HID (ratón)
- Una app móvil/escritorio vía Bluetooth LE

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────────────────────┐
│                          ESP32-S3  (producción)                     │
│                                                                     │
│  MPU-6050 (I2C) ─┐                                                  │
│  Encoder H  ─────┤                                                  │
│  Encoder V  ─────┼─▶ sensor_task  ──────────── ws_server ──────▶ 🌐 WiFi   │
│  S1 / S2 / S3 ───┘   (50 Hz, Core 0) ─────── hid_mouse ──────▶ 🖱 USB HID │
│                                          └──── ble_stream ─────▶ 📱 BLE    │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐     ┌────────────────────────────────┐
│  Navegador web               │     │  App Kivy (Android / Windows)  │
│  http://m2daq.local/         │     │                                │
│  ws://m2daq.local/ws  ───────┤     │  BleService (bleak)            │
│  web_ui/index.html   (HTML5) │     │    └▶ JsBridge                 │
│  charts / gauges / bolt SVG  │     │         └▶ WebView (index.html)│
└──────────────────────────────┘     └────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   ESP32 convencional  (prueba / desarrollo)         │
│                          MicroPython + WiFi                         │
│                                                                     │
│  sensor_task simulado o real ──▶ ws_server (asyncio) ──▶ 🌐 WiFi   │
│  (firmware_mp/)                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Estructura del repositorio

```
M2.50_DAQ-UI/
├── firmware/            # Firmware ESP32-S3 — ESP-IDF v5.2, C
│   ├── main/            # main.c — orquestación del arranque
│   ├── components/      # Componentes modulares
│   │   ├── nvs_config/  # Configuración persistente en NVS flash
│   │   ├── sensor_task/ # Tarea 50 Hz que lee todos los sensores
│   │   ├── mpu6050/     # Driver I2C MPU-6050 + filtro complementario
│   │   ├── encoder/     # Encoders cuadraturas vía PCNT hardware
│   │   ├── hid_mouse/   # TinyUSB HID boot mouse
│   │   ├── ws_server/   # Servidor HTTP + WebSocket + SPIFFS
│   │   └── ble_stream/  # GATT server NimBLE para app móvil
│   ├── partitions.csv   # Tabla de particiones flash
│   └── sdkconfig.defaults
│
├── web_ui/              # Interfaz web (servida desde SPIFFS / bundled en app)
│   ├── index.html       # Dashboard principal
│   ├── js/
│   │   ├── ws_client.js    # Cliente WebSocket con reconexión exponencial
│   │   ├── svg_bolt.js     # Animación SVG del cerrojo M2.50
│   │   ├── gauges.js       # Rosa de los vientos (yaw) + pitch/roll numérico
│   │   ├── encoders.js     # Contadores de encoders
│   │   ├── charts.js       # Gráficas rolling 6s (uPlot)
│   │   └── bt_toggle.js    # Toggle BLE + calibración yaw
│   └── vendor/
│       └── uplot.min.js    # Librería de gráficas (~52 KB)
│
├── app/                 # App Kivy — Android APK + Windows EXE
│   ├── main.py          # Entry point, ScreenManager
│   ├── screens/         # bt_scan_screen.py, dashboard_screen.py
│   ├── services/        # ble_service.py (bleak), js_bridge.py
│   ├── widgets/         # ble_device_item.py (RecycleView row)
│   ├── kv/              # Layouts Kivy (bt_scan.kv, dashboard.kv)
│   ├── assets/web_ui/   # Copia sincronizada de web_ui/
│   ├── requirements.txt
│   ├── buildozer.spec   # Android build
│   └── pyinstaller.spec # Windows EXE build
│
├── firmware_mp/         # Simulador MicroPython — ESP32 convencional + WiFi
│   ├── boot.py          # Frecuencia CPU, silencia debug
│   ├── config.py        # Todos los parámetros (WiFi, pines, SIMULATE_SENSORS)
│   ├── main.py          # Entry point asyncio
│   ├── server.py        # HTTP + WebSocket RFC 6455 manual
│   ├── sensors.py       # Abstracción dual: simulado / hardware real
│   ├── mpu6050_driver.py# Driver I2C MPU-6050 en MicroPython
│   ├── deploy.sh        # Script mpremote para subir archivos al ESP32
│   └── web/             # Copia estática de web_ui/ (subida al ESP32)
│
├── tools/               # Scripts de build y despliegue
│   ├── flash_all.sh     # Build + flash completo (ESP32-S3)
│   └── sync_web_ui.sh   # Sincroniza web_ui/ → app/assets/web_ui/
│
├── 2D.html              # Simulador 2D autónomo (sin hardware)
├── PLAN.md              # Este documento
└── INSTRUCTIONS.md      # Instrucciones de ejecución por componente
```

---

## Formato canónico del paquete de datos

Todos los canales (WebSocket, BLE GATT, simulador MicroPython) emiten el **mismo JSON a 50 Hz**:

```json
{
  "s1": false,        // S1_BLOQUEADO  — sensor activo-bajo, true = activo
  "s2": false,        // S2_RETENEDOR  — sensor activo-bajo, true = activo
  "s3": false,        // S3_VALVULA    — sensor activo-bajo, true = activo
  "gas_valve": false, // = s3 (alias para claridad en UI)
  "pitch": 1.23,      // grados, rango ≈ -90..+90
  "roll": -0.45,      // grados, rango ≈ -90..+90
  "yaw": 180.5,       // grados, rango 0..360
  "enc_h": 12345,     // cuentas acumuladas, encoder horizontal
  "enc_v": -678,      // cuentas acumuladas, encoder vertical
  "ts": 123456789     // milisegundos desde arranque
}
```

Números decimales: `pitch` y `roll` con 2 decimales (`%.2f`), `yaw` con 1 decimal (`%.1f`).

---

## Asignación de pines GPIO (ESP32-S3 DevKitC-1)

| Función | GPIO |
|---|---|
| I2C SDA (MPU-6050) | 8 |
| I2C SCL (MPU-6050) | 9 |
| MPU-6050 INT | 10 |
| Encoder H — fase A | 1 |
| Encoder H — fase B | 2 |
| Encoder V — fase A | 3 |
| Encoder V — fase B | 4 |
| S1 — BLOQUEADO (activo-bajo) | 5 |
| S2 — RETENEDOR (activo-bajo) | 6 |
| S3 — VÁLVULA GAS (activo-bajo) | 7 |
| LED de estado (activo-alto) | 21 |

Los mismos pines se usan en el simulador MicroPython cuando `SIMULATE_SENSORS = False`.

---

## Componentes del firmware ESP32-S3

### `nvs_config` — Configuración persistente
Almacena en NVS flash: SSID/password WiFi, hostname mDNS, puerto HTTP, sensibilidad HID (eje X/Y) y flag BLE. Valores por defecto en primer arranque:

| Parámetro | Valor por defecto |
|---|---|
| SSID | `M2-DAQ_AP` |
| Password | ` ` (abierto) |
| Hostname | `m2daq` |
| Puerto | 80 |
| Sensibilidad HID X/Y | 1.0 |
| BLE habilitado | false |

### `sensor_task` — Tarea maestra 50 Hz
Corre en Core 0. Lee MPU-6050, encoders y GPIOs cada 20 ms, construye `sensor_data_t` y los pasa a hasta 4 callbacks registrados (ws_server, hid_mouse, ble_stream).

### `mpu6050` — Driver IMU
I2C a 400 kHz. Filtro complementario: α=0.98 (gyro), 1-α=0.02 (acelerómetro). Rango gyro ±250°/s, acelerómetro ±2g. Yaw por integración pura (drift esperado sin magnetómetro).

### `encoder` — Encoders cuadraturas
PCNT hardware con decodificación 4× (ambos flancos de ambas fases). Contador 64-bit con manejo de overflow del contador 16-bit de hardware. Filtro anti-rebote 1 µs.

### `hid_mouse` — Ratón USB HID
TinyUSB HID boot protocol. Convierte delta de encoders a movimiento de ratón aplicando sensibilidad configurable. Rango por paquete: -127..+127.

### `ws_server` — Servidor HTTP + WebSocket
- Sirve `web_ui/` desde partición SPIFFS (1.375 MB)
- WebSocket en `/ws`, hasta 4 clientes simultáneos
- API REST: `GET/POST /api/config`, `POST /api/config/bluetooth`, `POST /api/calibrate`
- Broadcast síncrono desde callback del sensor_task

### `ble_stream` — GATT server BLE
NimBLE dual-role. UUID de servicio personalizado 128-bit. Dos características:
- **Sensor** (notify, UUID ...0002): emite JSON a 50 Hz
- **Control** (write, UUID ...0003): acepta `"bt:on"`, `"bt:off"`, `"calibrate"`

Nombre de advertising: `<hostname>-BLE` (ej. `m2daq-BLE`).

---

## App Kivy (Android / Windows)

Arquitectura de dos pantallas:

```
Pantalla 1: BLE Scanner
  └─ BleakScanner → lista de dispositivos "M2*-BLE"
  └─ Tap → guarda ble_address → navega a Pantalla 2

Pantalla 2: Dashboard
  └─ WebView carga assets/web_ui/index.html (archivo local)
  └─ BleService (hilo asyncio) → recibe JSON via GATT notify
  └─ JsBridge → inyecta window.onBTData(json) en WebView
  └─ web_ui/js/ws_client.js detecta window.__KIVY_MODE__ == true
     y consume datos vía onBTData en vez de WebSocket
```

Builds:
- **Android**: `buildozer android debug` (requiere Ubuntu/WSL, API 24+)
- **Windows**: `pyinstaller pyinstaller.spec` (requiere Python 3.10+, Kivy 2.3)

---

## Simulador MicroPython (`firmware_mp/`)

Permite probar el sistema completo con un **ESP32 convencional** (no S3) programado en MicroPython v1.22+, sin necesidad del hardware de producción.

Características:
- WiFi STA con fallback AP automático (`M2-DAQ-SIM`)
- Servidor HTTP + WebSocket implementado manualmente sobre `uasyncio` conforme RFC 6455
- Modo simulado: IMU sinusoidal, encoders random walk, ciclo de disparo automático
- Modo real: driver MPU-6050 idéntico al firmware C, encoders por IRQ, sensores digitales activo-bajo
- Selección por `SIMULATE_SENSORS = True/False` en `config.py`
- La web UI (`web_ui/index.html`) se sirve **sin modificación** desde el filesystem del ESP32

---

## Flujo de datos completo

```
Hardware físico
  MPU-6050 (I2C, 400kHz) ──▶ pitch, roll, yaw (filtro α=0.98)
  Encoder H (PCNT, 4×)   ──▶ enc_h (int64, cuentas)
  Encoder V (PCNT, 4×)   ──▶ enc_v (int64, cuentas)
  S1, S2, S3 (GPIO)      ──▶ bool (activo-bajo Invertido)
            │
            ▼  20 ms (50 Hz)
      sensor_data_t
            │
     ┌──────┼──────────────────┐
     ▼      ▼                  ▼
  ws_server  hid_mouse      ble_stream
  JSON WS    USB HID delta  BLE GATT notify
  a browsers a PC aiming    a app Kivy
```

---

## API REST (firmware ESP32-S3 y simulador MicroPython)

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/api/config` | Devuelve configuración actual en JSON |
| `POST` | `/api/config` | Actualiza SSID, password, hostname, port, sensibilidad HID |
| `POST` | `/api/config/bluetooth` | `{"enabled": true/false}` — activa/desactiva BLE |
| `POST` | `/api/calibrate` | Reinicia integrador yaw a 0° |

El simulador MicroPython responde a todos estos endpoints (BT es stub cosmético).

---

## Tecnologías utilizadas

| Componente | Tecnología |
|---|---|
| Firmware producción | C, ESP-IDF v5.2+, FreeRTOS |
| Firmware prueba | MicroPython v1.22+, uasyncio |
| Sensores | MPU-6050 (I2C), encoders cuadraturas, GPIO |
| USB HID | TinyUSB boot protocol (solo ESP32-S3) |
| BLE | NimBLE GATT server (solo ESP32-S3) |
| Web UI | HTML5, CSS3, JavaScript ES5, SVG, uPlot |
| App móvil/escritorio | Python 3.10+, Kivy 2.3, bleak 0.21 |
| Build Android | buildozer + python-for-android |
| Build Windows | PyInstaller |
| Sistema de build firmware | CMake + ESP-IDF build system |

---

## Estado del proyecto

| Componente | Estado |
|---|---|
| Firmware ESP32-S3 | Completo |
| Web UI | Completo |
| App Kivy (Android + Windows) | Completo |
| Simulador MicroPython | Completo |
| Documentación | Completa |
| Autenticación API REST | Pendiente (mejora futura) |
| Magnetómetro (corrección drift yaw) | Pendiente (mejora futura) |
| OTA firmware | Particiones preparadas, lógica pendiente |
