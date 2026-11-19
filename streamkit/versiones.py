"""Versiones instaladas y actualización desde GitHub, sin cortar el stream.

Cada versión nueva se descomprime en su propia carpeta (datos/versiones/<versión>), nunca encima de la que está
corriendo: Windows no deja pisar un programa abierto. elegida.txt dice cuál usar; el guardián pasa a ella la web y el bot
enseguida, y el núcleo de transmisión solo si cambió (version.json lo dice) y cuando OBS deja de transmitir.
Desde el código fuente no hay versiones: se actualiza con git pull.
"""
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.request
import zipfile

from rutas import CONGELADO, DATOS

CARPETA = os.path.join(DATOS, 'versiones')
ELEGIDA = os.path.join(CARPETA, 'elegida.txt')
REPO = 'Matias-Obezzi/stream-kit'
EXE = 'StreamKit.exe'
descarga = {'estado': '', 'error': '', 'version': ''}  # lo muestra Inicio mientras baja
_ultima = {'hora': 0.0, 'datos': None}


def tupla(version):
    return tuple(int(x) for x in re.findall(r'\d+', str(version))[:3])


def elegida():
    try:
        with open(ELEGIDA, encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def exe(version):
    return os.path.join(CARPETA, version, EXE)


def info(programa):
    """El version.json que build.py deja al lado del .exe: versión y huella del núcleo."""
    try:
        with open(os.path.join(os.path.dirname(programa), 'version.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}


def objetivo(propia):
    """El .exe que tiene que correr: la versión elegida si es más nueva que esta y está entera; si no, este mismo."""
    if not CONGELADO:
        return None
    v = elegida()
    if v and tupla(v) > tupla(propia) and os.path.exists(exe(v)):
        return exe(v)
    return sys.executable


def mismo_nucleo(a, b):
    """Si dos versiones traen el mismo núcleo de transmisión, no hace falta reiniciarlo (y cortar el stream)."""
    na = info(a).get('nucleo')
    return bool(na) and na == info(b).get('nucleo')


def ultima():
    """La última versión publicada en GitHub (pregunta como mucho cada 30 minutos)."""
    if _ultima['datos'] is None or time.time() - _ultima['hora'] > 1800:
        pedido = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases/latest',
                                        headers={'User-Agent': 'StreamKit', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(pedido, timeout=10) as r:
            d = json.load(r)
        zips = [a['browser_download_url'] for a in d.get('assets', []) if a['name'].endswith('-windows.zip')]
        _ultima['datos'] = {'version': d['tag_name'].lstrip('v'), 'zip': zips[0] if zips else '', 'notas': d.get('body') or ''}
        _ultima['hora'] = time.time()
    return _ultima['datos']


def extraer(zip_path, destino):
    """Descomprime el zip del release en destino, con la carpeta del .exe como raíz. Rechaza rutas que se salgan."""
    tmp = destino + '.tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        for nombre in z.namelist():
            ruta = os.path.normpath(os.path.join(tmp, nombre))
            if not ruta.startswith(os.path.normpath(tmp) + os.sep):
                raise ValueError(f'El zip trae una ruta rara: {nombre}')
        z.extractall(tmp)
    raiz = next((r for r, _, archivos in os.walk(tmp) if EXE in archivos), None)
    if not raiz:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f'El zip no trae {EXE}.')
    shutil.rmtree(destino, ignore_errors=True)
    os.replace(raiz, destino)
    shutil.rmtree(tmp, ignore_errors=True)


def elegir(version):
    os.makedirs(CARPETA, exist_ok=True)
    with open(ELEGIDA + '.tmp', 'w', encoding='utf-8') as f:
        f.write(version)
    os.replace(ELEGIDA + '.tmp', ELEGIDA)


def _instalar(version, url):
    try:
        os.makedirs(CARPETA, exist_ok=True)
        zip_path = os.path.join(CARPETA, f'{version}.zip')
        descarga['estado'] = 'Bajando…'
        pedido = urllib.request.Request(url, headers={'User-Agent': 'StreamKit'})
        with urllib.request.urlopen(pedido, timeout=60) as r, open(zip_path, 'wb') as f:
            shutil.copyfileobj(r, f)
        descarga['estado'] = 'Descomprimiendo…'
        extraer(zip_path, os.path.join(CARPETA, version))
        os.remove(zip_path)
        elegir(version)  # desde acá el guardián la toma sola
        descarga['estado'] = 'Instalada'
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        descarga['estado'], descarga['error'] = '', f'No se pudo actualizar: {e}'


def instalar(actual):
    """Baja la última versión en segundo plano. Error si no hay nada más nuevo o ya está bajando."""
    if not CONGELADO:
        raise ValueError('Estás corriendo Stream Kit desde el código: actualizá con git pull.')
    if descarga['estado'] in ('Bajando…', 'Descomprimiendo…'):
        raise ValueError('Ya se está bajando.')
    u = ultima()
    if tupla(u['version']) <= tupla(actual) or not u['zip']:
        raise ValueError('Ya tenés la última versión.')
    descarga.update(estado='Bajando…', error='', version=u['version'])
    threading.Thread(target=_instalar, args=(u['version'], u['zip']), daemon=True).start()


def limpiar(en_uso):
    """Borra versiones viejas, zips y descargas a medias. Solo la llama el guardián al arrancar, sin nada corriendo."""
    if not os.path.isdir(CARPETA):
        return
    dejar = {elegida()} | {os.path.basename(os.path.dirname(p)) for p in en_uso if p}
    for nombre in os.listdir(CARPETA):
        ruta = os.path.join(CARPETA, nombre)
        if nombre != 'elegida.txt' and nombre not in dejar:
            if os.path.isdir(ruta):
                shutil.rmtree(ruta, ignore_errors=True)
            else:
                os.remove(ruta)
