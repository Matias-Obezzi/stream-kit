"""Autoconfigurar OBS para Stream Kit: que transmita a esta app, sin transmisión mejorada (multipista) y con la pista de
VOD de Twitch disponible. Corre en el proceso de la web.

OBS guarda su config al cerrarse y pisaría cualquier cambio: solo se toca con OBS cerrado. Si está abierto, se lo cierra,
se cambia y se lo vuelve a abrir. Antes de cambiar nada, deja una copia de lo que había.
"""
import json
import os
import re
import shutil
import subprocess
import time

CARPETA = os.path.join(os.environ.get('APPDATA', ''), 'obs-studio')
CLAVE = 'stream'
SIN_VENTANA = 0x08000000
# el servidor que tenía OBS antes, para pasar su clave a Stream Kit
SERVICIOS = {'twitch': ('Twitch', 'rtmp://live.twitch.tv/app'), 'youtube': ('YouTube', 'rtmp://a.rtmp.youtube.com/live2')}


def servidor(puerto):
    return f'rtmp://127.0.0.1:{puerto}/live'


def proceso_obs():
    """(pid, ruta del .exe) si OBS está abierto, o None."""
    r = subprocess.run(['powershell', '-NoProfile', '-Command',
                        "Get-CimInstance Win32_Process -Filter \"Name='obs64.exe'\" | Select-Object -First 1 ProcessId,ExecutablePath | ConvertTo-Json"],
                       capture_output=True, text=True, creationflags=SIN_VENTANA)
    try:
        d = json.loads(r.stdout)
        return d['ProcessId'], d['ExecutablePath']
    except (ValueError, KeyError, TypeError):
        return None


def transmitiendo():
    """Si el último log de OBS tiene un stream que arrancó y no terminó."""
    logs = os.path.join(CARPETA, 'logs')
    try:
        ultimo = max((os.path.join(logs, n) for n in os.listdir(logs) if n.endswith('.txt')), key=os.path.getmtime)
        with open(ultimo, encoding='utf-8', errors='replace') as f:
            texto = f.read()
    except (OSError, ValueError):
        return False
    return texto.rfind('==== Streaming Start') > texto.rfind('==== Streaming Stop')


def leer_ini(ruta):
    try:
        with open(ruta, encoding='utf-8-sig', newline='') as f:
            return f.read()
    except OSError:
        return ''


def valor_ini(texto, seccion, clave):
    m = re.search(rf'^\[{re.escape(seccion)}\]\r?\n(.*?)(?=^\[|\Z)', texto, re.M | re.S)
    v = m and re.search(rf'^{re.escape(clave)}=(.*?)\r?$', m[1], re.M)
    return v[1] if v else None


def poner_ini(ruta, seccion, clave, valor):
    """Cambia o agrega clave=valor en una sección, sin tocar el resto (OBS los guarda con BOM y saltos de Windows)."""
    texto = leer_ini(ruta)
    nl = '\r\n' if '\r\n' in texto or not texto else '\n'
    m = re.search(rf'^\[{re.escape(seccion)}\]\r?\n(.*?)(?=^\[|\Z)', texto, re.M | re.S)
    if not m:
        texto = f'[{seccion}]{nl}{clave}={valor}{nl}{nl}' + texto
    elif re.search(rf'^{re.escape(clave)}=.*$', m[1], re.M):
        cuerpo = re.sub(rf'^{re.escape(clave)}=.*?(?=\r?$)', lambda _: f'{clave}={valor}', m[1], count=1, flags=re.M)
        texto = texto[:m.start(1)] + cuerpo + texto[m.end(1):]
    else:
        texto = texto[:m.start(1)] + f'{clave}={valor}{nl}' + texto[m.start(1):]
    with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(texto)


def perfil():
    """La carpeta del perfil que usa OBS (OBS 31 o más nuevo la anota en user.ini; antes, en global.ini)."""
    for archivo in ('user.ini', 'global.ini'):
        nombre = valor_ini(leer_ini(os.path.join(CARPETA, archivo)), 'Basic', 'ProfileDir')
        if nombre:
            return os.path.join(CARPETA, 'basic', 'profiles', nombre)
    return None


