# python tests/test_metricas.py: el cálculo de /metricas con mediciones inventadas, y una lectura real de este mismo proceso
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import os
import metricas as m

reloj, procesos = [0.0], {}
pc = [((0.0, 0.0), (4e9, 16e9))]
md = m.Medidor(leer=lambda pid: procesos.get(pid), leer_pc=lambda: pc[0], reloj=lambda: reloj[0])
m.NUCLEOS = 4
PARTES = [('Bot', '', 10, None), ('Envío a Twitch', '', 20, 0), ('Caído', '', 30, None), ('Sin pid', '', None, None)]

# primera vuelta: memoria sí, porcentajes todavía no; lo que no corre no aparece
procesos.update({10: (1.0, 50e6), 20: (5.0, 80e6)})
r = md.medir(PARTES)
assert [f['nombre'] for f in r['partes']] == ['Bot', 'Envío a Twitch'] and r['partes'][0]['cpu'] is None
assert r['total'] == {'cpu': None, 'ram': 130e6} and r['pc']['cpu'] is None

# 2 s después: el bot usó 0,4 s de CPU (5 % de 4 núcleos) y Twitch mandó 2 MB (8000 kbps)
reloj[0] = 2.0
procesos.update({10: (1.4, 52e6), 20: (7.0, 80e6)})
pc[0] = ((6.0, 8.0), (5e9, 16e9))  # en 8 s de núcleos, 6 ociosos: 25 % de la PC
PARTES[1] = ('Envío a Twitch', '', 20, 2_000_000)
r = md.medir(PARTES)
bot, tw = r['partes']
assert bot['cpu'] == 5.0 and bot['ram'] == 52e6 and bot['kbps'] is None
assert tw['cpu'] == 25.0 and tw['kbps'] == 8000
assert r['total']['cpu'] == 30.0 and r['pc'] == {'cpu': 25.0, 'ram': 5e9, 'ram_total': 16e9}

# un proceso nuevo con el mismo nombre (se reconectó a Twitch): su contador vuelve a 0 y no da negativo
reloj[0] = 4.0
procesos.update({20: (0.1, 70e6)})
PARTES[1] = ('Envío a Twitch', '', 20, 10)
r = md.medir(PARTES)
assert r['partes'][1]['cpu'] is None and r['partes'][1]['kbps'] is None

# de verdad, con este proceso: Windows contesta CPU y memoria
real = m.proceso(os.getpid())
assert real and real[0] > 0 and real[1] > 1e6
(ocioso, total), (usada, ram_total) = m.pc()
assert 0 < ocioso <= total and 0 < usada < ram_total
assert m.proceso(0xFFFFFFF0) is None, 'un proceso que no existe no rompe nada'
print('ok')
