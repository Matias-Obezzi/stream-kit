"""Pantallas para OBS: cada una es un lienzo con piezas (chat, alertas, marco, metas...) que se arma en /pantallas.

OBS la muestra con una fuente de navegador apuntando a /pantalla/<id>. Las piezas se dibujan en la web (web/piezas.js);
acá se guardan, se revisan y se juntan los datos en vivo que usan: espectadores, seguidores, títulos y lo que pasó en el
stream (follows, subs, bits y kicks).
"""
import json
import os
import re
import secrets
import threading
import time

import canal
import panel_bot
from rutas import BOT, DATOS, WEB

ARCHIVO = os.path.join(DATOS, 'pantallas.json')
APOYOS = os.path.join(BOT, 'apoyos.json')  # lo escribe el bot
with open(os.path.join(WEB, 'piezas.json'), encoding='utf-8') as _f:
    ESQUEMA = json.load(_f)  # qué opciones tiene cada pieza: lo comparten la web, el editor y el MCP
TIPOS = tuple(ESQUEMA)
MAX_CSS = 20000
FORMATOS = {'horizontal': (1920, 1080), 'vertical': (1080, 1920)}
MAX_PANTALLAS, MAX_PIEZAS = 50, 40
candado = threading.Lock()


def leer():
    try:
        with open(ARCHIVO, encoding='utf-8') as f:
            lista = json.load(f)
        return lista if isinstance(lista, list) else []
    except (OSError, ValueError):
        return []


def escribir(lista):
    tmp = ARCHIVO + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARCHIVO)


def entero(valor, minimo, maximo, que):
    try:
        n = int(round(float(valor)))
    except (TypeError, ValueError):
        raise ValueError(f'{que} tiene que ser un número.')
    return max(minimo, min(maximo, n))


