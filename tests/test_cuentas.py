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

BASE = {'client_id': 'abc123', 'kick_client_id': '01ABC'}

# guardar: solo las claves de las apps (los nombres salen de cada conexión) y nunca devuelve la clave secreta
c.guardar({**BASE, 'kick_client_secret': 'secreto12345'})
cfg = c.leer_config()
assert cfg['client_id'] == 'abc123' and cfg['kick_client_secret'] == 'secreto12345' and reinicios
leido = c.leer()
assert leido['kick_secreto'] is True and 'secreto12345' not in json.dumps(leido)
assert set(leido['config']) == {'client_id', 'kick_client_id'} and not leido['cuentas']['bot_twitch']['conectada']
# sin clave nueva, queda la guardada
c.guardar(BASE)
assert c.leer_config()['kick_client_secret'] == 'secreto12345'

# lo que no se acepta
def rechaza(**k):
    try:
        c.guardar({**BASE, **k})
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')
assert 'Twitch' in rechaza(client_id='con espacio')
assert 'clave secreta' in rechaza(kick_client_secret='a b')

# otra app de Twitch: sus sesiones viejas se borran; las de Kick quedan
for archivo in ('token.json', 'token-canal.json', 'token-kick.json'):
    json.dump({'access_token': 'a', 'refresh_token': 'r', 'login': 'x'}, open(os.path.join(c.BOT, archivo), 'w'))
c.guardar({**BASE, 'client_id': 'otra1'})
assert not os.path.exists(os.path.join(c.BOT, 'token.json')) and not os.path.exists(os.path.join(c.BOT, 'token-canal.json'))
assert os.path.exists(os.path.join(c.BOT, 'token-kick.json'))

# login de Twitch: muestra el código, espera la autorización y el nombre sale de la cuenta con la que se entró
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
assert c.leer_config()['bot'] == 'otrobot' and c.leer()['cuentas']['bot_twitch']['como'] == 'otrobot'
intentos = iter([{'access_token': 'at', 'refresh_token': 'rt'}])
respuestas({'oauth2/device': {'user_code': 'EFGH', 'verification_uri': 'https://twitch.tv/activate?y', 'device_code': 'd', 'interval': 0, 'expires_in': 30},
            'oauth2/token': token, 'oauth2/validate': {'login': 'micanal', 'user_id': '7'}})
c.empezar('canal_twitch')
assert esperar_fin('canal_twitch')['estado'] == 'listo' and c.leer_config()['canal'] == 'micanal'

# login de Kick de tu canal: el nombre del canal (con - en vez de _) y sus números salen de la cuenta
import urllib.parse, urllib.request
def kick(tipo, tabla):
    respuestas({'oauth/token': {'access_token': 'kt', 'refresh_token': 'kr', 'scope': c.CUENTAS[tipo][3]}, **tabla})
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(c.empezar(tipo)['link']).query)
    urllib.request.urlopen(f"http://127.0.0.1:47614/callback?state={q['state'][0]}&code=x", timeout=5).read()
    return esperar_fin(tipo)
canal = {'kick.com/api/v2/channels/mi-canal': {'id': 5, 'chatroom': {'id': 6}, 'user_id': 7}}
fin = kick('canal_kick', {'public/v1/users': {'data': [{'name': 'Mi_Canal', 'user_id': 7}]},
                          'public/v1/channels': {'data': [{'slug': 'mi-canal'}]}, **canal})
cfg = c.leer_config()
assert fin['estado'] == 'listo', fin
assert (cfg['kick_canal_slug'], cfg['kick_canal'], cfg['kick_chatroom'], cfg['kick_broadcaster_id']) == ('mi-canal', 5, 6, 7)
# si Kick no da el canal, se prueba con el nombre de la cuenta; si ese canal es de otro, no se guarda nada
os.remove(os.path.join(c.BOT, 'token-canal-kick.json'))
assert kick('canal_kick', {'public/v1/users': {'data': [{'name': 'Mi_Canal', 'user_id': 7}]}, 'public/v1/channels': falla(404), **canal})['estado'] == 'listo'
os.remove(os.path.join(c.BOT, 'token-canal-kick.json'))
fin = kick('canal_kick', {'public/v1/users': {'data': [{'name': 'Mi_Canal', 'user_id': 8}]}, 'public/v1/channels': falla(404), **canal})
assert fin['estado'] == 'error' and not os.path.exists(os.path.join(c.BOT, 'token-canal-kick.json')), fin
assert kick('bot_kick', {'public/v1/users': {'data': [{'name': 'ElBot', 'user_id': 9}]}})['estado'] == 'listo'
assert c.leer_config()['kick_bot'] == 'elbot'

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
