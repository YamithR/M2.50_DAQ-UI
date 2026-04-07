#!/usr/bin/env python3
"""
deploy.py — Despliega todos los archivos del proyecto M2.50 DAQ-UI al ESP32-S3.

Uso:
    python3 deploy.py [--port /dev/ttyACM0]

Maneja el timing del USB CDC compuesto (CDC+HID) del ESP32-S3:
  1. Detecta el puerto automáticamente si no se especifica.
  2. Espera a que el puerto aparezca después del reset.
  3. Envía Ctrl+C durante la ventana de 3 s de main.py para interrumpir.
  4. Sube todos los archivos vía raw REPL.
  5. Ejecuta un hard-reset al finalizar.
"""

import sys
import os
import time
import argparse
import struct
import pathlib
import binascii

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Instala pyserial:  pip install pyserial")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# MANIFIESTO DE ARCHIVOS
# base_dir es la raíz del repositorio (donde está deploy.py)
# ──────────────────────────────────────────────────────────────────────────────
BASE = pathlib.Path(__file__).parent

FILES = [
    # (ruta_local_relativa_al_repo, ruta_destino_en_ESP32)
    ("firmware/boot.py",                    "boot.py"),
    ("firmware/config.py",                  "config.py"),
    ("firmware/main.py",                    "main.py"),
    ("firmware/sensors.py",                 "sensors.py"),
    ("firmware/server.py",                  "server.py"),
    ("firmware/gy89_driver.py",             "gy89_driver.py"),
    ("firmware/hid_mouse.py",               "hid_mouse.py"),
    # lib/usb
    ("firmware/lib/usb/__init__.py",        "lib/usb/__init__.py"),
    ("firmware/lib/usb/device/__init__.py", "lib/usb/device/__init__.py"),
    ("firmware/lib/usb/device/core.py",     "lib/usb/device/core.py"),
    ("firmware/lib/usb/device/hid.py",      "lib/usb/device/hid.py"),
    # web
    ("web/index.html",                      "web/index.html"),
    ("web/js/ws_client.js",                 "web/js/ws_client.js"),
    ("web/js/svg_bolt.js",                  "web/js/svg_bolt.js"),
    ("web/js/gauges.js",                    "web/js/gauges.js"),
    ("web/js/encoders.js",                  "web/js/encoders.js"),
    ("web/js/charts.js",                    "web/js/charts.js"),
    ("web/js/bt_toggle.js",                 "web/js/bt_toggle.js"),
]

DIRS = [
    "lib",
    "lib/usb",
    "lib/usb/device",
    "web",
    "web/js",
]

CHIP_VID = 0x1a86   # CH340 / CH9102 / native ESP32-S3 CDC


# ──────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE PUERTO
# ──────────────────────────────────────────────────────────────────────────────

def find_port() -> str | None:
    """Devuelve el primer puerto USB CDC que parezca un ESP32."""
    esp_vids = {0x1a86, 0x10c4, 0x0403, 0x303a, 0x239a, 0x2341}
    for p in serial.tools.list_ports.comports():
        if p.vid in esp_vids:
            return p.device
    # fallback
    for p in serial.tools.list_ports.comports():
        dev = p.device
        if "ACM" in dev or "USB" in dev:
            return dev
    return None


def wait_for_port(port: str, timeout: float = 10.0) -> bool:
    """Espera a que el puerto aparezca (después de un reset USB)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(port):
            time.sleep(0.3)  # déjalo estabilizar
            return True
        time.sleep(0.2)
    return False


# ──────────────────────────────────────────────────────────────────────────────
# RAW REPL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

TIMEOUT_CMD = 10.0   # segundos por comando


def _read_until(ser: serial.Serial, pattern: bytes, timeout: float = 5.0) -> bytes:
    buf = b""
    t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            if pattern in buf:
                return buf
    raise TimeoutError(f"Esperando {pattern!r}, recibido: {buf!r}")


def enter_raw_repl(ser: serial.Serial) -> None:
    """Interrumpe el programa en ejecución y entra al raw REPL."""
    ser.timeout = 0.1
    # Limpiar buffer
    ser.reset_input_buffer()
    # Doble Ctrl+C para interrumpir cualquier programa
    ser.write(b"\r\x03\x03")
    time.sleep(0.5)
    ser.reset_input_buffer()
    # Ctrl+A = entrar raw REPL
    ser.write(b"\r\x01")
    _read_until(ser, b"raw REPL; CTRL-B to exit", timeout=5.0)
    print("  [repl] Raw REPL activo.")


def exec_raw(ser: serial.Serial, code: str) -> str:
    """Ejecuta código Python en raw REPL. Devuelve stdout."""
    ser.reset_input_buffer()
    ser.write(code.encode() + b"\x04")  # Ctrl+D = ejecutar
    # Leer hasta OK / Error
    buf = b""
    t0 = time.time()
    while time.time() - t0 < TIMEOUT_CMD:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf += chunk
            if buf.startswith(b"OK") and buf.count(b"\x04") >= 2:
                break
    if not buf.startswith(b"OK"):
        raise RuntimeError(f"Error ejecutando código:\n{buf.decode(errors='replace')}")
    # buf = b"OK" + stdout + b"\x04" + stderr + b"\x04"
    parts = buf[2:].split(b"\x04")
    stdout = parts[0].decode(errors="replace")
    stderr = parts[1].decode(errors="replace") if len(parts) > 1 else ""
    if stderr.strip():
        raise RuntimeError(f"Error en ESP32:\n{stderr}")
    return stdout


def mkdir_p(ser: serial.Serial, path: str) -> None:
    exec_raw(ser, f"""
