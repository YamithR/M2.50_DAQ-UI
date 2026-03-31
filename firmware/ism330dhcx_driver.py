# ism330dhcx_driver.py — Driver I2C nativo para el ISM330DHCX de STMicroelectronics.
# Sin dependencias de terceros. Filtro complementario integrado.
# Dirección I2C por defecto: 0x6B (SDO = VCC, JP1 abierto en SparkFun Qwiic).

import math
import time
from machine import I2C, Pin

# ---------------------------------------------------------------------------
# Mapa de registros del ISM330DHCX
# ---------------------------------------------------------------------------
_WHO_AM_I   = 0x0F
_CTRL1_XL   = 0x10   # Control acelerómetro
_CTRL2_G    = 0x11   # Control giróscopo
_CTRL3_C    = 0x12   # Control 3 (BDU, SW_RESET, IF_INC)
_STATUS_REG = 0x1E   # Bits: TDA | GDA | XLDA
_OUTX_L_G   = 0x22   # Giróscopo  — X_lo … Z_hi (6 bytes little-endian)
_OUTX_L_A   = 0x28   # Acelerómetro — X_lo … Z_hi (6 bytes little-endian)

_WHO_AM_I_VALUE = 0x6B   # Identificador único del chip

# ---------------------------------------------------------------------------
# Sensibilidades
# ---------------------------------------------------------------------------
_GYRO_SENS  = 17.5e-3    # dps / LSB   (FS ±500 dps, 16-bit)
_ACCEL_SENS = 0.122e-3   # g   / LSB   (FS ±4g,     16-bit)

# ---------------------------------------------------------------------------
# Filtro complementario
# ---------------------------------------------------------------------------
_ALPHA  = 0.98
_DT     = 0.02           # s — debe coincidir con PERIOD_MS = 20 ms en config.py
_RAD2DEG = 57.2957795   # 180 / π — pre-calculado


