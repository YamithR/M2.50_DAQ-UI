# sensors.py — Abstracción dual: sensores simulados / hardware real.
# Interfaz pública: init(), read() → dict, reset_yaw(), reset_pitch(), reset_roll(), reset_encoders()

import time
import math
import micropython
import config

# ---------------------------------------------------------------------------
# Estado del módulo
# ---------------------------------------------------------------------------
_imu      = None             # Instancia GY89 o MPU6050Driver (modo hw)
_pin_s1   = None
_pin_s2   = None
_pin_s3   = None
_pin_eh_b = None             # Encoder H, fase B (lectura en ISR)
_pin_ev_b = None             # Encoder V, fase B (lectura en ISR)

# Contadores de encoder en lista mutable para que los ISR puedan modificarlos
# sin necesidad de closure con 'global' (más seguro en MicroPython ISR)
_counters = [0, 0]           # [enc_h, enc_v]

# Métodos pre-enlazados para el hot-path de las ISR.
# Se asignan en init() para evitar el doble lookup (global + atributo) en cada flanco.
_eh_b_val = None
_ev_b_val = None

# ---------------------------------------------------------------------------
# ISR de encoders — @micropython.native compila a ARM nativo (~3× más rápido)
# ---------------------------------------------------------------------------
@micropython.native
def _enc_h_isr(p):
    # Cuadratura: dirección = A_actual XOR B
    # A↑ B=0 → +1 | A↓ B=1 → +1 | A↑ B=1 → -1 | A↓ B=0 → -1
    _counters[0] += 1 if (p.value() ^ _eh_b_val()) else -1


@micropython.native
def _enc_v_isr(p):
    _counters[1] += 1 if (p.value() ^ _ev_b_val()) else -1


# ---------------------------------------------------------------------------
# Constantes de simulación pre-calculadas (se inicializan una sola vez)
# ---------------------------------------------------------------------------
_SIM_DT        = config.PERIOD_MS / 1000.0
_SIM_YAW_OMEGA = config.SIM_YAW_DRIFT_HZ * 2.0 * math.pi

# Estado de simulación
_sim_t         = 0.0
_sim_yaw       = 0.0
_sim_eh        = 0
_sim_ev        = 0
_sim_eh_vel    = 0
_sim_ev_vel    = 0


# ---------------------------------------------------------------------------
# Pública: init()
# ---------------------------------------------------------------------------
def init() -> None:
    """Inicializa hardware o parámetros de simulación según config.SIMULATE_SENSORS."""
    global _imu, _pin_s1, _pin_s2, _pin_s3, _pin_eh_b, _pin_ev_b, _eh_b_val, _ev_b_val

    if config.SIMULATE_SENSORS:
        print("[sensors] Modo SIMULADO — sin hardware externo requerido.")
        return

    # ---- Hardware real ----
    from machine import Pin

    # Sensores digitales (activo-bajo → pull-up interno)
    _pin_s1 = Pin(config.PIN_S1, Pin.IN, Pin.PULL_UP)
    _pin_s2 = Pin(config.PIN_S2, Pin.IN, Pin.PULL_UP)
    _pin_s3 = Pin(config.PIN_S3, Pin.IN, Pin.PULL_UP)

    # Encoders cuadratura: IRQ en fase A, dirección por estado de fase B
    # LPD3806: salida NPN open-collector → pull-up interno obligatorio
    _pin_eh_b = Pin(config.PIN_ENC_H_B, Pin.IN, Pin.PULL_UP)
    _pin_ev_b = Pin(config.PIN_ENC_V_B, Pin.IN, Pin.PULL_UP)
    pin_eh_a  = Pin(config.PIN_ENC_H_A, Pin.IN, Pin.PULL_UP)
    pin_ev_a  = Pin(config.PIN_ENC_V_A, Pin.IN, Pin.PULL_UP)

    # Enlazar métodos en init para que las ISR no hagan lookup de atributo en cada flanco
    _eh_b_val = _pin_eh_b.value
    _ev_b_val = _pin_ev_b.value

    pin_eh_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_enc_h_isr)
    pin_ev_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_enc_v_isr)

    # IMU/Barómetro GY-89 — fallo no fatal: encoders y digitales siguen funcionando
    try:
        import gy89_driver
        _imu = gy89_driver.GY89(
            config.PIN_SDA, config.PIN_SCL,
            gyr_addr=config.IMU_GYR_ADDR,
            acc_addr=config.IMU_ACC_ADDR,
            freq=config.IMU_FREQ,
        )
        print("[sensors] GY-89 (L3GD20 + LSM303D + BMP180) inicializado correctamente.")
    except Exception as e:
        print(f"[sensors] AVISO — GY-89 no disponible: {e} — probando MPU-6050 …")
        _imu = None
        try:
            import mpu6050_driver
            _imu = mpu6050_driver.MPU6050Driver(
                config.PIN_SDA, config.PIN_SCL,
                addr=config.IMU_MPU6050_ADDR,
                freq=config.IMU_FREQ,
            )
            print("[sensors] MPU-6050 (GY-521) inicializado como fallback de IMU.")
        except Exception as e2:
            print(f"[sensors] AVISO — MPU-6050 tampoco disponible: {e2}")
            _imu = None

    print("[sensors] Hardware inicializado.")


# ---------------------------------------------------------------------------
# Pública: read() → dict
# ---------------------------------------------------------------------------
def read() -> dict:
    """Devuelve el paquete canónico de datos del sistema."""
    if config.SIMULATE_SENSORS:
        return _read_simulated()
    return _read_hardware()


