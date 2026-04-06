# gy89_driver.py — Driver I2C nativo para el módulo GY-89 10DOF.
# Chips: L3GD20 (giróscopo 3 ejes), LSM303D (acelerómetro + magnetómetro),
#        BMP180 (barómetro + temperatura).
# Sin dependencias de terceros. Filtro complementario + yaw magnético integrado.

import math
import time
import struct
from machine import I2C, Pin

# ─────────────────────────────────────────────────────────────────────────────
# L3GD20 — Giróscopo 3 ejes
# ─────────────────────────────────────────────────────────────────────────────
_GYR_WHO_AM_I   = 0x0F
_GYR_CTRL_REG1  = 0x20   # ODR, BW, PD, ejes
_GYR_CTRL_REG4  = 0x23   # BDU, FS
_GYR_OUT_X_L    = 0x28   # 6 bytes little-endian: Gx, Gy, Gz

_GYR_WHO_VAL_L3GD20  = 0xD4
_GYR_WHO_VAL_L3GD20H = 0xD7

# FS=±500 dps → sensibilidad 17.5 mdps/LSB
_GYR_SENS = 17.5e-3

# ─────────────────────────────────────────────────────────────────────────────
# LSM303D — Acelerómetro + Magnetómetro
# ─────────────────────────────────────────────────────────────────────────────
_ACC_WHO_AM_I   = 0x0F
_ACC_WHO_VAL    = 0x49
_ACC_CTRL1      = 0x20   # ODR accel, BDU, ejes
_ACC_CTRL2      = 0x21   # AFS (full scale accel)
_MAG_CTRL5      = 0x24   # Resolución mag. + ODR mag.
_MAG_CTRL6      = 0x25   # Full scale mag.
_MAG_CTRL7      = 0x26   # Modo mag. (continuo)
_ACC_OUT_X_L    = 0x28   # 6 bytes accel (con bit 0x80 para auto-increment)
_MAG_OUT_X_L    = 0x08   # 6 bytes mag   (con bit 0x80 para auto-increment)

# FS=±2g → 0.061 mg/LSB (16-bit con signo)
_ACC_SENS = 0.061e-3
# FS=±2 Gauss → 0.080 mGauss/LSB
_MAG_SENS = 0.080e-3

# ─────────────────────────────────────────────────────────────────────────────
# BMP180 — Barómetro + Temperatura
# ─────────────────────────────────────────────────────────────────────────────
_BMP_ADDR       = 0x77
_BMP_CAL_REG    = 0xAA   # 22 bytes de calibración (AC1..MD)
_BMP_CTRL       = 0xF4
_BMP_DATA       = 0xF6
_BMP_CMD_TEMP   = 0x2E
_BMP_CMD_PRES   = 0x34   # + (OSS<<6) para sobremuestreo
_BMP_OSS        = 0      # 0=ultra-low-power (4.5 ms), suficiente a 50 Hz
_SEA_LEVEL_HPA  = 1013.25

# ─────────────────────────────────────────────────────────────────────────────
# Filtro complementario
# ─────────────────────────────────────────────────────────────────────────────
_ALPHA   = 0.98          # peso del giróscopo
_DT      = 0.02          # período de integración (debe coincidir con PERIOD_MS=20 ms)
_RAD2DEG = 57.2957795

# Fracción del yaw magnético usada en la fusión (el resto viene del giróscopo)
_MAG_YAW_BLEND = 0.05


