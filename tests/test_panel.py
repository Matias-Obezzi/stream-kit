# python tests/test_panel.py: sin internet y sin tocar el bot real. Prueba qué acepta el panel y cómo espera el guardián
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import os, tempfile
os.environ["STREAMKIT_DATOS"] = tempfile.mkdtemp()  # config de ejemplo en una carpeta aparte: no toca la tuya
import json, os, tempfile
import guardian, panel_bot as p

BASE = {'comandos': {'!redes': {'respuesta': 'Todas en https://ejemplo.com', 'espera': 15}}, 'espera_lista_comandos': 15,
        'timers': [{'texto': 'Hola', 'minutos': 5}], 'banear_frases': ['streamboo'], 'no_banear': ['streamboost']}
def con(**k):
    return {**BASE, **k}
def cmd(respuesta='x', espera=15):
    return {'respuesta': respuesta, 'espera': espera}
def tim(texto='Hola', minutos=5):
    return {'texto': texto, 'minutos': minutos}
def rechaza(**k):
    try:
        p.validar(con(**k))
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')

assert p.validar(con(comandos={' !REDES ': cmd(' hola ', 0)}))['comandos'] == {'!redes': {'respuesta': 'hola', 'espera': 0}}
assert p.validar(con(timers=[]))['timers'] == []
varios = p.validar(con(timers=[tim(' a ', 5), tim('b', 240), tim('a', 1)]))['timers']  # el mismo texto dos veces puede ser a propósito
assert varios == [tim('a', 5), tim('b', 240), tim('a', 1)]
assert set(p.validar(con(extra=1))) == set(BASE), 'lo que no es editable no pasa'
for malo in ({'redes': cmd()}, {'!a b': cmd()}, {'!': cmd()}, {'!comandos': cmd()}, {'!a': cmd('x\r\nPRIVMSG #otro :hola')}, {'!a': cmd('/ban alguien')},
             {'!a': cmd('.ban alguien')}, {'!a': cmd('')}, {'!a': cmd('x' * 501)}, {'!a': cmd(5)}, {'!a': cmd(), '!A': cmd()}, {'!a': 'x'}, {'!a': {'espera': 5}}):
    rechaza(comandos=malo)
assert 'no entra' in rechaza(comandos={f'!{"x" * 28}{i}': cmd('y') for i in range(100)})
for espera in (-1, 3601, 1.5, '5', None, True, float('inf'), float('nan')):
    rechaza(comandos={'!a': cmd(espera=espera)})
    rechaza(espera_lista_comandos=espera)
rechaza(comandos={'!a': {'respuesta': 'x'}})
for minutos in (0, 241, 1.5, '5', None, True, float('inf'), float('nan')):
    rechaza(timers=[tim(minutos=minutos)])
rechaza(timers=[{'texto': 'x'}])
rechaza(timers=[tim('/ban x')])
rechaza(timers=[tim('')])
rechaza(timers=[tim('x\ny')])
rechaza(timers=['hola'])
rechaza(timers='hola')
rechaza(timers=[tim()] * 21)
assert p.validar(con(timers=[tim()] * 20))
# una frase vacía o cortísima banearía a medio chat
for frase in ('...', 'a', 'a b', '', '   '):
    rechaza(banear_frases=[frase])
rechaza(banear_frases='streamboo')
rechaza(no_banear=None)

# guardar: conserva lo que el panel no edita, no toca el archivo si está mal, y sin cambios no reinicia
carpeta = tempfile.mkdtemp()
p.CONFIG = os.path.join(carpeta, 'config.json')
json.dump({**BASE, 'client_id': 'abc', 'kick_pusher_clave': 'def'}, open(p.CONFIG, 'w'))
reinicios = []
p.reiniciar = lambda: reinicios.append(1)
assert p.guardar(con()) is False and not reinicios
assert p.guardar(con(timers=[tim(minutos=7)])) is True and len(reinicios) == 1
guardado = json.load(open(p.CONFIG, encoding='utf-8'))
assert guardado['timers'] == [tim(minutos=7)] and guardado['client_id'] == 'abc' and guardado['kick_pusher_clave'] == 'def'
assert not set(p.leer()) & {'client_id', 'kick_pusher_clave'}
assert p.estado_y_config()['config'] and not p.estado_y_config()['error']
try:
    p.guardar(con(timers=[tim(minutos=0)]))
    raise AssertionError
except ValueError:
    pass
assert json.load(open(p.CONFIG, encoding='utf-8'))['timers'] == [tim(minutos=7)]

