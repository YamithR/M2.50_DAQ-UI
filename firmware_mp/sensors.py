"""
sensors.py — Abstracción de sensores dual: simulado / hardware real

Expone tres funciones públicas:
  init()           → inicializa hardware o parámetros de simulación
  read() → dict    → devuelve paquete canónico de datos
  reset_yaw()      → reinicia integrador yaw a 0°

El paquete devuelto por read() es idéntico al sensor_data_t del firmware C:
  {s1, s2, s3, gas_valve, pitch, roll, yaw, enc_h, enc_v, ts}

El modo se selecciona con SIMULATE_SENSORS en config.py.
"""

import math
import time
import config

# ── Importación condicional de random ─────────────────────────────────────────
# MicroPython antiguo: urandom / MicroPython v1.22+: random
try:
    import random as _rnd
except ImportError:
    import urandom as _rnd

# =============================================================================
#  MODO SIMULADO
# =============================================================================

# Estado interno de la simulación (accedido solo desde el loop asyncio)
_yaw_sim   = 0.0
_enc_h     = 0
_enc_v     = 0
_enc_h_vel = 0     # velocidad actual encoder H (cuentas/tick)
_enc_v_vel = 0

def _small_noise(scale):
    """Ruido pequeño: float en [-scale/2, +scale/2]."""
    return (_rnd.getrandbits(8) / 255.0 - 0.5) * scale


def _sim_imu():
    """
    Genera IMU simulada:
    - pitch: sinusoide lenta ±SIM_PITCH_AMP° con ruido
    - roll:  sinusoide más lenta ±SIM_ROLL_AMP° con ruido
    - yaw:   integración de una señal oscilatoria lenta + ruido (deriva realista)
    """
    global _yaw_sim
    t = time.ticks_ms() / 1000.0   # segundos desde boot

    pitch = config.SIM_PITCH_AMP * math.sin(t * 0.40) + _small_noise(0.3)
    roll  = config.SIM_ROLL_AMP  * math.sin(t * 0.25 + 0.8) + _small_noise(0.2)

    # Yaw: deriva lenta como un giróscopo real integrando
    yaw_rate = 2.0 * math.sin(t * config.SIM_YAW_DRIFT_HZ * 2 * math.pi) \
               + _small_noise(0.1)
    _yaw_sim = (_yaw_sim + yaw_rate * 0.02) % 360.0  # DT = 1/BROADCAST_HZ = 0.02

    return pitch, roll, _yaw_sim


def _sim_encoders():
    """
    Encoders con movimiento tipo random walk con inercia.
    La velocidad cambia con baja probabilidad en cada tick.
    """
    global _enc_h, _enc_v, _enc_h_vel, _enc_v_vel

    # Probabilidad ≈3% de cambiar velocidad por tick (1/32)
    if _rnd.getrandbits(5) == 0:
        _enc_h_vel = _rnd.getrandbits(3) - 3   # -3..+4
    if _rnd.getrandbits(5) == 0:
        _enc_v_vel = _rnd.getrandbits(3) - 3

    _enc_h += _enc_h_vel
    _enc_v += _enc_v_vel
    return _enc_h, _enc_v


def _sim_digital():
    """
    Máquina de estados del ciclo de disparo del M2.50 (período = SIM_FIRE_CYCLE_MS):

    Fase 1 (30%): cerrojo bloqueado    → S1 activo
    Fase 2 (30%): retenedor enganchado → S1 + S2 activos
    Fase 3 ( 5%): válvula de gas abre  → S3 activo (pulso corto = disparo)
    Fase 4 (35%): retorno / reposo     → todos inactivos
    """
    cycle_ms = config.SIM_FIRE_CYCLE_MS
    t = time.ticks_ms() % cycle_ms

    if t < int(cycle_ms * 0.30):
        s1, s2, s3 = True,  False, False
    elif t < int(cycle_ms * 0.60):
        s1, s2, s3 = True,  True,  False
    elif t < int(cycle_ms * 0.65):
        s1, s2, s3 = False, False, True
    else:
        s1, s2, s3 = False, False, False

    return s1, s2, s3


def _sim_reset_yaw():
    global _yaw_sim
    _yaw_sim = 0.0


# =============================================================================
#  MODO HARDWARE REAL
# =============================================================================

