"""Claves de las apps de Twitch y Kick y los logins de las cuatro cuentas, desde la web (/config).

Corre en el proceso de la web. Las sesiones quedan en bot/: las usan el bot (chatbot.py) y el título (canal.py).
"""
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse

import panel_bot
from canal import guardar_json, pedir
from rutas import BOT, config as ruta_config

CONFIG = ruta_config(os.path.join('bot', 'config.json'))
ALCANCES = 'chat:read chat:edit moderator:manage:banned_users moderator:manage:chat_messages moderator:read:followers clips:edit'
ALCANCES_CANAL = 'channel:manage:broadcast'  # tu cuenta, no la del bot: un moderador no puede cambiar el título por API
KICK_ALCANCES = 'user:read chat:write moderation:ban moderation:chat_message:manage'
KICK_ALCANCES_CANAL = 'user:read channel:read channel:write'
KICK_REDIRECCION = 'http://localhost:47614/callback'
# tipo de login: plataforma, archivo de la sesión, campo de config con el nombre de la cuenta, permisos
CUENTAS = {
    'bot_twitch': ('twitch', 'token.json', 'bot', ALCANCES),
    'canal_twitch': ('twitch', 'token-canal.json', 'canal', ALCANCES_CANAL),
    'bot_kick': ('kick', 'token-kick.json', 'kick_bot', KICK_ALCANCES),
    'canal_kick': ('kick', 'token-canal-kick.json', 'kick_canal_slug', KICK_ALCANCES_CANAL),
}
CAMPOS = {  # lo que se escribe en la pantalla, con lo que acepta cada uno
    'client_id': (r'[a-z0-9]{0,64}', 'El Client ID de Twitch'),
    'canal': (r'\w{0,25}', 'Tu canal de Twitch'),
    'bot': (r'\w{0,25}', 'La cuenta de Twitch del bot'),
    'kick_client_id': (r'[A-Za-z0-9]{0,64}', 'El Client ID de Kick'),
    'kick_canal_slug': (r'[\w-]{0,40}', 'Tu canal de Kick'),
    'kick_bot': (r'[\w-]{0,40}', 'La cuenta de Kick del bot'),
}
logins = {}  # cómo va cada login, para que la pantalla lo muestre
candado = threading.Lock()


def leer_config():
    with open(CONFIG, encoding='utf-8') as f:
        return json.load(f)


