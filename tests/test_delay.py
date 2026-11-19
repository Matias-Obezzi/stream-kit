"""Prueba de punta a punta sin Twitch (~100 s): simula OBS con ffmpeg y graba la salida a un archivo.
Activa el delay a los 10 s, vuelve a vivo a los 29 s y verifica que la salida decodifique limpia.
Lo hace dos veces: con video de relleno y con el modo repetir (sin relleno).
Uso: python tests/test_delay.py
"""
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = _os.path.join(_RAIZ, 'streamkit')
os.environ['STREAMKIT_DATOS'] = tempfile.mkdtemp()  # no toca tus datos
os.environ['STREAMKIT_PUERTOS'] = '48712'  # ni los puertos de tu Stream Kit abierto
import delay  # noqa: E402
import threading, urllib.error, urllib.request  # noqa: E402

# la API del núcleo: sin la clave no contesta; con la clave maneja el delay. El botón de StreamDock, con su propia clave
b = delay.Bridge({'delay_seconds': 1, 'deck_token': 'boton'}, 'ffmpeg', [])
threading.Thread(target=delay.api, args=(b, os.path.join(os.environ['STREAMKIT_DATOS'], 'c.json'), 'secreto', None), daemon=True).start()
def pedir(ruta, metodo='GET', clave='secreto'):
    for _ in range(50):
        try:
            r = urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{delay.PUERTO_NUCLEO}{ruta}', method=metodo,
                                       data=b'' if metodo == 'POST' else None, headers={'X-Nucleo': clave}), timeout=5)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b''
        except OSError:
            time.sleep(0.1)  # todavía arrancando
assert pedir('/api/state', clave='otra')[0] == 403
codigo, cuerpo = pedir('/api/state')
assert codigo == 200 and json.loads(cuerpo)['mode'] == 'live' and json.loads(cuerpo)['destinations'] == []
assert pedir('/api/delay', 'POST')[0] == 200 and b.want == 'delay'
assert pedir('/api/deck/toggle?mal', 'POST')[0] == 403 and pedir('/api/deck/toggle?boton', 'POST')[0] == 200 and b.want == 'toggle'
assert json.loads(pedir('/nucleo/deck_token', 'POST')[1]) == {'token': 'boton'}

# bitrate propio por plataforma, historial de la red y prueba de subida
def mandar(ruta, cuerpo):
    try:
        r = urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{delay.PUERTO_NUCLEO}{ruta}', method='POST',
                                   data=json.dumps(cuerpo).encode(), headers={'X-Nucleo': 'secreto'}), timeout=5)
        return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')
codigo, r = mandar('/api/red/prueba', {})
assert codigo == 400 and 'Twitch' in r['error'], r  # sin Twitch configurado no hay contra qué probar
assert mandar('/api/destinations/add', {'name': 'Kick', 'url': 'rtmps://kick.test/app', 'key': 'k'})[0] == 200
kid = json.loads(pedir('/api/state')[1])['destinations'][0]['id']
assert mandar('/api/destinations/bitrate', {'id': kid, 'bitrate': 300})[0] == 400
assert mandar('/api/destinations/bitrate', {'id': kid, 'bitrate': 6000})[0] == 200
d = json.loads(pedir('/api/state')[1])['destinations'][0]
assert d['bitrate'] == 6000 and b.outputs[kid].bitrate == 6000, d
assert mandar('/api/destinations/bitrate', {'id': kid, 'bitrate': 0})[0] == 200 and b.outputs[kid].bitrate == 0
h = json.loads(pedir('/api/red/historial')[1])
assert h['destinos'] == {kid: 'Kick'} and h['muestras'] == [] and h['saltos'] == []
b.obs_connected = True
codigo, r = mandar('/api/red/prueba', {})
assert codigo == 400 and 'sin stream' in r['error'], r  # con stream no se prueba: competiría
b.obs_connected = False
v = delay.opciones_video('ffmpeg', 6000)
assert v[1] in ('h264_nvenc', 'h264_qsv', 'h264_amf', 'libx264') and '6000k' in v and 'expr:gte(t,n_forced*2)' in v