def leer_servicio(carpeta):
    try:
        with open(os.path.join(carpeta, 'service.json'), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def estado(puerto):
    carpeta = perfil()
    abierto = proceso_obs()
    if not carpeta:
        return {'instalado': os.path.isdir(CARPETA), 'abierto': bool(abierto), 'transmitiendo': False, 'configurado': False}
    s = leer_servicio(carpeta).get('settings', {})
    vod = all(valor_ini(leer_ini(os.path.join(CARPETA, a)), 'General', 'EnableCustomServerVodTrack') == 'true' for a in ('global.ini', 'user.ini'))
    return {'instalado': True, 'abierto': bool(abierto), 'transmitiendo': bool(abierto) and transmitiendo(),
            'configurado': s.get('server') == servidor(puerto) and s.get('key') == CLAVE and vod,
            'perfil': os.path.basename(carpeta)}


def clave_anterior(servicio, puerto):
    """El destino que usaba OBS antes de Stream Kit (nombre, URL, clave), para no perderlo. None si no había."""
    s = servicio.get('settings', {})
    clave, url = s.get('key', ''), s.get('server', '')
    if not clave or url == servidor(puerto):
        return None
    if servicio.get('type') == 'rtmp_common':  # un servicio de la lista de OBS: su "server" puede ser "auto"
        nombre = s.get('service', '')
        return next(((n, u, clave) for k, (n, u) in SERVICIOS.items() if k in nombre.lower()), None)
    if not re.fullmatch(r'rtmps?://\S+', url):
        return None
    nombre = next((n for k, n in (('twitch', 'Twitch'), ('youtube', 'YouTube'), ('kick', 'Kick'), ('live-video.net', 'Kick'),
                                  ('facebook', 'Facebook'), ('tiktok', 'TikTok')) if k in url.lower()), 'Desde OBS')
    return nombre, url, clave


def cerrar(pid, espera=40):
    """Le pide a OBS que se cierre, como la X de la ventana: si está transmitiendo, OBS pregunta y hay que contestarle."""
    subprocess.run(['taskkill', '/PID', str(pid)], capture_output=True, creationflags=SIN_VENTANA)
    fin = time.monotonic() + espera
    while time.monotonic() < fin:
        if not proceso_obs():
            return True
        time.sleep(0.5)
    return False


def configurar(puerto, cerrar_obs=False, abierto=None, cerrar_fn=None, abrir_fn=None):
    """Devuelve qué hizo. ValueError con el motivo si no se pudo (OBS abierto sin permiso, no se cerró, no está)."""
    abierto = proceso_obs() if abierto is None else abierto
    carpeta = perfil()
    if not carpeta or not os.path.isdir(carpeta):
        raise ValueError('No encontré la configuración de OBS en esta PC. Abrilo una vez y cerralo, y probá de nuevo.')
    if abierto and not cerrar_obs:
        raise ValueError('OBS está abierto: hay que cerrarlo para configurarlo.')
    if abierto and not (cerrar_fn or cerrar)(abierto[0]):
        raise ValueError('OBS no se cerró. Si te preguntó si querés salir, contestale que sí y probá de nuevo.')
    base = respaldo = os.path.join(CARPETA, 'stream-kit-respaldo', time.strftime('%Y%m%d-%H%M%S'))
    n = 1
    while os.path.exists(respaldo):  # dos veces en el mismo segundo: la copia anterior no se pisa
        n += 1
        respaldo = f'{base}-{n}'
    os.makedirs(respaldo)
    for origen in (os.path.join(carpeta, 'service.json'), os.path.join(carpeta, 'basic.ini'),
                   os.path.join(CARPETA, 'global.ini'), os.path.join(CARPETA, 'user.ini')):
        if os.path.exists(origen):
            shutil.copy2(origen, respaldo)
    anterior = clave_anterior(leer_servicio(carpeta), puerto)
    with open(os.path.join(carpeta, 'service.json'), 'w', encoding='utf-8') as f:
        json.dump({'type': 'rtmp_custom', 'settings': {'server': servidor(puerto), 'key': CLAVE, 'use_auth': False, 'bwtest': False}}, f, indent=4)
    poner_ini(os.path.join(carpeta, 'basic.ini'), 'Stream1', 'EnableMultitrackVideo', 'false')  # la app espera un solo video H.264
    for archivo in ('global.ini', 'user.ini'):  # con servidor propio, OBS esconde la pista de VOD si no está esto
        poner_ini(os.path.join(CARPETA, archivo), 'General', 'EnableCustomServerVodTrack', 'true')
    reabierto = False
    if abierto and abierto[1]:
        (abrir_fn or (lambda exe: subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=0x00000008 | 0x00000200, close_fds=True)))(abierto[1])
        reabierto = True
    return {'reabierto': reabierto, 'anterior': anterior, 'respaldo': respaldo, 'perfil': os.path.basename(carpeta)}
