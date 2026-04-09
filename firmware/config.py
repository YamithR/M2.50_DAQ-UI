# config.py — Única fuente de verdad de todos los parámetros del sistema M2.50 DAQ-UI
# Editar este archivo antes de cada despliegue.

# ---------------------------------------------------------------------------
# WiFi — modo estación (STA)
# ADVERTENCIA: cambia estas credenciales antes de desplegar en producción.
# ---------------------------------------------------------------------------
WIFI_SSID       = "Oniris_G5-ID"  # nombre del WiFi al que se conectará el ESP32 en modo STA
WIFI_PASSWORD   = "Oniri$2025"    # contraseña del WiFi (mínimo 8 caracteres WPA2)
WIFI_TIMEOUT_S  = 15              # segundos antes de activar AP fallback

# ---------------------------------------------------------------------------
# WiFi — modo punto de acceso (AP fallback)
# ---------------------------------------------------------------------------
AP_SSID         = "M2-DAQ-SIM"    # nombre del WiFi del ESP32 en modo AP
AP_PASSWORD     = "m2daq1234"     # mínimo 8 caracteres WPA2
AP_IP           = "192.168.0.162" # IP fija del ESP32 en modo AP

# ---------------------------------------------------------------------------
# Servidor HTTP / WebSocket
# ---------------------------------------------------------------------------
HOSTNAME        = "m2-daq-sim"    # nombre mDNS (sin .local)
PORT            = 80              # puerto TCP para el servidor HTTP y WebSocket
WEB_ROOT        = "/web"          # ruta en el filesystem del ESP32

# ---------------------------------------------------------------------------
# Modo sensor
# ---------------------------------------------------------------------------
SIMULATE_SENSORS = False          # True = sin hardware externo / False = con hardware (I2C + encoders)

# ---------------------------------------------------------------------------
# Temporización
# ---------------------------------------------------------------------------
BROADCAST_HZ    = 50             # frecuencia de transmisión de datos por WebSocket (Hz)
PERIOD_MS       = 1000 // BROADCAST_HZ   # 20 ms (pre-calculado)

# ---------------------------------------------------------------------------
# Pines GPIO — ESP32-S3 DevKitC-1 v1.1, N16R8
# NOTA: GPIO 35/36/37 reservados para Flash/PSRAM — NO USAR.
# ---------------------------------------------------------------------------
PIN_SDA         = 8    # I2C SDA → GY-89 (L3GD20 + LSM303D + BMP180)
PIN_SCL         = 9    # I2C SCL → GY-89
PIN_ENC_H_A     = 4    # Encoder horizontal fase A (IRQ)
PIN_ENC_H_B     = 5    # Encoder horizontal fase B (lectura en ISR)
PIN_ENC_V_A     = 6    # Encoder vertical fase A (IRQ)
PIN_ENC_V_B     = 7    # Encoder vertical fase B (lectura en ISR)
PIN_S1          = 15   # S1_BLOQUEADO  (activo-bajo, pull-up interno)
PIN_S2          = 16   # S2_RETENEDOR  (activo-bajo, pull-up interno)
PIN_S3          = 17   # S3_VÁLVULA    (activo-bajo, pull-up interno)
PIN_TRIGGER_OUT = 12   # Salida digital: HIGH durante el disparo (sincronizado con clic HID)

# ---------------------------------------------------------------------------
# IMU / Barómetro — GY-89 10DOF
#   · L3GD20  (giróscopo)       — I2C 0x6B si SDO=High, 0x6A si SDO=Low
#   · LSM303D (accel + mag.)    — I2C 0x1E si SA0=Low,  0x1D si SA0=High
#   · BMP180  (presión + temp.) — I2C 0x77 (fijo)
# ---------------------------------------------------------------------------
IMU_GYR_ADDR    = 0x6B            # L3GD20  — SDO conectado a VCC
IMU_ACC_ADDR    = 0x1E            # LSM303D — SA0 conectado a GND
IMU_FREQ        = 400_000         # Hz bus I2C (compartido por los tres chips)

