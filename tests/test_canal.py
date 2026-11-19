# python tests/test_canal.py: sin internet y sin tocar tus sesiones. Prueba qué lee, qué manda y qué rechaza el cambio de título
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import os, tempfile
os.environ["STREAMKIT_DATOS"] = tempfile.mkdtemp()  # config de ejemplo en una carpeta aparte: no toca la tuya
import io, json, os, tempfile, urllib.error
import canal as c

carpeta = tempfile.mkdtemp()
c.CONFIG, c.TOKEN_TWITCH, c.TOKEN_KICK = (os.path.join(carpeta, n) for n in ('config.json', 'tw.json', 'ki.json'))
json.dump({'client_id': 'cid', 'kick_client_id': 'kid'}, open(c.CONFIG, 'w'))

pedidos, respuestas = [], []
def falso(url, cuerpo=None, metodo=None, cabeceras=None):
    pedidos.append((url, cuerpo, metodo, cabeceras))
    r = respuestas.pop(0)
    if isinstance(r, tuple):
        raise urllib.error.HTTPError(url, r[0], 'x', {}, io.BytesIO(json.dumps(r[1]).encode()))
    return r
c.pedir = falso

# sin sesiones: cada una dice cómo conectarla, y nada sale a internet
r = c.leer()
assert r['twitch']['error'].endswith('Configuración') and r['kick']['error'].endswith('Configuración') and not pedidos

json.dump({'access_token': 'a1', 'refresh_token': 'r1', 'user_id': '42'}, open(c.TOKEN_TWITCH, 'w'))
json.dump({'access_token': 'k1', 'refresh_token': 'kr1', 'client_secret': 's'}, open(c.TOKEN_KICK, 'w'))
respuestas[:] = [{'data': [{'title': 'Ranked', 'game_id': '516575', 'game_name': 'VALORANT', 'broadcaster_language': 'es', 'tags': ['Argentina']}]},
                 {'data': [{'stream_title': 'Ranked', 'category': {'id': 64, 'name': 'VALORANT'}, 'stream': {'language': 'es', 'custom_tags': []}}]}]
r = c.leer()
assert r['twitch'] == {'titulo': 'Ranked', 'categoria': {'id': '516575', 'nombre': 'VALORANT'}, 'idioma': 'es', 'etiquetas': ['Argentina']}
assert r['kick'] == {'titulo': 'Ranked', 'categoria': {'id': 64, 'nombre': 'VALORANT'}, 'idioma': 'es', 'etiquetas': [], 'en_vivo': False}
assert pedidos[0][0].endswith('channels?broadcaster_id=42') and pedidos[0][3]['Client-Id'] == 'cid' and pedidos[1][0].endswith('/public/v1/channels')

# con 401 refresca una sola vez, guarda la sesión nueva sin perder el resto y reintenta
pedidos.clear()
respuestas[:] = [(401, {}), {'access_token': 'a2', 'refresh_token': 'r2'}, {'data': [{'id': '1', 'name': 'VALORANT'}]},
                 {'data': [{'id': 64, 'name': 'VALORANT'}, {'id': 6417, 'name': 'Valorant: Mobile'}]}]
r = c.buscar('valo')
assert r['twitch'] == [{'id': '1', 'nombre': 'VALORANT'}] and [k['id'] for k in r['kick']] == [64, 6417]
assert json.load(open(c.TOKEN_TWITCH)) == {'access_token': 'a2', 'refresh_token': 'r2', 'user_id': '42'}
assert 'refresh_token=r1' in pedidos[1][1].decode() and pedidos[2][3]['Authorization'] == 'Bearer a2'
assert 'name=valo' in pedidos[3][0] and '/public/v2/categories' in pedidos[3][0]
assert c.buscar('va') == {'twitch': [], 'kick': []}, 'menos de 3 letras: no busca'