class GY89:
    """Driver nativo para GY-89 10DOF.

    Parámetros:
        sda      -- número de pin GPIO para SDA
        scl      -- número de pin GPIO para SCL
        gyr_addr -- dirección I2C del L3GD20   (0x6B si SDO=High, 0x6A si SDO=Low)
        acc_addr -- dirección I2C del LSM303D  (0x1E si SA0=Low,  0x1D si SA0=High)
        freq     -- frecuencia del bus I2C en Hz
    """

    def __init__(self, sda: int, scl: int,
                 gyr_addr: int = 0x6B,
                 acc_addr: int = 0x1E,
                 freq: int = 400_000):

        self._i2c     = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
        self._gyr     = gyr_addr
        self._acc     = acc_addr

        # Buffers reutilizables para evitar allocations en cada ciclo
        self._buf6 = bytearray(6)
        self._buf1 = bytearray(1)

        self._init_gyro()
        self._init_acc_mag()
        self._init_bmp()

        # Estado del filtro complementario
        self._roll  = 0.0
        self._pitch = 0.0
        self._yaw   = 0.0

        # Offsets de calibración
        self._roll_offset  = 0.0
        self._pitch_offset = 0.0

        # Barómetro (se actualiza cada 10 ciclos = 5 Hz para no bloquear)
        self._baro_cnt     = 0
        self._pressure_hpa = 1013.25
        self._temp_c       = 25.0
        self._altitude_m   = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Acceso bajo nivel a registros I2C
    # ──────────────────────────────────────────────────────────────────────────
    def _wr(self, addr: int, reg: int, val: int) -> None:
        self._buf1[0] = val
        self._i2c.writeto_mem(addr, reg, self._buf1)

    def _rd(self, addr: int, reg: int, n: int = 1) -> bytes:
        return self._i2c.readfrom_mem(addr, reg, n)

    def _rd_into(self, addr: int, reg: int, buf: bytearray) -> None:
        """Lectura multi-byte con auto-incremento (bit 7 de la dirección)."""
        self._i2c.readfrom_mem_into(addr, reg | 0x80, buf)

    @staticmethod
    def _s16(buf: bytearray, offset: int) -> int:
        val = buf[offset] | (buf[offset + 1] << 8)
        return val if val < 32768 else val - 65536

    # ──────────────────────────────────────────────────────────────────────────
    # Inicialización L3GD20
    # ──────────────────────────────────────────────────────────────────────────
    def _init_gyro(self) -> None:
        who = self._rd(self._gyr, _GYR_WHO_AM_I)[0]
        if who not in (_GYR_WHO_VAL_L3GD20, _GYR_WHO_VAL_L3GD20H):
            raise RuntimeError(
                f"L3GD20 no encontrado en 0x{self._gyr:02X} "
                f"(WHO_AM_I=0x{who:02X})"
            )
        # CTRL_REG1: DR=00 (95 Hz), BW=00 (cutoff 12.5 Hz), PD=1, Zen=Yen=Xen=1
        self._wr(self._gyr, _GYR_CTRL_REG1, 0x0F)
        # CTRL_REG4: BDU=1, FS=±500 dps (FS[1:0]=01)
        self._wr(self._gyr, _GYR_CTRL_REG4, 0x90)

    def _read_gyro(self):
        """Retorna (gx, gy, gz) en grados/segundo."""
        self._rd_into(self._gyr, _GYR_OUT_X_L, self._buf6)
        gx = self._s16(self._buf6, 0) * _GYR_SENS
        gy = self._s16(self._buf6, 2) * _GYR_SENS
        gz = self._s16(self._buf6, 4) * _GYR_SENS
        return gx, gy, gz

    # ──────────────────────────────────────────────────────────────────────────
    # Inicialización LSM303D
    # ──────────────────────────────────────────────────────────────────────────
    def _init_acc_mag(self) -> None:
        who = self._rd(self._acc, _ACC_WHO_AM_I)[0]
        if who != _ACC_WHO_VAL:
            raise RuntimeError(
                f"LSM303D no encontrado en 0x{self._acc:02X} "
                f"(WHO_AM_I=0x{who:02X}, esperado 0x{_ACC_WHO_VAL:02X})"
            )
        # CTRL1: AODR=0101 (100 Hz), BDU=1, Zen=Yen=Xen=1
        self._wr(self._acc, _ACC_CTRL1, 0x57)
        # CTRL2: AFS=000 (±2g)
        self._wr(self._acc, _ACC_CTRL2, 0x00)
        # CTRL5: M_RES=11 (alta resolución), M_ODR=100 (50 Hz)
        #   bit7=0(TEMP_EN off), bits6:5=11, bits4:2=100, bits1:0=00
        #   = 0b01110000 = 0x70
        self._wr(self._acc, _MAG_CTRL5, 0x70)
        # CTRL6: MFS=00 (±2 Gauss)
        self._wr(self._acc, _MAG_CTRL6, 0x00)
        # CTRL7: MD=00 (modo continuo)
        self._wr(self._acc, _MAG_CTRL7, 0x00)

    def _read_accel(self):
        """Retorna (ax, ay, az) en g."""
        self._rd_into(self._acc, _ACC_OUT_X_L, self._buf6)
        ax = self._s16(self._buf6, 0) * _ACC_SENS
        ay = self._s16(self._buf6, 2) * _ACC_SENS
        az = self._s16(self._buf6, 4) * _ACC_SENS
        return ax, ay, az

    def _read_mag(self):
        """Retorna (mx, my, mz) en Gauss."""
        self._rd_into(self._acc, _MAG_OUT_X_L, self._buf6)
        mx = self._s16(self._buf6, 0) * _MAG_SENS
        my = self._s16(self._buf6, 2) * _MAG_SENS
        mz = self._s16(self._buf6, 4) * _MAG_SENS
        return mx, my, mz

    # ──────────────────────────────────────────────────────────────────────────
    # Inicialización BMP180
    # ──────────────────────────────────────────────────────────────────────────
    def _init_bmp(self) -> None:
        """Lee los 22 bytes de calibración y los deserializa."""
        raw = self._rd(_BMP_ADDR, _BMP_CAL_REG, 22)
        # AC1..AC3: signed, AC4..AC6: unsigned, B1..MD: signed
        self._cal = struct.unpack('>hhhHHHhhhhh', raw)

    def _bmp_read_temp_raw(self) -> int:
        self._wr(_BMP_ADDR, _BMP_CTRL, _BMP_CMD_TEMP)
        time.sleep_ms(5)
        d = self._rd(_BMP_ADDR, _BMP_DATA, 2)
        return (d[0] << 8) | d[1]

    def _bmp_read_pres_raw(self) -> int:
        self._wr(_BMP_ADDR, _BMP_CTRL, _BMP_CMD_PRES + (_BMP_OSS << 6))
        time.sleep_ms(5)
        d = self._rd(_BMP_ADDR, _BMP_DATA, 3)
        return ((d[0] << 16) | (d[1] << 8) | d[2]) >> (8 - _BMP_OSS)

    def _bmp_compensate(self, ut: int, up: int):
        """Aplicar compensación BMP180 (aritmética entera según datasheet)."""
        AC1, AC2, AC3, AC4, AC5, AC6, B1, B2, MB, MC, MD = self._cal

        X1 = ((ut - AC6) * AC5) >> 15
        X2 = (MC << 11) // (X1 + MD)
        B5 = X1 + X2
        T  = (B5 + 8) >> 4                          # en 0.1 °C

        B6 = B5 - 4000
        X1 = (B2 * ((B6 * B6) >> 12)) >> 11
        X2 = (AC2 * B6) >> 11
        X3 = X1 + X2
        B3 = (((AC1 * 4 + X3) << _BMP_OSS) + 2) >> 2
        X1 = (AC3 * B6) >> 13
        X2 = (B1 * ((B6 * B6) >> 12)) >> 16
        X3 = ((X1 + X2) + 2) >> 2
        B4 = (AC4 * (X3 + 32768)) >> 15
        B7 = (up - B3) * (50000 >> _BMP_OSS)

        if B7 < 0x80000000:
            p = (B7 * 2) // B4
        else:
            p = (B7 // B4) * 2

        X1 = (p >> 8) * (p >> 8)
        X1 = (X1 * 3038) >> 16
        X2 = (-7357 * p) >> 16
        p  = p + ((X1 + X2 + 3791) >> 4)

        return T / 10.0, p / 100.0     # °C, hPa

    def _update_baro(self) -> None:
        try:
            ut = self._bmp_read_temp_raw()
            up = self._bmp_read_pres_raw()
            t, p = self._bmp_compensate(ut, up)
            alt  = 44330.0 * (1.0 - (p / _SEA_LEVEL_HPA) ** (1.0 / 5.255))
            self._temp_c       = t
            self._pressure_hpa = p
            self._altitude_m   = alt
        except Exception:
            pass   # Mantiene los valores previos

    # ──────────────────────────────────────────────────────────────────────────
    # Filtro complementario con fusión magnética para yaw
    # ──────────────────────────────────────────────────────────────────────────
    def _update_filter(self,
                       gx, gy, gz,
                       ax, ay, az,
                       mx, my, mz) -> None:

        # Estimación de roll/pitch por acelerómetro
        accel_pitch = math.atan2(ay, az)  * _RAD2DEG
        accel_roll  = math.atan2(-ax, az) * _RAD2DEG

        # Filtro complementario roll/pitch
        self._pitch = _ALPHA * (self._pitch + gy * _DT) + (1.0 - _ALPHA) * accel_pitch
        self._roll  = _ALPHA * (self._roll  + gx * _DT) + (1.0 - _ALPHA) * accel_roll

        # Yaw magnético compensado por inclinación (tilt-compensated heading)
        roll_r  = self._roll  / _RAD2DEG
        pitch_r = self._pitch / _RAD2DEG
        mx2 = mx * math.cos(pitch_r) + mz * math.sin(pitch_r)
        my2 = (mx * math.sin(roll_r) * math.sin(pitch_r)
               + my * math.cos(roll_r)
               - mz * math.sin(roll_r) * math.cos(pitch_r))
        mag_yaw = math.atan2(-my2, mx2) * _RAD2DEG
        if mag_yaw < 0.0:
            mag_yaw += 360.0

        # Fusión giróscopo + magnetómetro para yaw
        gyro_yaw = (self._yaw + gz * _DT) % 360.0
        self._yaw = ((1.0 - _MAG_YAW_BLEND) * gyro_yaw
                     + _MAG_YAW_BLEND * mag_yaw) % 360.0

    # ──────────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────────
    def read_angles(self):
        """Retorna (roll, pitch, yaw) en grados, con offsets de calibración.

        Actualiza también el barómetro cada 10 llamadas (~5 Hz).
        """
        try:
            gx, gy, gz = self._read_gyro()
            ax, ay, az = self._read_accel()
            mx, my, mz = self._read_mag()
            self._update_filter(gx, gy, gz, ax, ay, az, mx, my, mz)
        except Exception:
            pass   # Devuelve los ángulos previos

        self._baro_cnt += 1
        if self._baro_cnt >= 10:
            self._baro_cnt = 0
            self._update_baro()

        return (
            self._roll  - self._roll_offset,
            self._pitch - self._pitch_offset,
            self._yaw,
        )

    def read_baro(self):
        """Retorna (pressure_hpa, temp_c, altitude_m) del último ciclo BMP180."""
        return self._pressure_hpa, self._temp_c, self._altitude_m

    # ──────────────────────────────────────────────────────────────────────────
    # Calibración
    # ──────────────────────────────────────────────────────────────────────────
    def reset_yaw(self) -> None:
        """Reinicia el integrador de yaw a 0°."""
        self._yaw = 0.0

    def reset_pitch(self) -> None:
        """Define la posición actual de pitch como referencia (0°)."""
        self._pitch_offset = self._pitch

    def reset_roll(self) -> None:
        """Define la posición actual de roll como referencia (0°)."""
        self._roll_offset = self._roll