# sin OBS transmitiendo, el delay no arranca: si no, el video de relleno sale solo a las plataformas
b = delay.Bridge({'delay_seconds': 1}, 'ffmpeg', [(9, 0, b'v', 'key'), (9, 33, b'v', 'frame')])
b.request('delay')
assert b.step(0.0) == [] and b.mode == 'stream' and not b.delay
b.request('toggle')
assert b.step(0.1) == [] and b.mode == 'stream'

# OBS corta mientras pasa el video: el puente tiene que cerrar Twitch, no repetir el video para siempre
b = delay.Bridge({'delay_seconds': 1}, 'ffmpeg', [(9, 0, b'v', 'key'), (9, 33, b'v', 'frame')])
b.obs_connected = True
b.request('delay')
b.step(0.0)
b.buf.append((0.5, 0, 0, b'', 'end'))
assert b.mode == 'filler' and any(t[3] == 'end' for t in b.step(10.0)) and b.mode == 'stream'

# modo repetir: al activar vuelve al cuadro clave más nuevo con al menos 3 s y sale de ahí, sin relleno
b = delay.Bridge({'delay_seconds': 3, 'filler_mode': 'rewind'}, 'ffmpeg', [])
b.obs_connected = True
for i in range(10):  # 10 s de OBS, un cuadro clave por segundo
    b.buf.append((float(i), 9, i * 1000, b'v', 'key'))
    b.step(float(i))
b.request('delay')
out = b.step(9.5)
assert b.mode == 'stream' and b.delay == 3.5 and out[-1] == (9, 6000, b'v', 'key'), (b.delay, out)
b.request('live')
b.step(9.6)
assert not b.delay and not b.buf and not b.hist

assert delay.dest_url({'url': 'rtmp://live.twitch.tv/app/', 'key': 'abc'}) == 'rtmp://live.twitch.tv/app/abc'

# la pista del VOD de OBS (Enhanced RTMP, pista 1): config y tiempos aparte de la principal
vod_cfg, vod_frame = bytes([0x95, 0x00]) + b'mp4a\x01\x11\x90', bytes([0x95, 0x01]) + b'mp4a\x01\x21'
assert delay.kind(8, vod_cfg) == 'header' and delay.kind(8, vod_frame) == 'frame'
assert delay.extra_track(8, vod_frame) and not delay.extra_track(8, b'\xaf\x01\x21')
assert delay.track_key(8, vod_cfg) != delay.track_key(8, b'\xaf\x00\x11\x90') == (8, 0, 0)
assert delay.Output('ffmpeg', 'rtmp://live.twitch.tv/app/x').vod_track and not delay.Output('ffmpeg', 'rtmps://kick/app/x').vod_track

# red lenta: la cola crece, a los 3000 se tira lo atrasado y se cuenta el salto
o = delay.Output('ffmpeg', 'rtmps://kick/app/secreta')
o.running, o.q = (lambda: True), __import__('queue').Queue()
for _ in range(3001):
    o.send(b'x' * 100, 'frame', {}, 0)
assert o.pendiente == 300100 and not o.descartes
o.send(b'x' * 100, 'frame', {}, 0)
assert o.descartes == 1 and o.pendiente == 0 and o.q.empty() and o.need_key and o.ultimo_descarte
o.pendiente = 125_000  # 1 s a 1000 kbps
b.outputs, b.recibidos = {'k': o}, 0
cuentas = iter([(1000, 0), (2000, 10), (3000, 20)])  # 1000 salidos y 10 reenviados por segundo: 1 %
threading.Thread(target=b.medir, kwargs={'cada': 0.05, 'tcp': lambda: next(cuentas, (3000, 20))}, daemon=True).start()
b.recibidos += 6250  # 1000 kbps en 0,05 s
time.sleep(0.12)
m = b.medidas(o)
assert b.perdida == 1.0 and m['descartes'] == 1, (b.perdida, m)
assert o.limite == 1_250_000, o.limite  # 10 s al pico de 1000 kbps
o.pendiente = 1_300_000
o.send(b'x' * 100, 'key', {}, 0)  # con la medida, se tira por segundos y no por cantidad de paquetes
assert o.descartes == 2 and o.pendiente == 0
assert delay.tcp_segmentos() is not None  # Windows lo da

