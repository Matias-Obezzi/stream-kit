"""MCP para agentes de IA: ver, crear, cambiar y borrar las pantallas para OBS, y leer los datos en vivo.

Lo sirve la misma app en http://127.0.0.1:8080/mcp (transporte HTTP de MCP: cada pedido es un POST con un mensaje
JSON-RPC y la respuesta va en JSON). Solo contesta a esta PC. En Claude Code:
    claude mcp add --transport http stream-kit http://127.0.0.1:8080/mcp
"""
import json

import pantallas

VERSIONES = ('2025-06-18', '2025-03-26', '2024-11-05')  # la primera es la que usamos si el cliente pide otra

INSTRUCCIONES = (
    'Stream Kit arma pantallas para OBS: lienzos de 1920x1080 (horizontal) o 1080x1920 (vertical) con piezas como el '
    'chat de Twitch y Kick, alertas, marcos para la cámara, textos, metas o una lluvia de emojis. Cada pantalla se ve '
    'en OBS con una fuente de navegador que apunta a su link, del mismo tamaño que la pantalla; lo vacío es '
    'transparente. Usá ver_piezas para saber qué piezas hay y qué opciones tiene cada una antes de armar o cambiar '
    'una pantalla. Para cambiar una, leela con ver_pantalla, cambiá lo que haga falta y guardala entera con '
    'guardar_pantalla y el mismo id. OBS toma los cambios solo en unos segundos.'
)

PANTALLA = {
    'type': 'object',
    'description': 'Una pantalla entera. Sin id se crea una nueva; con el id de una que existe, se reemplaza.',
    'properties': {
        'id': {'type': 'string', 'description': 'El id de una pantalla que ya existe, para cambiarla.'},
        'nombre': {'type': 'string', 'description': 'Hasta 60 caracteres.'},
        'formato': {'type': 'string', 'enum': ['horizontal', 'vertical'], 'description': 'horizontal: 1920x1080. vertical: 1080x1920.'},
        'piezas': {'type': 'array', 'description': 'Hasta 40. Las de más adelante en la lista quedan arriba de las otras.', 'items': {
            'type': 'object', 'required': ['tipo', 'x', 'y', 'w', 'h'],
            'properties': {
                'tipo': {'type': 'string', 'enum': list(pantallas.TIPOS)},
                'x': {'type': 'number', 'description': 'Desde la izquierda, en px de la pantalla.'},
                'y': {'type': 'number', 'description': 'Desde arriba, en px de la pantalla.'},
                'w': {'type': 'number', 'description': 'Ancho en px.'},
                'h': {'type': 'number', 'description': 'Alto en px.'},
                'op': {'type': 'object', 'description': 'Opciones de la pieza (ver_piezas dice cuáles hay). Las que faltan toman su valor de siempre.'},
                'clase': {'type': 'string', 'description': 'Una clase CSS para apuntarle desde css.'},
            }}},
        'tema': {'type': 'string', 'description': 'El id de un tema (ver_temas): sus colores van en las opciones de color '
                 'como "tema:acento" y su letra con "fuente": "tema". Sin tema, esas opciones usan su valor de siempre.'},
        'css': {'type': 'string', 'description': 'CSS propio, que vale solo adentro de esta pantalla. Cada pieza tiene '
                'data-tipo y su clase; adentro hay .pz-mensaje, .pz-quien, .pz-alerta, .pz-alerta-quien, .pz-marco, '
                '.pz-marco-titulo, .pz-bloque, .pz-meta, .pz-meta-barra i, .pz-gota y .emote. Los colores de las '
                'opciones van directo en cada pieza: para pisarlos hace falta !important.'},
    },
    'required': ['nombre', 'piezas'],
}
ID = {'type': 'object', 'properties': {'id': {'type': 'string'}}, 'required': ['id']}
NADA = {'type': 'object', 'properties': {}}

