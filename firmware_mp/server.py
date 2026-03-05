"""
server.py — Servidor HTTP + WebSocket RFC 6455 para MicroPython

Implementado manualmente sobre asyncio.start_server() sin librerías externas.

Funcionalidades:
  - Sirve archivos estáticos desde WEB_ROOT (web_ui/)
  - Endpoint WebSocket en /ws (broadcast 50 Hz de datos de sensores)
  - REST stubs: GET /api/config, POST /api/calibrate, POST /api/config/bluetooth
  - Hasta 8 clientes WebSocket simultáneos
"""

import asyncio
import hashlib
import binascii
import time
import os
import config
import sensors as _sensors

# ── Lista global de writers WebSocket activos ─────────────────────────────────
_ws_writers = []

# ── Tabla MIME ────────────────────────────────────────────────────────────────
_MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript',
    '.css':  'text/css',
    '.json': 'application/json',
    '.ico':  'image/x-icon',
    '.png':  'image/png',
    '.svg':  'image/svg+xml',
}

# Tamaño de chunk para servir archivos grandes (ej. uplot.min.js 52 KB)
_FILE_CHUNK = 512

# Magic del protocolo WebSocket RFC 6455
_WS_MAGIC = b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


# =============================================================================
#  WebSocket — handshake, frame encoder / decoder
# =============================================================================

def _ws_accept_key(client_key_str):
    """
    Calcula Sec-WebSocket-Accept conforme RFC 6455:
      BASE64(SHA1(client_key + WS_MAGIC))
    """
    raw    = client_key_str.strip().encode() + _WS_MAGIC
    digest = hashlib.sha1(raw).digest()
    return binascii.b2a_base64(digest).strip().decode()


def _ws_encode_text(payload_bytes):
    """
    Codifica un frame WebSocket texto (FIN=1, opcode=0x01) sin masking.
    Soporta payloads de tamaño 0..65535 bytes.
    """
    n = len(payload_bytes)
    if n <= 125:
        header = bytes([0x81, n])
    else:
        # Extended payload length (2 bytes)
        header = bytes([0x81, 0x7E, (n >> 8) & 0xFF, n & 0xFF])
    return header + payload_bytes


async def _ws_read_frame(reader):
    """
    Lee un frame WebSocket del cliente (siempre enmascarado RFC 6455).
    Retorna (opcode, payload_bytes).
    Lanza excepción si la conexión se cierra.
    """
    hdr    = await reader.readexactly(2)
    opcode = hdr[0] & 0x0F
    masked = (hdr[1] & 0x80) != 0
    length = hdr[1] & 0x7F

    if length == 126:
        ext    = await reader.readexactly(2)
        length = (ext[0] << 8) | ext[1]
    elif length == 127:
        ext    = await reader.readexactly(8)
        # Solo soportamos 32-bit length (suficiente para este uso)
        length = int.from_bytes(ext[4:8], 'big')

    mask_key = await reader.readexactly(4) if masked else b''
    payload  = await reader.readexactly(length) if length else b''

    if masked and mask_key:
        payload = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))

    return opcode, payload


async def _handle_ws_upgrade(reader, writer, headers):
    """
    Realiza el handshake de upgrade a WebSocket y entrega la conexión
    a _ws_client_task (tarea separada que permanece activa).
    """
    client_key = headers.get('sec-websocket-key', '')
    accept_key = _ws_accept_key(client_key)

    response = (
        'HTTP/1.1 101 Switching Protocols\r\n'
        'Upgrade: websocket\r\n'
        'Connection: Upgrade\r\n'
        'Sec-WebSocket-Accept: {}\r\n'
        '\r\n'
    ).format(accept_key)

    writer.write(response.encode())
    await writer.drain()

    # Lanzar tarea de lectura del cliente (no bloqueante)
    asyncio.create_task(_ws_client_task(reader, writer))


