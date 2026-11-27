"""Núcleo de transmisión: OBS -> esta app (rtmp://127.0.0.1) -> Twitch, YouTube, Kick... todos con el mismo delay.

Reenvía el stream sin recodificar a cada destino. Al activar el delay manda un video de relleno
mientras guarda lo que llega, y después sigue con lo guardado (atrasado). También tiene el ícono de la bandeja y los atajos.
Es lo único que no se puede reiniciar en vivo, así que hace lo mínimo: la web (panel.py) corre aparte y le habla por api().
Si cambiás este archivo o rutas.py, la versión nueva reinicia el núcleo (build.py saca la huella de los dos).
Uso: pythonw app.py                    (el guardián arranca esto, la web y el bot)
     python delay.py [config.json]     solo el núcleo, para probar (d / l / q por consola)
"""
import ctypes
import faulthandler
import io
import json
import os
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from rutas import CLAVE_NUCLEO, DATOS, PUERTO_NUCLEO, RECURSOS, config as ruta_config

SALIDA_ACTUALIZAR = 3  # código con el que sale cuando el guardián lo pasa a otra versión (0 es Salir: cierra todo)
VIDEOS = os.path.join(DATOS, 'videos')
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
UPLOAD_EXT = IMAGE_EXT + ('.mp4', '.mov', '.mkv', '.webm', '.flv', '.avi')
FLV_HEADER = b'FLV\x01\x05\x00\x00\x00\x09\x00\x00\x00\x00'
RESYNC = (0, 0, b'', 'resync')
ATRASO_MAXIMO = 10  # segundos que una plataforma puede quedar atrás por la red antes de tirar lo atrasado
PISO = 2500  # kbps: lo menos que priorizar les deja a las otras plataformas si no se configuró otro piso
ESPERA_SUBIR = 180  # segundos de la principal andando bien antes de devolverles bitrate a las demás
NO_WINDOW = 0x08000000  # la app corre sin consola: sin esto cada ffmpeg abriría una ventana negra
LOW = NO_WINDOW | 0x4000  # además prioridad baja, para no competir con OBS
CFG_LOCK = threading.Lock()


def read_tags(f):
    """Lee un stream FLV y devuelve (tipo, ts_ms, datos) por tag."""
    head = f.read(13)
    if len(head) < 13 or head[:3] != b'FLV':
        return
    while True:
        h = f.read(11)
        if len(h) < 11:
            return
        size = int.from_bytes(h[1:4], 'big')
        data = f.read(size)
        if len(data) < size or len(f.read(4)) < 4:
            return
        yield h[0], int.from_bytes(h[4:7], 'big') | h[7] << 24, data


def tag_bytes(typ, ts, data):
    ts &= 0xFFFFFFFF
    return (bytes([typ]) + len(data).to_bytes(3, 'big') + (ts & 0xFFFFFF).to_bytes(3, 'big')
            + bytes([ts >> 24]) + b'\0\0\0' + data + (11 + len(data)).to_bytes(4, 'big'))


def kind(typ, data):
    """'header' (config del códec), 'key' (cuadro clave), 'frame' o 'skip'."""
    if typ == 9 and len(data) > 1:
        if data[0] >> 4 == 5 or (data[0] & 0x0F == 7 and data[1] == 2):
            return 'skip'  # info de video / fin de secuencia: cortaría el stream en Twitch
        if data[0] & 0x0F == 7 and data[1] == 0:
            return 'header'
        return 'key' if data[0] >> 4 == 1 else 'frame'
    if typ == 8 and len(data) > 1:
        if data[0] >> 4 == 9:  # Enhanced RTMP: así manda OBS la pista del VOD de Twitch
            p = data[1] & 0x0F if data[0] & 0x0F == 5 else data[0] & 0x0F
            return 'header' if p in (0, 4) else 'frame' if p == 1 else 'skip'
        return 'header' if data[0] >> 4 == 10 and data[1] == 0 else 'frame'
    return 'skip'  # metadata (18): ffmpeg genera la suya


def extra_track(typ, data):
    """Audio de una pista que no es la principal: en OBS, la del VOD de Twitch."""
    return typ == 8 and len(data) > 6 and data[0] == 0x95 and data[6] != 0


def track_key(typ, data):
    """(tipo, pista, clase de config): cada pista lleva su config y sus tiempos aparte."""
    return (typ, data[6], data[1] & 0x0F) if extra_track(typ, data) else (typ, 0, 0)


def hay_ffmpeg(ffmpeg):
    return bool(shutil.which(ffmpeg))


def recomendar(mbps, tope, activas):
    """kbps por plataforma según la prueba de subida. La prueba mide UNA conexión: si no llegó al tope, lo que limita es
    esa conexión (con pérdida de paquetes en el camino, TCP no pasa de unos Mb/s) y cada plataforma va por la suya, así
    que no se reparte; si llegó al tope, lo que limita es la subida entera y se reparte entre las activas."""
    kbps = mbps * 750  # tres cuartos de lo medido: margen para los picos
    return int(min(8000, kbps / max(1, activas) if tope else kbps) // 500 * 500)


def tcp_segmentos():
    """(salidos, reenviados) de TCP en toda la PC, de Windows. None si no se puede leer."""
    stats = (wintypes.DWORD * 15)()  # MIB_TCPSTATS: el 11 son los salidos y el 12 los reenviados
    try:
        if ctypes.windll.iphlpapi.GetTcpStatisticsEx(ctypes.byref(stats), 2) == 0:  # 2 = IPv4
            return stats[10], stats[11]
    except (AttributeError, OSError):
        pass
    return None


def ffprobe(ffmpeg):
    return os.path.join(os.path.dirname(ffmpeg), 'ffprobe')


def filter_path(path):
    """Ruta escapada para usar dentro de un filtro de ffmpeg ('C:' rompe el parser)."""
    return path.replace('\\', '/').replace(':', '\\:')


def probe_duration(ffmpeg, path):
    """Duración en segundos de un video, o None si es una imagen o no se puede leer."""
    if path.lower().endswith(IMAGE_EXT):
        return None
    r = subprocess.run([ffprobe(ffmpeg), '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, creationflags=NO_WINDOW)
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None


def dest_url(d):
    url, key = d['url'].strip(), d.get('key', '').strip()
    return url.rstrip('/') + '/' + key if key else url


_encoder = {}


def encoder_h264(ffmpeg):
    """El codificador para recomprimir una plataforma: la placa de video si hay (NVIDIA, Intel, AMD), si no el CPU."""
    if ffmpeg not in _encoder:
        _encoder[ffmpeg] = 'libx264'
        for enc in ('h264_nvenc', 'h264_qsv', 'h264_amf'):
            r = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=s=256x144:d=0.2',
                                '-c:v', enc, '-f', 'null', '-'], stdin=subprocess.DEVNULL, capture_output=True,
                               creationflags=NO_WINDOW, timeout=20)
            if r.returncode == 0:
                _encoder[ffmpeg] = enc
                break
    return _encoder[ffmpeg]


def opciones_video(ffmpeg, kbps):
    """-c:v para mandar a kbps propios: CBR con un cuadro clave cada 2 s, lo que piden Twitch, Kick y YouTube."""
    enc = encoder_h264(ffmpeg)
    rc = {'h264_nvenc': ['-preset', 'p4', '-rc', 'cbr'], 'h264_qsv': ['-preset', 'faster'],
          'h264_amf': ['-rc', 'cbr', '-quality', 'speed'], 'libx264': ['-preset', 'veryfast', '-tune', 'zerolatency']}[enc]
    return ['-c:v', enc, *rc, '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{kbps * 2}k',
            '-force_key_frames', 'expr:gte(t,n_forced*2)', '-pix_fmt', 'yuv420p']


def saved_filler(cfg):
    """El video de relleno que ya está armado: tras una caída no se espera a codificarlo de nuevo, con el stream cortado."""
    if cfg.get('filler_mode') == 'rewind':
        return []
    try:
        with open(os.path.join(DATOS, 'filler.flv'), 'rb') as f:
            return [(t, ts, d, kind(t, d)) for t, ts, d in read_tags(f)] or None
    except OSError:
        return None


def make_filler(cfg, ffmpeg):
    """Codifica el video de relleno con los mismos parámetros que OBS y lo carga en memoria."""
    if cfg.get('filler_mode') == 'rewind':  # sin relleno: se repite lo último que salió
        return []
    w, h = cfg['resolution'].split('x')
    fps, kbps = str(cfg['fps']), cfg['video_bitrate_kbps']
    path = os.path.join(DATOS, 'filler.flv')
    file = cfg.get('filler_file') if cfg.get('filler_mode') == 'file' else ''
    audio = '1:a'
    if file:
        file = os.path.join(DATOS, file)
        if file.lower().endswith(IMAGE_EXT):
            src = ['-loop', '1', '-framerate', fps, '-i', file]
        else:  # video: se repite las veces elegidas (delay_seconds = duración x vueltas), con su audio si tiene
            src = ['-stream_loop', '-1', '-i', file]
            probe = subprocess.run([ffprobe(ffmpeg), '-v', 'error', '-select_streams', 'a', '-show_entries',
                                    'stream=index', '-of', 'csv=p=0', file],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, creationflags=NO_WINDOW)
            if probe.stdout.strip():
                audio = '0:a:0'
        vf = f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1'
    else:  # texto escrito a mano, como imagen fija
        txt = os.path.join(DATOS, 'filler_text.txt')
        with open(txt, 'w', encoding='utf-8') as f:
            f.write(cfg.get('filler_text') or 'Activando delay')
        src = ['-f', 'lavfi', '-i', f'color=black:s={w}x{h}:r={fps}']
        vf = (f"drawtext=fontfile='{filter_path('C:/Windows/Fonts/arialbd.ttf')}':textfile='{filter_path(txt)}':"
              "expansion=none:text_align=C:fontsize=h/12:fontcolor=white:x=(w-tw)/2:y=(h-th)/2")
    print('Preparando el video de delay...', flush=True)
    rate = ['-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{2 * kbps}k', '-g', str(2 * int(fps))]
    # NVENC como OBS (high, 2 B-frames, CBR), así Twitch no recibe otra config de H.264 al cambiar; x264 si no hay NVIDIA
    for vcodec in (['-c:v', 'h264_nvenc', '-preset', 'p5', '-rc', 'cbr', '-profile:v', 'high', '-bf', '2'],
                   ['-c:v', 'libx264', '-preset', 'veryfast', '-sc_threshold', '0']):
        # -nostdin/DEVNULL: si ffmpeg hereda la consola mientras se lee, en Windows se cuelga al terminar
        r = subprocess.run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-nostdin', *src,
                            '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(cfg['delay_seconds']),
                            '-map', '0:v:0', '-map', audio, '-vf', vf + ',format=yuv420p', '-r', fps, *vcodec, *rate,
                            '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-f', 'flv', path],
                           stdin=subprocess.DEVNULL, creationflags=LOW)
        if r.returncode == 0:
            break
    else:
        raise RuntimeError('No se pudo armar el video de delay (¿está ffmpeg en el PATH y el archivo es válido?).')
    with open(path, 'rb') as f:
        return [(t, ts, d, kind(t, d)) for t, ts, d in read_tags(f)]


