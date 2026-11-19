# python tests/test_versiones.py: elegir versión, descomprimir seguro y limpiar, sin internet y sin tocar tus datos
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'streamkit'))
import json, os, tempfile, zipfile
os.environ['STREAMKIT_DATOS'] = tempfile.mkdtemp()
import versiones as v

assert v.tupla('0.10.2') > v.tupla('0.9.9') > v.tupla('v0.9') and v.tupla('1.0') == (1, 0)
assert v.objetivo('0.5.0') is None, 'desde el código no hay versiones'
try:
    v.instalar('0.5.0')
    raise AssertionError('instaló desde el código')
except ValueError as e:
    assert 'git pull' in str(e)

# el zip del release: carpeta StreamKit/ adentro; queda en versiones/<versión> con el .exe en la raíz
tmp = tempfile.mkdtemp()
z = os.path.join(tmp, 'r.zip')
with zipfile.ZipFile(z, 'w') as f:
    f.writestr('StreamKit/StreamKit.exe', 'exe')
    f.writestr('StreamKit/_internal/web/inicio.html', 'html')
    f.writestr('StreamKit/version.json', json.dumps({'version': '0.6.0', 'nucleo': 'abc'}))
v.extraer(z, os.path.join(v.CARPETA, '0.6.0'))
assert os.path.exists(v.exe('0.6.0')) and os.path.exists(os.path.join(v.CARPETA, '0.6.0', '_internal', 'web', 'inicio.html'))
assert not os.path.exists(os.path.join(v.CARPETA, '0.6.0.tmp'))
assert v.info(v.exe('0.6.0')) == {'version': '0.6.0', 'nucleo': 'abc'}

# rutas que se salen de la carpeta (zip slip) o un zip sin el programa: no
for nombre in ('../afuera.txt', 'StreamKit/../../afuera.txt'):
    with zipfile.ZipFile(z, 'w') as f:
        f.writestr(nombre, 'x')
    try:
        v.extraer(z, os.path.join(v.CARPETA, 'mala'))
        raise AssertionError(f'aceptó {nombre}')
    except ValueError as e:
        assert 'ruta rara' in str(e)
with zipfile.ZipFile(z, 'w') as f:
    f.writestr('StreamKit/LEEME.md', 'x')
try:
    v.extraer(z, os.path.join(v.CARPETA, 'mala'))
    raise AssertionError('aceptó un zip sin el programa')
except ValueError as e:
    assert 'StreamKit.exe' in str(e)

# con el .exe: la elegida si es más nueva y está entera; si no, el mismo
v.CONGELADO = True
import sys
v.elegir('0.6.0')
assert v.objetivo('0.5.0') == v.exe('0.6.0')
assert v.objetivo('0.6.0') == sys.executable, 'ya es esa: no salta a sí misma'
assert v.objetivo('0.7.0') == sys.executable, 'una más vieja no'
v.elegir('0.6.1')
assert v.objetivo('0.5.0') == sys.executable, 'elegida sin carpeta: sigue la que está'

# mismo núcleo: no hace falta reiniciar la parte que transmite
os.makedirs(os.path.join(v.CARPETA, '0.6.1'))
for ver, nucleo in (('0.6.1', 'abc'),):
    open(v.exe(ver), 'w').write('exe')
    json.dump({'version': ver, 'nucleo': nucleo}, open(os.path.join(v.CARPETA, ver, 'version.json'), 'w'))
assert v.mismo_nucleo(v.exe('0.6.0'), v.exe('0.6.1'))
json.dump({'version': '0.6.1', 'nucleo': 'otro'}, open(os.path.join(v.CARPETA, '0.6.1', 'version.json'), 'w'))
assert not v.mismo_nucleo(v.exe('0.6.0'), v.exe('0.6.1'))
assert not v.mismo_nucleo(sys.executable, v.exe('0.6.1')), 'sin version.json (versiones viejas): se reinicia'

# limpiar: queda la elegida y la que está en uso
open(os.path.join(v.CARPETA, '0.6.1.zip'), 'w').write('a medias')
os.makedirs(os.path.join(v.CARPETA, '0.5.9'))
v.limpiar([v.exe('0.6.0')])
assert sorted(os.listdir(v.CARPETA)) == ['0.6.0', '0.6.1', 'elegida.txt'], os.listdir(v.CARPETA)
print('ok')
