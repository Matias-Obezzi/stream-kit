"""La web de Stream Kit (http://127.0.0.1:8080): panel, chat, título, pantallas para OBS, MCP y actualizaciones.

Corre en su propio proceso, separada del núcleo de transmisión (delay.py): así se puede reiniciar o pasar a una versión
nueva en pleno stream. Lo que toca el delay (estado, activar, destinos, vistas previas) se lo pide al núcleo por su API
local con la clave de nucleo.clave. La config la escribe solo el núcleo: acá se lee.
Uso: python app.py --web   (lo arranca el guardián)
"""
import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

import canal
import cuentas
import deck
import mcp
import metricas
import obs
import panel_bot
import pantallas
import versiones
from delay import UPLOAD_EXT, VIDEOS, lan_ip
from rutas import CLAVE_NUCLEO, PUERTO_NUCLEO, RAIZ, RECURSOS, WEB, config as ruta_config

CONFIG = ruta_config('config.json')
PAGINAS = ('/', '/delay', '/chat', '/canal', '/pantallas', '/bot', '/metricas', '/config')  # las de ui/src/rutas.tsx
TIPOS = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml',
         '.woff2': 'font/woff2', '.png': 'image/png', '.webp': 'image/webp'}
NUCLEO_CAIDO = {'error': 'El núcleo de transmisión no contesta: si se cayó, el guardián lo levanta en unos segundos.'}
_cfg = {}


def version():
    return getattr(sys.modules.get('__main__'), 'VERSION', '')


def leer_cfg():
    """La config del núcleo. Si justo no se puede leer, la última que se leyó."""
    try:
        with open(CONFIG, encoding='utf-8') as f:
            _cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return _cfg


