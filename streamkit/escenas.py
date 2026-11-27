"""Título y categoría según la escena de OBS: cada escena puede tener un preset de /canal. Mientras OBS transmite, si
cambiás de escena y te quedás QUEDARSE segundos, se pone su preset en Twitch y Kick.

Escucha el servidor websocket de OBS (Herramientas → Ajustes del servidor WebSocket), con la contraseña que OBS guarda
en su carpeta. Corre dentro del proceso de la web.
"""
import base64
import hashlib
import json
import os
import socket
import threading
import time

import canal
import obs
from rutas import DATOS
from ws import ws_codificar, ws_cuadro

REGLAS = os.path.join(DATOS, 'escenas-canal.json')
QUEDARSE = 5  # pasar de largo por una escena no cambia nada
SUSCRIPCION = (1 << 2) | (1 << 6)  # eventos de escenas y de salidas (empezó o terminó el stream)
estado = {'estado': 'conectando', 'escena': '', 'escenas': [], 'en_vivo': False, 'ultimo': None}


def ajustes_obs():
    """(activado, puerto, contraseña) del servidor websocket de OBS."""
    with open(os.path.join(obs.CARPETA, 'plugin_config', 'obs-websocket', 'config.json'), encoding='utf-8') as f:
        c = json.load(f)
    return bool(c.get('server_enabled')), int(c.get('server_port') or 4455), (c.get('server_password') or '') if c.get('auth_required') else ''


def respuesta_auth(clave, sal, desafio):
    secreto = base64.b64encode(hashlib.sha256((clave + sal).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secreto + desafio).encode()).digest()).decode()


def reglas():
    try:
        with open(REGLAS, encoding='utf-8') as f:
            r = json.load(f)
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_reglas(datos):
    """{escena: nombre de preset}. Una escena sin preset no se guarda."""
    if not isinstance(datos, dict) or len(datos) > 100:
        raise ValueError('Pedido inválido.')
    nombres = {p.get('nombre') for p in canal.presets()}
    r = {}
    for escena, preset in datos.items():
        if not isinstance(escena, str) or not isinstance(preset, str) or len(escena) > 200:
            raise ValueError('Pedido inválido.')
        if preset:
            if preset not in nombres:
                raise ValueError(f'No hay un preset «{preset}».')
            r[escena] = preset
    canal.guardar_json(REGLAS, r)
    return r


def aplicar(escena):
    """Pone el preset de esa escena en las plataformas conectadas. Devuelve lo que pasó, o None si la escena no tiene."""
    nombre = reglas().get(escena)
    preset = next((p for p in canal.presets() if p.get('nombre') == nombre), None)
    if not preset:
        return None
    plataformas = [p for p, token in (('twitch', canal.TOKEN_TWITCH), ('kick', canal.TOKEN_KICK)) if os.path.exists(token)]
    if not plataformas:
        r = {'error': 'Falta conectar tu cuenta de Twitch o de Kick en Configuración'}
    else:
        try:
            r = canal.guardar({**preset, 'plataformas': plataformas,
                               'categorias': {p: c.get('id') for p, c in (preset.get('categorias') or {}).items()}})
        except ValueError as e:
            r = {'error': str(e)}
    return {'escena': escena, 'preset': nombre, 'cuando': time.time(), 'resultado': r}


class Vigia:
    """Decide cuándo aplicar: separado del socket para probarlo sin OBS."""

    def __init__(self, aplicar=aplicar):
        self.aplicar, self.pendiente, self.desde, self.puesta = aplicar, None, 0.0, None

    def escena(self, nombre, ahora):
        estado['escena'] = nombre
        self.pendiente, self.desde = nombre, ahora

    def vivo(self, si, ahora):
        estado['en_vivo'] = si
        if si:  # al arrancar, la escena en la que estás cuenta como recién elegida
            self.pendiente, self.desde, self.puesta = estado['escena'], ahora, None

    def tic(self, ahora):
        if not self.pendiente or not estado['en_vivo'] or ahora - self.desde < QUEDARSE:
            return
        escena, self.pendiente = self.pendiente, None
        preset = reglas().get(escena)
        if not preset or preset == self.puesta:  # volver a una escena con el mismo preset no lo pone de nuevo
            return
        self.puesta = preset
        r = self.aplicar(escena)
        if r:
            estado['ultimo'] = r
            print(f'Escena «{escena}»: preset «{preset}»: {json.dumps(r["resultado"])}', flush=True)