class Output:
    """Un destino (Twitch, YouTube, Kick...): su propio ffmpeg y su cola, así uno lento o caído no frena a los demás."""

    def __init__(self, ffmpeg, url, bitrate=0, antes=None):
        self.ffmpeg, self.url = ffmpeg, url
        # el que reemplaza (cambió el bitrate o la clave con el stream andando): hasta que ese no cierre no se conecta,
        # porque la plataforma rechaza una segunda conexión con la misma clave
        self.antes, self.cambio = antes, time.monotonic() if antes else 0.0
        self.bitrate = bitrate  # kbps propios: se recomprime el video (0: se manda tal cual llega de OBS)
        self.salida = 0  # bytes que salieron de verdad a la plataforma cuando se recomprime (los cuenta ffmpeg)
        if bitrate:  # saber qué codificador hay tarda: que no frene al hilo del stream cuando arranque
            threading.Thread(target=encoder_h264, args=(ffmpeg,), daemon=True).start()
        self.vod_track = 'twitch.tv' in url  # la pista del VOD es cosa de Twitch: a los demás no se les manda
        self.proc = self.q = None
        self.error = ''
        self.retry_at = 0.0
        self.need_key = self.closed = False
        self.enviados = 0  # bytes mandados a la plataforma, para /metricas
        self.pendiente = 0  # bytes en la cola, todavía sin mandar: con la red lenta crece
        self.descartes, self.ultimo_descarte = 0, 0.0  # veces que se tiró lo atrasado (el salto que ve la gente)
        self.kbps = 0  # lo que salió en el último segundo, lo mide Bridge.medir
        self.limite = 0  # bytes: ATRASO_MAXIMO segundos al ritmo de OBS, lo pone Bridge.medir (0: sin medir todavía)

    def running(self):
        return bool(self.proc and self.proc.poll() is None)

    def state(self):
        return 'live' if self.running() else 'error' if self.error else 'idle'

    def send(self, blob, k, headers, ts, extra=False):
        """Lo llama el hilo del stream con el tag ya armado: nunca bloquea."""
        if self.closed or (extra and not self.vod_track):
            return
        if not self.running():
            if k != 'key' or time.monotonic() < self.retry_at or (self.bitrate and self.ffmpeg not in _encoder):
                return
            if self.antes:
                if self.antes.running():
                    return
                self.antes = None
            self._start(headers, ts)
        elif self.need_key:
            if k != 'key':
                return
            self.need_key = False
        # red lenta: con más de ATRASO_MAXIMO s en la cola se tira lo pendiente y sigue en el próximo cuadro clave.
        # La cuenta de paquetes queda por si todavía no hay medida (3000 son 20 a 40 s según los fps y las pistas)
        if (self.limite and self.pendiente > self.limite) or self.q.qsize() > 3000:
            with self.q.mutex:
                self.q.queue.clear()
            self.need_key = True
            self.pendiente = 0
            self.descartes += 1
            self.ultimo_descarte = time.time()
            safe = self.url.rsplit('/', 1)[0]  # sin la clave
            print(f'[{safe}] la red no da abasto: se tiró lo atrasado (van {self.descartes}).', flush=True)
            return
        self.q.put(blob)
        self.pendiente += len(blob)

    def header(self, blob, extra=False):
        if self.running() and not self.closed and (self.vod_track or not extra):
            self.q.put(blob)
            self.pendiente += len(blob)

    def stop(self):
        """Termina la transmisión en ese destino (OBS cortó)."""
        if self.running():
            self.q.put(None)

    def close(self):
        """Destino borrado, desactivado o reemplazado: no vuelve a arrancar."""
        self.closed = True
        if self.q:  # lo atrasado ya no se va a ver: cerrar enseguida y bien, así la plataforma suelta la clave
            with self.q.mutex:
                self.q.queue.clear()
        self.pendiente = 0
        self.stop()

    def kill(self):
        if self.proc:
            self.proc.kill()

    def _start(self, headers, ts):
        self.error, self.need_key, self.q, self.pendiente = '', False, queue.Queue(), 0
        self.q.put(FLV_HEADER + b''.join(tag_bytes(key[0], ts, d) for key, d in headers.items()
                                         if self.vod_track or not extra_track(key[0], d)))
        # el video siempre primero: con el audio primero, Kick corta cada 18 s. Twitch lleva todos los audios (el VOD)
        maps = ['-map', '0:v:0', '-map', '0:a?' if self.vod_track else '0:a:0?']
        if self.bitrate:  # se decodifica y se vuelve a codificar solo el video; el audio va tal cual
            entrada = ['-hwaccel', 'auto', '-f', 'flv', '-i', 'pipe:0']
            codec = [*opciones_video(self.ffmpeg, self.bitrate), '-c:a', 'copy', '-progress', 'pipe:1', '-stats_period', '1']
        else:
            entrada, codec = ['-f', 'flv', '-i', 'pipe:0'], ['-c', 'copy']
        self.salida = 0
        self.proc = subprocess.Popen([self.ffmpeg, '-hide_banner', '-loglevel', 'error', *entrada,
                                      *maps, *codec, '-f', 'flv', '-y', self.url],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE if self.bitrate else subprocess.DEVNULL,
                                     stderr=subprocess.PIPE, bufsize=0, creationflags=NO_WINDOW)
        threading.Thread(target=self._write, args=(self.proc, self.q), daemon=True).start()
        threading.Thread(target=self._errors, args=(self.proc,), daemon=True).start()
        if self.bitrate:
            threading.Thread(target=self._progreso, args=(self.proc,), daemon=True).start()

    def _progreso(self, proc):
        for linea in proc.stdout:  # -progress: total_size=<bytes que salieron>
            if linea.startswith(b'total_size=') and linea[11:].strip().isdigit():
                self.salida = int(linea[11:])

    def _write(self, proc, q):
        try:
            while (blob := q.get()) is not None:
                proc.stdin.write(blob)
                self.enviados += len(blob)
                self.pendiente = max(0, self.pendiente - len(blob))  # el hilo del stream suma; acá aprox. alcanza
            proc.stdin.close()
            proc.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()

    def _errors(self, proc):
        # mensajes propios: los de ffmpeg dicen "I/O error" para todo y traen la URL con la clave
        text = proc.stderr.read().decode('utf-8', 'replace')
        if not proc.wait():
            self.error = ''
            return
        safe = self.url.rsplit('/', 1)[0] + '/•••'  # para el log: la URL sin la clave
        print(f'[{safe}] ffmpeg terminó con error:\n' + text.replace(self.url, safe).strip(), flush=True)
        self.retry_at = time.monotonic() + 5  # reintenta en 5 s (no martillar la plataforma si la clave está mal)
        if re.search(r'resolve|Connection to tcp|refused|timed out', text, re.I):
            self.error = 'No se pudo conectar con el servidor: revisá la URL y tu internet.'
        elif 'Error opening output' in text and time.monotonic() - self.cambio < 90:
            # recién reemplazado: la plataforma todavía tiene la conexión anterior (Twitch la guarda hasta ~30 s)
            self.error = 'Esperando que la plataforma suelte la conexión anterior; reintentando.'
        elif 'Error opening output' in text:  # conectó pero la plataforma cortó al publicar
            self.error = 'La plataforma rechazó la conexión: revisá la clave de transmisión.'
        else:
            self.error = 'Se cortó la conexión con la plataforma; reintentando.'


