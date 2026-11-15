"""Prueba de punta a punta sin Twitch (~100 s): simula OBS con ffmpeg y graba la salida a un archivo.
Activa el delay a los 10 s, vuelve a vivo a los 29 s y verifica que la salida decodifique limpia.
Lo hace dos veces: con video de relleno y con el modo repetir (sin relleno).
Uso: python test_delay.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import delay  # noqa: E402

# OBS corta mientras pasa el video: el puente tiene que cerrar Twitch, no repetir el video para siempre
b = delay.Bridge({'delay_seconds': 1}, 'ffmpeg', [(9, 0, b'v', 'key'), (9, 33, b'v', 'frame')])
b.request('delay')
b.step(0.0)
b.buf.append((0.5, 0, 0, b'', 'end'))
assert b.mode == 'filler' and any(t[3] == 'end' for t in b.step(10.0)) and b.mode == 'stream'

# modo repetir: al activar vuelve al cuadro clave más nuevo con al menos 3 s y sale de ahí, sin relleno
b = delay.Bridge({'delay_seconds': 3, 'filler_mode': 'rewind'}, 'ffmpeg', [])
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

# dos destinos (archivos) a la vez: los dos tienen que salir completos y limpios
for mode in ('text', 'rewind'):
    tmp = tempfile.mkdtemp()
    outs = [os.path.join(tmp, n) for n in ('twitch.tv.flv', 'otro.flv')]  # solo el de Twitch lleva la pista del VOD
    cfg = json.load(open(os.path.join(HERE, 'config.example.json'), encoding='utf-8'))
    cfg.update(destinations=[{'id': str(i), 'name': f'archivo {i}', 'url': o, 'key': '', 'enabled': True}
                             for i, o in enumerate(outs)],
               filler_mode=mode, filler_text='Ya volvemos\nen un ratito', delay_seconds=8, resolution='640x360',
               fps=30, video_bitrate_kbps=1000, listen_port=19350, panel_port=0, open_panel=False)
    json.dump(cfg, open(os.path.join(tmp, 'test.json'), 'w'))

    # sus archivos (el video de relleno, los logs) van a la carpeta de la prueba, no a la tuya
    app = subprocess.Popen([sys.executable, '-u', os.path.join(HERE, 'delay.py'), os.path.join(tmp, 'test.json')],
                           stdin=subprocess.PIPE, text=True, env={**os.environ, 'STREAMKIT_DATOS': tmp})
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
