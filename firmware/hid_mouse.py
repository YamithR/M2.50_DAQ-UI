# hid_mouse.py — Mouse USB HID Absoluto vía USB OTG del ESP32-S3.
#
# ── Nota sobre firmware ────────────────────────────────────────────────────
# El módulo usb.device requiere un firmware MicroPython compilado con soporte
# USB Device (TinyUSB). Las builds estándar de micropython.org para ESP32-S3
# NO incluyen esto por defecto.
#
# Para habilitarlo tienes tres opciones (en orden de dificultad):
#
#   OPCIÓN A — Instalar el módulo vía mip (si tu fw tiene machine.USBDevice):
#     import mip
#     mip.install("usb-device")
#     mip.install("usb-device-hid")
#     # Luego reiniciar y desplegar de nuevo.
#
#   OPCIÓN B — Flashear firmware con USB Device incluido:
#     Descarga el firmware "USB" (GENERIC_S3-USB) de:
#     https://micropython.org/download/ESP32_GENERIC_S3/
#     Busca el archivo con "USB" en el nombre.
#
#   OPCIÓN C — Compilar firmware personalizado:
#     Añadir MICROPY_HW_USB_DEVICE=1 al board config del ESP32-S3.
#
# pyb.USB_HID NO funciona en ESP32-S3 — es exclusivo de STM32/Pyboard.
#
# ── Modo de operación ──────────────────────────────────────────────────────
# Posición ABSOLUTA [0, 32767]:
#   ENC_H = 0 → X = 16383 (centro horizontal)
#   ENC_V = 0 → Y = 16383 (centro vertical)
#   Sobre-giro → satura en 0 o 32767 sin deriva.
# Flanco ascendente de S3 → clic izquierdo de HID_CLICK_MS ms.

import struct
import config

# ── Descriptor de reporte HID — Mouse absoluto 3 botones ──────────────────
_HID_REPORT_DESC = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    # Botones
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x03,        #     Usage Maximum (3)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x03,        #     Report Count (3)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    # Relleno (5 bits)
    0x95, 0x01, 0x75, 0x05, 0x81, 0x03,
    # X, Y absolutos 16 bits sin signo [0, 32767]
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,        #     Logical Minimum (0)
    0x26, 0xFF, 0x7F,  #     Logical Maximum (32767)
    0x35, 0x00,        #     Physical Minimum (0)
    0x46, 0xFF, 0x7F,  #     Physical Maximum (32767)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0xC0,              #   End Collection
    0xC0,              # End Collection
])

_ABS_MAX = 32767

# ── Estado interno ─────────────────────────────────────────────────────────
_hid_iface    = None   # objeto con método send_abs(buttons, x, y)
_prev_s3      = False
_click_frames = 0
_CLICK_FRAMES = max(1, round(config.HID_CLICK_MS / 20))

# ── Mapeo cuentas → coordenada absoluta [0, 32767] ────────────────────────
def _map_abs(cnt, cnt_min, cnt_max):
    if cnt <= cnt_min: return 0
    if cnt >= cnt_max: return _ABS_MAX
    return int((cnt - cnt_min) / (cnt_max - cnt_min) * _ABS_MAX)


# ══════════════════════════════════════════════════════════════════════════════
# APPROACH 1 — usb.device.hid  (ESP32-S3 con firmware USB Device)
# ══════════════════════════════════════════════════════════════════════════════
def _init_usb_device():
    """Intenta inicializar mediante usb.device.hid (micropython-lib)."""
    import usb.device
    from usb.device.hid import HIDInterface

    class _AbsMouse(HIDInterface):
        def __init__(self):
            super().__init__(
                _HID_REPORT_DESC,
                set_report_buf=None,   # sin Output entries en el descriptor
                protocol=0,            # _INTERFACE_PROTOCOL_NONE (no boot protocol)
                interface_str="M2 Abs Mouse",
                interval_ms=8,
            )
            self._report = bytearray(5)

        def send_abs(self, buttons, x, y):
            struct.pack_into('<BHH', self._report, 0, buttons, x, y)
            self.send_report(self._report)

    iface = _AbsMouse()
    usb.device.get().init(iface, builtin_driver=True)
    print("[hid] Mouse absoluto iniciado vía usb.device.hid (CDC+HID compuesto).")
    return iface