class Preview:
    """Video para el panel: un ffmpeg aparte decodifica una copia del stream. Solo corre mientras el panel lo pide."""

    def __init__(self, ffmpeg):
        self.ffmpeg = ffmpeg
        self.lock = threading.Lock()
        self.proc = self.q = self.header = self.jpg = None
        self.need_key = True
        self.last_ask = 0.0

    def feed(self, typ, ts, data, k):
        """Lo llama el hilo del stream: nunca bloquea."""
        if typ != 9:
            return
        if k == 'header':
            self.header = data
        if self.proc and time.monotonic() - self.last_ask > 5:  # panel cerrado, oculto o con el preview apagado
            self.stop()
        q = self.q
        if not q:
            return
        if self.need_key:
            if k != 'key' or not self.header:
                return
            self.need_key = False
            q.put((ts, self.header))
        if q.qsize() > 120:  # el decodificador quedó atrás: se saltea hasta el próximo cuadro clave
            self.need_key = True
            return
        q.put((ts, data))

    def latest(self):
        """Último cuadro en JPG (o None). Arranca el decodificador si no estaba corriendo."""
        self.last_ask = time.monotonic()
        with self.lock:
            if not self.proc:
                self.q, self.need_key, self.jpg = queue.Queue(), True, None
                self.proc = subprocess.Popen(
                    [self.ffmpeg, '-hide_banner', '-loglevel', 'quiet', '-hwaccel', 'auto', '-threads', '2',
                     '-probesize', '32768', '-analyzeduration', '0', '-f', 'flv', '-i', 'pipe:0', '-an',
                     '-vf', 'fps=20,scale=960:-2', '-c:v', 'mjpeg', '-q:v', '5', '-f', 'mpjpeg', 'pipe:1'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
                    creationflags=LOW)
                threading.Thread(target=self._write, args=(self.proc, self.q), daemon=True).start()
                threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
        return self.jpg

    def stop(self):
        with self.lock:
            if self.proc:
                self.proc.kill()
            self.proc = self.q = self.jpg = None

    def _write(self, proc, q):
        try:
            proc.stdin.write(b'FLV\x01\x01\x00\x00\x00\x09\x00\x00\x00\x00')  # header FLV solo video
            while proc.poll() is None:
                try:
                    ts, data = q.get(timeout=1)
                except queue.Empty:
                    continue
                proc.stdin.write(tag_bytes(9, ts, data))
        except OSError:
            pass

    def _read(self, proc):
        # mpjpeg: headers por cuadro con Content-length y después el JPG.
        # Con buffer: read(n) sobre el pipe crudo devuelve menos bytes y el JPG sale cortado (mitad negra)
        f = io.BufferedReader(proc.stdout)
        while line := f.readline():
            if line.lower().startswith(b'content-length:'):
                f.readline()
                jpg = f.read(int(line.split(b':')[1]))
                if self.proc is proc:
                    self.jpg = jpg


class Bridge:
    def __init__(self, cfg, ffmpeg, filler):
        self.cfg, self.ffmpeg = cfg, ffmpeg
        self.filler, self.filler_headers, self.next_filler = [], [], filler
        self.cv = threading.Condition()
        self.buf = deque()  # (recibido, tipo, ts, datos, kind) de OBS
        self.hist = deque()  # modo repetir: lo que ya salió en vivo, para volver atrás al activar el delay
        self.live_headers = {}
        self.want = None
        self.mode, self.delay = 'stream', 0.0
        # estado de salida (solo lo toca el hilo que envía)
        self.headers = {}
        self.resync = True
        self.offset = self.last_out = self.last_pts = 0
        self.last_type = {}  # último tiempo por pista: la del VOD no empuja los tiempos del audio principal
        self.last_wall = None
        self.ingest_proc = None
        self.recibidos = 0  # bytes que llegaron de OBS, para /metricas
        self.entrada_kbps = 0  # lo que llegó de OBS en el último segundo
        self.perdida = None  # % de paquetes TCP reenviados en toda la PC (None: sin datos)
        self.historial = deque(maxlen=1800)  # una muestra por segundo con stream: 30 min para el gráfico
        self.saltos, self.saltos_vistos = deque(maxlen=300), {}  # (hora, id del destino) de cada vez que se tiró lo atrasado
        self.prueba = {'estado': ''}  # la prueba de subida
        self.outputs = {}  # id del destino -> Output
        self.sync_lock = threading.Lock()  # lo llaman el panel y priorizar: dos a la vez armarían dos ffmpeg con la misma clave
        # plataforma principal: kbps que priorizar les bajó a las demás (id -> kbps) y su estado
        self.ajuste, self.mal, self.bien_desde, self.cambio, self.subida, self.espera = {}, 0, 0.0, -1e9, -1e9, ESPERA_SUBIR
        self.bajada, self.sin_ayuda, self.llena, self.descartes_otras = -1e9, False, False, {}
        self.descartes_principal, self.salto_en = 0, -1e9
        self.sync_outputs()
        # para el panel
        self.obs_connected = False
        self.busy = ''  # mensaje mientras se prepara un video nuevo
        self.durations = {}  # (archivo, fecha) -> duración
        self.previews = {'in': Preview(ffmpeg), 'out': Preview(ffmpeg)}  # lo que manda OBS / lo que sale

    def request(self, action):
        with self.cv:
            self.want = action
            self.cv.notify()

    def use_filler(self, filler):
        """Cambia el video de relleno; se usa la próxima vez que arranca."""
        with self.cv:
            self.next_filler = filler

    def sync_outputs(self):
        """Arranca o para destinos según la config; se puede llamar con el stream andando."""
        want = {d['id']: d for d in self.cfg.get('destinations', []) if d.get('enabled', True)}
        kbps = {i: self.ajuste.get(i) or d.get('bitrate', 0) for i, d in want.items()}  # lo bajado por priorizar manda
        with self.sync_lock:
            outs, viejos = dict(self.outputs), {}
            for i in list(outs):
                if i not in want or outs[i].url != dest_url(want[i]) or outs[i].bitrate != kbps[i]:
                    viejos[i] = outs.pop(i)
                    viejos[i].close()
            for i, d in want.items():
                if i not in outs:
                    outs[i] = Output(self.ffmpeg, dest_url(d), kbps[i], viejos.get(i))
            self.outputs = outs  # se reemplaza entero: el hilo que envía itera sobre una copia

    def priorizar(self, ahora=None):
        """Plataforma principal: si se atrasa o salta, las demás bajan al piso; si anda bien un rato, vuelven a lo suyo.
        Cada cambio reconecta a esa plataforma (unos segundos de corte), por eso va de un solo salto y no de a poco.
        Si con las demás en el piso la principal sigue mal, el problema es su conexión: las demás vuelven y no se insiste.
        Salvo que otra también se atrase: entonces es la subida, que no da para todas, y las demás quedan en el piso."""
        ahora = time.monotonic() if ahora is None else ahora
        pid = self.cfg.get('principal') or ''
        p = self.outputs.get(pid)
        otras = {i: o for i, o in self.outputs.items() if i != pid and o.running()}
        if not p or not p.running() or not otras:
            self.mal, self.bien_desde = 0, 0.0
            if not any(o.running() for o in self.outputs.values()):  # terminó el stream: vuelve lo configurado
                self.espera, self.sin_ayuda, self.llena = ESPERA_SUBIR, False, False
                if self.ajuste:
                    self.ajuste = {}
                    self.sync_outputs()
            return
        salto = p.descartes > self.descartes_principal
        self.descartes_principal = p.descartes
        if salto:
            self.salto_en = ahora  # cuenta aunque el último cambio sea reciente: se aplica apenas se pueda
        atraso = p.pendiente / (max(1, self.entrada_kbps) * 125)
        self.mal = self.mal + 1 if atraso > 2 or salto else 0
        self.bien_desde = (self.bien_desde or ahora) if atraso < 0.5 and not salto else 0.0
        otra = next((i for i, o in otras.items() if o.descartes > self.descartes_otras.get(id(o), o.descartes)), None)
        self.descartes_otras = {id(o): o.descartes for o in otras.values()}
        piso = int(self.cfg.get('piso') or PISO)
        config = {d['id']: d.get('bitrate', 0) or self.entrada_kbps for d in self.cfg.get('destinations', [])}
        nombres = {d['id']: d['name'] for d in self.cfg.get('destinations', [])}
        if otra and not self.bien_desde and not self.llena:
            self.llena, self.sin_ayuda = True, False
            print(f'{nombres.get(otra, otra)} también se atrasa: la subida no da para todas. Las demás quedan en el piso '
                  f'aunque {nombres.get(pid, pid)} siga mal.', flush=True)
        if (self.mal >= 3 or ahora - self.salto_en < 30) and ahora - self.cambio > 20 and not self.sin_ayuda:
            cambios = {}
            for i, o in otras.items():
                nuevo = min(piso, config.get(i, o.bitrate or self.entrada_kbps))
                if nuevo < (o.bitrate or self.entrada_kbps):
                    cambios[i] = nuevo
            self.cambio, self.mal, self.salto_en = ahora, 0, -1e9  # aunque ya estén en el piso: no reintentar cada segundo
            if cambios:
                if ahora - self.subida < 120:  # subirlo la hizo andar mal: la próxima subida espera el doble
                    self.espera = min(1800, self.espera * 2)
                self.ajuste.update(cambios)
                self.bajada = ahora
                print('La principal se atrasa: ' + ', '.join(f'{nombres.get(i, i)} a {k} kbps' for i, k in cambios.items()), flush=True)
                self.sync_outputs()
            elif self.ajuste and ahora - self.bajada > 60 and not self.llena:
                self.ajuste, self.sin_ayuda = {}, True
                print(f'Con las demás en el piso, {nombres.get(pid, pid)} sigue mal: el problema es su conexión, no la subida. '
                      'Las demás vuelven a su bitrate.', flush=True)
                self.sync_outputs()
        elif self.bien_desde and ahora - self.bien_desde > self.espera and ahora - self.cambio > self.espera:
            self.sin_ayuda = self.llena = False  # la principal se arregló: si vuelve a fallar, se prueba bajar de nuevo
            if self.ajuste:
                self.ajuste = {}
                self.cambio = self.subida = ahora
                print('La principal anda bien: las demás vuelven a su bitrate.', flush=True)
                self.sync_outputs()

    def medir(self, cada=1.0, tcp=tcp_segmentos):
        """Cada segundo: kbps de entrada y de cada salida, y la pérdida de la red (promedio de los últimos 10 s)."""
        antes_in, antes_out, ventana, entradas = self.recibidos, {}, deque(maxlen=10), deque(maxlen=10)
        antes_tcp = tcp()
        while True:
            time.sleep(cada)
            self.entrada_kbps = round((self.recibidos - antes_in) * 8 / 1000 / cada)
            antes_in = self.recibidos
            entradas.append(self.entrada_kbps)  # el límite va con el pico: un bache de OBS no hace tirar de más
            for o in list(self.outputs.values()):
                hecho = o.salida if o.bitrate else o.enviados  # recomprimido: lo que sale, no lo que entra
                # promedio de los últimos 5 s: ffmpeg cuenta lo que sale de a bloques y un segundo solo salta
                serie = antes_out.setdefault(id(o), deque(maxlen=6))
                serie.append(hecho)
                o.kbps = round(max(0, serie[-1] - serie[0]) * 8 / 1000 / (cada * (len(serie) - 1))) if len(serie) > 1 else 0
                o.limite = max(entradas) * 1000 // 8 * ATRASO_MAXIMO
            ahora = tcp()
            if ahora and antes_tcp:
                ventana.append(((ahora[0] - antes_tcp[0]) % 2**32, (ahora[1] - antes_tcp[1]) % 2**32))  # los contadores dan la vuelta
                salidos = sum(s for s, _ in ventana)
                self.perdida = round(100 * sum(r for _, r in ventana) / salidos, 2) if salidos > 500 else None
            antes_tcp = ahora
            try:
                self.priorizar()
            except Exception as e:  # que un error acá no apague las medidas
                print(f'priorizar: {e!r}', flush=True)
            salidas = list(self.outputs.items())
            for i, o in salidas:
                if o.descartes > self.saltos_vistos.get(id(o), 0):
                    self.saltos.append((round(time.time()), i))
                self.saltos_vistos[id(o)] = o.descartes
            if self.obs_connected or any(o.running() for _, o in salidas):  # sin stream no se guarda nada
                self.historial.append({'t': round(time.time()), 'in': self.entrada_kbps, 'perdida': self.perdida,
                                       'd': {i: [o.kbps, round(o.pendiente / max(1, self.entrada_kbps * 125), 1)]
                                             for i, o in salidas if o.running()}})

    def historia(self):
        """La red en los últimos 30 min, para el gráfico de Consumo."""
        return {'muestras': list(self.historial), 'saltos': list(self.saltos),
                'destinos': {d['id']: d['name'] for d in self.cfg.get('destinations', [])}}

    def probar_subida(self, segundos=20, mbps=25):
        """Mide cuánto sube la conexión hasta Twitch con su modo de prueba (?bandwidthtest=true: no sale en vivo).
        Manda ruido a mbps durante segundos y cuenta lo que pasa. Solo sin stream: si no, competiría con él."""
        with self.cv:
            if self.prueba.get('estado') == 'probando':
                raise ValueError('Ya se está probando.')
            if self.obs_connected or any(o.running() for o in self.outputs.values()):
                raise ValueError('Probá la subida sin stream: si no, la prueba le quita lugar a la transmisión.')
            twitch = next((d for d in self.cfg.get('destinations', []) if 'twitch.tv' in d.get('url', '') and d.get('key')), None)
            if not twitch:
                raise ValueError('Para probar hace falta Twitch con su clave en Plataformas: la prueba usa su modo sin salir en vivo.')
            self.prueba = {'estado': 'probando', 'progreso': 0, 'mbps': 0}
        url = dest_url(twitch) + '?bandwidthtest=true'
        threading.Thread(target=self._prueba, args=(url, segundos, mbps), daemon=True).start()

    def _prueba(self, url, segundos, mbps):
        safe = url.rsplit('/', 1)[0]
        cmd = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-re', '-f', 'lavfi', '-i',
               f'color=s=1280x720:r=30:d={segundos},noise=alls=80:allf=t', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo',
               '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-b:v', f'{mbps}M',
               '-maxrate', f'{mbps}M', '-bufsize', f'{mbps}M', '-g', '60', '-c:a', 'aac', '-b:a', '128k',
               '-progress', 'pipe:1', '-stats_period', '1', '-f', 'flv', url]
        muestras, inicio = [], time.monotonic()
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 creationflags=NO_WINDOW | LOW)
            for linea in p.stdout:
                if linea.startswith(b'total_size=') and linea[11:].strip().isdigit():
                    muestras.append((time.monotonic() - inicio, int(linea[11:])))
                    if len(muestras) > 1:
                        (t0, b0), (t1, b1) = muestras[-2], muestras[-1]
                        self.prueba.update(mbps=round((b1 - b0) * 8 / 1e6 / max(t1 - t0, 0.1), 1),
                                           progreso=min(1, (t1) / segundos))
                if time.monotonic() - inicio > segundos + 15:  # trabada: no se espera para siempre
                    p.kill()
                    break
            err = p.stderr.read().decode('utf-8', 'replace').replace(url, safe + '/•••')
            codigo = p.wait()
            utiles = [m for m in muestras if m[0] >= 5]  # los primeros segundos llenan buffers: no cuentan
            if len(utiles) < 3:
                raise ValueError(f'No se pudo medir ({err.strip()[:200] or f"ffmpeg terminó con {codigo}"}).')
            (t0, b0), (t1, b1) = utiles[0], utiles[-1]
            total = round((b1 - b0) * 8 / 1e6 / (t1 - t0), 1)
            activas = max(1, sum(1 for d in self.cfg.get('destinations', []) if d.get('enabled', True)))
            tope = total >= mbps * 0.9
            recomendado = recomendar(total, tope, activas)
            self.prueba = {'estado': 'listo', 'mbps': total, 'tope': tope, 'recomendado': recomendado,
                           'plataformas': activas, 'hora': time.time(), 'progreso': 1}
            print(f'Prueba de subida: {total} Mb/s; recomendado {recomendado} kbps por plataforma ({activas}).', flush=True)
        except (OSError, ValueError) as e:
            self.prueba = {'estado': 'error', 'error': str(e), 'hora': time.time()}

    def files(self):
        if not os.path.isdir(VIDEOS):
            return []
        out = []
        for name in sorted(os.listdir(VIDEOS)):
            if name.lower().endswith(UPLOAD_EXT):
                p = os.path.join(VIDEOS, name)
                key = (name, os.path.getmtime(p))
                if key not in self.durations:
                    self.durations[key] = probe_duration(self.ffmpeg, p)
                out.append({'name': name, 'duration': self.durations[key]})
        return out

    def medidas(self, o):
        """Bitrate, segundos atrasados (lo que está en la cola, al ritmo que manda OBS) y saltos de una salida."""
        ritmo = self.entrada_kbps * 1000 / 8
        return {'kbps': o.kbps, 'recomprime': bool(o.bitrate), 'atraso': round(o.pendiente / ritmo, 1) if ritmo and o.running() else 0,
                'descartes': o.descartes, 'ultimo_descarte': o.ultimo_descarte}

    def status(self, full=True):
        with self.cv:
            mode = 'filler' if self.mode == 'filler' else 'delayed' if self.delay else 'live'
            left = 0
            if mode == 'filler' and self.filler:
                left = (self.filler[-1][1] - self.filler[0][1]) / 1000 - (time.monotonic() - self.t0)
            s = {'mode': mode, 'delay': round(self.delay, 1), 'filler_left': max(0, round(left)),
                 'obs': self.obs_connected, 'sending': any(o.running() for o in self.outputs.values()),
                 'ffmpeg': hay_ffmpeg(self.ffmpeg)}
        if not full:
            return s
        cfg = self.cfg
        s['destinations'] = [{'id': d['id'], 'name': d['name'], 'url': d['url'], 'enabled': d.get('enabled', True),
                              'bitrate': d.get('bitrate', 0), 'bajado': self.ajuste.get(d['id'], 0),
                              'state': o.state() if (o := self.outputs.get(d['id'])) else 'off',
                              'error': o.error if o else '', **(self.medidas(o) if o else {})}
                             for d in cfg.get('destinations', [])]
        s['red'] = {'entrada_kbps': self.entrada_kbps, 'perdida': self.perdida}
        s['prioridad'] = {'principal': cfg.get('principal') or '', 'piso': int(cfg.get('piso') or PISO)}
        s['prueba'] = self.prueba
        s['filler'] = {'mode': cfg.get('filler_mode', 'text'), 'file': os.path.basename(cfg.get('filler_file') or ''),
                       'loops': cfg.get('filler_loops', 1), 'text': cfg.get('filler_text', 'Activando delay'),
                       'seconds': cfg['delay_seconds']}
        s['busy'], s['files'] = self.busy, self.files()
        return s

    # --- entrada desde OBS ---
    def ingest(self):
        url = f"rtmp://127.0.0.1:{self.cfg['listen_port']}/live/stream"
        while True:
            if not hay_ffmpeg(self.ffmpeg):  # sin ffmpeg no se puede recibir a OBS: la web avisa en Inicio cómo instalarlo
                time.sleep(5)
                continue
            print('Esperando a OBS en', url.rsplit('/', 1)[0], flush=True)
            p = self.ingest_proc = subprocess.Popen(
                [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-listen', '1', '-i', url,
                 '-map', '0', '-c', 'copy', '-f', 'flv', '-flush_packets', '1', '-'],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, creationflags=NO_WINDOW)
            connected = False
            for typ, ts, data in read_tags(p.stdout):
                self.recibidos += len(data) + 15
                if not connected:
                    print('OBS conectado.', flush=True)
                    connected = self.obs_connected = True
                    self.previews['in'].stop()  # los tiempos de OBS vuelven a 0: decodificador nuevo
                k = kind(typ, data)
                if k == 'skip':
                    continue
                self.previews['in'].feed(typ, ts, data, k)
                with self.cv:  # step() lee live_headers con el mismo lock
                    if k == 'header':
                        self.live_headers[track_key(typ, data)] = data
                    self.buf.append((time.monotonic(), typ, ts, data, k))
                    self.cv.notify()
            p.wait()
            self.obs_connected = False
            if connected:
                print('OBS se desconectó.', flush=True)
                self.previews['in'].stop()  # sin esto el panel queda con el último cuadro congelado
                with self.cv:
                    self.buf.append((time.monotonic(), 0, 0, b'', 'end'))

    # --- máquina de estados ---
    def start_filler(self, now, out):
        if self.next_filler:
            f, self.next_filler = self.next_filler, None
            self.filler = [t for t in f if t[3] in ('key', 'frame')]
            self.filler_headers = [t for t in f if t[3] == 'header']
        self.mode, self.fi, self.t0 = 'filler', 0, now
        out += [RESYNC] + self.filler_headers

    def step(self, now):
        out = []
        live = [RESYNC] + [(key[0], 0, d, 'header') for key, d in self.live_headers.items()]
        want, self.want = self.want, None
        if want == 'toggle':
            want = 'delay' if self.mode == 'stream' and not self.delay else 'live'
        rewind, n = self.cfg.get('filler_mode') == 'rewind', self.cfg['delay_seconds']
        if want == 'delay':
            if self.mode != 'stream' or self.delay:
                print('El delay ya está activo.', flush=True)
            elif not self.obs_connected:  # sin esto el video de relleno salía a las plataformas sin estar en stream
                print('OBS no está transmitiendo: el delay no se activa.', flush=True)
            elif not rewind:
                self.start_filler(now, out)
                print(f"DELAY ACTIVANDO: mostrando el video ({n} s)", flush=True)
            elif keys := [i for i, t in enumerate(self.hist) if t[4] == 'key']:
                # vuelve al cuadro clave más nuevo que tenga al menos n s (o al más viejo que haya)
                i = ([i for i in keys if self.hist[i][0] <= now - n] or keys[:1])[-1]
                self.buf.extendleft(reversed(list(self.hist)[i:]))
                self.hist.clear()
                self.delay = now - self.buf[0][0]
                out += live
                print(f'EN DIFERIDO al instante: {self.delay:.1f} s (se repite lo último).', flush=True)
            else:
                print('Todavía no hay nada guardado para repetir (¿está OBS conectado?).', flush=True)
        elif want == 'live':
            if self.mode == 'filler' or self.delay:
                self.mode, self.delay = 'stream', 0.0
                self.buf.clear()
                self.hist.clear()
                out += live
                print('EN VIVO (sin delay).', flush=True)
            else:
                print('Ya estás en vivo.', flush=True)

        if self.mode == 'filler':
            f, elapsed = self.filler, (now - self.t0) * 1000
            while self.fi < len(f) and f[self.fi][1] - f[0][1] <= elapsed:
                out.append(f[self.fi])
                self.fi += 1
            if self.fi == len(f):
                # 'end': OBS cortó durante el video; se entrega para cerrar los destinos en vez de repetir el video
                while self.buf and self.buf[0][4] not in ('key', 'end'):
                    self.buf.popleft()
                if self.buf:
                    self.mode, self.delay = 'stream', now - self.buf[0][0]
                    out += live
                    if self.buf[0][4] == 'key':
                        print(f'EN DIFERIDO: {self.delay:.1f} s de atraso.', flush=True)
                else:  # OBS no mandó nada mientras tanto: repetir el video
                    self.start_filler(now, out)
        if self.mode == 'stream':
            while self.buf and self.buf[0][0] + self.delay <= now:
                t = self.buf.popleft()
                out.append(t[1:])
                if t[4] == 'end':  # OBS cortó: lo anterior no se puede repetir en la conexión nueva
                    self.hist.clear()
                elif rewind and not self.delay:
                    self.hist.append(t)
            # n + 10 s: alcanza para tener un cuadro clave de hace n s aunque OBS los mande cada 10 s
            while self.hist and self.hist[0][0] < now - n - 10:
                self.hist.popleft()
        return out

    def run(self):
        while True:
            with self.cv:
                self.cv.wait(0.005)
                todo = self.step(time.monotonic())
            for t in todo:
                self.emit(*t)

    # --- salida hacia los destinos ---
    def emit(self, typ, ts, data, k):
        outs = list(self.outputs.values())
        if k == 'resync':
            self.resync = True
        elif k == 'end':
            for o in outs:
                o.stop()
            self.previews['out'].stop()
            self.resync = True
        elif k == 'header':
            self.headers[track_key(typ, data)] = data
            self.previews['out'].feed(typ, self.last_out, data, k)
            blob, extra = tag_bytes(typ, self.last_out, data), extra_track(typ, data)
            for o in outs:
                o.header(blob, extra)
        else:
            if self.resync:  # cada tramo nuevo arranca en cuadro clave, con tiempos continuos
                if k != 'key':
                    return
                gap = 33 if self.last_wall is None else max(33, int((time.monotonic() - self.last_wall) * 1000))
                # last_pts: los B-frames del tramo anterior se muestran después de su dts
                self.offset = max(self.last_out + gap, self.last_pts + 33) - ts
                self.resync = False
            pista = track_key(typ, data)[:2]
            out_ts = max(ts + self.offset, self.last_type.get(pista, 0))
            self.last_type[pista] = out_ts
            self.last_out = max(self.last_out, out_ts)
            if typ == 9:
                self.last_pts = max(self.last_pts, out_ts + int.from_bytes(data[2:5], 'big', signed=True))
            self.last_wall = time.monotonic()
            blob, extra = tag_bytes(typ, out_ts, data), extra_track(typ, data)
            for o in outs:
                o.send(blob, k, self.headers, out_ts, extra)
            self.previews['out'].feed(typ, out_ts, data, k)


