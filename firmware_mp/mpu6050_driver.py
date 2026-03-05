"""
mpu6050_driver.py — Driver I2C MicroPython para MPU-6050

Implementa el mismo filtro complementario que el firmware ESP32-S3 (mpu6050.c):
  ALPHA = 0.98  (peso del giróscopo)
  DT    = 0.02  (período de muestreo = 1/50 Hz)

Produce pitch, roll (±90°) y yaw (0..360°) en grados.
"""

import math
from machine import I2C, Pin


class MPU6050:
    # Dirección I2C
    ADDR = 0x68

    # Registro map (idéntico a firmware C)
    REG_PWR_MGMT_1  = 0x6B
    REG_SMPLRT_DIV  = 0x19
    REG_CONFIG      = 0x1A
    REG_GYRO_CFG    = 0x1B
    REG_ACCEL_CFG   = 0x1C
    REG_ACCEL_XOUT  = 0x3B   # 14 bytes: accel(6) + temp(2) + gyro(6)
    REG_WHO_AM_I    = 0x75

    # Factores de escala (idénticos a firmware C)
    ACCEL_SCALE = 16384.0   # LSB/g  para rango ±2g
    GYRO_SCALE  = 131.0     # LSB/(°/s) para rango ±250°/s

    # Filtro complementario — mismas constantes que mpu6050.h
    ALPHA = 0.98
    DT    = 0.02   # debe coincidir con BROADCAST_HZ = 50

    # 57.29578 = 180/π — evita llamar math.pi en cada muestra
    RAD2DEG = 57.29578

    def __init__(self, sda_pin, scl_pin):
        """
        Inicializa el bus I2C y el dispositivo MPU-6050.

        Args:
            sda_pin: número de pin GPIO para SDA
            scl_pin: número de pin GPIO para SCL
        Raises:
            RuntimeError: si el WHO_AM_I no coincide (sensor no encontrado)
        """
        self._i2c   = I2C(0, sda=Pin(sda_pin), scl=Pin(scl_pin), freq=400_000)
        self._pitch = 0.0
        self._roll  = 0.0
        self._yaw   = 0.0
        self._init_device()

    # ── I2C helpers ──────────────────────────────────────────────────────────

    def _write_reg(self, reg, val):
        self._i2c.writeto_mem(self.ADDR, reg, bytes([val]))

    def _read_regs(self, reg, n):
        return self._i2c.readfrom_mem(self.ADDR, reg, n)

    # ── Inicialización del dispositivo ────────────────────────────────────────

    def _init_device(self):
        who = self._read_regs(self.REG_WHO_AM_I, 1)[0]
        if who != self.ADDR:
            raise RuntimeError(
                "MPU-6050 no encontrado (WHO_AM_I=0x{:02X}, esperado 0x68)".format(who)
            )
        # Despierta del modo sleep
        self._write_reg(self.REG_PWR_MGMT_1,  0x00)
        # Divisor de muestra: 1kHz / (1+8) ≈ 111 Hz (coincide con firmware C)
        self._write_reg(self.REG_SMPLRT_DIV,  0x08)
        # Filtro paso bajo LPF ≈ 44 Hz
        self._write_reg(self.REG_CONFIG,      0x03)
        # Giróscopo ±250 °/s
        self._write_reg(self.REG_GYRO_CFG,    0x00)
        # Acelerómetro ±2g
        self._write_reg(self.REG_ACCEL_CFG,   0x00)

    # ── Lectura de sensores y filtro ──────────────────────────────────────────

    @staticmethod
    def _i16(hi, lo):
        """Convierte par de bytes big-endian a entero con signo 16-bit."""
        v = (hi << 8) | lo
        return v - 65536 if v > 32767 else v

    def read(self):
        """
        Lee el sensor y aplica el filtro complementario.

        Returns:
            (pitch, roll, yaw) en grados
        """
        raw = self._read_regs(self.REG_ACCEL_XOUT, 14)
        i16 = self._i16

        ax = i16(raw[0],  raw[1])  / self.ACCEL_SCALE   # g
        ay = i16(raw[2],  raw[3])  / self.ACCEL_SCALE
        az = i16(raw[4],  raw[5])  / self.ACCEL_SCALE
        # raw[6], raw[7] = temperatura (ignorada, igual que firmware C)
        gx = i16(raw[8],  raw[9])  / self.GYRO_SCALE    # °/s
        gy = i16(raw[10], raw[11]) / self.GYRO_SCALE
        gz = i16(raw[12], raw[13]) / self.GYRO_SCALE

        # Ángulos derivados del acelerómetro (idénticos a firmware C líneas 118-119)
        pitch_acc = math.atan2(ay, az)  * self.RAD2DEG
        roll_acc  = math.atan2(-ax, az) * self.RAD2DEG

        # Filtro complementario (idéntico a firmware C líneas 122-130)
        self._pitch = self.ALPHA * (self._pitch + gx * self.DT) \
                    + (1.0 - self.ALPHA) * pitch_acc
        self._roll  = self.ALPHA * (self._roll  + gy * self.DT) \
                    + (1.0 - self.ALPHA) * roll_acc
        self._yaw  += gz * self.DT

        # Envuelve yaw a 0..360
        self._yaw %= 360.0

        return self._pitch, self._roll, self._yaw

    def reset_yaw(self):
        """Reinicia el integrador de yaw a 0°."""
        self._yaw = 0.0