def sesion(vigia):
    activado, puerto, clave = ajustes_obs()
    if not activado:
        estado['estado'] = 'apagado'
        return
    s = socket.create_connection(('127.0.0.1', puerto), 5)
    try:
        s.sendall(('GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n'
                   f'Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        buf = b''
        while b'\r\n\r\n' not in buf:
            d = s.recv(4096)
            if not d:
                raise ConnectionError('OBS cortó al conectar')
            buf += d
        cabecera, _, buf = buf.partition(b'\r\n\r\n')
        if b' 101 ' not in cabecera.split(b'\r\n')[0]:
            raise ConnectionError('OBS no aceptó el websocket')
        enviar = lambda op, d: s.sendall(ws_codificar(json.dumps({'op': op, 'd': d}).encode()))
        pedir = lambda tipo: enviar(6, {'requestType': tipo, 'requestId': tipo})
        s.settimeout(1)
        while True:
            try:
                d = s.recv(65536)
                if not d:
                    raise ConnectionError('OBS se cerró')
                buf += d
            except socket.timeout:
                pass
            while c := ws_cuadro(buf):
                tipo, cuerpo, buf = c
                if tipo == 8:  # cierre: 4009 es contraseña incorrecta
                    codigo = int.from_bytes(cuerpo[:2], 'big') if len(cuerpo) >= 2 else 0
                    estado['estado'] = 'clave' if codigo == 4009 else 'desconectado'
                    return
                if tipo == 9:
                    s.sendall(ws_codificar(cuerpo, 10))
                    continue
                if tipo != 1:
                    continue
                m = json.loads(cuerpo)
                op, d = m.get('op'), m.get('d') or {}
                if op == 0:  # Hello
                    ident = {'rpcVersion': 1, 'eventSubscriptions': SUSCRIPCION}
                    if d.get('authentication'):
                        if not clave:
                            estado['estado'] = 'clave'
                            return
                        ident['authentication'] = respuesta_auth(clave, d['authentication']['salt'], d['authentication']['challenge'])
                    enviar(1, ident)
                elif op == 2:  # Identified
                    estado['estado'] = 'conectado'
                    for t in ('GetSceneList', 'GetStreamStatus'):
                        pedir(t)
                elif op == 7:  # respuesta a un pedido
                    r = d.get('responseData') or {}
                    # al conectar solo se lee dónde estás: si la web se reinicia en pleno stream, no pisa el título que tengas
                    if d.get('requestType') == 'GetSceneList':
                        estado['escenas'] = [x.get('sceneName') for x in reversed(r.get('scenes') or [])]  # OBS las da de abajo para arriba
                        estado['escena'] = r.get('currentProgramSceneName') or ''
                    elif d.get('requestType') == 'GetStreamStatus':
                        estado['en_vivo'] = bool(r.get('outputActive'))
                elif op == 5:  # evento
                    ev, datos = d.get('eventType'), d.get('eventData') or {}
                    if ev == 'CurrentProgramSceneChanged':
                        vigia.escena(datos.get('sceneName') or '', time.monotonic())
                    elif ev == 'StreamStateChanged':
                        vigia.vivo(bool(datos.get('outputActive')), time.monotonic())
                    elif ev in ('SceneCreated', 'SceneRemoved', 'SceneNameChanged', 'SceneListChanged'):
                        pedir('GetSceneList')
            vigia.tic(time.monotonic())
    finally:
        s.close()


def escuchar():
    vigia = Vigia()
    while True:
        try:
            sesion(vigia)
        except FileNotFoundError:
            estado['estado'] = 'sin obs'
        except (OSError, ValueError, KeyError):  # OBS cerrado: reintenta
            estado['estado'] = 'desconectado'
        estado['en_vivo'] = False
        time.sleep(5)


def arrancar():
    threading.Thread(target=escuchar, daemon=True).start()


def leer():
    return {**estado, 'reglas': reglas()}
