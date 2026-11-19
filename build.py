"""python build.py: arma el .exe en esta PC, sin gastar minutos de GitHub.

Deja dist/StreamKit/ (la carpeta del programa) y dist/StreamKit-<versión>-windows.zip, listo para subir como release:
  gh release create v<versión> dist/StreamKit-<versión>-windows.zip --title "Stream Kit <versión>" --notes "..."
Necesita PyInstaller (python -m pip install pyinstaller) y Node, para armar el panel de ui/.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

from app import VERSION

AQUI = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(AQUI, 'dist')
# lo que va adentro del programa, con la misma forma que en el repo: las pantallas y los recursos
DATOS = [('web', 'web'), ('recursos', 'recursos'), ('llms.txt', '.')]
NUCLEO = ('delay.py', 'rutas.py')  # el núcleo de transmisión: si cambian, actualizar reinicia el núcleo (solo sin stream)


def huella_nucleo():
    h = hashlib.sha256()
    for nombre in NUCLEO:
        with open(os.path.join(AQUI, 'streamkit', nombre), 'rb') as f:
            h.update(f.read().replace(b'\r\n', b'\n'))  # igual con o sin el CRLF que pone git en Windows
    return h.hexdigest()[:16]


def panel():
    """Arma el panel (ui/, React) en web/app, que va adentro del .exe con el resto de web/."""
    ui = os.path.join(AQUI, 'ui')
    npm = shutil.which('npm') or 'npm'
    if not os.path.isdir(os.path.join(ui, 'node_modules')):
        subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=ui, check=True)
    subprocess.run([npm, 'run', 'build'], cwd=ui, check=True)


def main():
    os.chdir(AQUI)
    panel()
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--name', 'StreamKit',
                    '--icon', os.path.join(AQUI, 'recursos', 'icons', 'on.ico'), '--paths', os.path.join(AQUI, 'streamkit'), '--distpath', DIST, '--workpath', os.path.join('build', 'pyinstaller'),
                    '--specpath', 'build', *[f'--add-data={os.path.join(AQUI, origen)}{os.pathsep}{destino}' for origen, destino in DATOS],
                    os.path.join(AQUI, 'app.py')], check=True)
    carpeta = os.path.join(DIST, 'StreamKit')
    shutil.copyfile('README.md', os.path.join(carpeta, 'LEEME.md'))
    shutil.copyfile('LICENSE', os.path.join(carpeta, 'LICENSE.txt'))
    with open(os.path.join(carpeta, 'version.json'), 'w', encoding='utf-8') as f:  # lo lee el guardián al actualizar
        json.dump({'version': VERSION, 'nucleo': huella_nucleo()}, f)
    zip_final = os.path.join(DIST, f'StreamKit-{VERSION}-windows.zip')
    with zipfile.ZipFile(zip_final, 'w', zipfile.ZIP_DEFLATED) as z:
        for raiz, _, archivos in os.walk(carpeta):
            for a in archivos:
                ruta = os.path.join(raiz, a)
                z.write(ruta, os.path.relpath(ruta, DIST))  # adentro del zip queda la carpeta StreamKit/
    print(f'\nListo: {zip_final} ({os.path.getsize(zip_final) // 1024 // 1024} MB)')


if __name__ == '__main__':
    main()
