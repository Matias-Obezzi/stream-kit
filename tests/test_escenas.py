# python tests/test_escenas.py: cuándo se pone el preset de una escena, sin OBS ni internet
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))
import tempfile
_os.environ['STREAMKIT_DATOS'] = tempfile.mkdtemp()  # carpeta aparte: no toca la tuya
import canal, escenas

canal.guardar_json(canal.PRESETS, [{'nombre': 'Ranked', 'titulo': 'ranked', 'idioma': 'es', 'etiquetas': [], 'categorias': {}},
                                   {'nombre': 'Charla', 'titulo': 'charla', 'idioma': 'es', 'etiquetas': [], 'categorias': {}}])
assert escenas.guardar_reglas({'Juego': 'Ranked', 'Chat': 'Charla', 'Pausa': ''}) == {'Juego': 'Ranked', 'Chat': 'Charla'}
try:
    escenas.guardar_reglas({'Juego': 'No existe'})
    raise AssertionError('aceptó un preset que no hay')
except ValueError:
    pass

puestos = []
v = escenas.Vigia(aplicar=lambda e: puestos.append(e) or {'resultado': {}})
v.escena('Juego', 0)
v.tic(10)
assert puestos == []  # sin stream no se toca nada
v.vivo(True, 20)
v.tic(22)
assert puestos == []  # todavía no pasaron 5 s
v.tic(25)
assert puestos == ['Juego']  # al arrancar, la escena en la que estás
v.escena('Chat', 30)
v.escena('Juego', 31)  # pasó de largo por Chat
v.tic(40)
assert puestos == ['Juego']  # y volvió a una con el mismo preset: no se repite
v.escena('Chat', 50)
v.tic(56)
assert puestos == ['Juego', 'Chat']
v.escena('Pausa', 60)
v.tic(70)
assert puestos == ['Juego', 'Chat']  # escena sin preset: queda lo que estaba
v.vivo(False, 80)
v.escena('Juego', 81)
v.tic(90)
assert puestos == ['Juego', 'Chat']  # terminó el stream

# la contraseña, como la pide obs-websocket: base64(sha256(base64(sha256(clave + sal)) + desafío))
import base64, hashlib
s = base64.b64encode(hashlib.sha256(b'clave' + b'sal').digest())
assert escenas.respuesta_auth('clave', 'sal', 'des') == base64.b64encode(hashlib.sha256(s + b'des').digest()).decode()
print('ok')
