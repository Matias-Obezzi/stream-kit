"""Guardián de Stream Kit: arranca el núcleo de transmisión, la web y el bot como procesos separados, los vuelve a
levantar si se caen y los pasa a una versión nueva sin cortar el stream.

Es lo único que arranca con Windows. No toca video ni chat: si se cae él, los otros siguen andando.
Versión nueva (la baja la web a datos/versiones y la marca en elegida.txt): la web y el bot se reinician con ella
enseguida. El núcleo, que es el que tiene a OBS y a las plataformas, solo si su código cambió, y recién cuando OBS deja
de transmitir. Mientras tanto sigue el de antes, y el panel avisa que queda pendiente.
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
import urllib.request
import webbrowser

import versiones
from rutas import BOT, CLAVE_NUCLEO, CONGELADO, DATOS, PUERTO_BOT, PUERTO_GUARDIAN, PUERTO_NUCLEO, RAIZ

AQUI = DATOS
ESTADO = os.path.join(AQUI, 'servicios.json')  # lo lee el panel
ERRORES_BOT = os.path.join(BOT, 'error.log')  # lo que el bot no alcanza a anotar en bot.log, como un config.json roto
ESPERA_MAXIMA = 60
SALIR, ACTUALIZAR = 0, 3  # códigos de salida del núcleo: Salir en la bandeja cierra todo; 3, lo pasó a otra versión
log = logging.getLogger('guardian')
PROPIA = ''  # la versión del guardián: la de los servicios que corren con su mismo programa


def proxima_espera(corrio, anterior):
    """Cuánto esperar antes de relevantarlo: poco si venía andando, cada vez más si se cae apenas arranca."""
    return 1 if corrio >= 60 else min(anterior * 2, ESPERA_MAXIMA)


def puerto_ocupado(puerto):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', puerto)) == 0


def puerto_panel():
    try:
        with open(os.path.join(AQUI, 'config.json'), encoding='utf-8') as f:
            return json.load(f).get('panel_port', 8080)
    except (OSError, ValueError):
        return 8080


def matar_ffmpeg_huerfanos(pid):
    # el que escucha a OBS ocuparía el puerto y el núcleo nuevo no podría escuchar
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    f"Get-CimInstance Win32_Process -Filter \"ParentProcessId={pid} and Name='ffmpeg.exe'\""
                    ' | Invoke-CimMethod -MethodName Terminate'], capture_output=True, creationflags=0x08000000)


def al_nucleo(metodo, ruta):
    with open(CLAVE_NUCLEO, encoding='utf-8') as f:
        clave = f.read().strip()
    pedido = urllib.request.Request(f'http://127.0.0.1:{PUERTO_NUCLEO}{ruta}', method=metodo,
                                    data=b'' if metodo == 'POST' else None, headers={'X-Nucleo': clave})
    with urllib.request.urlopen(pedido, timeout=5) as r:
        return json.loads(r.read() or b'{}')


def en_vivo():
    """Si OBS le está mandando al núcleo o el núcleo a alguna plataforma. Sin respuesta, se asume que sí: no se toca."""
    try:
        s = al_nucleo('GET', '/api/state')
        return bool(s.get('obs') or s.get('sending'))
    except (OSError, ValueError):
        return True


class Servicio:
    def __init__(self, nombre):
        self.nombre = nombre  # 'delay' (el núcleo), 'web' o 'bot': también es la opción de app.py
        self.proc = None
        self.programa = None  # el .exe con el que está corriendo (None desde el código fuente)
        self.inicio = self.proximo = 0.0
        self.espera = 1
        self.reinicios = 0
        self.ultimo_fallo = self.extra = ''
        self.reemplazando = False  # lo cerró el guardián para pasarlo a otra versión: no es una caída

    def puede_arrancar(self):
        # uno de otra sesión del guardián todavía corriendo: dos pelearían por el mismo puerto
        puerto = {'delay': PUERTO_NUCLEO, 'web': puerto_panel()}.get(self.nombre)
        return time.monotonic() >= self.proximo and not (puerto and puerto_ocupado(puerto))

    def arrancar(self, exe):
        # el mismo programa con otra opción: el .exe de la versión elegida, o python con app.py desde el código fuente
        programa = [exe] if CONGELADO else [sys.executable, os.path.join(RAIZ, 'app.py')]
        opciones = [f'--{self.nombre}', *self.extra.split()]
        entorno = {**os.environ, 'STREAMKIT_DATOS': DATOS}  # una versión de datos/versiones no tiene los datos al lado
        if self.nombre == 'bot':
            with open(ERRORES_BOT, 'w', encoding='utf-8') as errores:
                self.proc = subprocess.Popen([*programa, *opciones], cwd=AQUI, env=entorno, stderr=errores)
        else:
            self.proc = subprocess.Popen([*programa, *opciones], cwd=AQUI, env=entorno)
        self.programa, self.extra, self.inicio = exe, '', time.monotonic()
        log.info('%s arrancó (pid %s, versión %s)', self.nombre, self.proc.pid, self.version())

    def version(self):
        return versiones.info(self.programa).get('version', PROPIA) if self.programa else PROPIA

    def termino(self, codigo):
        """Anota la caída y agenda el próximo arranque. Si salió a pedido (versión nueva, reinicio del bot), vuelve ya."""
        pid, corrio = self.proc.pid, time.monotonic() - self.inicio
        self.proc = None
        if self.nombre == 'bot':
            try:  # lo último que publicó ya no vale: la web no tiene que mostrarlo conectado
                os.remove(os.path.join(BOT, 'estado.json'))
            except OSError:
                pass
        if self.nombre == 'delay':
            matar_ffmpeg_huerfanos(pid)
        a_pedido = self.reemplazando or (self.nombre == 'bot' and codigo == 0) or (self.nombre == 'delay' and codigo == ACTUALIZAR)
        if a_pedido:
            log.info('%s se reinicia a pedido', self.nombre)
            if self.nombre == 'delay':
                self.extra = '--restarted=actualizacion'
            self.espera, self.proximo, self.reemplazando = 1, 0.0, False
            return
        self.reinicios += 1
        self.ultimo_fallo = f'{time.strftime("%d/%m %H:%M")}, código {codigo & 0xFFFFFFFF:#x}'
        self.espera = proxima_espera(corrio, self.espera)
        self.proximo = time.monotonic() + self.espera
        log.warning('%s se cayó tras %d s (%s): vuelve en %d s', self.nombre, corrio, self.ultimo_fallo, self.espera)
        if self.nombre == 'delay':
            self.extra = f'--restarted={codigo & 0xFFFFFFFF:#x}'

    def estado(self):
        return {'corriendo': self.proc is not None, 'reinicios': self.reinicios, 'ultimo_fallo': self.ultimo_fallo,
                'pid': self.proc.pid if self.proc else None, 'version': self.version()}  # para /metricas e Inicio


def publicar(servicios, propia, pendiente=False):
    datos = {'actualizado': time.time(), 'pid': os.getpid(), **{s.nombre: s.estado() for s in servicios}}
    if 'delay' in datos:
        datos['delay']['pendiente'] = pendiente  # hay un núcleo nuevo esperando a que cortes el stream
    try:
        with open(ESTADO + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(datos, f)
        os.replace(ESTADO + '.tmp', ESTADO)
    except OSError:  # el panel justo lo está leyendo: sale en la próxima vuelta
        pass


def pasar_de_version(s, objetivo):
    """Cierra la web o el bot para que vuelvan con la versión nueva. El núcleo no pasa por acá."""
    s.reemplazando = True
    log.info('%s pasa a %s', s.nombre, versiones.info(objetivo).get('version', objetivo))
    if s.nombre == 'bot':
        try:  # conectarse a su puerto lo cierra bien (guarda lo pendiente); si no contesta, a la fuerza
            socket.create_connection(('127.0.0.1', PUERTO_BOT), 2).close()
            return
        except OSError:
            pass
    s.proc.terminate()


def correr(propia):
    global PROPIA
    PROPIA = propia
    candado = socket.socket()
    try:
        candado.bind(('127.0.0.1', PUERTO_GUARDIAN))
    except OSError:
        webbrowser.open(f'http://127.0.0.1:{puerto_panel()}')
        return
    candado.listen(1)

    log.addHandler(logging.handlers.RotatingFileHandler(os.path.join(AQUI, 'guardian.log'), maxBytes=200_000,
                                                        backupCount=1, encoding='utf-8'))
    log.handlers[0].setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.setLevel(logging.INFO)
    log.info('guardián %s arrancó', propia)

    try:  # un bot de una sesión anterior del guardián: se cierra y queda el nuevo, así no contesta dos veces
        socket.create_connection(('127.0.0.1', PUERTO_BOT), 1).close()
        time.sleep(1)
    except OSError:
        pass
    if not puerto_ocupado(PUERTO_NUCLEO) and not puerto_ocupado(puerto_panel()):  # nada de antes corriendo
        versiones.limpiar([versiones.objetivo(propia)])

    delay, web, bot = servicios = Servicio('delay'), Servicio('web'), Servicio('bot')
    web.extra = '--abrir'  # la primera vez abre el panel; al reiniciarla en vivo, no
    ultimo = ultimo_vivo = 0.0
    pendiente = False
    while True:
        cambio = False
        objetivo = versiones.objetivo(propia)
        for s in servicios:
            try:
                if s.proc is None:
                    if s.puede_arrancar():
                        s.arrancar(objetivo)
                        cambio = True
                elif (codigo := s.proc.poll()) is not None:
                    if s is delay and codigo == SALIR:  # Salir en la bandeja: se cierra todo
                        log.info('Salir: cierro todo')
                        for otro in (web, bot):
                            if otro.proc:
                                otro.proc.terminate()
                        publicar((), propia)
                        return
                    s.termino(codigo)
                    cambio = True
                elif s.programa != objetivo and not s.reemplazando:
                    if s is not delay:
                        pasar_de_version(s, objetivo)
                    elif versiones.mismo_nucleo(s.programa, objetivo):
                        pendiente = False  # el núcleo de antes es igual al nuevo: sigue corriendo como está
                    elif time.monotonic() - ultimo_vivo >= 5:
                        ultimo_vivo = time.monotonic()
                        pendiente = en_vivo()
                        if not pendiente:
                            log.info('núcleo nuevo y sin stream: lo paso a la versión nueva')
                            s.reemplazando = True
                            try:
                                al_nucleo('POST', '/nucleo/salir')
                            except (OSError, ValueError):
                                s.proc.terminate()
                        cambio = True
                elif s is delay:
                    pendiente = False
            except Exception:  # el guardián no se puede caer por un servicio
                log.exception('error con %s', s.nombre)
                s.proc, s.proximo = None, time.monotonic() + ESPERA_MAXIMA
        if cambio or time.monotonic() - ultimo >= 5:
            publicar(servicios, propia, pendiente)
            ultimo = time.monotonic()
        time.sleep(1)


if __name__ == '__main__':
    correr('')
