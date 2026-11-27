"""Cuadros de websocket, sin dependencias: los usan el bot (Twitch, Kick) y la web (OBS)."""
import os


def ws_codificar(datos, op=1):
    mascara, n = os.urandom(4), len(datos)
    largo = bytes([0x80 | n]) if n < 126 else bytes([0xFE]) + n.to_bytes(2, "big")
    return bytes([0x80 | op]) + largo + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))


def ws_cuadro(buf):
    """Saca un cuadro del websocket: (tipo, datos, resto), o None si falta que llegue más."""
    if len(buf) < 2:
        return None
    largo, pos = buf[1] & 0x7F, 2
    if largo >= 126:
        pos = 4 if largo == 126 else 10
        if len(buf) < pos:
            return None
        largo = int.from_bytes(buf[2:pos], "big")
    if len(buf) < pos + largo:
        return None
    return buf[0] & 0x0F, buf[pos:pos + largo], buf[pos + largo:]
