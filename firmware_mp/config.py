# =============================================================================
#  config.py — Todos los parámetros del simulador (fuente única de verdad)
#  Editar este archivo antes de desplegar al ESP32.
# =============================================================================

# ── WiFi ─────────────────────────────────────────────────────────────────────
WIFI_SSID      = "M2-DAQ"      # SSID de la red WiFi a la que conectarse
WIFI_PASSWORD  = "12341234"     # Contraseña de la red WiFi
WIFI_TIMEOUT_S = 15                 # Segundos máximos esperando IP antes de AP

# ── AP fallback (si STA falla) ───────────────────────────────────────────────
AP_SSID        = "M2-DAQ-SIM"       # SSID del AP que el ESP32 levanta como fallback
AP_PASSWORD    = "m2daq1234"        # Contraseña del AP (mínimo 8 caracteres WPA2)

# ── Servidor ─────────────────────────────────────────────────────────────────
HOSTNAME       = "m2-daq-sim"       # Nombre mDNS (sin .local)
PORT           = 80                 # Puerto HTTP / WebSocket
WEB_ROOT       = "/web"             # Ruta en el filesystem del ESP32 con web_ui/

# ── Modo sensor ──────────────────────────────────────────────────────────────
#   True  → genera datos simulados (no necesita hardware externo)
#   False → lee hardware real: MPU-6050 I2C + encoders GPIO + S1/S2/S3 GPIO
SIMULATE_SENSORS = True

# ── Temporización ────────────────────────────────────────────────────────────
BROADCAST_HZ   = 50
PERIOD_MS      = 1000 // BROADCAST_HZ   # = 20 ms

# ── Pines GPIO (iguales al firmware ESP32-S3 de producción) ──────────────────
PIN_SDA        = 8    # I2C SDA → MPU-6050
PIN_SCL        = 9    # I2C SCL → MPU-6050
PIN_ENC_H_A    = 1    # Encoder horizontal fase A
PIN_ENC_H_B    = 2    # Encoder horizontal fase B
PIN_ENC_V_A    = 3    # Encoder vertical fase A
PIN_ENC_V_B    = 4    # Encoder vertical fase B
PIN_S1         = 5    # S1_BLOQUEADO  (activo-bajo, pull-up interno)
PIN_S2         = 6    # S2_RETENEDOR  (activo-bajo, pull-up interno)
PIN_S3         = 7    # S3_VALVULA    (activo-bajo, pull-up interno)

# ── Parámetros de simulación ─────────────────────────────────────────────────
SIM_PITCH_AMP      = 8.0    # Amplitud sinusoide pitch (grados ±)
SIM_ROLL_AMP       = 4.0    # Amplitud sinusoide roll (grados ±)
SIM_YAW_DRIFT_HZ   = 0.04   # Frecuencia de la oscilación lenta del yaw
SIM_FIRE_CYCLE_MS  = 6000   # Duración de un ciclo completo de disparo simulado
