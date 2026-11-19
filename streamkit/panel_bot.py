"""Lo que el panel necesita del bot: leer y guardar su config, ver cómo está y pedirle que se reinicie.

No importa el código del bot: corre dentro del proceso del delay y no puede arrastrar nada de él.
"""
import json
import os
import re
import socket
import threading
import time
import unicodedata

import rutas
from rutas import BOT, DATOS, config as ruta_config

AQUI = DATOS
CONFIG = ruta_config(os.path.join('bot', 'config.json'))
ESTADO_BOT = os.path.join(BOT, 'estado.json')
EVENTOS_BOT = os.path.join(BOT, 'eventos.json')  # el chat y las alertas: los escribe el bot
LOG_BOT = os.path.join(BOT, 'bot.log')
SERVICIOS = os.path.join(AQUI, 'servicios.json')
PUERTO_BOT = rutas.PUERTO_BOT  # conectarse a este puerto reinicia el bot: el guardián lo levanta de nuevo
SIN_SENAL = 20  # el bot y el guardián escriben su estado cada 5 s
LARGO_MENSAJE = 500  # el máximo de Twitch y Kick
EDITABLES = ('comandos', 'espera_lista_comandos', 'timers', 'banear_frases', 'no_banear')
candado = threading.Lock()
ultimos = {}  # lo último que se pudo leer de cada archivo, por si justo lo están reemplazando


def mensaje_valido(texto, que):
    if not isinstance(texto, str):
        raise ValueError(f'{que}: tiene que ser texto.')
    texto = texto.strip()
    if not 1 <= len(texto) <= LARGO_MENSAJE:
        raise ValueError(f'{que}: tiene que tener entre 1 y {LARGO_MENSAJE} caracteres.')
    if re.search(r'[\x00-\x1f\x7f]', texto):  # un salto de línea en el chat de Twitch sería otra orden
        raise ValueError(f'{que}: no puede tener saltos de línea.')
    if texto[0] in '/.':  # el chat los toma como comandos: /ban, .ban
        raise ValueError(f'{que}: no puede empezar con / ni con punto.')
    return texto


def entero(valor, minimo, maximo, que):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not minimo <= valor <= maximo or valor != int(valor):
        raise ValueError(f'{que}: tiene que ser un número entero entre {minimo} y {maximo}.')
    return int(valor)


def frases(lista, que):
    if not isinstance(lista, list) or len(lista) > 200:
        raise ValueError(f'{que}: revisá la lista.')
    limpias = []
    for f in lista:
        if not isinstance(f, str) or len(f) > 100:
            raise ValueError(f'{que}: cada una puede tener hasta 100 caracteres.')
        # el bot ignora signos y mayúsculas: con menos de 4 letras o números, una frase banearía a medio chat
        if len(re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', f).casefold())) < 4:
            raise ValueError(f'{que}: "{f}" es muy corta. Tiene que tener al menos 4 letras o números.')
        limpias.append(f.strip())
    return limpias


def validar(datos):
    """Devuelve solo los campos editables, listos para guardar. Si algo está mal, ValueError con el motivo."""
    if not isinstance(datos, dict) or not isinstance(datos.get('comandos'), dict):
        raise ValueError('Pedido inválido.')
    if len(datos['comandos']) > 100:
        raise ValueError('Son demasiados comandos: el máximo es 100.')
    comandos = {}
    for nombre, comando in datos['comandos'].items():
        nombre = str(nombre).strip().lower()
        if not re.fullmatch(r'!\w{1,30}', nombre):
            raise ValueError(f'"{nombre}": un comando empieza con ! y sigue con letras o números, sin espacios.')
        if nombre == '!comandos':
            raise ValueError('!comandos ya existe: el bot lo arma solo con la lista.')
        if nombre == '!clip':
            raise ValueError('!clip ya existe: crea un clip en Twitch.')
        if nombre in comandos:
            raise ValueError(f'{nombre} está dos veces.')
        if not isinstance(comando, dict):
            raise ValueError(f'{nombre}: revisá el comando.')
        comandos[nombre] = {'respuesta': mensaje_valido(comando.get('respuesta'), nombre),
                            'espera': entero(comando.get('espera'), 0, 3600, f'Espera de {nombre}')}
    if len('Comandos: ' + ' '.join(comandos)) > LARGO_MENSAJE:
        raise ValueError('La lista de !comandos no entra en un mensaje: acortá nombres o quitá alguno.')
    timers = datos.get('timers')
    if not isinstance(timers, list) or len(timers) > 20 or not all(isinstance(t, dict) for t in timers):
        raise ValueError('Mensajes automáticos: revisá la lista, el máximo es 20.')
    return {
        'comandos': comandos,
        'espera_lista_comandos': entero(datos.get('espera_lista_comandos'), 0, 3600, 'Espera de !comandos'),
        'timers': [{'texto': mensaje_valido(t.get('texto'), 'Mensaje automático'),
                    'minutos': entero(t.get('minutos'), 1, 240, 'Minutos del mensaje automático')} for t in timers],
        'banear_frases': frases(datos.get('banear_frases'), 'Frases que banean'),
        'no_banear': frases(datos.get('no_banear'), 'Excepciones'),
    }


def reiniciar():
    try:
        socket.create_connection(('127.0.0.1', PUERTO_BOT), 2).close()
    except OSError:  # no estaba corriendo: el guardián ya lo está levantando
        pass


def guardar(datos):
    cambios = validar(datos)
    with candado:
        with open(CONFIG, encoding='utf-8') as f:
            config = json.load(f)
        if all(config.get(k) == v for k, v in cambios.items()):
            return False
        config.update(cambios)  # client_id, cuentas y claves de Kick quedan como estaban
        with open(CONFIG + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(CONFIG + '.tmp', CONFIG)
    reiniciar()
    return True


def leer_json(ruta):
    try:
        with open(ruta, encoding='utf-8') as f:
            ultimos[ruta] = json.load(f)
    except FileNotFoundError:
        ultimos.pop(ruta, None)
    except (OSError, ValueError):  # lo están reemplazando justo ahora
        pass
    return ultimos.get(ruta, {})


def ultimo_aviso():
    """La última advertencia o error de bot.log, sin leer el archivo entero."""
    try:
        with open(LOG_BOT, 'rb') as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 16384))
            lineas = f.read().decode('utf-8', 'replace').splitlines()
    except OSError:
        return ''
    return next((l for l in reversed(lineas) if re.match(r'\S+ \S+ (WARNING|ERROR|CRITICAL) ', l)), '')