MODS = {'alt': 1, 'ctrl': 2, 'shift': 4, 'win': 8}


def tray(bridge, cfg, url, quit_app):
    """Ícono en la bandeja (verde = delay activo, rojo = sin delay) y atajos globales: un solo bucle de Windows."""
    u32, s32 = ctypes.windll.user32, ctypes.windll.shell32
    w = wintypes
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    u32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u32.DefWindowProcW.restype = LRESULT
    u32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    u32.CreateWindowExW.restype = w.HWND
    u32.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
    u32.LoadImageW.restype = w.HANDLE
    u32.CreatePopupMenu.restype = w.HMENU
    u32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
    u32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
    u32.DestroyMenu.argtypes = [w.HMENU]
    u32.SetTimer.argtypes = [w.HWND, ctypes.c_size_t, w.UINT, w.LPVOID]
    u32.RegisterHotKey.argtypes = [w.HWND, ctypes.c_int, w.UINT, w.UINT]
    u32.SetForegroundWindow.argtypes = [w.HWND]
    s32.Shell_NotifyIconW.argtypes = [w.DWORD, w.LPVOID]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [('style', w.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int),
                    ('cbWndExtra', ctypes.c_int), ('hInstance', w.HINSTANCE), ('hIcon', w.HICON),
                    ('hCursor', w.HANDLE), ('hbrBackground', w.HBRUSH), ('lpszMenuName', w.LPCWSTR),
                    ('lpszClassName', w.LPCWSTR)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [('cbSize', w.DWORD), ('hWnd', w.HWND), ('uID', w.UINT), ('uFlags', w.UINT),
                    ('uCallbackMessage', w.UINT), ('hIcon', w.HICON), ('szTip', w.WCHAR * 128),
                    ('dwState', w.DWORD), ('dwStateMask', w.DWORD), ('szInfo', w.WCHAR * 256),
                    ('uVersion', w.UINT), ('szInfoTitle', w.WCHAR * 64), ('dwInfoFlags', w.DWORD),
                    ('guidItem', ctypes.c_byte * 16), ('hBalloonIcon', w.HICON)]

    WM_TRAY, WM_TIMER, WM_HOTKEY = 0x8001, 0x0113, 0x0312
    taskbar_created = u32.RegisterWindowMessageW('TaskbarCreated')
    icons = {on: u32.LoadImageW(None, os.path.join(RECURSOS, 'icons', f'{"on" if on else "off"}.ico'), 1, 0, 0, 0x50)
             for on in (True, False)}
    nid = NOTIFYICONDATAW()
    last = ['']

    def update():
        s = bridge.status(full=False)
        tip = 'Stream delay: ' + {'live': 'sin delay', 'filler': f"activando ({s['filler_left']} s)",
                                  'delayed': f"delay {round(s['delay'])} s"}[s['mode']]
        if tip != last[0]:
            nid.hIcon, nid.szTip, last[0] = icons[s['mode'] != 'live'], tip, tip
            s32.Shell_NotifyIconW(1, ctypes.byref(nid))  # NIM_MODIFY

    def menu(hwnd):
        live = bridge.status(full=False)['mode'] == 'live'
        m = u32.CreatePopupMenu()
        u32.AppendMenuW(m, 0, 1, 'Abrir panel')
        u32.AppendMenuW(m, 0, 2, 'Activar delay' if live else 'Volver a vivo')
        u32.AppendMenuW(m, 0x800, 0, None)  # separador
        u32.AppendMenuW(m, 0, 3, 'Salir')
        pt = w.POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(hwnd)  # sin esto el menú no se cierra al hacer clic afuera
        cmd = u32.TrackPopupMenu(m, 0x100 | 0x2, pt.x, pt.y, 0, hwnd, None)  # TPM_RETURNCMD | TPM_RIGHTBUTTON
        u32.DestroyMenu(m)
        if cmd == 1:
            webbrowser.open(url)
        elif cmd == 2:
            bridge.request('toggle')
        elif cmd == 3:
            s32.Shell_NotifyIconW(2, ctypes.byref(nid))  # NIM_DELETE
            quit_app()

    def proc(hwnd, msg, wp, lp):
        if msg == WM_TRAY:
            if lp == 0x0202:  # clic izquierdo
                webbrowser.open(url)
            elif lp == 0x0205:  # clic derecho
                menu(hwnd)
            return 0
        if msg == WM_HOTKEY:
            bridge.request({1: 'delay', 2: 'live'}[wp])
            return 0
        if msg == WM_TIMER:
            update()
            return 0
        if msg == taskbar_created:  # se reinició el explorador de Windows: volver a poner el ícono
            s32.Shell_NotifyIconW(0, ctypes.byref(nid))
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    wndproc = WNDPROC(proc)  # referencia viva mientras exista la ventana
    k32 = ctypes.windll.kernel32
    k32.GetModuleHandleW.restype = w.HMODULE  # sin esto ctypes corta el puntero a 32 bits (handle inválido)
    wc = WNDCLASSW(lpfnWndProc=wndproc, hInstance=k32.GetModuleHandleW(None),
                   lpszClassName='StreamDelayTray')
    u32.RegisterClassW(ctypes.byref(wc))
    hwnd = u32.CreateWindowExW(0, wc.lpszClassName, 'Stream delay', 0, 0, 0, 0, 0, None, None, wc.hInstance, None)
    nid.cbSize, nid.hWnd, nid.uID, nid.uFlags, nid.uCallbackMessage = ctypes.sizeof(nid), hwnd, 1, 0x7, WM_TRAY
    nid.hIcon, nid.szTip = icons[False], 'Stream delay'
    s32.Shell_NotifyIconW(0, ctypes.byref(nid))  # NIM_ADD
    for i, name in ((1, cfg['hotkey_delay']), (2, cfg['hotkey_live'])):
        *mods, key = name.lower().split('+')
        vk = 0x6F + int(key[1:]) if key[0] == 'f' and key[1:].isdigit() else ord(key.upper())
        if not u32.RegisterHotKey(hwnd, i, sum(MODS[m] for m in mods) | 0x4000, vk):
            print(f'No se pudo registrar el atajo {name} (¿lo usa otro programa?)', flush=True)
    u32.SetTimer(hwnd, 1, 1000, None)
    update()
    msg = w.MSG()
    while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        u32.TranslateMessage(ctypes.byref(msg))
        u32.DispatchMessageW(ctypes.byref(msg))


def save_config(cfg, cfg_path):
    with CFG_LOCK:  # entera o nada: la web la lee desde otro proceso
        with open(cfg_path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(cfg_path + '.tmp', cfg_path)


def apply_settings(bridge, cfg_path, changes):
    """Arma el video nuevo en segundo plano y, si sale bien, lo usa y guarda la config."""
    bridge.busy = 'Preparando el video de delay...'
    try:
        filler = make_filler(dict(bridge.cfg, **changes), bridge.ffmpeg)
    except RuntimeError as e:
        bridge.busy = str(e)
        return
    bridge.cfg.update(changes)
    bridge.use_filler(filler)
    save_config(bridge.cfg, cfg_path)
    bridge.busy = ''


def lan_ip():
    """IP de esta PC en la red de la casa (UDP connect no manda nada: solo elige la interfaz)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(('10.255.255.255', 1))
            return s.getsockname()[0]
        except OSError:
            return '127.0.0.1'


def api(bridge, cfg_path, clave, salir):
    """La API del núcleo: solo desde esta PC y con la clave de nucleo.clave. La usan la web (panel.py), que corre en
    otro proceso para poder reiniciarla o actualizarla sin cortar el stream, y el guardián."""
    cfg = bridge.cfg

    def partes():
        """Los procesos del núcleo, para /metricas: él y sus ffmpeg."""
        vivo = lambda p: p.pid if p and p.poll() is None else None
        lista = [('Núcleo de transmisión', 'Recibe a OBS, guarda el delay y manda a cada plataforma', os.getpid(), None),
                 ('Recepción de OBS', 'ffmpeg que recibe el stream de OBS', vivo(bridge.ingest_proc), bridge.recibidos)]
        for d in cfg.get('destinations', []):
            o = bridge.outputs.get(d['id'])
            if o:
                lista.append((f"Envío a {d['name']}", 'ffmpeg que manda el stream a la plataforma', vivo(o.proc), o.enviados))
        for k, nombre in (('in', 'Vista previa de OBS'), ('out', 'Vista previa del stream')):
            lista.append((nombre, 'ffmpeg del panel de Delay: se apaga solo al cerrarlo', vivo(bridge.previews[k].proc), None))
        return lista

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body=b'{}', ctype='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def error(self, msg):
            return self.reply(400, json.dumps({'error': msg}).encode())

        def permitido(self):
            return self.client_address[0] == '127.0.0.1' and secrets.compare_digest(self.headers.get('X-Nucleo', ''), clave)

        def do_GET(self):
            if not self.permitido():
                return self.reply(403)
            path = self.path.partition('?')[0]
            if path == '/api/state':
                return self.reply(200, json.dumps(bridge.status()).encode())
            if path == '/api/deck':
                s = bridge.status(full=False)
                return self.reply(200, json.dumps({k: s[k] for k in ('mode', 'delay', 'filler_left')}).encode())
            if path in ('/snap/in.jpg', '/snap/out.jpg'):
                jpg = bridge.previews[path[6:-4]].latest()
                return self.reply(200, jpg, 'image/jpeg') if jpg else self.reply(204, b'')
            if path == '/nucleo/partes':
                return self.reply(200, json.dumps(partes()).encode())
            if path == '/api/red/historial':
                return self.reply(200, json.dumps(bridge.historia()).encode())
            self.reply(404)

        def do_POST(self):
            if not self.permitido():
                return self.reply(403)
            path, _, query = self.path.partition('?')
            if path == '/api/deck/toggle':  # botón de StreamDock: necesita la clave que se le instaló
                token = cfg.get('deck_token', '')
                if not token or not secrets.compare_digest(unquote(query), token):
                    return self.reply(403)
                bridge.request('toggle')
                return self.reply(200)
            if path in ('/api/delay', '/api/live'):
                bridge.request(path[5:])
                return self.reply(200)
            if path == '/api/red/prueba':
                try:
                    bridge.probar_subida()
                except ValueError as e:
                    return self.error(str(e))
                return self.reply(200)
            if path == '/nucleo/deck_token':  # para instalar el botón: la clave queda en la config, que es del núcleo
                if not cfg.get('deck_token'):
                    cfg['deck_token'] = secrets.token_urlsafe(16)
                    save_config(cfg, cfg_path)
                return self.reply(200, json.dumps({'token': cfg['deck_token']}).encode())
            if path == '/nucleo/salir':  # el guardián lo pasa a una versión nueva (solo sin stream)
                self.reply(200)
                threading.Timer(0.3, salir).start()
                return
            size = int(self.headers.get('Content-Length') or 0)
            try:
                s = json.loads(self.rfile.read(size) or b'{}')
            except ValueError:
                return self.error('Pedido inválido.')
            if path == '/api/settings':
                return self.settings(s)
            if path.startswith('/api/destinations/'):
                return self.destinations(path.rsplit('/', 1)[1], s)
            self.reply(404)

        def settings(self, s):
            if bridge.busy.startswith('Preparando'):
                return self.reply(409, json.dumps({'error': 'Ya se está preparando un video.'}).encode())
            try:
                seconds = float(s.get('seconds') or 0)
                loops = int(s.get('loops') or 1)
            except (TypeError, ValueError):
                return self.error('Revisá los números.')
            if s.get('mode') == 'file':
                files = {f['name']: f for f in bridge.files()}
                name = s.get('file', '')
                if name not in files:
                    return self.error('Elegí un video o imagen.')
                if files[name]['duration']:  # video: el delay sale de duración x vueltas
                    if not 1 <= loops <= 100:
                        return self.error('Las vueltas tienen que ser entre 1 y 100.')
                    seconds = round(files[name]['duration'] * loops, 1)
                changes = {'filler_mode': 'file', 'filler_file': os.path.join(VIDEOS, name), 'filler_loops': loops}
            elif s.get('mode') == 'text':
                text = str(s.get('text', '')).strip()
                if not 1 <= len(text) <= 200:
                    return self.error('Escribí un texto de hasta 200 caracteres.')
                changes = {'filler_mode': 'text', 'filler_text': text}
            elif s.get('mode') == 'rewind':
                changes = {'filler_mode': 'rewind'}
            else:
                return self.error('Modo desconocido.')
            if not 5 <= seconds <= 600:
                return self.error(f'El delay tiene que quedar entre 5 s y 10 min (así daría {seconds:g} s).')
            changes['delay_seconds'] = seconds
            threading.Thread(target=apply_settings, args=(bridge, cfg_path, changes), daemon=True).start()
            return self.reply(200)

        def destinations(self, action, s):
            dests = bridge.cfg.setdefault('destinations', [])
            if action == 'add':
                name, url, key = (str(s.get(k, '')).strip() for k in ('name', 'url', 'key'))
                if not name or len(name) > 40:
                    return self.error('Poné un nombre (hasta 40 letras).')
                if not re.fullmatch(r'rtmps?://\S+', url):
                    return self.error('La URL tiene que empezar con rtmp:// o rtmps://')
                if re.search(r'\s', key) or len(key) > 300:
                    return self.error('La clave no puede tener espacios.')
                dests.append({'id': secrets.token_hex(4), 'name': name, 'url': url, 'key': key, 'enabled': True})
            elif action == 'prioridad':  # la plataforma principal ('' ninguna) y el piso de las demás
                pid = str(s.get('principal') or '')
                if pid and not any(d['id'] == pid for d in dests):
                    return self.error('No encuentro esa plataforma.')
                try:
                    piso = int(s.get('piso') or PISO)
                except (TypeError, ValueError):
                    return self.error('El piso tiene que ser un número.')
                if not 500 <= piso <= 20000:
                    return self.error('El piso tiene que estar entre 500 y 20000 kbps.')
                if pid != (bridge.cfg.get('principal') or ''):
                    bridge.ajuste, bridge.sin_ayuda, bridge.llena = {}, False, False  # otra principal: las demás vuelven a lo suyo y se empieza de cero
                bridge.cfg['principal'], bridge.cfg['piso'] = pid, piso
            else:
                d = next((d for d in dests if d['id'] == s.get('id')), None)
                if not d:
                    return self.error('No encuentro ese destino.')
                if action == 'delete':
                    dests.remove(d)
                elif action == 'enable':
                    d['enabled'] = bool(s.get('enabled'))
                elif action == 'bitrate':  # kbps propios (se recomprime) o 0: lo mismo que manda OBS
                    try:
                        kbps = int(s.get('bitrate') or 0)
                    except (TypeError, ValueError):
                        return self.error('El bitrate tiene que ser un número.')
                    if kbps and not 500 <= kbps <= 20000:
                        return self.error('El bitrate tiene que estar entre 500 y 20000 kbps (o 0: lo que manda OBS).')
                    d['bitrate'] = kbps
                    bridge.ajuste.pop(d['id'], None)  # lo que elige a mano manda sobre lo que bajó priorizar
                elif action == 'update':  # otra clave (o URL) sin quitarla: si estaba transmitiendo, se reconecta solo ese destino
                    url, key = str(s.get('url', d['url'])).strip(), str(s.get('key', '')).strip()
                    if not re.fullmatch(r'rtmps?://\S+', url):
                        return self.error('La URL tiene que empezar con rtmp:// o rtmps://')
                    if re.search(r'\s', key) or len(key) > 300:
                        return self.error('La clave no puede tener espacios.')
                    d['url'] = url
                    if key:  # vacía: queda la que estaba
                        d['key'] = key
                else:
                    return self.reply(404)
            save_config(bridge.cfg, cfg_path)
            bridge.sync_outputs()
            return self.reply(200)

    ThreadingHTTPServer(('127.0.0.1', PUERTO_NUCLEO), Handler).serve_forever()


def load_config(cfg_path):
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    if 'destinations' not in cfg:  # config de antes: un solo destino en output_url + stream_key
        url, key = cfg.pop('output_url', ''), cfg.pop('stream_key', '')
        cfg['destinations'] = [{'id': 'twitch', 'name': 'Twitch' if 'twitch' in url else 'Destino', 'url': url,
                                'key': key, 'enabled': True}] if url else []
        cfg.setdefault('filler_mode', 'file' if cfg.get('filler_file') else 'text')
        cfg.pop('filler_image', None)
        save_config(cfg, cfg_path)
    return cfg


class Log:
    """Salida de pythonw: cada línea con fecha y hora, para cruzarla con el log de OBS."""

    def __init__(self, f):
        self.f, self.bol, self.lock = f, True, threading.Lock()

    def write(self, s):
        with self.lock:
            for part in s.splitlines(keepends=True):
                if self.bol:
                    self.f.write(time.strftime('%Y-%m-%d %H:%M:%S '))
                self.f.write(part)
                self.bol = part.endswith('\n')
        return len(s)

    def flush(self):
        self.f.flush()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    cfg_path = args[0] if args else ruta_config('config.json')
    cfg = load_config(cfg_path)
    url = f"http://127.0.0.1:{cfg.get('panel_port', 8080)}"
    with socket.socket() as s:  # dos núcleos pelearían por el puerto de OBS
        if s.connect_ex(('127.0.0.1', PUERTO_NUCLEO)) == 0:
            sys.exit('El núcleo ya está corriendo.')
    if cfg.get('panel_lan') and not cfg.get('lan_key'):  # la config es del núcleo: la web solo la lee
        cfg['lan_key'] = secrets.token_urlsafe(6)
        save_config(cfg, cfg_path)
    restarted = next((a.split('=')[1] for a in sys.argv if a.startswith('--restarted=')), None)
    if sys.stdout is None:  # pythonw (sin consola): los mensajes van a un archivo
        log = os.path.join(DATOS, 'delay.log')
        if os.path.exists(log):  # el de la vez anterior queda: si se cayó y la reabrís, no se pierde por qué
            os.replace(log, os.path.join(DATOS, 'delay.old.log'))
        f = open(log, 'w', encoding='utf-8', buffering=1)
        faulthandler.enable(f)  # cierres de Python a bajo nivel (sin esto pythonw no deja rastro)
        sys.stdout = sys.stderr = Log(f)
    if restarted == 'actualizacion':
        print('Núcleo reiniciado para pasar a la versión nueva.', flush=True)
    elif restarted:
        print(f'La app se había cerrado sola (código {restarted}, detalle en delay.old.log): se reabrió.', flush=True)
    ffmpeg = cfg.get('ffmpeg') or 'ffmpeg'
    try:
        filler = saved_filler(cfg) if restarted else None
        if filler is None and not hay_ffmpeg(ffmpeg):
            print('Falta ffmpeg: la web sigue andando y en Inicio dice cómo instalarlo.', flush=True)
            filler = []  # sin relleno: al activar el delay se repite lo último, como en el modo repetir
        bridge = Bridge(cfg, ffmpeg, make_filler(cfg, ffmpeg) if filler is None else filler)
    except RuntimeError as e:
        sys.exit(str(e))

    def quit_app(codigo=0):
        print('Núcleo cerrado (Salir o fin normal).' if codigo == 0 else 'Núcleo cerrado para actualizarlo.', flush=True)  # si el log corta sin esto, la mataron de afuera
        for p in [bridge.ingest_proc, *(o.proc for o in bridge.outputs.values()),
                  *(v.proc for v in bridge.previews.values())]:
            if p:
                p.kill()
        os._exit(codigo)

    def console():  # comandos d / l / q cuando hay consola (pruebas, o abierto con python en vez de pythonw)
        for line in sys.stdin:
            cmd = line.strip().lower()
            if cmd == 'q':
                quit_app()
            if cmd in ('d', 'l'):
                bridge.request('delay' if cmd == 'd' else 'live')

    clave = secrets.token_urlsafe(24)
    with open(CLAVE_NUCLEO + '.tmp', 'w', encoding='utf-8') as f:
        f.write(clave)
    os.replace(CLAVE_NUCLEO + '.tmp', CLAVE_NUCLEO)
    for target in (bridge.ingest, bridge.run, bridge.medir, lambda: api(bridge, cfg_path, clave, lambda: quit_app(SALIDA_ACTUALIZAR))):
        threading.Thread(target=target, daemon=True).start()
    if sys.stdin:
        threading.Thread(target=console, daemon=True).start()
    print(f"Núcleo listo. Panel: {url}\nAtajos: {cfg['hotkey_delay']} = activar delay, {cfg['hotkey_live']} = volver a vivo.",
          flush=True)
    try:
        tray(bridge, cfg, url, quit_app)
        print('Windows cerró la ventana de la bandeja.', flush=True)
    except KeyboardInterrupt:
        pass
    quit_app()


if __name__ == '__main__':
    main()
