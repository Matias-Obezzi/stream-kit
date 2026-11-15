"""Guardián de Stream Kit: arranca el delay y el bot como procesos separados y los vuelve a levantar si se caen.

Es lo único que arranca con Windows. No toca video ni chat: si se cae él, los otros dos siguen andando.
Uso: pythonw app.py    (Salir en la bandeja cierra todo; volver a abrirlo solo abre el panel)
"""
import json
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import time
import webbrowser

from rutas import BOT, CONGELADO, DATOS, PROGRAMA

AQUI = DATOS
ESTADO = os.path.join(AQUI, 'servicios.json')  # lo lee el panel
ERRORES_BOT = os.path.join(BOT, 'error.log')  # lo que el bot no alcanza a anotar en bot.log, como un config.json roto
PANEL = 8080
PUERTO_CANDADO = 47612
PUERTO_BOT = 47613
ESPERA_MAXIMA = 60
log = logging.getLogger('guardian')


def proxima_espera(corrio, anterior):
    """Cuánto esperar antes de relevantarlo: poco si venía andando, cada vez más si se cae apenas arranca."""
    return 1 if corrio >= 60 else min(anterior * 2, ESPERA_MAXIMA)


def puerto_ocupado(puerto):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', puerto)) == 0


def matar_ffmpeg_huerfanos(pid):
    # el que escucha a OBS ocuparía el puerto y el delay nuevo no podría escuchar
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f"Get-CimInstance Win32_Process -Filter \"ParentProcessId={pid} and Name='ffmpeg.exe'\""
                    ' | Invoke-CimMethod -MethodName Terminate'], capture_output=True, creationflags=0x08000000)


class Servicio:
    def __init__(self, nombre):
        self.nombre = nombre
        self.proc = None
        self.inicio = self.proximo = 0.0
        self.espera = 1
        self.reinicios = 0
        self.ultimo_fallo = self.extra = ''

    def puede_arrancar(self):
        # el delay de otra sesión del guardián todavía corriendo: dos pelearían por el puerto de OBS
        return time.monotonic() >= self.proximo and not (self.nombre == 'delay' and puerto_ocupado(PANEL))

    def arrancar(self):
        # el mismo programa con otra opción: el .exe solo, o python con app.py desde el código fuente
        programa = [sys.executable] if CONGELADO else [sys.executable, os.path.join(PROGRAMA, 'app.py')]
        if self.nombre == 'delay':
            self.proc = subprocess.Popen([*programa, '--delay', *self.extra.split()], cwd=AQUI)
        else:
            with open(ERRORES_BOT, 'w', encoding='utf-8') as errores:
                self.proc = subprocess.Popen([*programa, '--bot'], cwd=AQUI, stderr=errores)
        self.inicio = time.monotonic()
        log.info('%s arrancó (pid %s)', self.nombre, self.proc.pid)

    def termino(self, codigo):
        """Anota la caída y agenda el próximo arranque. El bot sale con 0 cuando el panel le pide reiniciarse."""
        pid, corrio = self.proc.pid, time.monotonic() - self.inicio
        self.proc = None
        if self.nombre == 'bot':
            try:  # lo último que publicó ya no vale: la web no tiene que mostrarlo conectado
                os.remove(os.path.join(BOT, 'estado.json'))
            except OSError:
                pass
        if self.nombre == 'bot' and codigo == 0:
            log.info('bot reiniciado a pedido')
            self.espera, self.proximo = 1, 0.0
            return
        self.reinicios += 1
        self.ultimo_fallo = f'{time.strftime("%d/%m %H:%M")}, código {codigo & 0xFFFFFFFF:#x}'
        self.espera = proxima_espera(corrio, self.espera)
        self.proximo = time.monotonic() + self.espera
        log.warning('%s se cayó tras %d s (%s): vuelve en %d s', self.nombre, corrio, self.ultimo_fallo, self.espera)
        if self.nombre == 'delay':
            matar_ffmpeg_huerfanos(pid)
            self.extra = f'--restarted={codigo & 0xFFFFFFFF:#x}'

    def estado(self):
        return {'corriendo': self.proc is not None, 'reinicios': self.reinicios, 'ultimo_fallo': self.ultimo_fallo,
                'pid': self.proc.pid if self.proc else None}  # para /metricas


def publicar(servicios):
    datos = {'actualizado': time.time(), 'pid': os.getpid(), **{s.nombre: s.estado() for s in servicios}}
    try:
        with open(ESTADO + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(datos, f)
        os.replace(ESTADO + '.tmp', ESTADO)
    except OSError:  # el panel justo lo está leyendo: sale en la próxima vuelta
        pass


def correr():
    candado = socket.socket()
    try:
        candado.bind(('127.0.0.1', PUERTO_CANDADO))
    except OSError:
        webbrowser.open(f'http://127.0.0.1:{PANEL}')
        return
    candado.listen(1)

    log.addHandler(logging.handlers.RotatingFileHandler(os.path.join(AQUI, 'guardian.log'), maxBytes=200_000,
                                                        backupCount=1, encoding='utf-8'))
    log.handlers[0].setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.setLevel(logging.INFO)
    log.info('guardián arrancó')

    try:  # un bot de una sesión anterior del guardián: se cierra y queda el nuevo, así no contesta dos veces
        socket.create_connection(('127.0.0.1', PUERTO_BOT), 1).close()
        time.sleep(1)
    except OSError:
        pass

    delay, bot = servicios = Servicio('delay'), Servicio('bot')
    ultimo = 0.0
    while True:
        cambio = False
        for s in servicios:
            try:
                if s.proc is None:
                    if s.puede_arrancar():
                        s.arrancar()
                        cambio = True
                elif (codigo := s.proc.poll()) is not None:
                    if s is delay and codigo == 0:  # Salir en la bandeja: se cierra todo
                        log.info('Salir: cierro todo')
                        if bot.proc:
                            bot.proc.terminate()
                        publicar(())
                        return
                    s.termino(codigo)
                    cambio = True
            except Exception:  # el guardián no se puede caer por un servicio
                log.exception('error con %s', s.nombre)
                s.proc, s.proximo = None, time.monotonic() + ESPERA_MAXIMA
        if cambio or time.monotonic() - ultimo >= 5:
            publicar(servicios)
            ultimo = time.monotonic()
        time.sleep(1)


if __name__ == '__main__':
    correr()
