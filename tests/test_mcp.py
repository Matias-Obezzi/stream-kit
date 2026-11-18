# python tests/test_mcp.py: el MCP para agentes, mensaje por mensaje. Sin internet y sin tocar tus pantallas.
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))
import json, os, tempfile
os.environ['STREAMKIT_DATOS'] = tempfile.mkdtemp()
import mcp

n = iter(range(1, 1000))
def pedir(metodo, params=None):
    return mcp.atender({'jsonrpc': '2.0', 'id': next(n), 'method': metodo, **({'params': params} if params is not None else {})}, 8080, '9.9')
def usar(nombre, **args):
    r = pedir('tools/call', {'name': nombre, 'arguments': args})['result']
    texto = r['content'][0]['text']
    return (texto, True) if r.get('isError') else (json.loads(texto), False)

r = pedir('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'prueba', 'version': '1'}})['result']
assert r['protocolVersion'] == '2025-06-18' and r['capabilities'] == {'tools': {}} and r['serverInfo']['version'] == '9.9'
assert 'http://127.0.0.1:8080/llms.txt' in r['instructions']
assert pedir('initialize', {'protocolVersion': '1999-01-01'})['result']['protocolVersion'] == mcp.VERSIONES[0], 'versión que no conoce: la suya'
assert mcp.atender({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, 8080, '') is None, 'las notificaciones no llevan respuesta'
assert pedir('ping')['result'] == {}
herramientas = {h['name']: h for h in pedir('tools/list')['result']['tools']}
assert set(herramientas) == {'ver_piezas', 'listar_pantallas', 'ver_pantalla', 'guardar_pantalla', 'borrar_pantalla', 'datos_en_vivo'}
assert all(h['description'] and h['inputSchema']['type'] == 'object' for h in herramientas.values())
json.dumps(herramientas)  # todo se puede mandar

piezas, _ = usar('ver_piezas')
assert piezas['formatos']['vertical'] == {'ancho': 1080, 'alto': 1920} and 'descripcion' in piezas['piezas']['chat']
assert usar('listar_pantallas') == ([], False)

# un agente arma una pantalla, se equivoca en una opción, lo corrige y la cambia
error, fallo = usar('guardar_pantalla', pantalla={'nombre': 'Juego', 'piezas': [{'tipo': 'chat', 'x': 1460, 'y': 420, 'w': 420, 'h': 620, 'op': {'tamaño': 20}}]})
assert fallo and 'Tiene: duracion' in error, error
p, fallo = usar('guardar_pantalla', pantalla={'nombre': 'Juego', 'css': '.pz-quien { text-transform: uppercase }',
                                              'piezas': [{'tipo': 'chat', 'x': 1460, 'y': 420, 'w': 420, 'h': 620, 'op': {'tamano': 20}}]})
assert not fallo and p['link'] == f"http://127.0.0.1:8080/pantalla/{p['id']}" and p['css']
lista, _ = usar('listar_pantallas')
assert lista == [{'id': p['id'], 'nombre': 'Juego', 'formato': 'horizontal', 'piezas': 1, 'link': p['link']}]
vista, _ = usar('ver_pantalla', id=p['id'])
vista['piezas'].append({'tipo': 'marco', 'x': 40, 'y': 40, 'w': 640, 'h': 360, 'op': {'titulo': 'Cámara'}})
del vista['link']
cambiada, fallo = usar('guardar_pantalla', pantalla=vista)
assert not fallo and cambiada['id'] == p['id'] and len(cambiada['piezas']) == 2
assert usar('ver_pantalla', id='nada')[1], 'id que no existe: error que se puede leer'
assert usar('borrar_pantalla', id=p['id']) == ({'borrada': p['id']}, False) and usar('listar_pantallas') == ([], False)
assert usar('borrar_pantalla', id=p['id'])[1]

datos, _ = usar('datos_en_vivo')
assert set(datos) == {'viewers', 'seguidores', 'stream', 'en_vivo', 'titulo'}

assert pedir('tools/call', {'name': 'rm', 'arguments': {}})['error']['code'] == -32602
assert pedir('tools/call', {'name': 'ver_pantalla', 'arguments': [1]})['error']['code'] == -32602
assert pedir('resources/list')['error']['code'] == -32601
assert mcp.atender({'id': 1, 'method': 'ping'}, 8080, '')['error']['code'] == -32600
assert mcp.atender('basura', 8080, '')['error']['code'] == -32600
print('ok')