async def _ws_client_task(reader, writer):
    """
    Tarea por cliente WebSocket:
    - Registra el writer para recibir broadcasts
    - Lee frames del cliente (principalmente Close y Ping)
    - Se elimina de la lista al desconectarse
    """
    _ws_writers.append(writer)
    try:
        while True:
            opcode, payload = await _ws_read_frame(reader)

            if opcode == 0x08:   # Close
                break
            elif opcode == 0x09:  # Ping → responder Pong
                pong = bytes([0x8A, len(payload)]) + payload
                writer.write(pong)
                await writer.drain()
            # Frames de texto/binario del cliente se ignoran (dashboard es solo lectura)

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


# =============================================================================
#  Archivos estáticos
# =============================================================================

async def _handle_static(path, writer):
    """
    Sirve un archivo estático desde WEB_ROOT.
    - Detecta MIME por extensión
    - Cache-Control: no-cache para index.html, 1h para el resto
    - Escribe contenido en chunks de _FILE_CHUNK bytes para no agotar la heap
    """
    if path == '/' or path == '':
        path = '/index.html'

    fs_path = config.WEB_ROOT + path
    ext = ''
    dot = path.rfind('.')
    if dot != -1:
        ext = path[dot:]

    content_type = _MIME.get(ext, 'application/octet-stream')
    cache = 'no-cache' if path == '/index.html' else 'max-age=3600'

    try:
        stat = os.stat(fs_path)
        size = stat[6]
    except OSError:
        writer.write(
            b'HTTP/1.1 404 Not Found\r\n'
            b'Content-Length: 0\r\n'
            b'Connection: close\r\n\r\n'
        )
        await writer.drain()
        return

    header = (
        'HTTP/1.1 200 OK\r\n'
        'Content-Type: {}\r\n'
        'Content-Length: {}\r\n'
        'Cache-Control: {}\r\n'
        'Connection: close\r\n'
        '\r\n'
    ).format(content_type, size, cache)

    writer.write(header.encode())

    # Envía en chunks para no consumir toda la heap con archivos grandes
    with open(fs_path, 'rb') as f:
        while True:
            chunk = f.read(_FILE_CHUNK)
            if not chunk:
                break
            writer.write(chunk)
    await writer.drain()


# =============================================================================
#  REST API stubs
# =============================================================================

def _json_ok(writer):
    body = b'{"ok":true}'
    writer.write(
        b'HTTP/1.1 200 OK\r\n'
        b'Content-Type: application/json\r\n'
        b'Content-Length: 11\r\n'
        b'Connection: close\r\n\r\n'
        + body
    )


async def _handle_api(method, path, reader, writer, headers):
    """
    Gestiona los endpoints REST consumidos por bt_toggle.js.
    Drena el body si existe antes de responder.
    """
    clen = int(headers.get('content-length', 0))
    if clen > 0:
        await reader.readexactly(clen)   # descarta body

    if path == '/api/calibrate' and method == 'POST':
        _sensors.reset_yaw()
        _json_ok(writer)

    elif path == '/api/config/bluetooth' and method == 'POST':
        # Este ESP32 no tiene BLE — responde OK cosméticamente
        _json_ok(writer)

    elif path == '/api/config' and method == 'GET':
        body = (
            '{{"ssid":"{ssid}","hostname":"{host}",'
            '"port":{port},"bt_enabled":false,'
            '"hid_sens_x":1.0,"hid_sens_y":1.0}}'
        ).format(
            ssid=config.WIFI_SSID,
            host=config.HOSTNAME,
            port=config.PORT,
        )
        body_b = body.encode()
        header = (
            'HTTP/1.1 200 OK\r\n'
            'Content-Type: application/json\r\n'
            'Content-Length: {}\r\n'
            'Connection: close\r\n\r\n'
        ).format(len(body_b))
        writer.write(header.encode())
        writer.write(body_b)

    elif path == '/api/config' and method == 'POST':
        # Acepta la petición sin aplicar cambios (simulador de solo lectura de config)
        _json_ok(writer)

    else:
        writer.write(
            b'HTTP/1.1 404 Not Found\r\n'
            b'Content-Length: 0\r\n'
            b'Connection: close\r\n\r\n'
        )

    await writer.drain()


# =============================================================================
#  Router HTTP principal
# =============================================================================

