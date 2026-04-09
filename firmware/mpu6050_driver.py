# mpu6050_driver.py — Driver I2C nativo para MPU-6050 con filtro complementario.
#
# Compatible con: MPU-6050, MPU-6500, GY-521.
# API pública idéntica a gy89_driver.GY89 para permitir hot-swap transparente:
#   read_angles() → (roll, pitch, yaw)  [grados]
#   reset_yaw() / reset_pitch() / reset_roll()
#
# Sin magnetómetro → yaw integrado con giróscopo (deriva lenta, no absoluto).

import math
from machine import SoftI2C, Pin
import config

# ---------------------------------------------------------------------------
# Registros del MPU-6050
# ---------------------------------------------------------------------------
_WHO_AM_I     = 0x75
_PWR_MGMT_1   = 0x6B
_ACCEL_CONFIG = 0x1C
_GYRO_CONFIG  = 0x1B
_ACCEL_XOUT0  = 0x3B   # 6 bytes: XH XL YH YL ZH ZL
_GYRO_XOUT0   = 0x43   # 6 bytes: XH XL YH YL ZH ZL

# Sensibilidades con rango por defecto: ±2 g y ±250 °/s
_ACCEL_SCALE = 16384.0   # LSB/g
_GYRO_SCALE  = 131.0     # LSB/(°/s)

# Filtro complementario — idéntico al de gy89_driver
_ALPHA = 0.98
_DT    = config.PERIOD_MS / 1000.0   # 0.02 s a 50 Hz


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _s16(hi: int, lo: int) -> int:
    """Combina dos bytes en un entero con signo de 16 bits."""
    v = (hi << 8) | lo
    return v - 65536 if v >= 32768 else v


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
class MPU6050Driver:
    """Driver de bajo nivel para MPU-6050 / MPU-6500 con filtro complementario.

    Parámetros
    ----------
    sda_pin, scl_pin : int
        Números de GPIO para SDA y SCL (mismos que PIN_SDA / PIN_SCL).
    addr : int
        Dirección I2C. 0x68 cuando AD0=GND (defecto), 0x69 cuando AD0=VCC.
    freq : int
        Frecuencia del bus I2C en Hz.
    """

    def __init__(self, sda_pin: int, scl_pin: int,
                 addr: int = 0x68, freq: int = 400_000):
        self._i2c = SoftI2C(sda=Pin(sda_pin), scl=Pin(scl_pin), freq=freq)
        self._addr = addr

        # Verificar WHO_AM_I: 0x68 (MPU-6050) o 0x70 (MPU-6500)
        who = self._i2c.readfrom_mem(self._addr, _WHO_AM_I, 1)[0]
        if who not in (0x68, 0x70):
            raise OSError(
                f"MPU-6050: WHO_AM_I=0x{who:02X} inesperado "
                f"(esperado 0x68 o 0x70 en addr 0x{self._addr:02X})"
            )

        # Salir del modo sleep (bit 6 de PWR_MGMT_1)
        self._i2c.writeto_mem(self._addr, _PWR_MGMT_1, bytes([0x00]))

        # Rango acelerómetro ±2 g (0x00) y giróscopo ±250 °/s (0x00)
        self._i2c.writeto_mem(self._addr, _ACCEL_CONFIG, bytes([0x00]))
        self._i2c.writeto_mem(self._addr, _GYRO_CONFIG,  bytes([0x00]))

        # Estado interno del filtro complementario
        self._roll         = 0.0
        self._pitch        = 0.0
        self._yaw          = 0.0
        self._roll_offset  = 0.0
        self._pitch_offset = 0.0

    # -------------------------------------------------------------------------
    # Lectura de registros raw
    # -------------------------------------------------------------------------
    def _read_raw(self, reg: int):
        """Lee 6 bytes desde `reg` y devuelve (x, y, z) como int16."""
        b = self._i2c.readfrom_mem(self._addr, reg, 6)
        return _s16(b[0], b[1]), _s16(b[2], b[3]), _s16(b[4], b[5])

    # -------------------------------------------------------------------------
    # API pública — compatible con gy89_driver.GY89
    # -------------------------------------------------------------------------
    def read_angles(self) -> tuple:
        """Aplica el filtro complementario y devuelve (roll, pitch, yaw) en grados.

        Convención de ejes (igual que gy89_driver):
          roll  = rotación alrededor del eje X (longitudinal)
          pitch = rotación alrededor del eje Y (transversal)
          yaw   = rotación alrededor del eje Z (vertical), 0–360°
        """
        # ── Acelerómetro → g ─────────────────────────────────────────────────
        ax_r, ay_r, az_r = self._read_raw(_ACCEL_XOUT0)
        ax = ax_r / _ACCEL_SCALE
        ay = ay_r / _ACCEL_SCALE
        az = az_r / _ACCEL_SCALE

        # ── Giróscopo → °/s ──────────────────────────────────────────────────
        gx_r, gy_r, gz_r = self._read_raw(_GYRO_XOUT0)
        gx = gx_r / _GYRO_SCALE
        gy = gy_r / _GYRO_SCALE
        gz = gz_r / _GYRO_SCALE

        # ── Ángulos del acelerómetro (referencia estática) ────────────────────
        roll_acc  = math.degrees(math.atan2(ay, az))
        pitch_acc = math.degrees(math.atan2(-ax, az))

        # ── Filtro complementario (α=0.98) ────────────────────────────────────
        self._roll  = _ALPHA * (self._roll  + gx * _DT) + (1.0 - _ALPHA) * roll_acc
        self._pitch = _ALPHA * (self._pitch + gy * _DT) + (1.0 - _ALPHA) * pitch_acc
        self._yaw   = (self._yaw + gz * _DT) % 360.0

        return (
            self._roll  - self._roll_offset,
            self._pitch - self._pitch_offset,
            self._yaw,
        )

    def reset_yaw(self) -> None:
        """Pone el yaw a 0° en la posición actual."""
        self._yaw = 0.0

    def reset_pitch(self) -> None:
        """Calibra el offset de pitch a la posición actual."""
        self._pitch_offset = self._pitch

    def reset_roll(self) -> None:
        """Calibra el offset de roll a la posición actual."""
        self._roll_offset = self._roll