# guardar: cada plataforma con sus campos y su categoría; sin categoría elegida no la toca
pedidos.clear()
respuestas[:] = [{}, {}]
datos = {'titulo': ' Ranked con Hush ', 'idioma': 'es', 'etiquetas': ['Argentina', 'Español'], 'categorias': {'twitch': '516575', 'kick': ''},
         'plataformas': ['twitch', 'kick']}
assert c.guardar(datos) == {'twitch': {'ok': True}, 'kick': {'ok': True}}
assert pedidos[0][2] == 'PATCH' and pedidos[0][0].endswith('channels?broadcaster_id=42')
assert json.loads(pedidos[0][1]) == {'title': 'Ranked con Hush', 'broadcaster_language': 'es', 'tags': ['Argentina', 'Español'], 'game_id': '516575'}
assert json.loads(pedidos[1][1]) == {'stream_title': 'Ranked con Hush', 'custom_tags': ['Argentina', 'Español']}, 'Kick sin categoría ni idioma'

# si una falla, la otra igual se cambia, y el error dice lo que contestó la plataforma
pedidos.clear()
respuestas[:] = [(400, {'message': 'invalid tag'}), {}]
r = c.guardar({**datos, 'categorias': {'kick': '64'}})
assert r['twitch'] == {'ok': False, 'error': 'Twitch respondió 400: invalid tag'} and r['kick'] == {'ok': True}
assert json.loads(pedidos[1][1])['category_id'] == 64 and 'game_id' not in json.loads(pedidos[0][1])
respuestas[:] = [{}]
assert c.guardar({**datos, 'plataformas': ['kick']}) == {'kick': {'ok': True}}, 'solo la elegida'

# lo que rechaza antes de salir a internet
pedidos.clear()
def rechaza(**k):
    try:
        c.guardar({**datos, **k})
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')
assert 'título' in rechaza(titulo='')
assert 'título' in rechaza(titulo='x' * 141)
assert 'saltos' in rechaza(titulo='a\nb')
assert 'idioma' in rechaza(idioma='xx')
assert 'sin espacios' in rechaza(etiquetas=['dos palabras'])
assert 'sin espacios' in rechaza(etiquetas=['con-guion'])
assert '10' in rechaza(etiquetas=[f'e{i}' for i in range(11)])
assert 'repetida' in rechaza(etiquetas=['Ranked', 'ranked'])
assert 'plataforma' in rechaza(plataformas=[])
assert 'plataforma' in rechaza(plataformas=['youtube'])
assert 'Categoría' in rechaza(categorias={'twitch': '1; drop'})
assert not pedidos, 'nada salió a internet'
assert c.validar({**datos, 'etiquetas': ['Ñandú', 'Valorant2']})[2] == ['Ñandú', 'Valorant2'], 'tildes y números sí'

# presets: se guardan con las mismas reglas, el mismo nombre reemplaza
assert c.presets() == []
pre = {'nombre': 'Ranked', 'titulo': 'Rankeds', 'idioma': 'es', 'etiquetas': ['Argentina'],
       'categorias': {'twitch': {'id': '516575', 'nombre': 'VALORANT'}, 'kick': ''}}
c.guardar_preset(pre)
c.guardar_preset({**pre, 'titulo': 'Rankeds 2'})
assert [(p['nombre'], p['titulo'], list(p['categorias'])) for p in c.presets()] == [('Ranked', 'Rankeds 2', ['twitch'])]
def rechaza_preset(**k):
    try:
        c.guardar_preset({**pre, **k})
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')
assert 'nombre' in rechaza_preset(nombre=' ')
assert 'título' in rechaza_preset(titulo='')
assert 'Categoría' in rechaza_preset(categorias={'twitch': {'id': 'x', 'nombre': 'a'}})
assert 'inválido' in rechaza_preset(categorias=['twitch'])
c.borrar_preset('Ranked')
assert c.presets() == []
assert not pedidos, 'nada salió a internet'
print('ok')