async def _handle_client(reader, writer):
    """
    Gestiona una conexión TCP entrante:
    1. Lee la línea de petición y las cabeceras HTTP
    2. Despacha a WS, REST o archivos estáticos
    """
    try:
        # Línea de petición (timeout 5s)
        try:
            line = await asyncio.wait_for(reader.readline(), 5)
        except asyncio.TimeoutError:
            return
        if not line:
            return

        parts = line.decode('utf-8', 'ignore').split()
        if len(parts) < 2:
            return
        method, path = parts[0].upper(), parts[1]

        # Eliminar query string
        if '?' in path:
            path = path[:path.index('?')]

        # Cabeceras
        headers = {}
        while True:
            try:
                hline = await asyncio.wait_for(reader.readline(), 3)
            except asyncio.TimeoutError:
                break
            if hline in (b'\r\n', b'\n', b''):
                break
            decoded = hline.decode('utf-8', 'ignore')
            if ':' in decoded:
                k, v = decoded.split(':', 1)
                headers[k.lower().strip()] = v.strip()

        # Despacho
        if (path == '/ws' and
                headers.get('upgrade', '').lower() == 'websocket'):
            await _handle_ws_upgrade(reader, writer, headers)
            return   # ownership del writer transferido a _ws_client_task

        elif path.startswith('/api/'):
            await _handle_api(method, path, reader, writer, headers)

        else:
            await _handle_static(path, writer)

    except Exception as e:
        # Fallo silencioso para mantener el servidor corriendo
        _ = e
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# =============================================================================
#  Loop de broadcast 50 Hz
# =============================================================================

async def _broadcast_loop():
    """
    Coroutine que corre indefinidamente:
    - Lee sensores cada PERIOD_MS ms
    - Construye el JSON manualmente (mismo formato que firmware C)
    - Codifica frame WS y envía a todos los clientes conectados
    - Elimina clientes muertos (excepción en write/drain)
    """
    while True:
        t0 = time.ticks_ms()
        d  = _sensors.read()

        # Construcción manual del JSON (idéntico al snprintf del firmware C)
        pkt = (
            '{{"s1":{s1},"s2":{s2},"s3":{s3},'
            '"gas_valve":{gv},'
            '"pitch":{pitch:.2f},"roll":{roll:.2f},"yaw":{yaw:.1f},'
            '"enc_h":{enc_h},"enc_v":{enc_v},'
            '"ts":{ts}}}'
        ).format(
            s1    = 'true' if d['s1']        else 'false',
            s2    = 'true' if d['s2']        else 'false',
            s3    = 'true' if d['s3']        else 'false',
            gv    = 'true' if d['gas_valve'] else 'false',
            pitch = d['pitch'],
            roll  = d['roll'],
            yaw   = d['yaw'],
            enc_h = d['enc_h'],
            enc_v = d['enc_v'],
            ts    = d['ts'],
        )
        frame = _ws_encode_text(pkt.encode())

        # Envía a todos los clientes, elimina muertos
        dead = []
        for w in _ws_writers:
            try:
                w.write(frame)
                await w.drain()
            except Exception:
                dead.append(w)
        for w in dead:
            if w in _ws_writers:
                _ws_writers.remove(w)

        # Compensar tiempo de proceso para mantener 50 Hz
        elapsed  = time.ticks_diff(time.ticks_ms(), t0)
        sleep_ms = max(1, config.PERIOD_MS - elapsed)
        await asyncio.sleep_ms(sleep_ms)


# =============================================================================
#  Entry point
# =============================================================================

async def start_server():
    """
    Inicializa sensores, arranca el loop de broadcast y el servidor TCP.
    No retorna — corre indefinidamente.
    """
    _sensors.init()

    asyncio.create_task(_broadcast_loop())

    server = await asyncio.start_server(
        _handle_client,
        '0.0.0.0',
        config.PORT,
        backlog=4,
    )

    print("Servidor HTTP+WS en puerto {}".format(config.PORT))
    print("WebSocket: ws://<ip>/ws")
    print("Modo sensor: {}".format(
        "SIMULADO" if config.SIMULATE_SENSORS else "HARDWARE REAL"
    ))

    # Espera cierre del servidor (nunca ocurre en condiciones normales)
    await server.wait_closed()