# dos destinos (archivos) a la vez: los dos tienen que salir completos y limpios
for mode in ('text', 'rewind'):
    tmp = tempfile.mkdtemp()
    outs = [os.path.join(tmp, n) for n in ('twitch.tv.flv', 'otro.flv')]  # solo el de Twitch lleva la pista del VOD
    cfg = json.load(open(os.path.join(_RAIZ, 'recursos', 'ejemplos', 'config.json'), encoding='utf-8'))
    cfg.update(destinations=[{'id': str(i), 'name': f'archivo {i}', 'url': o, 'key': '', 'enabled': True,
                              'bitrate': 800 if i else 0}  # el segundo recomprimido a bitrate propio
                             for i, o in enumerate(outs)],
               filler_mode=mode, filler_text='Ya volvemos\nen un ratito', delay_seconds=8, resolution='640x360',
               fps=30, video_bitrate_kbps=1000, listen_port=19350, panel_port=0, open_panel=False)
    json.dump(cfg, open(os.path.join(tmp, 'test.json'), 'w'))

    # sus archivos (el video de relleno, los logs) van a la carpeta de la prueba, no a la tuya
    app = subprocess.Popen([sys.executable, '-u', os.path.join(HERE, 'delay.py'), os.path.join(tmp, 'test.json')],
                           stdin=subprocess.PIPE, text=True, env={**os.environ, 'STREAMKIT_DATOS': tmp, 'STREAMKIT_PUERTOS': str(48720 + len(mode))})
    time.sleep(4)
    obs = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-re', '-f', 'lavfi', '-i',
                            'testsrc=s=640x360:r=30', '-f', 'lavfi', '-i', 'sine=f=440:r=48000', '-f', 'lavfi', '-i',
                            'sine=f=880:r=48000', '-map', '0:v', '-map', '1:a', '-map', '2:a', '-t', '40',
                            '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p', '-g', '60', '-c:a', 'aac',
                            '-f', 'flv', f"rtmp://127.0.0.1:{cfg['listen_port']}/live/stream"])
    t0 = time.time()
    for at, cmd in ((10, 'd'), (29, 'l')):
        time.sleep(at - (time.time() - t0))
        app.stdin.write(cmd + '\n')
        app.stdin.flush()
    obs.wait()
    time.sleep(4)
    app.stdin.write('q\n')
    app.stdin.flush()
    app.wait(10)

    for out in outs:
        errors = subprocess.run(['ffmpeg', '-hide_banner', '-v', 'error', '-i', out, '-f', 'null', '-'],
                                capture_output=True, text=True).stderr
        dur = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                    out], capture_output=True, text=True).stdout)
        assert not errors, errors
        audios = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index',
                                 '-of', 'csv=p=0', out], capture_output=True, text=True).stdout.split()
        assert len(audios) == (2 if 'twitch' in out else 1), (out, audios)
        primera = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', out],
                                 capture_output=True, text=True).stdout.split()[0]
        assert primera == 'video', (out, primera)  # con el audio primero, Kick corta cada 18 s
        assert 38 < dur < 46, dur  # 40 s de OBS + 8 s de video (o repetidos) - lo que se saltea al volver a vivo
        print(f'OK ({mode}): {dur:.1f} s de salida sin errores ({out})')
