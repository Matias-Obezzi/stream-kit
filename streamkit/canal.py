"""Título, categoría, idioma y etiquetas del stream en Twitch y Kick, con tu cuenta (no la del bot).

Corre dentro del proceso de la web. Las sesiones se conectan una vez desde el bot: --login-canal y --login-canal-kick.
"""
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

from rutas import BOT, config as ruta_config

CONFIG = ruta_config(os.path.join('bot', 'config.json'))
TOKEN_TWITCH = os.path.join(BOT, 'token-canal.json')  # no compartir: con esto se cambia tu canal
TOKEN_KICK = os.path.join(BOT, 'token-canal-kick.json')
IDIOMAS = ('es', 'en', 'pt', 'other')  # Twitch acepta más, pero estos son los que tienen sentido acá
LARGO_TITULO = 140  # el máximo de Twitch; Kick acepta eso también
candado = threading.Lock()  # los refresh token son de un solo uso: dos pedidos a la vez no pueden refrescar juntos
FALTA = {'twitch': 'Falta conectar tu cuenta de Twitch: andá a Configuración',
         'kick': 'Falta conectar tu cuenta de Kick: andá a Configuración'}


def pedir(url, cuerpo=None, metodo=None, cabeceras=None):
    pedido = urllib.request.Request(url, data=cuerpo, method=metodo, headers={'User-Agent': 'StreamKit', **(cabeceras or {})})
    with urllib.request.urlopen(pedido, timeout=15) as r:
        datos = r.read()
    return json.loads(datos) if datos else {}


def leer_json(ruta):
    with open(ruta, encoding='utf-8') as f:
        return json.load(f)