_mpu        = None
_pin_s1     = None
_pin_s2     = None
_pin_s3     = None
_pin_h_b    = None   # fase B encoder H (leída en ISR de fase A)
_pin_v_b    = None   # fase B encoder V (leída en ISR de fase A)
_enc_h_real = 0
_enc_v_real = 0


def _isr_enc_h(pin):
    """ISR: flanco en encoder H fase A → determina dirección por estado de fase B."""
    global _enc_h_real
    _enc_h_real += 1 if _pin_h_b.value() else -1


def _isr_enc_v(pin):
    """ISR: flanco en encoder V fase A → determina dirección por estado de fase B."""
    global _enc_v_real
    _enc_v_real += 1 if _pin_v_b.value() else -1


def _init_real():
    """Inicializa MPU-6050, encoders por IRQ y sensores digitales activo-bajo."""
    global _mpu, _pin_s1, _pin_s2, _pin_s3, _pin_h_b, _pin_v_b

    from machine import Pin
    from mpu6050_driver import MPU6050

    # IMU
    _mpu = MPU6050(config.PIN_SDA, config.PIN_SCL)

    # Encoders — IRQ en fase A (ambos flancos), dirección por fase B
    _pin_h_b = Pin(config.PIN_ENC_H_B, Pin.IN, Pin.PULL_UP)
    _pin_v_b = Pin(config.PIN_ENC_V_B, Pin.IN, Pin.PULL_UP)

    pin_h_a = Pin(config.PIN_ENC_H_A, Pin.IN, Pin.PULL_UP)
    pin_v_a = Pin(config.PIN_ENC_V_A, Pin.IN, Pin.PULL_UP)
    pin_h_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_isr_enc_h)
    pin_v_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=_isr_enc_v)

    # Sensores digitales activo-bajo con pull-up
    _pin_s1 = Pin(config.PIN_S1, Pin.IN, Pin.PULL_UP)
    _pin_s2 = Pin(config.PIN_S2, Pin.IN, Pin.PULL_UP)
    _pin_s3 = Pin(config.PIN_S3, Pin.IN, Pin.PULL_UP)


def _real_read():
    """Lee hardware real y devuelve (s1, s2, s3, pitch, roll, yaw, enc_h, enc_v)."""
    pitch, roll, yaw = _mpu.read()
    # Activo-bajo: valor GPIO 0 → sensor activo → True
    s1 = not _pin_s1.value()
    s2 = not _pin_s2.value()
    s3 = not _pin_s3.value()
    return s1, s2, s3, pitch, roll, yaw, _enc_h_real, _enc_v_real


# =============================================================================
#  INTERFAZ PÚBLICA
# =============================================================================

def init():
    """
    Inicializa la capa de sensores según SIMULATE_SENSORS.
    Debe llamarse una vez antes del loop de broadcast.
    """
    if not config.SIMULATE_SENSORS:
        try:
            _init_real()
            print("Sensores: modo HARDWARE REAL")
        except Exception as e:
            print("Sensores: fallo hardware ({}) — usando simulación".format(e))
            # Forzar modo simulado si el hardware falla
            import config as _cfg
            _cfg.SIMULATE_SENSORS = True
    else:
        print("Sensores: modo SIMULADO")


def read():
    """
    Devuelve el paquete de datos canónico (idéntico al sensor_data_t del firmware C).

    Returns:
        dict con claves: s1, s2, s3, gas_valve, pitch, roll, yaw, enc_h, enc_v, ts
    """
    if config.SIMULATE_SENSORS:
        pitch, roll, yaw   = _sim_imu()
        enc_h, enc_v       = _sim_encoders()
        s1, s2, s3         = _sim_digital()
    else:
        s1, s2, s3, pitch, roll, yaw, enc_h, enc_v = _real_read()

    return {
        's1':        s1,
        's2':        s2,
        's3':        s3,
        'gas_valve': s3,      # gas_valve = s3, igual que firmware C
        'pitch':     pitch,
        'roll':      roll,
        'yaw':       yaw,
        'enc_h':     enc_h,
        'enc_v':     enc_v,
        'ts':        time.ticks_ms(),   # ms desde boot, igual que firmware C
    }


def reset_yaw():
    """Reinicia el integrador de yaw a 0°."""
    if config.SIMULATE_SENSORS:
        _sim_reset_yaw()
    else:
        if _mpu is not None:
            _mpu.reset_yaw()
