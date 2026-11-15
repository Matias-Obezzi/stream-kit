"""Dónde está cada cosa. Desde el código fuente, todo queda en esta carpeta. En el .exe, las páginas y los íconos
van adentro del programa, y la config, las sesiones y los logs quedan al lado del .exe, para que sobrevivan a una
actualización."""
import os
import shutil
import sys

CONGELADO = getattr(sys, 'frozen', False)
PROGRAMA = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
DATOS = os.environ.get('STREAMKIT_DATOS') or (os.path.dirname(sys.executable) if CONGELADO else PROGRAMA)  # la variable: para las pruebas
BOT = os.path.join(DATOS, 'bot')  # config del bot, sesiones de Twitch y Kick, chat y logs del bot
os.makedirs(BOT, exist_ok=True)


def config(relativa):
    """Ruta de una config. La primera vez la crea copiando su ejemplo (config.json -> config.example.json)."""
    ruta = os.path.join(DATOS, relativa)
    if not os.path.exists(ruta):
        base, ext = os.path.splitext(relativa)
        shutil.copyfile(os.path.join(PROGRAMA, base + '.example' + ext), ruta)
    return ruta