# ---------------------------------------------------------------------------
# Pública: calibración
# ---------------------------------------------------------------------------
def reset_yaw() -> None:
    global _sim_yaw
    if config.SIMULATE_SENSORS:
        _sim_yaw = 0.0
    elif _imu is not None:
        _imu.reset_yaw()


def reset_pitch() -> None:
    if not config.SIMULATE_SENSORS and _imu is not None:
        _imu.reset_pitch()


def reset_roll() -> None:
    if not config.SIMULATE_SENSORS and _imu is not None:
        _imu.reset_roll()


def reset_encoders() -> None:
    """Pone a cero ambos contadores de encoder (hardware y simulación)."""
    _counters[0] = 0
    _counters[1] = 0


def _map_enc(cnt, cnt_min, cnt_max, ang_min, ang_max):
    """Mapeo lineal con saturación: cuentas → grados."""
    t = max(0.0, min(1.0, (cnt - cnt_min) / (cnt_max - cnt_min)))
    return ang_min + t * (ang_max - ang_min)


# ---------------------------------------------------------------------------
# Lectura — hardware real
# ---------------------------------------------------------------------------
def _read_hardware() -> dict:
    # Digitales: GPIO=0 (pull-up activo) → sensor activo → valor lógico True
    s1 = not _pin_s1.value() if _pin_s1 else False
    s2 = not _pin_s2.value() if _pin_s2 else False
    s3 = not _pin_s3.value() if _pin_s3 else False

    if _imu is not None:
        _raw = _imu.read_angles()   # (roll_raw, pitch_raw, yaw_raw)
        _m, _s = config.IMU_AXIS_MAP, config.IMU_AXIS_SIGN
        roll  = _s[0] * _raw[_m[0]]
        pitch = _s[1] * _raw[_m[1]]
        yaw   = (_s[2] * _raw[_m[2]]) % 360.0  # normaliza a 0–360 tras invertir signo
    else:
        roll = pitch = yaw = 0.0

    yaw_signed = ((yaw + 180.0) % 360.0) - 180.0

    return {
        "s1": s1, "s2": s2, "s3": s3, "gas_valve": s3,
        "roll":         round(roll,         2),
        "pitch":        round(pitch,        2),
        "yaw":          round(yaw,          2),
        "yaw_signed":   round(yaw_signed,   2),
        "enc_h":        _counters[0],
        "enc_v":        _counters[1],
        "enc_h_deg":    round(_map_enc(_counters[0], config.ENC_H_CNT_MIN, config.ENC_H_CNT_MAX, config.ENC_H_ANG_MIN, config.ENC_H_ANG_MAX), 1),
        "enc_v_deg":    round(_map_enc(_counters[1], config.ENC_V_CNT_MIN, config.ENC_V_CNT_MAX, config.ENC_V_ANG_MIN, config.ENC_V_ANG_MAX), 1),
        "ts":           round(time.ticks_ms() / 1000, 1),
    }


# ---------------------------------------------------------------------------
# Lectura — simulación
# ---------------------------------------------------------------------------
def _read_simulated() -> dict:
    global _sim_t, _sim_yaw, _sim_eh, _sim_ev, _sim_eh_vel, _sim_ev_vel

    import random

    t = _sim_t

    # Roll y pitch oscilantes
    roll  = config.SIM_ROLL_AMP  * math.cos(t * 0.35)
    pitch = config.SIM_PITCH_AMP * math.sin(t * 0.40)

    # Yaw: integración de señal de giróscopo simulada (deriva senoidal)
    _sim_yaw = (_sim_yaw + 2.0 * math.sin(t * _SIM_YAW_OMEGA) * _SIM_DT) % 360.0
    yaw_signed = ((_sim_yaw + 180.0) % 360.0) - 180.0

    # Encoders: random walk con inercia (~3% probabilidad de cambiar velocidad)
    if random.random() < 0.03:
        _sim_eh_vel = random.randint(-3, 3)
    if random.random() < 0.03:
        _sim_ev_vel = random.randint(-3, 3)
    _sim_eh += _sim_eh_vel
    _sim_ev += _sim_ev_vel

    # Máquina de estados del ciclo de disparo (4 fases)
    phase = (time.ticks_ms() % config.SIM_FIRE_CYCLE_MS) / config.SIM_FIRE_CYCLE_MS
    if phase < 0.30:
        s1, s2, s3 = True,  False, False   # Bloqueado
    elif phase < 0.60:
        s1, s2, s3 = False, True,  False   # Retenedor (cerrojo amartillado y listo)
    elif phase < 0.65:
        s1, s2, s3 = False, False, True    # Disparo (válvula)
    else:
        s1, s2, s3 = False, False, False   # Reposo

    _sim_t += _SIM_DT

    return {
        "s1": s1, "s2": s2, "s3": s3, "gas_valve": s3,
        "roll":         round(roll,         2),
        "pitch":        round(pitch,        2),
        "yaw":          round(_sim_yaw,     2),
        "yaw_signed":   round(yaw_signed,   2),
        "enc_h":        _sim_eh,
        "enc_v":        _sim_ev,
        "enc_h_deg":    round(_map_enc(_sim_eh, config.ENC_H_CNT_MIN, config.ENC_H_CNT_MAX, config.ENC_H_ANG_MIN, config.ENC_H_ANG_MAX), 1),
        "enc_v_deg":    round(_map_enc(_sim_ev, config.ENC_V_CNT_MIN, config.ENC_V_CNT_MAX, config.ENC_V_ANG_MIN, config.ENC_V_ANG_MAX), 1),
        "ts":           round(time.ticks_ms() / 1000, 1),
    }