HERRAMIENTAS = [
    {'name': 'ver_piezas', 'description': 'Qué piezas se pueden poner en una pantalla, para qué sirve cada una, su tamaño '
     'de siempre y sus opciones (con tipo, valor de siempre, rango o valores posibles).', 'inputSchema': NADA,
     'annotations': {'readOnlyHint': True}},
    {'name': 'listar_pantallas', 'description': 'Las pantallas guardadas, con su id, nombre, formato, cantidad de piezas '
     'y link para OBS.', 'inputSchema': NADA, 'annotations': {'readOnlyHint': True}},
    {'name': 'ver_pantalla', 'description': 'Una pantalla entera: sus piezas con posición, tamaño y opciones, y su CSS.',
     'inputSchema': ID, 'annotations': {'readOnlyHint': True}},
    {'name': 'guardar_pantalla', 'description': 'Crea una pantalla o reemplaza una entera (con su id). Devuelve cómo '
     'quedó y su link para OBS. Si algo no va, el error dice qué corregir.',
     'inputSchema': {'type': 'object', 'properties': {'pantalla': PANTALLA}, 'required': ['pantalla']},
     'annotations': {'destructiveHint': True, 'idempotentHint': True}},
    {'name': 'borrar_pantalla', 'description': 'Borra una pantalla. En OBS queda vacía. No se puede deshacer.',
     'inputSchema': ID, 'annotations': {'destructiveHint': True}},
    {'name': 'ver_textos', 'description': 'Los textos compartidos: {"tema": "Ranked"}. Una pieza que diga {tema} en su texto '
     '(texto, título de marco o de meta, etiqueta o final de la cuenta regresiva) muestra el de "tema", en todas las pantallas.',
     'inputSchema': NADA, 'annotations': {'readOnlyHint': True}},
    {'name': 'guardar_textos', 'description': 'Reemplaza todos los textos compartidos (leelos antes con ver_textos para no '
     'borrar los demás). Nombres en minúsculas con letras, números y _, hasta 30; textos de hasta 300 caracteres. OBS los '
     'toma en unos 15 segundos.',
     'inputSchema': {'type': 'object', 'properties': {'textos': {'type': 'object', 'additionalProperties': {'type': 'string'}}},
                     'required': ['textos']},
     'annotations': {'destructiveHint': True, 'idempotentHint': True}},
    {'name': 'ver_temas', 'description': 'Los temas: paletas de cuatro colores (texto, fondo, acento, acento2) y una letra de '
     'Google. Una pantalla usa uno con "tema": id; sus piezas toman los colores con "tema:acento" (o tema:texto, '
     'tema:fondo, tema:acento2) en cualquier opción de color, y la letra con "fuente": "tema". Cambiar el tema cambia '
     'todas las pantallas que lo usan.', 'inputSchema': NADA, 'annotations': {'readOnlyHint': True}},
    {'name': 'guardar_temas', 'description': 'Reemplaza todos los temas (leelos antes con ver_temas para no borrar los demás '
     'y mantené sus id: las pantallas los usan). Un tema sin id es nuevo. Devuelve la lista con los id.',
     'inputSchema': {'type': 'object', 'properties': {'temas': {'type': 'array', 'items': {'type': 'object', 'properties': {
         'id': {'type': 'string'}, 'nombre': {'type': 'string'}, 'letra': {'type': 'string'},
         'colores': {'type': 'object', 'properties': {c: {'type': 'string'} for c in ('texto', 'fondo', 'acento', 'acento2')}}},
         'required': ['nombre', 'colores']}}}, 'required': ['temas']},
     'annotations': {'destructiveHint': True, 'idempotentHint': True}},
    {'name': 'datos_en_vivo', 'description': 'Lo que muestran las piezas ahora: espectadores, seguidores, títulos y lo '
     'que pasó en este stream (follows, subs, bits y kicks).', 'inputSchema': NADA, 'annotations': {'readOnlyHint': True}},
]


def link(pid, puerto):
    return f'http://127.0.0.1:{puerto}/pantalla/{pid}'


def usar(nombre, args, puerto):
    """Corre una herramienta. ValueError: algo que el agente tiene que corregir."""
    if nombre == 'ver_piezas':
        return {'formatos': {k: {'ancho': w, 'alto': h} for k, (w, h) in pantallas.FORMATOS.items()}, 'piezas': pantallas.ESQUEMA}
    if nombre == 'listar_pantallas':
        return [{'id': p['id'], 'nombre': p['nombre'], 'formato': p['formato'], 'piezas': len(p['piezas']),
                 'link': link(p['id'], puerto)} for p in pantallas.leer()]
    if nombre == 'ver_pantalla':
        p = next((p for p in pantallas.leer() if p.get('id') == args.get('id')), None)
        if not p:
            raise ValueError('No hay una pantalla con ese id. listar_pantallas dice cuáles hay.')
        return {**p, 'link': link(p['id'], puerto)}
    if nombre == 'guardar_pantalla':
        p = pantallas.guardar(args.get('pantalla'))
        return {**p, 'link': link(p['id'], puerto)}
    if nombre == 'borrar_pantalla':
        pantallas.borrar(args.get('id'))
        return {'borrada': args.get('id')}
    if nombre == 'ver_textos':
        return pantallas.leer_textos()
    if nombre == 'guardar_textos':
        return pantallas.guardar_textos(args.get('textos'))
    if nombre == 'ver_temas':
        return pantallas.leer_temas()
    if nombre == 'guardar_temas':
        return pantallas.guardar_temas(args.get('temas'))
    if nombre == 'datos_en_vivo':
        return pantallas.datos()
    raise KeyError(nombre)


def atender(mensaje, puerto, version):
    """Un mensaje JSON-RPC. Devuelve la respuesta, o None si era una notificación."""
    if not isinstance(mensaje, dict) or mensaje.get('jsonrpc') != '2.0' or not isinstance(mensaje.get('method'), str):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Pedido inválido.'}}
    if 'id' not in mensaje:
        return None  # notificaciones (initialized, cancelled): no llevan respuesta
    metodo, params = mensaje['method'], mensaje.get('params') or {}
    ok = lambda r: {'jsonrpc': '2.0', 'id': mensaje['id'], 'result': r}
    mal = lambda code, texto: {'jsonrpc': '2.0', 'id': mensaje['id'], 'error': {'code': code, 'message': texto}}
    if metodo == 'initialize':
        pedida = params.get('protocolVersion')
        return ok({'protocolVersion': pedida if pedida in VERSIONES else VERSIONES[0], 'capabilities': {'tools': {}},
                   'serverInfo': {'name': 'stream-kit', 'title': 'Stream Kit', 'version': version},
                   'instructions': INSTRUCCIONES + f' Guía completa, con cada pieza y sus opciones: http://127.0.0.1:{puerto}/llms.txt'})
    if metodo == 'ping':
        return ok({})
    if metodo == 'tools/list':
        return ok({'tools': HERRAMIENTAS})
    if metodo == 'tools/call':
        nombre, args = params.get('name'), params.get('arguments') or {}
        if not any(h['name'] == nombre for h in HERRAMIENTAS):
            return mal(-32602, f'No existe la herramienta {nombre}.')
        if not isinstance(args, dict):
            return mal(-32602, 'Los argumentos van como un objeto.')
        try:
            r = usar(nombre, args, puerto)
        except ValueError as e:  # el agente lo lee y lo corrige
            return ok({'content': [{'type': 'text', 'text': str(e)}], 'isError': True})
        return ok({'content': [{'type': 'text', 'text': json.dumps(r, ensure_ascii=False)}]})
    return mal(-32601, f'No conozco el método {metodo}.')