def al_nucleo(metodo, ruta, cuerpo=None):
    """(código, tipo, cuerpo) de lo que contesta el núcleo. Si no contesta (se está reiniciando o se cayó), 503."""
    try:
        with open(CLAVE_NUCLEO, encoding='utf-8') as f:
            clave = f.read().strip()
        pedido = urllib.request.Request(f'http://127.0.0.1:{PUERTO_NUCLEO}{ruta}', method=metodo,
                                        data=cuerpo if cuerpo is not None or metodo == 'GET' else b'',
                                        headers={'X-Nucleo': clave, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(pedido, timeout=15) as r:
            return r.status, r.headers.get('Content-Type', 'application/json'), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Content-Type', 'application/json'), e.read()
    except OSError:
        return 503, 'application/json', json.dumps(NUCLEO_CAIDO).encode()


def estado_nucleo():
    codigo, _, cuerpo = al_nucleo('GET', '/api/state')
    return json.loads(cuerpo) if codigo == 200 else None


def install_streamdock(port):
    """El botón de delay en Stream Deck o StreamDock, con una clave propia: así ninguna página web puede tocar el delay."""
    codigo, _, cuerpo = al_nucleo('POST', '/nucleo/deck_token')
    if codigo != 200:
        raise ValueError(NUCLEO_CAIDO['error'])
    hechas = deck.instalar(os.path.join(RECURSOS, 'streamdock'), f'http://127.0.0.1:{port}', json.loads(cuerpo)['token'])
    print('Botón instalado en: ' + (', '.join(h['nombre'] for h in hechas) or 'ninguna botonera (no encontré Stream Deck ni StreamDock)'))
    return hechas


def panel():
    cfg = leer_cfg()
    port, lan = cfg.get('panel_port', 8080), cfg.get('panel_lan', False)
    medidor = metricas.Medidor()

    def partes():
        """Cada proceso de Stream Kit, con lo que hace: el guardián levanta el núcleo, la web y el bot; los ffmpeg son del núcleo."""
        servicios = panel_bot.leer_json(panel_bot.SERVICIOS)
        lista = [('Guardián', 'Levanta el núcleo, la web y el bot, y los vuelve a levantar si se caen', servicios.get('pid'), None),
                 ('Web', 'Sirve este panel, el chat, las pantallas para OBS y el MCP', os.getpid(), None),
                 ('Bot', 'Chats de Twitch y Kick, comandos, alertas y moderación', servicios.get('bot', {}).get('pid'), None)]
        codigo, _, cuerpo = al_nucleo('GET', '/nucleo/partes')
        return lista + ([tuple(p) for p in json.loads(cuerpo)] if codigo == 200 else [])

    def version_info():
        servicios = panel_bot.leer_json(panel_bot.SERVICIOS)
        r = {'actual': version(), 'congelado': versiones.CONGELADO, 'descarga': versiones.descarga,
             'servicios': {k: servicios.get(k, {}).get('version', '') for k in ('delay', 'web', 'bot')},
             'nucleo_pendiente': servicios.get('delay', {}).get('pendiente', False)}
        try:
            r['ultima'] = versiones.ultima() if versiones.CONGELADO else None
        except (OSError, ValueError, KeyError) as e:
            r['error'] = f'No pude ver si hay versión nueva: {e}'
        return r

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def local(self):
            return self.client_address[0] == '127.0.0.1'

        def allowed(self):
            """Desde esta PC siempre; desde el celular, con la clave del link (queda en una cookie)."""
            # Host: una página web con un dominio que apunte a esta IP (DNS rebinding) no puede usar el panel
            if self.headers.get('Host', '').rsplit(':', 1)[0] not in ('127.0.0.1', 'localhost', lan_ip()):
                return False
            if self.local():
                return True
            m = re.search(r'(?:^|;\s*)k=([\w-]+)', self.headers.get('Cookie', ''))
            clave = leer_cfg().get('lan_key', '')
            return lan and bool(m) and bool(clave) and secrets.compare_digest(m[1], clave)

        def reply(self, code, body=b'', ctype='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            # el botón de StreamDock y las alertas de OBS (archivos locales) corren en otra página. El chat es público igual
            if self.path.startswith(('/api/deck', '/api/eventos')):
                self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)

        def nucleo(self, metodo, ruta, cuerpo=None):
            codigo, tipo, cuerpo = al_nucleo(metodo, ruta, cuerpo)
            return self.reply(codigo, cuerpo, tipo)

        def page(self, name, ctype='text/html; charset=utf-8'):
            try:
                with open(os.path.join(WEB, name), 'rb') as f:
                    return self.reply(200, f.read(), ctype)
            except FileNotFoundError:  # desde el código sin armar el panel
                return self.reply(500, 'Falta armar el panel: en ui/, npm install y npm run build.'.encode(), 'text/plain; charset=utf-8')

        def error(self, msg):
            return self.reply(400, json.dumps({'error': msg}).encode())

        def mcp(self):
            """MCP para agentes de IA (ver mcp.py). Solo desde esta PC, y nunca desde una página web: el navegador manda
            Origin, y JSON obliga a pedir permiso antes (CORS), que acá no se da."""
            origen = self.headers.get('Origin')
            if not self.local() or (origen and origen not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}')):
                return self.reply(403)
            if not (self.headers.get('Content-Type') or '').startswith('application/json'):
                return self.reply(415)
            size = int(self.headers.get('Content-Length') or 0)
            try:
                mensaje = json.loads(self.rfile.read(size) if 0 < size <= 1 << 20 else b'')
            except ValueError:
                return self.reply(400, json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'JSON roto.'}}).encode())
            respuesta = mcp.atender(mensaje, port, version())
            return self.reply(202) if respuesta is None else self.reply(200, json.dumps(respuesta, ensure_ascii=False).encode())

        def do_GET(self):
            path, _, query = self.path.partition('?')
            clave = leer_cfg().get('lan_key', '')
            if path == '/' and lan and query.startswith('k='):  # link del celular: guarda la clave y la saca de la URL
                if not clave or not secrets.compare_digest(unquote(query[2:]), clave):
                    return self.reply(403, 'Link viejo o incompleto: copiá el de nuevo del panel en la PC.'.encode(),
                                      'text/plain; charset=utf-8')
                self.send_response(303)
                self.send_header('Set-Cookie', f'k={clave}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000')
                self.send_header('Location', '/')
                return self.end_headers()
            if not self.allowed():
                return self.reply(403, 'Abrí el link que muestra el panel en la PC.'.encode(), 'text/plain; charset=utf-8')
            if path == '/mcp':  # el MCP solo habla por POST
                self.send_response(405)
                self.send_header('Allow', 'POST')
                self.send_header('Content-Length', '0')
                return self.end_headers()
            if re.fullmatch(r'/pantalla/[a-z0-9]{1,16}', path):  # lo que muestra OBS
                return self.page('pantalla.html')
            if path == '/api/pantallas':
                return self.reply(200, json.dumps(pantallas.leer()).encode())
            if path == '/api/pantallas/datos':
                return self.reply(200, json.dumps(pantallas.datos()).encode())
            if path in ('/config', '/api/config') and not self.local():  # claves y sesiones: solo desde esta PC
                return self.reply(403, 'La configuración solo se abre desde la PC.'.encode(), 'text/plain; charset=utf-8')
            if path in PAGINAS:  # el panel (ui/, armado en web/app): la misma página para todas, la ruta la resuelve ella
                return self.page(os.path.join('app', 'index.html'))
            if re.fullmatch(r'/assets/[A-Za-z0-9_.-]+', path):  # con hash en el nombre: no cambian nunca
                tipo = TIPOS.get(os.path.splitext(path)[1])
                if tipo and os.path.isfile(archivo := os.path.join(WEB, 'app', path.lstrip('/'))):
                    with open(archivo, 'rb') as f:
                        return self.reply(200, f.read(), tipo)
                return self.reply(404)
            if path == '/api/config':
                return self.reply(200, json.dumps(cuentas.leer()).encode())
            if path == '/api/botonera':
                return self.reply(200, json.dumps(deck.apps()).encode())
            if path == '/api/obs':
                if not self.local():
                    return self.reply(403)
                urls = [d.get('url') for d in obs.docks()]
                s = estado_nucleo() or {}
                return self.reply(200, json.dumps({**obs.estado(leer_cfg()['listen_port']), 'a_la_app': bool(s.get('obs')),
                                                   'dock_panel': f'http://127.0.0.1:{port}/' in urls,
                                                   'dock_chat': f'http://127.0.0.1:{port}/chat' in urls}).encode())
            if path == '/api/canal':
                return self.reply(200, json.dumps(canal.leer()).encode())
            if path == '/api/canal/presets':
                return self.reply(200, json.dumps(canal.presets()).encode())
            if path == '/api/canal/buscar':
                return self.reply(200, json.dumps(canal.buscar(unquote(query[2:]) if query.startswith('q=') else '')).encode())
            if path == '/api/eventos':
                desde = query[6:] if query.startswith('desde=') else ''
                if desde and not desde.isdigit():
                    return self.error('desde tiene que ser un número.')
                return self.reply(200, json.dumps(panel_bot.eventos(int(desde) if desde else None)).encode())
            if path == '/llms.txt':  # la guía para agentes de IA, con la lista de piezas al día
                with open(os.path.join(RAIZ, 'llms.txt'), encoding='utf-8') as f:
                    return self.reply(200, (f.read() + pantallas.referencia()).encode(), 'text/markdown; charset=utf-8')
            if path in ('/plataformas.js', '/emotes.js'):
                return self.page(path[1:], 'text/javascript; charset=utf-8')
            if path == '/piezas.js':  # con su esquema adelante: así carga de una vez, sin pedir otro archivo
                with open(os.path.join(WEB, 'piezas.json'), 'rb') as f, open(os.path.join(WEB, 'piezas.js'), 'rb') as g:
                    return self.reply(200, b'window.PIEZAS_ESQUEMA = ' + f.read() + b';\n' + g.read(), 'text/javascript; charset=utf-8')
            if path == '/api/chat/quienes':
                try:
                    return self.reply(200, json.dumps(panel_bot.quienes()).encode())
                except ValueError as e:
                    return self.error(str(e))
            if path == '/api/bot':
                return self.reply(200, json.dumps(panel_bot.estado_y_config()).encode())
            if path == '/api/state':
                s = estado_nucleo()
                if s is None:
                    return self.reply(503, json.dumps(NUCLEO_CAIDO).encode())
                if lan and self.local() and clave:  # la clave solo se le muestra a la PC
                    s['phone'] = f'http://{lan_ip()}:{port}/?k={clave}'
                return self.reply(200, json.dumps(s).encode())
            if path == '/api/version':
                return self.reply(200, json.dumps(version_info()).encode())
            if path == '/api/metricas':
                return self.reply(200, json.dumps(medidor.medir(partes())).encode())
            if path in ('/api/deck', '/snap/in.jpg', '/snap/out.jpg', '/api/red/historial'):
                return self.nucleo('GET', path)
            self.reply(404)

        def do_POST(self):
            path, _, query = self.path.partition('?')
            if not self.allowed():
                return self.reply(403)
            if path == '/api/deck/toggle':  # botón de StreamDock: la clave la revisa el núcleo
                return self.nucleo('POST', self.path)
            if path == '/mcp':
                return self.mcp()
            # header propio: una página web cualquiera no puede mandarlo sin permiso (CORS), así no maneja el panel
            if self.headers.get('X-Panel') != '1':
                return self.reply(403)
            size = int(self.headers.get('Content-Length') or 0)
            if path in ('/api/delay', '/api/live', '/api/red/prueba'):
                return self.nucleo('POST', path)
            if path == '/api/upload':
                name = os.path.basename(unquote(query))
                if not name.lower().endswith(UPLOAD_EXT):
                    return self.error('Formato no soportado.')
                os.makedirs(VIDEOS, exist_ok=True)
                with open(os.path.join(VIDEOS, name), 'wb') as f:
                    while size:
                        chunk = self.rfile.read(min(size, 1 << 20))
                        if not chunk:
                            break
                        f.write(chunk)
                        size -= len(chunk)
                return self.reply(200, json.dumps({'name': name}).encode())
            cuerpo = self.rfile.read(size) or b'{}'
            if path == '/api/settings' or path.startswith('/api/destinations/'):
                return self.nucleo('POST', path, cuerpo)
            try:
                s = json.loads(cuerpo)
            except ValueError:
                return self.error('Pedido inválido.')
            if path == '/api/actualizar':
                if not self.local():
                    return self.reply(403)
                try:
                    versiones.instalar(version())
                    return self.reply(200, json.dumps(versiones.descarga).encode())
                except (OSError, ValueError, KeyError) as e:
                    return self.error(str(e))
            if path == '/api/bot/guardar':
                try:
                    return self.reply(200, json.dumps({'cambio': panel_bot.guardar(s)}).encode())
                except (OSError, ValueError) as e:
                    return self.error(str(e))
            if path == '/api/canal/guardar':
                try:
                    return self.reply(200, json.dumps(canal.guardar(s)).encode())
                except ValueError as e:
                    return self.error(str(e))
            if path in ('/api/canal/presets/guardar', '/api/canal/presets/borrar'):
                try:
                    if path.endswith('borrar'):
                        canal.borrar_preset(s.get('nombre'))
                    else:
                        canal.guardar_preset(s)
                    return self.reply(200, json.dumps(canal.presets()).encode())
                except (OSError, ValueError) as e:
                    return self.error(str(e))
            if path in ('/api/pantallas/guardar', '/api/pantallas/borrar'):
                try:
                    if path.endswith('borrar'):
                        pantallas.borrar(s.get('id'))
                        return self.reply(200, b'{}')
                    return self.reply(200, json.dumps(pantallas.guardar(s)).encode())
                except ValueError as e:
                    return self.error(str(e))
            if path == '/api/chat/accion':
                try:
                    panel_bot.accion(s)
                    return self.reply(200, b'{}')
                except ValueError as e:
                    return self.error(str(e))
            if path == '/api/bot/reiniciar':
                panel_bot.reiniciar()
                return self.reply(200, b'{}')
            if path in ('/api/botonera/instalar', '/api/obs/dock'):
                if not self.local():
                    return self.reply(403)
                try:
                    if path == '/api/botonera/instalar':
                        return self.reply(200, json.dumps(install_streamdock(port)).encode())
                    dock = {'panel': ('Stream Kit', f'http://127.0.0.1:{port}/'), 'chat': ('Chat', f'http://127.0.0.1:{port}/chat')}.get(s.get('cual'))
                    if not dock:
                        return self.error('Pedido inválido.')
                    return self.reply(200, json.dumps(obs.agregar_dock(*dock, cerrar_obs=bool(s.get('cerrar')))).encode())
                except (OSError, ValueError) as e:
                    return self.error(str(e))
            if path == '/api/obs/configurar':
                if not self.local():
                    return self.reply(403)
                try:
                    r = obs.configurar(leer_cfg()['listen_port'], cerrar_obs=bool(s.get('cerrar')))
                except (OSError, ValueError) as e:
                    return self.error(str(e))
                anterior, r['anterior'] = r['anterior'], None  # la clave no vuelve a la página
                if anterior and not any(d['url'] == anterior[1] for d in leer_cfg().get('destinations', [])):
                    nuevo = json.dumps({'name': anterior[0], 'url': anterior[1], 'key': anterior[2]}).encode()
                    if al_nucleo('POST', '/api/destinations/add', nuevo)[0] == 200:
                        r['importado'] = anterior[0]
                return self.reply(200, json.dumps(r).encode())
            if path in ('/api/config/guardar', '/api/config/conectar'):
                if not self.local():
                    return self.reply(403)
                try:
                    if path.endswith('guardar'):
                        cuentas.guardar(s)
                        return self.reply(200, json.dumps(cuentas.leer()).encode())
                    return self.reply(200, json.dumps(cuentas.empezar(s.get('tipo'))).encode())
                except (OSError, ValueError) as e:
                    return self.error(str(e))
            self.reply(404)

    servidor = ThreadingHTTPServer(('0.0.0.0' if lan else '127.0.0.1', port), Handler)
    if '--abrir' in sys.argv and cfg.get('open_panel', True):  # solo la primera vez: no al reiniciarla en pleno stream
        threading.Timer(1, webbrowser.open, (f'http://127.0.0.1:{port}',)).start()
    print(f'Web en http://127.0.0.1:{port}', flush=True)
    servidor.serve_forever()


def main():
    if sys.stdout is None:  # pythonw: los errores al archivo
        sys.stdout = sys.stderr = open(os.path.join(os.path.dirname(CONFIG), 'web.log'), 'w', encoding='utf-8', buffering=1)
    if '--streamdock' in sys.argv:
        return install_streamdock(leer_cfg().get('panel_port', 8080))
    panel()


if __name__ == '__main__':
    main()