# ══════════════════════════════════════════════════════════════════════════════
# APPROACH 2 — machine.USBDevice directo + usb.device.hid frozen
# Algunos builds de ESP32-S3 tienen machine.USBDevice pero no el módulo
# usb instalado como .py. En ese caso intentamos instalar vía mip.
# ══════════════════════════════════════════════════════════════════════════════
def _try_mip_install():
    """Intenta instalar usb-device-hid con mip si machine.USBDevice existe."""
    import machine
    if not hasattr(machine, 'USBDevice'):
        return False   # Este firmware no tiene soporte USB Device

    print("[hid] machine.USBDevice detectado — intentando instalar usb-device-hid via mip …")
    try:
        import mip
        mip.install("usb-device")
        mip.install("usb-device-hid")
        print("[hid] Paquetes instalados. Reinicia el ESP32 para activar USB HID.")
    except Exception as e:
        print(f"[hid] mip falló ({e}). Instala manualmente:")
        print("[hid]   import mip; mip.install('usb-device'); mip.install('usb-device-hid')")
    return False   # Requiere reinicio — no podemos activarlo ahora


# ══════════════════════════════════════════════════════════════════════════════
# Inicialización pública
# ══════════════════════════════════════════════════════════════════════════════
def init() -> bool:
    """Registra el mouse HID absoluto. Retorna True si tiene éxito.

    Intenta en orden:
      1. usb.device.hid   — requiere firmware con soporte USB Device
      2. mip install      — si machine.USBDevice existe pero falta el módulo
    Si ninguno funciona, el sistema sigue funcionando sin HID.
    """
    global _hid_iface

    # ── Intento 1: usb.device.hid ──────────────────────────────────────
    # ImportError  → módulo .py no encontrado
    # AttributeError → machine.USBDevice no existe en el firmware
    try:
        _hid_iface = _init_usb_device()
        return True
    except (ImportError, AttributeError):
        pass
    except Exception as e:
        print(f"[hid] usb.device.hid error: {e}")

    # ── Intento 2: instalar vía mip ─────────────────────────────────────
    try:
        _try_mip_install()
    except ImportError:
        pass   # ni mip ni machine disponibles

    # ── Sin soporte USB Device ───────────────────────────────────────────
    print("[hid] USB HID desactivado — firmware sin soporte USB Device.")
    print("[hid] Opciones para habilitarlo:")
    print("[hid]   A) Si tienes WiFi: import mip; mip.install('usb-device-hid')")
    print("[hid]   B) Flashear firmware 'USB': https://micropython.org/download/ESP32_GENERIC_S3/")
    _hid_iface = None
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Actualización periódica — llamar a 50 Hz desde el broadcast loop
# ══════════════════════════════════════════════════════════════════════════════
def update(enc_h: int, enc_v: int, s3: bool) -> None:
    """Envía un reporte HID absoluto. No-op si HID no está disponible."""
    global _prev_s3, _click_frames

    if _hid_iface is None:
        return

    x = _map_abs(enc_h, config.HID_ENC_H_MIN, config.HID_ENC_H_MAX)
    y = _map_abs(enc_v, config.HID_ENC_V_MIN, config.HID_ENC_V_MAX)
    if config.HID_INVERT_Y:
        y = _ABS_MAX - y

    if s3 and not _prev_s3:
        _click_frames = _CLICK_FRAMES
    _prev_s3 = s3

    buttons = 0x01 if _click_frames > 0 else 0x00
    if _click_frames > 0:
        _click_frames -= 1

    try:
        _hid_iface.send_abs(buttons, x, y)
    except Exception:
        pass