# ---------------------------------------------------------------------------
# IMU fallback — MPU-6050 / GY-521
#   Dirección por defecto: 0x68 (AD0=GND).  Usar 0x69 si AD0=VCC.
# ---------------------------------------------------------------------------
IMU_MPU6050_ADDR = 0x68           # MPU-6050 / GY-521

# ---------------------------------------------------------------------------
# IMU — Reasignación y orientación de ejes
#
#   IMU_AXIS_MAP  = (i_roll, i_pitch, i_yaw)
#     Índice del eje RAW del driver que se asigna a cada salida lógica.
#     0=roll_raw  1=pitch_raw  2=yaw_raw  (orden que devuelve read_angles())
#     Ejemplo para intercambiar roll y pitch:  IMU_AXIS_MAP = (1, 0, 2)
#
#   IMU_AXIS_SIGN = (s_roll, s_pitch, s_yaw)
#     Signo de cada eje de salida: +1 (sin invertir) o -1 (invertido).
#     Ejemplo para invertir yaw:  IMU_AXIS_SIGN = (1, 1, -1)
# ---------------------------------------------------------------------------
IMU_AXIS_MAP  = (0, 1, 2)         # identidad: roll→roll, pitch→pitch, yaw→yaw
IMU_AXIS_SIGN = (1, 1, -1)         # invertir yaw para que gire en la dirección esperada (opcional, según montaje físico)

# ---------------------------------------------------------------------------
# Encoder — Rangos físicos (FUENTE ÚNICA DE VERDAD)
#   Ajustar estos 8 valores para calibrar el sistema.
#   Firmware computa ángulos en grados; la UI los usa directamente.
#
#   Ejemplo: si 500 cuentas corresponden a 45° de elevación:
#     ENC_V_CNT_MAX = 500   ENC_V_ANG_MAX = 45
# ---------------------------------------------------------------------------
ENC_H_CNT_MIN =  -1000    # cuentas en el límite izquierdo
ENC_H_CNT_MAX =   1000    # cuentas en el límite derecho
ENC_H_ANG_MIN =   -180    # azimut [°] en ENC_H_CNT_MIN
ENC_H_ANG_MAX =    180    # azimut [°] en ENC_H_CNT_MAX

ENC_V_CNT_MIN =    -500   # cuentas en depresión máxima
ENC_V_CNT_MAX =     500   # cuentas en elevación máxima
ENC_V_ANG_MIN =     -45   # ángulo [°] en ENC_V_CNT_MIN (depresión)
ENC_V_ANG_MAX =      45   # ángulo [°] en ENC_V_CNT_MAX (elevación)

# ---------------------------------------------------------------------------
# USB HID Mouse absoluto (encoder → puntero de pantalla)
# ---------------------------------------------------------------------------
HID_ENC_H_MIN   = ENC_H_CNT_MIN   # ← alias, no editar aquí, editar ENC_* arriba
HID_ENC_H_MAX   = ENC_H_CNT_MAX
HID_ENC_V_MIN   = ENC_V_CNT_MIN
HID_ENC_V_MAX   = ENC_V_CNT_MAX
HID_INVERT_Y    = True    # True = elevación → cursor arriba (Y decrece)
HID_CLICK_MS    = 60      # duración del clic izquierdo en milisegundos

# ---------------------------------------------------------------------------
# Parámetros de simulación
# IMPORTANTE: deben coincidir con los valores en web/js/ws_client.js
# ---------------------------------------------------------------------------
SIM_ROLL_AMP        = 10.0        # grados ±
SIM_PITCH_AMP       =  8.0        # grados ±
SIM_YAW_DRIFT_HZ    =  0.04       # Hz — frecuencia de deriva del yaw
SIM_FIRE_CYCLE_MS   =  6000       # ms — duración de un ciclo de disparo completo
