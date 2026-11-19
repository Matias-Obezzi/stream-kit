"""Dónde está cada cosa.

El programa: el código en streamkit/, las pantallas en web/ y los íconos, el plugin de la botonera y las configs de
ejemplo en recursos/. En el .exe todo eso va adentro.
Los datos del usuario (config, sesiones de Twitch y Kick, chat y logs): desde el código fuente, en datos/; con el .exe,
al lado del .exe, para que sobrevivan a una actualización. --datos=CARPETA (o STREAMKIT_DATOS) los pone en otra carpeta.
"""
import os
import shutil
import sys

CONGELADO = getattr(sys, 'frozen', False)
RAIZ = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(RAIZ, 'web')
RECURSOS = os.path.join(RAIZ, 'recursos')
DATOS = os.environ.get('STREAMKIT_DATOS') or (os.path.dirname(sys.executable) if CONGELADO else os.path.join(RAIZ, 'datos'))
BOT = os.path.join(DATOS, 'bot')  # config del bot, sesiones de Twitch y Kick, chat y logs del bot
os.makedirs(BOT, exist_ok=True)
# puertos locales entre los procesos. Otra base (STREAMKIT_PUERTOS) = otra instalación que no choca con esta, para pruebas
PUERTOS = int(os.environ.get('STREAMKIT_PUERTOS') or 47612)
PUERTO_GUARDIAN, PUERTO_BOT, PUERTO_ORDENES, PUERTO_NUCLEO = PUERTOS, PUERTOS + 1, PUERTOS + 3, PUERTOS + 4  # +2: login de Kick, fijo
CLAVE_NUCLEO = os.path.join(DATOS, 'nucleo.clave')  # la web y el guardián le hablan al núcleo con esto; la crea el núcleo al arrancar


def config(relativa):
    """Ruta de una config. La primera vez la crea copiando su ejemplo de recursos/ejemplos."""
    ruta = os.path.join(DATOS, relativa)
    if not os.path.exists(ruta):
        shutil.copyfile(os.path.join(RECURSOS, 'ejemplos', relativa), ruta)
    return ruta
