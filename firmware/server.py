# server.py — Servidor HTTP + WebSocket RFC 6455 + REST API
#
# Optimizaciones aplicadas:
#  · JSON construido con str.format() (más rápido que json.dumps en MicroPython)
#  · Frame WS reutilizado: se codifica una sola vez por ciclo y se envía a todos
#  · Drift correction en broadcast_loop: sleep del tiempo RESTANTE del período
#  · Limpieza silenciosa de writers muertos (lista separada, sin excepciones)

import asyncio
import hashlib
import binascii
import json
import os

import config
import sensors

# ---------------------------------------------------------------------------
# Constantes WebSocket (RFC 6455)
# ---------------------------------------------------------------------------
_WS_MAGIC   = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_FILE_CHUNK = 512    # bytes para servir archivos estáticos (conserva heap)

# Tabla de tipos MIME por extensión
_MIME = {
    "html": "text/html; charset=utf-8",
    "js":   "application/javascript",
    "css":  "text/css",
    "json": "application/json",
    "svg":  "image/svg+xml",
    "ico":  "image/x-icon",
}

# Lista de StreamWriters WebSocket activos
_ws_writers: list = []


# ---------------------------------------------------------------------------
# Utilidades WebSocket
# ---------------------------------------------------------------------------
def _ws_accept_key(key: bytes) -> bytes:
    """Calcula el valor de Sec-WebSocket-Accept según RFC 6455 §4.2.2."""
    return binascii.b2a_base64(hashlib.sha1(key + _WS_MAGIC).digest()).strip()


def _ws_encode_frame(payload: bytes) -> bytes:
    """Construye un frame WebSocket de texto (opcode 0x01), FIN=1, sin mascarado."""
    n = len(payload)
    if n <= 125:
        header = bytes([0x81, n])
    elif n <= 65535:
        header = bytes([0x81, 126, n >> 8, n & 0xFF])
    else:
        header = bytes([
            0x81, 127,
            0, 0, 0, 0,
            (n >> 24) & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF,
        ])
    return header + payload


async def _ws_read_frame(reader):
    """Lee un frame WebSocket entrante del cliente.
    Retorna (opcode, payload). Retorna (None, None) en caso de EOF o error.
    """
    try:
        b0 = (await reader.read(1))[0]
        b1 = (await reader.read(1))[0]
        opcode = b0 & 0x0F
        masked = b1 & 0x80
        length = b1 & 0x7F

        if length == 126:
            raw = await reader.read(2)
            length = (raw[0] << 8) | raw[1]
        elif length == 127:
            raw = await reader.read(8)
            length = int.from_bytes(raw, "big")

        mask_key = await reader.read(4) if masked else b""
        data = bytearray(await reader.read(length))

        if masked:
            for i in range(length):
                data[i] ^= mask_key[i & 3]

        return opcode, bytes(data)
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Handshake WebSocket y tarea por cliente
# ---------------------------------------------------------------------------
async def _handle_ws_upgrade(reader, writer, headers: dict) -> None:
    key    = headers.get(b"sec-websocket-key", b"")
    accept = _ws_accept_key(key)

    writer.write(
        b"HTTP/1.1 101 Switching Protocols\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: " + accept + b"\r\n\r\n"
    )
    await writer.drain()

    _ws_writers.append(writer)
    print(f"[ws] Cliente conectado — total: {len(_ws_writers)}")

    await _ws_client_task(reader, writer)


