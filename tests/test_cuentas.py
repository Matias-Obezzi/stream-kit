# python tests/test_cuentas.py: sin internet y sin tocar tu config. Prueba la pantalla de Configuración: qué acepta, qué borra y los logins
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import json, os, tempfile, time, urllib.error
os.environ["STREAMKIT_DATOS"] = tempfile.mkdtemp()  # config de ejemplo en una carpeta aparte: no toca la tuya
import cuentas as c

reinicios = []
c.panel_bot.reiniciar = lambda: reinicios.append(1)
pedidos = []
def respuestas(tabla):
    def pedir(url, cuerpo=None, metodo=None, cabeceras=None):
        pedidos.append(url)
        r = next(v for k, v in tabla.items() if k in url)
        if isinstance(r, Exception):
            raise r
        return r() if callable(r) else r
    c.pedir = pedir
def falla(codigo, cuerpo=b'{}'):
    import io
    return urllib.error.HTTPError('u', codigo, 'x', {}, io.BytesIO(cuerpo))

BASE = {'client_id': 'abc123', 'canal': 'MiCanal', 'bot': 'MiBot', 'kick_client_id': '01ABC', 'kick_canal_slug': 'mi-canal', 'kick_bot': 'mibot'}

# guardar: pasa los nombres a minúscula, busca los números del canal de Kick y nunca devuelve la clave secreta
respuestas({'kick.com/api/v2/channels/mi-canal': {'id': 5, 'chatroom': {'id': 6}, 'user_id': 7}})
c.guardar({**BASE, 'kick_client_secret': 'secreto12345'})
cfg = c.leer_config()
assert (cfg['canal'], cfg['bot'], cfg['kick_canal'], cfg['kick_chatroom'], cfg['kick_broadcaster_id']) == ('micanal', 'mibot', 5, 6, 7)
assert cfg['client_id'] == 'abc123' and cfg['kick_client_secret'] == 'secreto12345' and reinicios
leido = c.leer()
assert leido['kick_secreto'] is True and 'secreto12345' not in json.dumps(leido)
assert leido['config']['canal'] == 'micanal' and not leido['cuentas']['bot_twitch']['conectada']
# sin clave nueva, queda la guardada; el canal de Kick no se vuelve a buscar si no cambió
pedidos.clear()
c.guardar(BASE)
assert c.leer_config()['kick_client_secret'] == 'secreto12345' and not pedidos

# lo que no se acepta
def rechaza(**k):
    try:
        c.guardar({**BASE, **k})
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')
assert 'Twitch' in rechaza(canal='con espacio')
assert 'clave secreta' in rechaza(kick_client_secret='a b')
respuestas({'kick.com': falla(404)})
assert 'No encontré el canal de Kick' in rechaza(kick_canal_slug='no-existe')
assert c.leer_config()['kick_canal_slug'] == 'mi-canal', 'si algo falla, no guarda nada'

# otra cuenta del bot: su sesión vieja se borra; la de tu canal queda
for archivo in ('token.json', 'token-canal.json'):
    json.dump({'access_token': 'a', 'refresh_token': 'r', 'login': 'x'}, open(os.path.join(c.BOT, archivo), 'w'))
c.guardar({**BASE, 'bot': 'otrobot'})
assert not os.path.exists(os.path.join(c.BOT, 'token.json')) and os.path.exists(os.path.join(c.BOT, 'token-canal.json'))

# login de Twitch: muestra el código, espera la autorización y comprueba que sea la cuenta pedida
def esperar_fin(tipo):
    fin = time.monotonic() + 5
    while c.logins[tipo].get('estado') == 'esperando' and time.monotonic() < fin:
        time.sleep(0.05)
    return c.logins[tipo]
intentos = iter([falla(400, b'{"message":"authorization_pending"}'), {'access_token': 'at', 'refresh_token': 'rt'}])
def token():
    r = next(intentos)
    if isinstance(r, Exception):
        raise r
    return r
respuestas({'oauth2/device': {'user_code': 'ABCD', 'verification_uri': 'https://twitch.tv/activate?x', 'device_code': 'd', 'interval': 0, 'expires_in': 30},
            'oauth2/token': token, 'oauth2/validate': {'login': 'otrobot', 'user_id': '99'}})
reinicios.clear()
r = c.empezar('bot_twitch')
assert r['codigo'] == 'ABCD' and r['link'].startswith('https://twitch.tv/activate')
assert esperar_fin('bot_twitch')['estado'] == 'listo'
guardada = json.load(open(os.path.join(c.BOT, 'token.json')))
assert guardada == {'access_token': 'at', 'refresh_token': 'rt', 'user_id': '99', 'login': 'otrobot'} and reinicios, 'el bot se reinicia para tomarla'
assert c.leer()['cuentas']['bot_twitch']['como'] == 'otrobot'
# con otra cuenta abierta en el navegador: no se guarda nada
os.remove(os.path.join(c.BOT, 'token-canal.json'))
intentos = iter([{'access_token': 'at', 'refresh_token': 'rt'}])
c.empezar('canal_twitch')
assert esperar_fin('canal_twitch')['estado'] == 'error' and 'no como micanal' in c.logins['canal_twitch']['mensaje']
assert not os.path.exists(os.path.join(c.BOT, 'token-canal.json'))

# sin las claves guardadas, no arranca ningún login
cfg = c.leer_config()
cfg['kick_client_secret'] = ''
c.guardar_json(c.CONFIG, cfg)
try:
    c.empezar('bot_kick')
    raise AssertionError
except ValueError as e:
    assert 'clave secreta' in str(e)
try:
    c.empezar('cualquiera')
    raise AssertionError
except ValueError:
    pass
print('ok')