def guardar_json(ruta, datos):
    with open(ruta + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(datos, f)
    os.replace(ruta + '.tmp', ruta)


def refrescar(plataforma, usado):
    """Pide una sesión nueva, salvo que otro pedido ya lo haya hecho mientras este esperaba el candado."""
    with candado:
        ruta = TOKEN_TWITCH if plataforma == 'twitch' else TOKEN_KICK
        t = leer_json(ruta)
        if t['access_token'] != usado:
            return
        config = leer_json(CONFIG)
        if plataforma == 'twitch':
            campos = {'client_id': config['client_id'], 'grant_type': 'refresh_token', 'refresh_token': t['refresh_token']}
            n = pedir('https://id.twitch.tv/oauth2/token', urllib.parse.urlencode(campos).encode())
        else:
            campos = {'client_id': config['kick_client_id'], 'client_secret': t['client_secret'], 'grant_type': 'refresh_token',
                      'refresh_token': t['refresh_token']}
            n = pedir('https://id.kick.com/oauth/token', urllib.parse.urlencode(campos).encode())
        guardar_json(ruta, {**t, 'access_token': n['access_token'], 'refresh_token': n.get('refresh_token') or t['refresh_token']})


def api(plataforma, metodo, ruta, cuerpo=None, reintento=True):
    t = leer_json(TOKEN_TWITCH if plataforma == 'twitch' else TOKEN_KICK)
    cabeceras = {'Authorization': 'Bearer ' + t['access_token'], 'Accept': 'application/json'}
    if plataforma == 'twitch':
        cabeceras['Client-Id'] = leer_json(CONFIG)['client_id']
        url = 'https://api.twitch.tv/helix/' + ruta
    else:
        url = 'https://api.kick.com/public/' + ruta
    if cuerpo is not None:
        cabeceras['Content-Type'] = 'application/json'
    try:
        return pedir(url, None if cuerpo is None else json.dumps(cuerpo).encode(), metodo, cabeceras)
    except urllib.error.HTTPError as e:
        if e.code == 401 and reintento:
            refrescar(plataforma, t['access_token'])
            return api(plataforma, metodo, ruta, cuerpo, False)
        raise


def motivo(plataforma, e):
    """El error en palabras, con lo que dice la plataforma si lo dice."""
    if isinstance(e, FileNotFoundError):
        return FALTA[plataforma]
    if isinstance(e, urllib.error.HTTPError):
        try:
            detalle = json.loads(e.read() or b'{}').get('message', '')
        except (ValueError, OSError, AttributeError):
            detalle = ''
        if e.code in (401, 403) or (e.code == 400 and not detalle):
            detalle = 'la sesión venció o no tiene permiso. ' + (
                'Revisá que la app de Kick tenga los permisos del canal y ' if plataforma == 'kick' else '') + 'conectala de nuevo'
        return f'{plataforma.capitalize()} respondió {e.code}' + (f': {detalle}' if detalle else '')
    return f'No pude hablar con {plataforma.capitalize()}: {e}'


def leer():
    """Lo que tiene puesto cada canal ahora."""
    r = {}
    try:
        uid = leer_json(TOKEN_TWITCH)['user_id']
        c = api('twitch', 'GET', 'channels?broadcaster_id=' + uid)['data'][0]
        r['twitch'] = {'titulo': c['title'], 'categoria': {'id': c['game_id'], 'nombre': c['game_name']},
                       'idioma': c['broadcaster_language'], 'etiquetas': c.get('tags') or []}
    except (OSError, ValueError, KeyError, IndexError) as e:
        r['twitch'] = {'error': motivo('twitch', e)}
    try:
        c = api('kick', 'GET', 'v1/channels')['data'][0]  # sin parámetros devuelve el canal de la sesión
        cat, stream = c.get('category') or {}, c.get('stream') or {}
        r['kick'] = {'titulo': c['stream_title'], 'categoria': {'id': cat.get('id'), 'nombre': cat.get('name', '')},
                     'idioma': stream.get('language', ''), 'etiquetas': stream.get('custom_tags') or [],
                     'en_vivo': bool(stream.get('is_live'))}  # sin stream, la API de Kick devuelve el título y la categoría vacíos
    except (OSError, ValueError, KeyError, IndexError) as e:
        r['kick'] = {'error': motivo('kick', e)}
    return r


def buscar(texto):
    """Categorías que coinciden en cada plataforma: cada una tiene sus propios ids."""
    texto = str(texto).strip()[:100]
    r = {'twitch': [], 'kick': []}
    if len(texto) < 3:  # Kick pide al menos 3 letras
        return r
    try:
        datos = api('twitch', 'GET', 'search/categories?' + urllib.parse.urlencode({'query': texto, 'first': 10}))['data']
        r['twitch'] = [{'id': c['id'], 'nombre': c['name']} for c in datos]
    except (OSError, ValueError, KeyError) as e:
        r['error_twitch'] = motivo('twitch', e)
    try:
        datos = api('kick', 'GET', 'v2/categories?' + urllib.parse.urlencode({'name': texto, 'limit': 10}))['data']
        r['kick'] = [{'id': c['id'], 'nombre': c['name']} for c in datos]
    except (OSError, ValueError, KeyError) as e:
        r['error_kick'] = motivo('kick', e)
    return r


def validar(datos):
    """Revisa lo que manda la web. Devuelve (titulo, idioma, etiquetas, ids de categoría por plataforma); si algo está mal, ValueError."""
    if not isinstance(datos, dict):
        raise ValueError('Pedido inválido.')
    titulo = datos.get('titulo')
    if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= LARGO_TITULO:
        raise ValueError(f'El título tiene que tener entre 1 y {LARGO_TITULO} caracteres.')
    if re.search(r'[\x00-\x1f\x7f]', titulo):
        raise ValueError('El título no puede tener saltos de línea.')
    idioma = datos.get('idioma')
    if idioma not in IDIOMAS:
        raise ValueError('Elegí un idioma de la lista.')
    etiquetas = datos.get('etiquetas')
    if not isinstance(etiquetas, list) or len(etiquetas) > 10:
        raise ValueError('Hasta 10 etiquetas.')
    for e in etiquetas:
        # la regla de Twitch: sin espacios ni signos, hasta 25. Kick acepta lo mismo
        if not isinstance(e, str) or not re.fullmatch(r'[^\W_]{1,25}', e):
            raise ValueError(f'"{e}": cada etiqueta va sin espacios ni signos, hasta 25 letras o números.')
    if len({e.casefold() for e in etiquetas}) != len(etiquetas):
        raise ValueError('Hay una etiqueta repetida.')
    plataformas = datos.get('plataformas')
    if not isinstance(plataformas, list) or not plataformas or not set(plataformas) <= {'twitch', 'kick'}:
        raise ValueError('Elegí al menos una plataforma.')
    categorias = {}
    for p in plataformas:
        c = (datos.get('categorias') or {}).get(p)
        if c in (None, ''):
            continue  # sin categoría elegida, esa plataforma la deja como está
        if not re.fullmatch(r'\d{1,12}', str(c)):
            raise ValueError(f'Categoría inválida en {p}.')
        categorias[p] = str(c)
    return titulo.strip(), idioma, etiquetas, categorias, plataformas


def guardar(datos):
    """Cambia cada plataforma elegida. Devuelve el resultado de cada una: si una falla, la otra igual se cambia."""
    titulo, idioma, etiquetas, categorias, plataformas = validar(datos)
    r = {}
    if 'twitch' in plataformas:
        cuerpo = {'title': titulo, 'broadcaster_language': idioma, 'tags': etiquetas}
        if 'twitch' in categorias:
            cuerpo['game_id'] = categorias['twitch']
        try:
            api('twitch', 'PATCH', 'channels?broadcaster_id=' + leer_json(TOKEN_TWITCH)['user_id'], cuerpo)
            r['twitch'] = {'ok': True}
        except (OSError, ValueError, KeyError) as e:
            r['twitch'] = {'ok': False, 'error': motivo('twitch', e)}
    if 'kick' in plataformas:  # Kick no deja cambiar el idioma por API: queda el del canal
        cuerpo = {'stream_title': titulo, 'custom_tags': etiquetas}
        if 'kick' in categorias:
            cuerpo['category_id'] = int(categorias['kick'])
        try:
            api('kick', 'PATCH', 'v1/channels', cuerpo)
            r['kick'] = {'ok': True}
        except (OSError, ValueError, KeyError) as e:
            r['kick'] = {'ok': False, 'error': motivo('kick', e)}
    return r
