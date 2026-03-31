# M2.50 DAQ-UI

Sistema de adquisición de datos para el simulador de combate con réplica
neumática del arma Browning M2 .50 Cal.  
Firmware MicroPython en ESP32-S3. Dashboard web en tiempo real a 50 Hz vía WebSocket.

---

## Requisitos previos

### Hardware
- ESP32-S3 DevKitC-1 v1.1 (N16R8 — 16 MB Flash, 8 MB PSRAM)
- IMU ISM330DHCX (SparkFun Qwiic, I2C addr `0x6B`)
- 2× encoder incremental cuadratura (H + V)
- 3× switch/sensor activo-bajo (S1, S2, S3)

### Software
```bash
pip install mpremote pyserial
```

### uPlot (obligatorio para las gráficas)
Descargar `uplot.min.js` (~52 KB) y copiarlo en `web/vendor/`:

```bash
curl -L https://github.com/leeoniya/uplot/releases/latest/download/uPlot.iife.min.js \
     -o web/vendor/uplot.min.js
```

> Sin este archivo el dashboard no mostrará las gráficas.

---

## Configuración

Editar `firmware/config.py` antes de desplegar:

| Parámetro | Descripción |
|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Credenciales red WiFi STA |
| `SIMULATE_SENSORS` | `True` = modo sin hardware (solo ESP32) |
| `PIN_*` | Pines GPIO según tu cableado |

---

## Despliegue

### Opción A — mpremote (recomendado)
```bash
chmod +x deploy.sh
./deploy.sh                   # autodetecta puerto
./deploy.sh /dev/ttyUSB0      # puerto explícito
```

### Opción B — raw REPL (cuando asyncio bloquea el REPL)
```bash
python3 deploy_raw.py /dev/ttyACM0
```

---

## Acceso al dashboard

| Modo | URL |
|---|---|
| WiFi STA | `http://<IP asignada por router>` |
| AP fallback | `http://192.168.4.1` — SSID: `M2-DAQ-SIM` |

El dashboard funciona offline (simulación local) incluso sin ESP32.

---

## Pines GPIO (ESP32-S3 DevKitC-1)

| GPIO | Señal |
|---|---|
| 8 / 9 | SDA / SCL (IMU I2C) |
| 4 / 5 | ENC_H fase A / B |
| 6 / 7 | ENC_V fase A / B |
| 15 | S1 — BLOQUEADO |
| 16 | S2 — RETENEDOR |
| 17 | S3 — VÁLVULA |

> GPIO 35/36/37 reservados para Flash/PSRAM — **no usar**.
