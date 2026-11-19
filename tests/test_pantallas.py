# python tests/test_pantallas.py: guardar, revisar y borrar pantallas, y lo que cuentan las metas. Sin internet.
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))
import json, os, tempfile, time
os.environ['STREAMKIT_DATOS'] = tempfile.mkdtemp()  # no toca tus pantallas
os.makedirs(os.path.join(os.environ['STREAMKIT_DATOS'], 'bot'), exist_ok=True)
import pantallas as p


def falla(datos, texto):
    try:
        p.guardar(datos)
    except ValueError as e:
        assert texto in str(e), e
        return
    raise AssertionError('tenía que fallar: ' + texto)


assert p.leer() == []
a = p.guardar({'nombre': '  Juego  ', 'formato': 'raro', 'css': '.mi-chat { color: red }', 'piezas': [
    {'tipo': 'chat', 'x': 1500.4, 'y': 600, 'w': 400, 'h': 460, 'clase': 'mi-chat',
     'op': {'duracion': 99999, 'color': '#ffffff', 'comandos': True, 'nombres': 'fijo'}},
    {'tipo': 'marco', 'x': -5000, 'y': 99999, 'w': 1, 'h': 10 ** 9, 'op': {'titulo': 'x' * 500}}]})
assert a['nombre'] == 'Juego' and a['formato'] == 'horizontal' and len(a['id']) == 8 and a['css'] == '.mi-chat { color: red }'
chat, marco = a['piezas']
assert chat['x'] == 1500 and chat['clase'] == 'mi-chat'
assert chat['op'] == {'duracion': 3600, 'color': '#ffffff', 'comandos': True, 'nombres': 'fijo'}, 'los números quedan en su rango'
assert (marco['w'], marco['h'], marco['x'], marco['y'], marco['op']) == (20, 2160, -10, 1070, {'titulo': 'x' * 300}), 'queda adentro del lienzo'
assert 'clase' not in marco
# lo que no va con la pieza se rechaza con un motivo que sirve para corregirlo (lo lee también un agente por el MCP)
pieza = lambda op, tipo='chat': {'nombre': 'x', 'piezas': [{'tipo': tipo, 'x': 0, 'y': 0, 'w': 100, 'h': 100, 'op': op}]}
falla(pieza({'inventada': 1}), 'Tiene: duracion')
falla(pieza({'color': 'red'}), 'color como')
falla(pieza({'duracion': '10'}), 'número')
falla(pieza({'duracion': True}), 'número')
falla(pieza({'comandos': 'si'}), 'true o false')
falla(pieza({'nombres': 'otro'}), 'propio, fijo')
falla(pieza({'texto': 5}, 'texto'), 'texto')
falla(pieza([1]), 'objeto')
falla({'nombre': 'x', 'piezas': [{'tipo': 'chat', 'clase': '1<script>'}]}, 'clase CSS')
falla({'nombre': 'x', 'css': 'x' * 20001}, 'CSS')
assert set(p.TIPOS) == {'chat', 'alertas', 'marco', 'texto', 'titulo', 'viewers', 'meta', 'lluvia', 'ultimo', 'cuenta', 'imagen'}
for tipo, e in p.ESQUEMA.items():  # cada opción de piezas.json tiene lo que necesitan el editor y la validación
    for o in e['opciones']:
        assert o['tipo'] in ('si', 'numero', 'color', 'elegir', 'texto', 'imagen') and 'def' in o and o['nombre'], (tipo, o)
        if o['tipo'] == 'numero':
            assert o['min'] <= o['def'] <= o['max'], (tipo, o)
        if o['tipo'] == 'elegir':
            assert o['def'] in [v for v, _ in o['valores']], (tipo, o)
    assert p.opciones(tipo, {o['clave']: o['def'] for o in e['opciones']}), 'los valores de siempre pasan'
assert p.leer() == [a]

