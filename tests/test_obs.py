# python tests/test_obs.py: Autoconfigurar OBS sobre una carpeta de OBS inventada. No toca tu OBS ni lo cierra
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import json, os, tempfile
import obs

obs.CARPETA = tempfile.mkdtemp()
perfil = os.path.join(obs.CARPETA, 'basic', 'profiles', 'MiPerfil')
os.makedirs(perfil)
def escribir(ruta, texto):
    with open(ruta, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(texto)
def leer(ruta):
    return open(ruta, encoding='utf-8-sig', newline='').read()
escribir(os.path.join(obs.CARPETA, 'user.ini'), '[General]\r\nFirstRun=true\r\n\r\n[Basic]\r\nProfile=Mi perfil\r\nProfileDir=MiPerfil\r\n')
escribir(os.path.join(obs.CARPETA, 'global.ini'), '[General]\r\nMaxLogs=10\r\nEnableCustomServerVodTrack=false\r\n')
escribir(os.path.join(perfil, 'basic.ini'), '[General]\r\nName=Mi perfil\r\n\r\n[Stream1]\r\nIgnoreRecommended=false\r\nEnableMultitrackVideo=true\r\n')
json.dump({'type': 'rtmp_common', 'settings': {'service': 'Twitch', 'server': 'auto', 'key': 'live_123'}}, open(os.path.join(perfil, 'service.json'), 'w'))

assert obs.perfil() == perfil
obs.proceso_obs = lambda: None  # sin preguntarle a Windows: el OBS de verdad no cuenta
e = obs.estado(1935)
assert e['instalado'] and not e['configurado'] and e['perfil'] == 'MiPerfil'

# abierto y sin permiso para cerrarlo: no toca nada
try:
    obs.configurar(1935, cerrar_obs=False, abierto=(99, r'C:\obs\bin\64bit\obs64.exe'))
    raise AssertionError('tenía que frenar')
except ValueError as x:
    assert 'abierto' in str(x)
assert 'live_123' in open(os.path.join(perfil, 'service.json')).read()

# abierto, con permiso: lo cierra, configura, deja copia, rescata la clave de Twitch y lo vuelve a abrir
cerrados, abiertos = [], []
r = obs.configurar(1935, cerrar_obs=True, abierto=(99, r'C:\obs\bin\64bit\obs64.exe'),
                   cerrar_fn=lambda pid: cerrados.append(pid) or True, abrir_fn=abiertos.append)
assert cerrados == [99] and abiertos == [r'C:\obs\bin\64bit\obs64.exe'] and r['reabierto']
assert r['anterior'] == ('Twitch', 'rtmp://live.twitch.tv/app', 'live_123')
servicio = json.load(open(os.path.join(perfil, 'service.json')))
assert servicio == {'type': 'rtmp_custom', 'settings': {'server': 'rtmp://127.0.0.1:1935/live', 'key': 'stream', 'use_auth': False, 'bwtest': False}}
basic = leer(os.path.join(perfil, 'basic.ini'))
assert 'EnableMultitrackVideo=false\r\n' in basic and 'IgnoreRecommended=false' in basic and 'Name=Mi perfil' in basic
assert 'EnableCustomServerVodTrack=true\r\n' in leer(os.path.join(obs.CARPETA, 'global.ini')) and 'MaxLogs=10' in leer(os.path.join(obs.CARPETA, 'global.ini'))
user = leer(os.path.join(obs.CARPETA, 'user.ini'))
assert user.startswith('[General]\r\nEnableCustomServerVodTrack=true\r\nFirstRun=true') and 'ProfileDir=MiPerfil' in user
assert open(os.path.join(obs.CARPETA, 'user.ini'), 'rb').read().startswith(b'\xef\xbb\xbf'), 'OBS los guarda con BOM'
copia = r['respaldo']
assert sorted(os.listdir(copia)) == ['basic.ini', 'global.ini', 'service.json', 'user.ini']
assert 'live_123' in open(os.path.join(copia, 'service.json')).read(), 'la copia es la de antes'
assert obs.estado(1935)['configurado']

# otra vez: ya no hay clave para rescatar; si no se cierra, avisa
assert obs.configurar(1935, abierto=())['anterior'] is None
try:
    obs.configurar(1935, cerrar_obs=True, abierto=(99, 'x'), cerrar_fn=lambda pid: False)
    raise AssertionError
except ValueError as x:
    assert 'no se cerró' in str(x)

# de dónde sale la clave de antes
assert obs.clave_anterior({'type': 'rtmp_custom', 'settings': {'server': 'rtmps://abc.global-contribute.live-video.net/app', 'key': 'sk_1'}}, 1935)[0] == 'Kick'
assert obs.clave_anterior({'type': 'rtmp_custom', 'settings': {'server': 'rtmp://127.0.0.1:1935/live', 'key': 'stream'}}, 1935) is None
assert obs.clave_anterior({'type': 'rtmp_common', 'settings': {'service': 'YouTube - RTMPS', 'key': 'yt'}}, 1935)[:2] == ('YouTube', 'rtmp://a.rtmp.youtube.com/live2')
assert obs.clave_anterior({'type': 'rtmp_common', 'settings': {'service': 'Twitch', 'key': ''}}, 1935) is None

# el log de OBS dice si está transmitiendo
os.makedirs(os.path.join(obs.CARPETA, 'logs'))
escribir(os.path.join(obs.CARPETA, 'logs', '1.txt'), '==== Streaming Start ====\n==== Streaming Stop ====\n==== Streaming Start ====\n')
assert obs.transmitiendo()

# paneles de OBS: se suman al que ya había, no se repiten, y la dirección queda tal cual
poner = os.path.join(obs.CARPETA, 'user.ini')
obs.poner_ini(poner, 'BasicWindow', 'ExtraBrowserDocks', '[{"title": "Chat", "url": "http://127.0.0.1:8080/chat", "uuid": "a"}]')
r = obs.agregar_dock('Stream Kit', 'http://127.0.0.1:8080/', abierto=())
assert not r['ya_estaba'] and [d['title'] for d in obs.docks()] == ['Chat', 'Stream Kit'] and obs.docks()[1]['url'] == 'http://127.0.0.1:8080/'
assert obs.agregar_dock('Chat', 'http://127.0.0.1:8080/chat', abierto=())['ya_estaba']
assert len(obs.docks()) == 2 and 'ProfileDir=MiPerfil' in leer(poner)
try:
    obs.agregar_dock('Otro', 'http://127.0.0.1:8080/x', abierto=(1, 'x'))
    raise AssertionError('abierto sin permiso')
except ValueError:
    pass
print('ok')