def opciones(tipo, op):
    """Las opciones de una pieza, revisadas con piezas.json. Lo que falta toma el valor de siempre al dibujarse.
    Los textos se muestran como texto, nunca como HTML."""
    if op is None:
        return {}
    if not isinstance(op, dict):
        raise ValueError('Las opciones de una pieza van como un objeto.')
    esquema = {o['clave']: o for o in ESQUEMA[tipo]['opciones']}
    limpio = {}
    for clave, valor in op.items():
        o = esquema.get(clave)
        if not o:
            raise ValueError(f'La pieza {tipo} no tiene la opción "{clave}". Tiene: {", ".join(esquema)}.')
        que = f'La opción "{clave}" de {tipo}'
        if o['tipo'] == 'si':
            if not isinstance(valor, bool):
                raise ValueError(f'{que} va con true o false.')
        elif o['tipo'] == 'numero':
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(f'{que} tiene que ser un número.')
            valor = max(o['min'], min(o['max'], valor))
        elif o['tipo'] == 'color':
            if not isinstance(valor, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', valor):
                raise ValueError(f'{que} es un color como #8b5cf6.')
        elif o['tipo'] == 'elegir':
            validos = [v for v, _ in o['valores']]
            if valor not in validos:
                raise ValueError(f'{que} tiene que ser uno de: {", ".join(validos)}.')
        else:
            if not isinstance(valor, str):
                raise ValueError(f'{que} tiene que ser un texto.')
            valor = valor[:300]
        limpio[clave] = valor
    return limpio


def validar(datos):
    if not isinstance(datos, dict):
        raise ValueError('Pedido inválido.')
    nombre = str(datos.get('nombre') or '').strip()[:60]
    if not nombre:
        raise ValueError('Ponele un nombre a la pantalla.')
    formato = datos.get('formato') if datos.get('formato') in FORMATOS else 'horizontal'
    ancho, alto = FORMATOS[formato]
    piezas = datos.get('piezas') if isinstance(datos.get('piezas'), list) else []
    if len(piezas) > MAX_PIEZAS:
        raise ValueError(f'Una pantalla puede tener hasta {MAX_PIEZAS} piezas.')
    limpias = []
    for p in piezas:
        if not isinstance(p, dict) or p.get('tipo') not in TIPOS:
            raise ValueError(f'Hay una pieza que no existe. Las que hay: {", ".join(TIPOS)}.')
        clase = str(p.get('clase') or '')
        if clase and not re.fullmatch(r'[a-zA-Z][\w-]{0,39}', clase):
            raise ValueError('La clase CSS de una pieza va con letras, números, - y _, y empieza con una letra.')
        w = entero(p.get('w'), 20, ancho * 2, 'El ancho')
        h = entero(p.get('h'), 20, alto * 2, 'El alto')
        limpias.append({'tipo': p['tipo'], 'x': entero(p.get('x'), -w + 10, ancho - 10, 'La posición'),
                        'y': entero(p.get('y'), -h + 10, alto - 10, 'La posición'), 'w': w, 'h': h,
                        'op': opciones(p['tipo'], p.get('op')), **({'clase': clase} if clase else {})})
    pid = str(datos.get('id') or '')
    if pid and not re.fullmatch(r'[a-z0-9]{1,16}', pid):
        raise ValueError('Pedido inválido.')
    css = datos.get('css') or ''
    if not isinstance(css, str) or len(css) > MAX_CSS:
        raise ValueError(f'El CSS tiene que ser un texto de hasta {MAX_CSS} caracteres.')
    return {'id': pid or secrets.token_hex(4), 'nombre': nombre, 'formato': formato, 'piezas': limpias, 'css': css,
            'actualizado': time.time()}


def guardar(datos):
    pantalla = validar(datos)
    with candado:
        lista = leer()
        i = next((k for k, p in enumerate(lista) if p.get('id') == pantalla['id']), None)
        if i is not None:
            lista[i] = pantalla  # queda en su lugar
        elif len(lista) >= MAX_PANTALLAS:
            raise ValueError(f'Podés tener hasta {MAX_PANTALLAS} pantallas.')
        else:
            lista.append(pantalla)
        escribir(lista)
    return pantalla


def borrar(pid):
    with candado:
        lista = leer()
        if not any(p.get('id') == pid for p in lista):
            raise ValueError('Esa pantalla ya no existe.')
        escribir([p for p in lista if p.get('id') != pid])


def contar(apoyos, desde):
    """Lo que pasó desde que arrancó el stream, para las metas: follows, subs (con las regaladas), bits y kicks."""
    cuenta = {'follows': 0, 'subs': 0, 'bits': 0, 'kicks': 0}
    for a in apoyos:
        if not isinstance(a, dict) or not desde or (a.get('t') or 0) < desde:
            continue
        cantidad = a.get('cantidad') if isinstance(a.get('cantidad'), int) else 0
        tipo = a.get('tipo')
        if tipo == 'follow':
            cuenta['follows'] += 1
        elif tipo in ('sub', 'resub'):
            cuenta['subs'] += 1
        elif tipo == 'regalo':
            cuenta['subs'] += max(cantidad, 1)
        elif tipo in ('bits', 'kicks'):
            cuenta[tipo] += cantidad
    return cuenta


titulos = {'t': 0, 'valor': {}}
TITULO_CADA = 60  # el título se pide a Twitch y Kick como mucho una vez por minuto


def leer_titulos():
    if time.time() - titulos['t'] > TITULO_CADA:
        titulos['t'] = time.time()
        try:
            titulos['valor'] = {p: c['titulo'] for p, c in canal.leer().items() if isinstance(c, dict) and c.get('titulo')}
        except Exception:  # sin cuentas conectadas: la pieza queda vacía
            titulos['valor'] = {}
    return titulos['valor']


def referencia():
    """Las piezas y sus opciones en Markdown, para el final de /llms.txt: sale de piezas.json, así nunca queda vieja."""
    lineas = ['', '## Piezas y opciones', '', 'Generado de web/piezas.json. Formato de cada opción: `clave` (tipo, valor de siempre).', '']
    for tipo, e in ESQUEMA.items():
        lineas += [f'### `{tipo}`: {e["nombre"]}', '', f'{e["descripcion"]} Tamaño de siempre: {e["w"]} × {e["h"]}.', '']
        for o in e['opciones']:
            extra = (f', de {o["min"]} a {o["max"]}' if o['tipo'] == 'numero' else
                     ', uno de: ' + ', '.join(f'`{v}` ({n})' for v, n in o['valores']) if o['tipo'] == 'elegir' else '')
            lineas.append(f'- `{o["clave"]}` ({o["tipo"]}, {json.dumps(o["def"], ensure_ascii=False)}{extra}): {o["nombre"]}')
        lineas.append('')
    return '\n'.join(lineas)


def datos():
    bot = panel_bot.leer_json(panel_bot.ESTADO_BOT)
    vivo = time.time() - bot.get('actualizado', 0) < panel_bot.SIN_SENAL
    inicios = [t for t in (bot.get('inicio') or {}).values() if isinstance(t, (int, float)) and t] if vivo else []
    try:
        with open(APOYOS, encoding='utf-8') as f:
            apoyos = json.load(f)
    except (OSError, ValueError):
        apoyos = []
    viewers = bot.get('viewers', {}) if vivo else {}
    return {'viewers': {p: n for p, n in viewers.items() if isinstance(n, int)},
            'seguidores': bot.get('seguidores', {}) if vivo else {},
            'stream': contar(apoyos if isinstance(apoyos, list) else [], min(inicios) if inicios else None),
            'en_vivo': bool(inicios), 'titulo': leer_titulos()}