def estado():
    ahora = time.time()
    bot, servicios = leer_json(ESTADO_BOT), leer_json(SERVICIOS)
    vivo = ahora - bot.get('actualizado', 0) < SIN_SENAL
    return {
        'bot': {'vivo': vivo, 'twitch': bot.get('twitch', ''), 'kick': bot.get('kick', ''), 'follows': bot.get('follows', ''), 'aviso': ultimo_aviso(),
                'viewers': bot.get('viewers', {}) if vivo else {}, 'ids': bot.get('ids', {}),
                **servicios.get('bot', {'reinicios': 0, 'ultimo_fallo': ''})},
        'delay': servicios.get('delay', {'reinicios': 0, 'ultimo_fallo': ''}),
        'guardian': ahora - servicios.get('actualizado', 0) < SIN_SENAL,
    }


def eventos(desde=None):
    """Sin desde: lo último, para llenar el chat al abrirlo. Con desde: solo lo que llegó después de ese id."""
    lista = leer_json(EVENTOS_BOT)
    lista = lista if isinstance(lista, list) else []
    return {'eventos': lista[-200:] if desde is None else [e for e in lista if e.get('id', 0) > desde],
            'ultimo': lista[-1].get('id', 0) if lista else 0}


PUERTO_ORDENES = rutas.PUERTO_ORDENES  # borrar, timeout y ban desde la vista de chat: los hace el bot, que tiene las sesiones de moderador
ACCIONES = ('borrar', 'timeout', 'banear', 'desbanear')


def accion(datos):
    """Revisa lo que manda la vista de chat y se lo pasa al bot. Si algo falla, ValueError con el motivo."""
    if not isinstance(datos, dict) or datos.get('accion') not in ACCIONES or datos.get('plataforma') not in ('twitch', 'kick'):
        raise ValueError('Pedido inválido.')
    orden = {'accion': datos['accion'], 'plataforma': datos['plataforma'], 'usuario': str(datos.get('usuario') or '')[:60]}
    if orden['accion'] == 'borrar':
        if not re.fullmatch(r'[0-9A-Za-z-]{1,64}', str(datos.get('mid') or '')):
            raise ValueError('Ese mensaje no se puede borrar: no tiene id.')
        orden['mid'] = datos['mid']
    else:
        if not re.fullmatch(r'\d{1,20}', str(datos.get('uid') or '')):
            raise ValueError('Ese usuario no tiene id.')
        orden['uid'] = str(datos['uid'])
    if orden['accion'] == 'timeout':
        orden['minutos'] = entero(datos.get('minutos'), 1, 10080, 'Minutos del timeout')  # el máximo de Kick: una semana
    error = al_bot(orden)['error']
    if error:
        raise ValueError(error)


def quienes():
    """Quién está en el chat de Twitch y quién escribió en este stream, por plataforma."""
    r = al_bot({'accion': 'quienes'})
    if r.get('error') or 'quienes' not in r:
        raise ValueError(r.get('error') or 'El bot no sabe responder esto: reinicialo.')
    return r['quienes']


def al_bot(orden):
    try:
        with socket.create_connection(('127.0.0.1', PUERTO_ORDENES), 2) as s:
            s.settimeout(40)  # el bot puede reintentar con la sesión refrescada: hasta 30 s
            s.sendall((json.dumps(orden) + '\n').encode())
            respuesta = b''
            while not respuesta.endswith(b'\n'):
                parte = s.recv(4096)
                if not parte:
                    break
                respuesta += parte
        return json.loads(respuesta)
    except (OSError, ValueError):
        raise ValueError('El bot no contestó. Fijate en Inicio si está corriendo.')


def leer():
    with open(CONFIG, encoding='utf-8') as f:
        config = json.load(f)
    return {k: config.get(k) for k in EDITABLES}


def estado_y_config():
    """Con la config rota el estado se sigue viendo: es justo cuando más hace falta."""
    try:
        return {'config': leer(), 'error': '', **estado()}
    except (OSError, ValueError) as e:
        return {'config': None, 'error': f'No pude leer bot/config.json: {e}', **estado()}