class ISM330DHCX:
    """Driver nativo para ISM330DHCX (IMU 6 ejes: acelerómetro + giróscopo).

    Parámetros:
        sda  -- número de pin GPIO para SDA
        scl  -- número de pin GPIO para SCL
        addr -- dirección I2C (0x6B si SDO=VCC, 0x6A si SDO=GND)
        freq -- frecuencia del bus I2C en Hz (por defecto 400 kHz)
    """

    def __init__(self, sda: int, scl: int, addr: int = 0x6B, freq: int = 400_000):
        self._i2c  = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
        self._addr = addr

        # Buffers reutilizables para lecturas I2C (evitan allocs en cada ciclo)
        self._buf6 = bytearray(6)
        self._buf1 = bytearray(1)

        self._init_sensor()

        # Estado del filtro complementario
        self._pitch = 0.0
        self._roll  = 0.0
        self._yaw   = 0.0

        # Offsets de calibración (se acumulan sobre el estado del filtro)
        self._pitch_offset = 0.0
        self._roll_offset  = 0.0

    # ------------------------------------------------------------------
    # Acceso a registros
    # ------------------------------------------------------------------
    def _write_reg(self, reg: int, val: int) -> None:
        self._buf1[0] = val
        self._i2c.writeto_mem(self._addr, reg, self._buf1)

    def _read_reg(self, reg: int, n: int = 1) -> bytes:
        return self._i2c.readfrom_mem(self._addr, reg, n)

    # ------------------------------------------------------------------
    # Inicialización del sensor
    # ------------------------------------------------------------------
    def _init_sensor(self) -> None:
        # Verificar identidad del chip
        who = self._read_reg(_WHO_AM_I, 1)[0]
        if who != _WHO_AM_I_VALUE:
            raise RuntimeError(
                f"ISM330DHCX no encontrado (WHO_AM_I=0x{who:02X}, esperado 0x{_WHO_AM_I_VALUE:02X})"
            )

        # 1. Software reset
        self._write_reg(_CTRL3_C, 0x01)
        time.sleep_ms(15)

        # 2. BDU (Block Data Update) + IF_INC (auto-increment de dirección en multibyte)
        self._write_reg(_CTRL3_C, 0x44)

        # 3. Acelerómetro: ODR 104 Hz, FS ±4g
        self._write_reg(_CTRL1_XL, 0x48)

        # 4. Giróscopo: ODR 104 Hz, FS ±500 dps
        self._write_reg(_CTRL2_G, 0x44)

    # ------------------------------------------------------------------
    # Espera por datos nuevos
    # ------------------------------------------------------------------
    def _wait_data(self, timeout_ms: int = 20) -> bool:
        """Espera hasta que STATUS_REG indique GDA+XLDA disponibles.
        Retorna True si los datos están listos, False si hubo timeout.
        """
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
            if (self._read_reg(_STATUS_REG, 1)[0] & 0x03) == 0x03:
                return True
        return False

    # ------------------------------------------------------------------
    # Lectura de datos crudos
    # ------------------------------------------------------------------
    @staticmethod
    def _s16(buf: bytearray, offset: int) -> int:
        """Interpreta dos bytes little-endian como entero con signo de 16 bits."""
        val = buf[offset] | (buf[offset + 1] << 8)
        return val if val < 32768 else val - 65536

    def _read_raw(self):
        """Lee giróscopo y acelerómetro.
        Retorna (gx, gy, gz, ax, ay, az) en dps y g respectivamente.
        Usa readfrom_mem_into para evitar allocs intermedios.
        """
        self._i2c.readfrom_mem_into(self._addr, _OUTX_L_G, self._buf6)
        gx = self._s16(self._buf6, 0) * _GYRO_SENS
        gy = self._s16(self._buf6, 2) * _GYRO_SENS
        gz = self._s16(self._buf6, 4) * _GYRO_SENS

        self._i2c.readfrom_mem_into(self._addr, _OUTX_L_A, self._buf6)
        ax = self._s16(self._buf6, 0) * _ACCEL_SENS
        ay = self._s16(self._buf6, 2) * _ACCEL_SENS
        az = self._s16(self._buf6, 4) * _ACCEL_SENS

        return gx, gy, gz, ax, ay, az

    # ------------------------------------------------------------------
    # Filtro complementario y lectura pública
    # ------------------------------------------------------------------
    def read_angles(self):
        """Retorna (roll, pitch, yaw) en grados con offsets de calibración aplicados.

        Si los datos no están listos dentro de 20 ms, retorna los últimos
        ángulos calculados para no bloquear el broadcast loop.
        """
        if not self._wait_data(20):
            return (
                self._roll  - self._roll_offset,
                self._pitch - self._pitch_offset,
                self._yaw,
            )

        gx, gy, gz, ax, ay, az = self._read_raw()

        # Estimaciones de ángulo por acelerómetro (referencia de gravedad)
        accel_pitch = math.atan2(ay, az) * _RAD2DEG
        accel_roll  = math.atan2(-ax, az) * _RAD2DEG

        # Filtro complementario: α = 0.98, DT = 0.02 s
        self._pitch = _ALPHA * (self._pitch + gy * _DT) + (1.0 - _ALPHA) * accel_pitch
        self._roll  = _ALPHA * (self._roll  + gx * _DT) + (1.0 - _ALPHA) * accel_roll
        self._yaw   = (self._yaw + gz * _DT) % 360.0

        return (
            self._roll  - self._roll_offset,
            self._pitch - self._pitch_offset,
            self._yaw,
        )

    # ------------------------------------------------------------------
    # Calibración
    # ------------------------------------------------------------------
    def reset_yaw(self) -> None:
        """Reinicia el integrador de yaw a 0°."""
        self._yaw = 0.0

    def reset_pitch(self) -> None:
        """Define la posición actual de pitch como referencia (0°)."""
        self._pitch_offset = self._pitch

    def reset_roll(self) -> None:
        """Define la posición actual de roll como referencia (0°)."""
        self._roll_offset = self._roll
