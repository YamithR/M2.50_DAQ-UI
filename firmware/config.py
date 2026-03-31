# config.py — Única fuente de verdad de todos los parámetros del sistema M2.50 DAQ-UI
# Editar este archivo antes de cada despliegue.

# ---------------------------------------------------------------------------
# WiFi — modo estación (STA)
# ADVERTENCIA: cambia estas credenciales antes de desplegar en producción.
# ---------------------------------------------------------------------------
WIFI_SSID       = "Oniris_G5-ID"
WIFI_PASSWORD   = "Oniri$2025"
WIFI_TIMEOUT_S  = 15              # segundos antes de activar AP fallback

# ---------------------------------------------------------------------------
# WiFi — modo punto de acceso (AP fallback)
# ---------------------------------------------------------------------------
AP_SSID         = "M2-DAQ-SIM"
AP_PASSWORD     = "m2daq1234"     # mínimo 8 caracteres WPA2
AP_IP           = "192.168.4.1"

# ---------------------------------------------------------------------------
# Servidor HTTP / WebSocket
# ---------------------------------------------------------------------------
HOSTNAME        = "m2-daq-sim"    # nombre mDNS (sin .local)
PORT            = 80
WEB_ROOT        = "/web"          # ruta en el filesystem del ESP32

# ---------------------------------------------------------------------------
# Modo sensor
# ---------------------------------------------------------------------------
SIMULATE_SENSORS = False          # True = sin hardware externo

# ---------------------------------------------------------------------------
# Temporización
# ---------------------------------------------------------------------------
BROADCAST_HZ    = 50
PERIOD_MS       = 1000 // BROADCAST_HZ   # 20 ms (pre-calculado)

# ---------------------------------------------------------------------------
# Pines GPIO — ESP32-S3 DevKitC-1 v1.1, N16R8
# NOTA: GPIO 35/36/37 reservados para Flash/PSRAM — NO USAR.
# ---------------------------------------------------------------------------
PIN_SDA         = 8    # I2C SDA → ISM330DHCX (SparkFun Qwiic)
PIN_SCL         = 9    # I2C SCL → ISM330DHCX
PIN_ENC_H_A     = 4    # Encoder horizontal fase A (IRQ)
PIN_ENC_H_B     = 5    # Encoder horizontal fase B (lectura en ISR)
PIN_ENC_V_A     = 6    # Encoder vertical fase A (IRQ)
PIN_ENC_V_B     = 7    # Encoder vertical fase B (lectura en ISR)
PIN_S1          = 15   # S1_BLOQUEADO  (activo-bajo, pull-up interno)
PIN_S2          = 16   # S2_RETENEDOR  (activo-bajo, pull-up interno)
PIN_S3          = 17   # S3_VÁLVULA    (activo-bajo, pull-up interno)

# ---------------------------------------------------------------------------
# IMU — ISM330DHCX
# ---------------------------------------------------------------------------
IMU_ADDR        = 0x6B            # SDO = VCC (JP1 abierto en SparkFun Qwiic)
# IMU_ADDR      = 0x6A            # SDO = GND (JP1 cerrado) — alternativa
IMU_FREQ        = 400_000         # Hz bus I2C

# ---------------------------------------------------------------------------
# Parámetros de simulación
# IMPORTANTE: deben coincidir con los valores en web/js/ws_client.js
# ---------------------------------------------------------------------------
SIM_ROLL_AMP        = 10.0        # grados ±
SIM_PITCH_AMP       =  8.0        # grados ±
SIM_YAW_DRIFT_HZ    =  0.04       # Hz — frecuencia de deriva del yaw
SIM_FIRE_CYCLE_MS   =  6000       # ms — duración de un ciclo de disparo completo