async def _ws_client_task(reader, writer) -> None:
    """Lee frames entrantes (Close / Ping) y elimina el writer al cerrar."""
    try:
        while True:
            opcode, payload = await _ws_read_frame(reader)
            if opcode is None or opcode == 8:   # EOF o Close
                break
            if opcode == 9:                      # Ping → Pong
                writer.write(bytes([0x8A, len(payload)]) + payload)
                await writer.drain()
    except Exception:
        pass
    finally:
        if writer in _ws_writers:
            _ws_writers.remove(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print(f"[ws] Cliente desconectado — total: {len(_ws_writers)}")


# ---------------------------------------------------------------------------
# Broadcast loop — 50 Hz con drift correction
# ---------------------------------------------------------------------------
# Plantilla JSON pre-compilada: {{ y }} son llaves literales en str.format()
_JSON_TPL = (
    '{{"s1":{s1},"s2":{s2},"s3":{s3},"gas_valve":{gv},'
    '"roll":{roll},"pitch":{pitch},"yaw":{yaw},"yaw_signed":{ys},'
    '"enc_h":{eh},"enc_v":{ev},"ts":{ts}}}'
)


async def _broadcast_loop() -> None:
    """Transmite datos a 50 Hz a todos los clientes WebSocket activos.

    Usa drift correction: mide el tiempo real consumido por cada ciclo y
    espera solo el tiempo restante del período, manteniendo la cadencia exacta.
    """
    import time
    period = config.PERIOD_MS

    while True:
        t_start = time.ticks_ms()

        if _ws_writers:
            d = sensors.read()

            # Construcción manual del JSON (más rápido que json.dumps en MicroPython)
            jstr = _JSON_TPL.format(
                s1   = "true"  if d["s1"]        else "false",
                s2   = "true"  if d["s2"]        else "false",
                s3   = "true"  if d["s3"]        else "false",
                gv   = "true"  if d["gas_valve"] else "false",
                roll = d["roll"],  pitch = d["pitch"],
                yaw  = d["yaw"],   ys    = d["yaw_signed"],
                eh   = d["enc_h"], ev    = d["enc_v"],
                ts   = d["ts"],
            )
            frame = _ws_encode_frame(jstr.encode())

            # Escribir a todos los clientes; acumular los muertos sin interrumpir
            dead = []
            for w in _ws_writers:
                try:
                    w.write(frame)
                except Exception:
                    dead.append(w)

            # yield al event loop para que los buffers se vacíen
            await asyncio.sleep_ms(0)

            # Limpiar clientes desconectados
            for w in dead:
                if w in _ws_writers:
                    _ws_writers.remove(w)

        # Drift correction: dormir solo el tiempo restante del período
        elapsed = time.ticks_diff(time.ticks_ms(), t_start)
        wait    = period - elapsed
        await asyncio.sleep_ms(max(0, wait))


# ---------------------------------------------------------------------------
# Servir archivos estáticos
# ---------------------------------------------------------------------------
async def _handle_static(writer, path: str) -> None:
    if path in ("/", ""):
        path = "/index.html"

    filepath = config.WEB_ROOT + path
    ext  = path.rsplit(".", 1)[-1].lower() if "." in path else "bin"
    mime = _MIME.get(ext, "application/octet-stream")

    try:
        size = os.stat(filepath)[6]
        writer.write(
            (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: {mime}\r\n"
                f"Content-Length: {size}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode()
        )
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(_FILE_CHUNK)
                if not chunk:
                    break
                writer.write(chunk)
                await writer.drain()
    except OSError:
        body = b"404 Not Found"
        writer.write(
            b"HTTP/1.1 404 Not Found\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 13\r\n"
            b"Connection: close\r\n\r\n" + body
        )
        await writer.drain()


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------
_CT_JSON = b"Content-Type: application/json\r\n"
_BODY_OK  = b'{"ok":true}'
_BODY_ERR = b'{"ok":false}'


async def _handle_api(writer, method: bytes, path: str) -> None:
    if path == "/api/config" and method == b"GET":
        body = json.dumps({
            "ssid":     config.WIFI_SSID,
            "hostname": config.HOSTNAME,
            "port":     config.PORT,
            "simulate": config.SIMULATE_SENSORS,
        }).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\n" + _CT_JSON +
            b"Content-Length: " + str(len(body)).encode() +
            b"\r\nConnection: close\r\n\r\n" + body
        )
    elif method == b"POST":
        handled = True
        if path in ("/api/calibrate", "/api/calibrate/yaw"):
            sensors.reset_yaw()
        elif path == "/api/calibrate/pitch":
            sensors.reset_pitch()
        elif path == "/api/calibrate/roll":
            sensors.reset_roll()
        elif path == "/api/calibrate/encoders":
            sensors.reset_encoders()
        else:
            handled = False

        if handled:
            writer.write(
                b"HTTP/1.1 200 OK\r\n" + _CT_JSON +
                b"Content-Length: " + str(len(_BODY_OK)).encode() +
                b"\r\nConnection: close\r\n\r\n" + _BODY_OK
            )
        else:
            writer.write(
                b"HTTP/1.1 404 Not Found\r\n" + _CT_JSON +
                b"Content-Length: " + str(len(_BODY_ERR)).encode() +
                b"\r\nConnection: close\r\n\r\n" + _BODY_ERR
            )
    elif method == b"POST" and path == "/api/config":
        # Acepta pero no aplica (requiere reinicio)
        writer.write(
            b"HTTP/1.1 200 OK\r\n" + _CT_JSON +
            b"Content-Length: " + str(len(_BODY_OK)).encode() +
            b"\r\nConnection: close\r\n\r\n" + _BODY_OK
        )
    else:
        writer.write(
            b"HTTP/1.1 405 Method Not Allowed\r\n" + _CT_JSON +
            b"Content-Length: " + str(len(_BODY_ERR)).encode() +
            b"\r\nConnection: close\r\n\r\n" + _BODY_ERR
        )

    await writer.drain()


# ---------------------------------------------------------------------------
# Router principal por conexión TCP
# ---------------------------------------------------------------------------
async def _handle_client(reader, writer) -> None:
    try:
        req_line = await reader.readline()
        parts = req_line.split()
        if len(parts) < 2:
            return

        method = parts[0]
        raw_path = parts[1]
        path = raw_path.decode() if isinstance(raw_path, bytes) else raw_path

        # Leer cabeceras hasta línea en blanco
        headers = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            if b":" in line:
                k, _, v = line.partition(b":")
                headers[k.strip().lower()] = v.strip()

        # Enrutar
        if path == "/ws" and headers.get(b"upgrade", b"").lower() == b"websocket":
            await _handle_ws_upgrade(reader, writer, headers)
            return  # writer es gestionado por _ws_client_task

        if path.startswith("/api/"):
            await _handle_api(writer, method, path)
        else:
            await _handle_static(writer, path)

    except Exception as e:
        print(f"[http] Error en cliente: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------
async def start_server() -> None:
    """Inicializa sensores, lanza el servidor TCP y el broadcast loop.
    Esta coroutine no retorna.
    """
    sensors.init()
    print(f"[server] Iniciando en 0.0.0.0:{config.PORT} …")

    srv = await asyncio.start_server(_handle_client, "0.0.0.0", config.PORT)
    asyncio.create_task(_broadcast_loop())

    print(f"[server] Escuchando en puerto {config.PORT}  —  50 Hz broadcast activo")
    await srv.wait_closed()