def sesion(archivo):
    try:
        with open(os.path.join(BOT, archivo), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def leer():
    """Lo que muestra la pantalla. La clave secreta de Kick nunca sale: solo si está guardada."""
    c = leer_config()
    cuentas = {}
    for tipo, (_, archivo, campo, _) in CUENTAS.items():
        s = sesion(archivo)
        cuentas[tipo] = {'conectada': bool(s), 'como': (s or {}).get('login', ''), 'cuenta': c.get(campo, ''),
                         **logins.get(tipo, {})}
    return {'config': {k: c.get(k, '') for k in CAMPOS}, 'kick_secreto': bool(c.get('kick_client_secret')), 'cuentas': cuentas}


def canal_kick(slug):
    """Los números del canal que piden el chat y la API de Kick, a partir del nombre."""
    try:
        d = pedir('https://kick.com/api/v2/channels/' + urllib.parse.quote(slug), cabeceras={'Accept': 'application/json'})
        return {'kick_canal': d['id'], 'kick_chatroom': d['chatroom']['id'], 'kick_broadcaster_id': d['user_id']}
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError(f'No encontré el canal de Kick "{slug}". Revisá el nombre (el que va en kick.com/...)')


def guardar(datos):
    if not isinstance(datos, dict):
        raise ValueError('Pedido inválido.')
    nuevos = {}
    for campo, (patron, nombre) in CAMPOS.items():
        valor = str(datos.get(campo, '')).strip()
        if campo != 'kick_client_id' and campo != 'client_id':
            valor = valor.lower()
        if not re.fullmatch(patron, valor):
            raise ValueError(f'{nombre}: revisá lo que escribiste.')
        nuevos[campo] = valor
    secreto = str(datos.get('kick_client_secret') or '').strip()
    if secreto and not re.fullmatch(r'[A-Za-z0-9]{8,128}', secreto):
        raise ValueError('La clave secreta de Kick: revisá lo que pegaste.')
    with candado:
        c = leer_config()
        if nuevos['kick_canal_slug'] and (nuevos['kick_canal_slug'] != c.get('kick_canal_slug') or not c.get('kick_canal')):
            nuevos.update(canal_kick(nuevos['kick_canal_slug']))
        if secreto:
            nuevos['kick_client_secret'] = secreto
        # otra cuenta u otra app: la sesión vieja ya no corresponde y hay que conectar de nuevo
        for tipo, (plataforma, archivo, campo, _) in CUENTAS.items():
            app = 'client_id' if plataforma == 'twitch' else 'kick_client_id'
            if c.get(campo, '') != nuevos[campo] or c.get(app, '') != nuevos[app]:
                try:
                    os.remove(os.path.join(BOT, archivo))
                except OSError:
                    pass
        c.update(nuevos)
        guardar_json(CONFIG, c)
    panel_bot.reiniciar()  # el bot lee la config al arrancar


def empezar(tipo):
    """Arranca un login. Devuelve lo que la pantalla tiene que mostrar: el código y el link, o el link para abrir."""
    if tipo not in CUENTAS:
        raise ValueError('Pedido inválido.')
    plataforma, archivo, campo, alcances = CUENTAS[tipo]
    c = leer_config()
    cuenta = c.get(campo, '')
    app = c.get('client_id' if plataforma == 'twitch' else 'kick_client_id', '')
    if not app or not cuenta:
        raise ValueError('Primero completá y guardá las claves y los nombres de arriba.')
    if plataforma == 'kick' and not c.get('kick_client_secret'):
        raise ValueError('Falta la clave secreta de Kick: pegala arriba y guardá.')
    hacer = twitch_login if plataforma == 'twitch' else kick_login
    return dict(hacer(tipo, c, cuenta, alcances, archivo))


def terminar(tipo, sesion_nueva, archivo, como):
    guardar_json(os.path.join(BOT, archivo), {**sesion_nueva, 'login': como})
    logins[tipo] = {'estado': 'listo', 'mensaje': f'Conectada como {como}'}
    if tipo.startswith('bot_'):
        panel_bot.reiniciar()  # el bot toma la sesión al arrancar


def fallar(tipo, mensaje):
    logins[tipo] = {'estado': 'error', 'mensaje': mensaje}


def twitch_login(tipo, c, cuenta, alcances, archivo):
    """Login por código (device flow): la pantalla muestra el link, que ya trae el código."""
    try:
        d = pedir('https://id.twitch.tv/oauth2/device', urllib.parse.urlencode({'client_id': c['client_id'], 'scopes': alcances}).encode())
    except urllib.error.HTTPError as e:
        raise ValueError(f'Twitch rechazó el Client ID ({e.code}). Revisá que la app sea de tipo Público.')
    except OSError as e:
        raise ValueError(f'No pude hablar con Twitch: {e}')

    def esperar():
        espera, fin = d['interval'], time.monotonic() + d['expires_in']
        while time.monotonic() < fin:
            time.sleep(espera)
            try:
                t = pedir('https://id.twitch.tv/oauth2/token', urllib.parse.urlencode({
                    'client_id': c['client_id'], 'scopes': alcances, 'device_code': d['device_code'],
                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'}).encode())
                break
            except urllib.error.HTTPError as e:
                cuerpo = e.read().decode(errors='replace')
                if 'authorization_pending' in cuerpo:
                    continue
                if 'slow_down' in cuerpo:
                    espera += 5
                    continue
                return fallar(tipo, 'Twitch rechazó el login. Probá de nuevo')
            except OSError:
                continue  # internet cortado un momento: sigue esperando
        else:
            return fallar(tipo, 'Pasó el tiempo y no llegó la autorización. Probá de nuevo')
        try:
            v = pedir('https://id.twitch.tv/oauth2/validate', cabeceras={'Authorization': 'OAuth ' + t['access_token']})
        except OSError as e:
            return fallar(tipo, f'No pude comprobar la cuenta: {e}')
        if v['login'] != cuenta:  # si no, el bot hablaría con tu cuenta, o el título cambiaría otro canal
            return fallar(tipo, f'Entraste como {v["login"]}, no como {cuenta}. Cerrá esa sesión en Twitch y probá de nuevo')
        terminar(tipo, {'access_token': t['access_token'], 'refresh_token': t['refresh_token'], 'user_id': v['user_id']}, archivo, v['login'])

    # se anota antes de arrancar a esperar: si la respuesta llega enseguida, no queda pisada por 'esperando'
    logins[tipo] = {'estado': 'esperando', 'codigo': d['user_code'], 'link': d['verification_uri'],
                    'mensaje': f'Abrí el link con la sesión iniciada en {cuenta} y aceptá'}
    threading.Thread(target=esperar, daemon=True).start()
    return logins[tipo]


def kick_login(tipo, c, cuenta, alcances, archivo):
    """Login con vuelta a esta PC (localhost:47614): Kick no tiene login por código."""
    verificador, estado = secrets.token_urlsafe(48), secrets.token_urlsafe(16)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b'=').decode()
    link = 'https://id.kick.com/oauth/authorize?' + urllib.parse.urlencode({
        'response_type': 'code', 'client_id': c['kick_client_id'], 'redirect_uri': KICK_REDIRECCION, 'scope': alcances,
        'state': estado, 'code_challenge': reto, 'code_challenge_method': 'S256'})
    recibido = {}

    class Vuelta(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get('state', [''])[0] == estado:  # cualquier otra visita a este puerto se ignora
                recibido['code'] = q.get('code', [''])[0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write('Listo. Volvé a Stream Kit: ya podés cerrar esta pestaña'.encode())

        def log_message(self, *_):
            pass

    try:
        servidor = http.server.HTTPServer(('127.0.0.1', 47614), Vuelta)
    except OSError:
        raise ValueError('Ya hay otro login de Kick esperando: terminalo o esperá 5 minutos.')

    def esperar():
        with servidor:
            servidor.timeout = 2
            fin = time.monotonic() + 300
            while 'code' not in recibido and time.monotonic() < fin:
                servidor.handle_request()
        if not recibido.get('code'):
            return fallar(tipo, 'No llegó la autorización de Kick. Probá de nuevo')
        try:
            t = pedir('https://id.kick.com/oauth/token', urllib.parse.urlencode({
                'grant_type': 'authorization_code', 'code': recibido['code'], 'client_id': c['kick_client_id'],
                'client_secret': c['kick_client_secret'], 'redirect_uri': KICK_REDIRECCION, 'code_verifier': verificador}).encode())
            faltan = set(alcances.split()) - set(t.get('scope', alcances).split())
            if faltan:  # Kick da solo los permisos que tiene activados la app, sin avisar
                return fallar(tipo, 'La app de Kick no tiene activados estos permisos: ' + ', '.join(sorted(faltan)))
            u = pedir('https://api.kick.com/public/v1/users', cabeceras={'Authorization': 'Bearer ' + t['access_token']})['data'][0]
        except urllib.error.HTTPError as e:
            return fallar(tipo, f'Kick rechazó el login ({e.code}). Revisá el Client ID y la clave secreta')
        except (OSError, ValueError, KeyError, IndexError) as e:
            return fallar(tipo, f'No pude terminar el login de Kick: {e}')
        if tipo == 'canal_kick' and u['user_id'] != c.get('kick_broadcaster_id'):  # cambiaría el canal de otro
            return fallar(tipo, f'Entraste como {u["name"]}, que no es el dueño de {cuenta}. Cerrá esa sesión en Kick y probá de nuevo')
        if tipo == 'bot_kick' and u['name'].lower() != cuenta:  # si no, el bot hablaría con tu cuenta
            return fallar(tipo, f'Entraste como {u["name"]}, no como {cuenta}. Cerrá esa sesión en Kick y probá de nuevo')
        terminar(tipo, {'access_token': t['access_token'], 'refresh_token': t['refresh_token'],
                        'client_secret': c['kick_client_secret']}, archivo, u['name'].lower())

    logins[tipo] = {'estado': 'esperando', 'link': link, 'mensaje': f'Se abrió Kick en otra pestaña: aceptá con la sesión iniciada en {cuenta}'}
    threading.Thread(target=esperar, daemon=True).start()
    return logins[tipo]