b = p.guardar({'nombre': 'Vertical', 'formato': 'vertical', 'piezas': []})
a2 = p.guardar({**a, 'nombre': 'Juego 2'})  # mismo id: se reemplaza en su lugar
assert [x['nombre'] for x in p.leer()] == ['Juego 2', 'Vertical'] and a2['id'] == a['id']

falla({'nombre': ' '}, 'nombre')
falla({'nombre': 'x', 'piezas': [{'tipo': 'script'}]}, 'no existe')
falla({'nombre': 'x', 'piezas': [{'tipo': 'chat', 'x': 'mucho'}]}, 'número')
falla({'nombre': 'x', 'piezas': [{'tipo': 'texto'}] * 41}, 'hasta 40')
falla({'nombre': 'x', 'id': '../config'}, 'inválido')
falla('nada', 'inválido')

p.borrar(b['id'])
assert [x['id'] for x in p.leer()] == [a['id']]
try:
    p.borrar(b['id'])
    raise AssertionError('tenía que fallar')
except ValueError:
    pass

# metas: lo del stream cuenta desde que arrancó; lo de antes, no
apoyos = [{'t': 50, 'tipo': 'follow'}, {'t': 100, 'tipo': 'follow'}, {'t': 101, 'tipo': 'sub'}, {'t': 102, 'tipo': 'resub', 'cantidad': 7},
          {'t': 103, 'tipo': 'regalo', 'cantidad': 5}, {'t': 104, 'tipo': 'bits', 'cantidad': 300}, {'t': 105, 'tipo': 'kicks', 'cantidad': 50},
          {'t': 106, 'tipo': 'raid', 'cantidad': 80}, 'basura', {'tipo': 'follow'}]
assert p.contar(apoyos, 100) == {'follows': 1, 'subs': 7, 'bits': 300, 'kicks': 50}
assert p.contar(apoyos, None) == {'follows': 0, 'subs': 0, 'bits': 0, 'kicks': 0}, 'sin stream no cuenta'

# datos en vivo: del estado del bot y de apoyos.json
ahora = time.time()
json.dump({'actualizado': ahora, 'viewers': {'twitch': 12, 'kick': None}, 'inicio': {'twitch': ahora - 60, 'kick': None},
           'seguidores': {'twitch': 1500, 'kick': 300}}, open(p.panel_bot.ESTADO_BOT, 'w'))
json.dump([{'t': ahora - 30, 'tipo': 'follow'}, {'t': ahora - 3600, 'tipo': 'follow'}], open(p.APOYOS, 'w'))
p.canal.leer = lambda: {'twitch': {'titulo': 'Mi stream'}, 'kick': {'error': 'sin cuenta'}}
d = p.datos()
assert d['viewers'] == {'twitch': 12} and d['seguidores'] == {'twitch': 1500, 'kick': 300} and d['en_vivo']
assert d['stream']['follows'] == 1 and d['titulo'] == {'twitch': 'Mi stream'}
json.dump({'actualizado': ahora - 999}, open(p.panel_bot.ESTADO_BOT, 'w'))
assert p.datos()['viewers'] == {} and not p.datos()['en_vivo'], 'bot caído: nada en vivo'
# la guía para agentes: cada pieza y cada opción de piezas.json, y llms.txt nombra todas las piezas
ref = p.referencia()
for tipo, e in p.ESQUEMA.items():
    assert f'### `{tipo}`' in ref and all(f"- `{o['clave']}` (" in ref for o in e['opciones']), tipo
guia = open(os.path.join(_RAIZ, 'llms.txt'), encoding='utf-8').read()
assert guia.startswith('# Stream Kit') and all(f'`{t}`' in guia for t in p.TIPOS)

