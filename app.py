"""Stream Kit: delay para OBS, bot de chat, alertas y título en Twitch y Kick.

Es lo que arranca el .exe, y también desde el código fuente:
  pythonw app.py            el guardián: levanta el núcleo, la web y el bot, y los vuelve a levantar si se caen
  python app.py --delay     solo el núcleo de transmisión: OBS, delay y plataformas (lo arranca el guardián)
  python app.py --web       solo la web del panel (lo arranca el guardián)
  python app.py --bot       solo el bot (lo arranca el guardián)
  python app.py --bot --reiniciar   cierra el bot y el guardián lo vuelve a levantar
  python app.py --streamdock        instala el botón del StreamDock (con Stream Kit abierto)
  --datos=CARPETA                   la config, las sesiones y los logs en otra carpeta (si no, al lado del .exe)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'streamkit'))  # el código vive en streamkit/

VERSION = '0.7.4'


def main():
    datos = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--datos=')), None)
    if datos:  # antes de importar rutas; el delay y el bot heredan la variable del guardián
        os.environ['STREAMKIT_DATOS'] = os.path.abspath(datos)
    if '--delay' in sys.argv:
        import delay
        delay.main()
    elif '--web' in sys.argv or '--streamdock' in sys.argv:
        import panel
        panel.main()
    elif '--bot' in sys.argv:
        import chatbot
        chatbot.main()
    else:
        import rutas
        import versiones
        exe = versiones.objetivo(VERSION)
        if exe and exe != sys.executable:  # hay una versión más nueva instalada desde el panel: arranca esa
            import subprocess
            subprocess.Popen([exe, f'--datos={rutas.DATOS}', *[a for a in sys.argv[1:] if not a.startswith('--datos=')]],
                             cwd=os.path.dirname(exe))
            return
        import guardian
        guardian.correr(VERSION)


if __name__ == '__main__':
    main()