# estado: sin archivos o con archivos viejos, caído; si justo no se puede leer, queda lo último
p.ESTADO_BOT, p.SERVICIOS, p.LOG_BOT = (os.path.join(carpeta, n) for n in ('estado.json', 'servicios.json', 'bot.log'))
e = p.estado()
assert not e['bot']['vivo'] and not e['guardian'] and e['bot']['aviso'] == ''
json.dump({'actualizado': p.time.time(), 'twitch': 'conectado', 'kick': 'vencida'}, open(p.ESTADO_BOT, 'w'))
e = p.estado()
assert e['bot']['vivo'] and e['bot']['twitch'] == 'conectado' and e['bot']['kick'] == 'vencida'
open(p.ESTADO_BOT, 'w').write('{a medias')
assert p.estado()['bot']['twitch'] == 'conectado'
json.dump({'actualizado': 1, 'twitch': 'conectado'}, open(p.ESTADO_BOT, 'w'))
assert not p.estado()['bot']['vivo']
open(p.LOG_BOT, 'w', encoding='utf-8').write('2026-11-05 10:00:00,1 INFO hola\n2026-11-05 10:00:01,1 ERROR malo\n2026-11-05 10:00:02,1 INFO chau\n')
assert p.ultimo_aviso().endswith('ERROR malo')

# chat para la web: sin archivo, vacío; sin desde, lo último; con desde, solo lo nuevo
p.EVENTOS_BOT = os.path.join(carpeta, 'eventos.json')
assert p.eventos() == {'eventos': [], 'ultimo': 0} and p.eventos(5) == {'eventos': [], 'ultimo': 0}
json.dump([{'id': i, 'tipo': 'chat'} for i in range(1, 251)], open(p.EVENTOS_BOT, 'w'))
assert len(p.eventos()['eventos']) == 200 and p.eventos()['ultimo'] == 250
assert [e['id'] for e in p.eventos(248)['eventos']] == [249, 250] and p.eventos(250)['eventos'] == []

# config rota: no se puede guardar encima, pero el estado se sigue viendo
crudo = open(p.CONFIG, 'rb').read()
open(p.CONFIG, 'w').write('{ roto')
e = p.estado_y_config()
assert e['config'] is None and e['error'] and 'bot' in e and 'delay' in e
open(p.CONFIG, 'wb').write(crudo)

# acciones del chat: la web revisa el pedido, se lo pasa al bot por su puerto y devuelve el error del bot en palabras
import socket, threading
recibidas, contestar = [], []
falso_bot = socket.create_server(('127.0.0.1', 0))
p.PUERTO_ORDENES = falso_bot.getsockname()[1]
def atender():
    while recibidas is not None:
        try:
            c, _ = falso_bot.accept()
        except OSError:  # la prueba ya lo cerró
            return
        with c:
            recibidas.append(json.loads(c.recv(4096)))
            c.sendall((json.dumps({'error': contestar.pop(0)}) + '\n').encode())
threading.Thread(target=atender, daemon=True).start()
contestar[:] = ['', 'Twitch respondió 400: ya está baneado']
p.accion({'accion': 'timeout', 'plataforma': 'kick', 'uid': 77, 'minutos': 10, 'usuario': 'Ana', 'otra': 'cosa'})
assert recibidas[0] == {'accion': 'timeout', 'plataforma': 'kick', 'usuario': 'Ana', 'uid': '77', 'minutos': 10}, 'solo lo que hace falta'
try:
    p.accion({'accion': 'banear', 'plataforma': 'twitch', 'uid': '42'})
    raise AssertionError('tenía que fallar')
except ValueError as e:
    assert str(e) == 'Twitch respondió 400: ya está baneado'
def rechaza(**k):
    try:
        p.accion(k)
    except ValueError as e:
        return str(e)
    raise AssertionError(f'aceptó {k}')
assert 'inválido' in rechaza(accion='borrar todo', plataforma='twitch', mid='a')
assert 'inválido' in rechaza(accion='banear', plataforma='youtube', uid='1')
assert 'id' in rechaza(accion='borrar', plataforma='twitch', mid='a&b=c')
assert 'id' in rechaza(accion='banear', plataforma='twitch', uid='1; 2')
assert 'id' in rechaza(accion='banear', plataforma='kick')
assert 'Minutos' in rechaza(accion='timeout', plataforma='kick', uid='1', minutos=0)
assert 'Minutos' in rechaza(accion='timeout', plataforma='kick', uid='1', minutos=10081)
assert len(recibidas) == 2, 'lo rechazado no llega al bot'
falso_bot.close()
p.PUERTO_ORDENES = socket.create_server(('127.0.0.1', 0)).getsockname()[1]  # nadie atiende
assert 'no contestó' in rechaza(accion='banear', plataforma='kick', uid='1')

# guardián: si se cae apenas arranca espera cada vez más, hasta un minuto; si venía andando vuelve enseguida
espera = 1
for esperado in (2, 4, 8, 16, 32, 60, 60):
    espera = guardian.proxima_espera(3, espera)
    assert espera == esperado
assert guardian.proxima_espera(600, 60) == 1
print('ok')
