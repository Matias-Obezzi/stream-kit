"""Stream Kit: delay para OBS, bot de chat, alertas y título en Twitch y Kick.

Es lo que arranca el .exe, y también desde el código fuente:
  pythonw app.py            el guardián: levanta el delay y el bot, y los vuelve a levantar si se caen
  python app.py --delay     solo el delay y la web (lo arranca el guardián)
  python app.py --bot       solo el bot (lo arranca el guardián)
  python app.py --bot --reiniciar   cierra el bot y el guardián lo vuelve a levantar
  python app.py --streamdock        instala el botón del StreamDock
"""
import sys

VERSION = '0.1.0'


def main():
    if '--delay' in sys.argv or '--streamdock' in sys.argv:
        import delay
        delay.main()
    elif '--bot' in sys.argv:
        import chatbot
        chatbot.main()
    else:
        import guardian
        guardian.correr()


if __name__ == '__main__':
    main()