# animaciones: las mismas opciones en cada pieza, con los valores de siempre de esa pieza (el chat y las alertas, como antes)
claves = lambda t: [o['clave'] for o in p.ESQUEMA[t]['opciones']]
de = lambda t, c: next(o['def'] for o in p.ESQUEMA[t]['opciones'] if o['clave'] == c)
assert claves('chat')[-3:] == ['entrada', 'salida', 'velocidad'] and (de('chat', 'entrada'), de('chat', 'salida')) == ('abajo', 'aparecer')
assert claves('texto')[-3:] == ['entrada', 'velocidad', 'retraso'] and de('texto', 'entrada') == 'ninguna'
assert not {'entrada', 'salida'} & set(claves('lluvia')) and '_animacion' not in p.ESQUEMA
assert 'animacion' not in p.ESQUEMA['chat'] and 'animacion_def' not in p.ESQUEMA['chat'], 'el esquema que se sirve ya viene armado'
assert p.opciones('texto', {'entrada': 'rebote', 'velocidad': 99999, 'retraso': 500}) == {'entrada': 'rebote', 'velocidad': 3000, 'retraso': 500}
falla(pieza({'salida': 'volar'}), 'ninguna, aparecer')
# fuentes de Google: solo el nombre, sin nada que se pueda colar en el link
assert p.opciones('texto', {'fuente': 'google', 'fuente_google': 'Bebas Neue'}) == {'fuente': 'google', 'fuente_google': 'Bebas Neue'}
falla(pieza({'fuente_google': 'x&family=y'}, 'texto'), 'letras, números y espacios')
# imagen: una subida o un link https
assert p.opciones('imagen', {'imagen': 'logo.png'}) == {'imagen': 'logo.png'}
assert p.opciones('imagen', {'imagen': 'https://ejemplo.com/a.gif'})['imagen'] == 'https://ejemplo.com/a.gif'
for malo in ('../config.json', 'a.svg', 'http://x.com/a.png', 'javascript:alert(1)', 'C:/x.png', 5):
    falla(pieza({'imagen': malo}, 'imagen'), 'imagen subida')
assert p.nombre_imagen('mi logo (1).webp') and not p.nombre_imagen('..png') and not p.nombre_imagen('a/b.png')
import io
crudo = io.BytesIO(b'PNG' + b'x' * 5001)
assert p.guardar_imagen('C:/fotos/logo.png', crudo.read, 5004) == 'logo.png' and p.imagenes() == ['logo.png']
assert os.path.getsize(os.path.join(p.IMAGENES, 'logo.png')) == 5004
for nombre, tam, texto in (('a.svg', 10, 'png, jpg'), ('.png', 10, 'png, jpg'), ('b.png', 16 * 1024 * 1024, '15 MB')):
    try:
        p.guardar_imagen(nombre, io.BytesIO(b'x' * 10).read, tam)
        raise AssertionError('tenía que fallar')
    except ValueError as e:
        assert texto in str(e) or 'nombre' in str(e), e
assert p.imagenes() == ['logo.png'], 'lo rechazado no queda'
# las carpetas del nombre no cuentan: ../../x.png se guarda como x.png, adentro de imagenes
assert p.guardar_imagen('../../x.png', io.BytesIO(b'x').read, 1) == 'x.png' and os.path.isfile(os.path.join(p.IMAGENES, 'x.png'))
# textos compartidos
assert p.leer_textos() == {} and p.datos()['textos'] == {}
assert p.guardar_textos({'tema': 'Ranked', 'proximo': 'x' * 400}) == {'tema': 'Ranked', 'proximo': 'x' * 300}
assert p.datos()['textos']['tema'] == 'Ranked'
for malo, texto in (({'Tema': 'x'}, 'minúsculas'), ({'tema del dia': 'x'}, 'minúsculas'), ({'t': 5}, 'texto'),
                    ([1], 'objeto'), ({f't{i}': '' for i in range(31)}, '30')):
    try:
        p.guardar_textos(malo)
        raise AssertionError('tenía que fallar')
    except ValueError as e:
        assert texto in str(e), e
assert p.leer_textos()['tema'] == 'Ranked', 'lo rechazado no pisa lo guardado'
print('ok')