import os
try:
    os.mkdir({path!r})
except OSError:
    pass
""")


def put_file(ser: serial.Serial, local_path: pathlib.Path, remote_path: str) -> None:
    """Sube un archivo mediante raw REPL (bloques de 256 bytes en hex)."""
    data = local_path.read_bytes()
    total = len(data)

    # Abrir archivo en el ESP32
    exec_raw(ser, f"_f = open({remote_path!r}, 'wb')\n")

    CHUNK = 256
    sent = 0
    while sent < total:
        chunk = data[sent : sent + CHUNK]
        hex_str = binascii.hexlify(chunk).decode()
        exec_raw(ser, f"import binascii; _f.write(binascii.unhexlify({hex_str!r}))\n")
        sent += len(chunk)
        pct = sent * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"    [{bar}] {pct:3d}%  {sent}/{total} bytes", end="\r")

    exec_raw(ser, "_f.close()\n")
    print(f"    {'█'*20}  100%  {total}/{total} bytes  ✓")


# ──────────────────────────────────────────────────────────────────────────────
# CONEXIÓN CON MANEJO DE TIMING USB CDC
# ──────────────────────────────────────────────────────────────────────────────

def connect_with_timing(port: str, max_attempts: int = 5) -> serial.Serial:
    """
    Conecta al ESP32-S3 con manejo del timing de USB CDC compuesto.
    Intenta enviar Ctrl+C durante la ventana de 3 s de main.py.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"  [conn] Intento {attempt}/{max_attempts} en {port} …")
        try:
            ser = serial.Serial(port, 115200, timeout=0.5)
            time.sleep(0.2)
            ser.reset_input_buffer()

            # Enviar Ctrl+C repetidamente durante 4 s
            # (cubre la ventana de 3 s de time.sleep_ms(3000) en main.py)
            t0 = time.time()
            interrupted = False
            while time.time() - t0 < 4.0:
                ser.write(b"\r\x03")
                time.sleep(0.1)
                data = ser.read(ser.in_waiting)
                if b">>>" in data or b"raw REPL" in data:
                    interrupted = True
                    break
                if b"Traceback" in data or b"KeyboardInterrupt" in data:
                    interrupted = True
                    break

            if not interrupted:
                # Intentar un soft-reset para empezar de cero y aprovechar la ventana
                print("  [conn] Enviando soft-reset para reiniciar con ventana limpia …")
                ser.write(b"\r\x04")  # Ctrl+D = soft reset
                time.sleep(0.3)
                # Esperar a que el puerto reaparezca
                ser.close()
                time.sleep(1.5)
                if not wait_for_port(port, timeout=8.0):
                    print("  [conn] Puerto no reapareció.")
                    continue
                ser = serial.Serial(port, 115200, timeout=0.5)
                time.sleep(0.3)
                # Durante la ventana de 3 s enviar Ctrl+C
                t0 = time.time()
                while time.time() - t0 < 3.5:
                    ser.write(b"\r\x03")
                    time.sleep(0.08)

            # Intentar entrar a raw REPL
            try:
                enter_raw_repl(ser)
                return ser
            except TimeoutError:
                ser.close()
                time.sleep(1.0)
                continue

        except serial.SerialException as e:
            print(f"  [conn] Error serial: {e}")
            time.sleep(2.0)

    raise RuntimeError(f"No se pudo establecer raw REPL en {port} tras {max_attempts} intentos.")


# ──────────────────────────────────────────────────────────────────────────────
# DEPLOY
# ──────────────────────────────────────────────────────────────────────────────

def deploy(port: str) -> None:
    print(f"\n{'='*60}")
    print(f"  M2.50 DAQ-UI — Deploy al ESP32-S3")
    print(f"  Puerto: {port}")
    print(f"{'='*60}\n")

    # Verificar que los archivos locales existen
    missing = []
    for local, _ in FILES:
        p = BASE / local
        if not p.exists():
            missing.append(str(p))
    if missing:
        print("ERROR — Archivos locales no encontrados:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    print("[1/4] Conectando al ESP32 …")
    ser = connect_with_timing(port)

    print("\n[2/4] Creando directorios …")
    for d in DIRS:
        print(f"  mkdir /{d}")
        mkdir_p(ser, d)

    print(f"\n[3/4] Subiendo {len(FILES)} archivos …")
    for i, (local, remote) in enumerate(FILES, 1):
        local_path = BASE / local
        size_kb = local_path.stat().st_size / 1024
        print(f"  [{i:02d}/{len(FILES)}] {remote}  ({size_kb:.1f} KB)")
        put_file(ser, local_path, remote)

    print("\n[4/4] Reiniciando ESP32 …")
    exec_raw(ser, "import machine; machine.reset()\n")
    ser.close()

    print(f"\n{'='*60}")
    print("  ✓  Deploy completado.")
    print("  Espera 5–10 s y abre: http://192.168.0.162")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy M2.50 DAQ-UI al ESP32-S3")
    parser.add_argument("--port", "-p", default=None,
                        help="Puerto serial, ej: /dev/ttyACM0 o COM5")
    args = parser.parse_args()

    port = args.port
    if port is None:
        port = find_port()
        if port is None:
            print("ERROR — No se encontró ningún ESP32 conectado.")
            print("         Conecta el cable y vuelve a intentar, o usa --port <puerto>")
            sys.exit(1)
        print(f"Puerto detectado automáticamente: {port}")

    deploy(port)


if __name__ == "__main__":
    main()
