# El bot de Stream Kit: mensajes cada X minutos mientras hay stream, comandos y ban a los bots de publicidad, en Twitch y Kick.
# Lo que dice y qué banea está en bot/config.json, y se edita en la web (/bot). Las cuentas se conectan en /config.
# Sin dependencias y sin navegador: un socket a cada chat, dormido hasta que llega un mensaje.
# python app.py --bot              lo arranca (lo hace el guardián, guardian.py, que también lo levanta si se cae)
# python app.py --bot --reiniciar  lo cierra y el guardián lo vuelve a levantar
import base64, collections, datetime, json, logging, logging.handlers, os, re, socket, ssl, sys, threading, time, unicodedata, urllib.error, urllib.parse, urllib.request

from cuentas import ALCANCES  # los permisos que pide el login de /config
from rutas import BOT as AQUI, config as ruta_config

CONFIG = json.load(open(ruta_config(os.path.join("bot", "config.json")), encoding="utf-8"))
TOKEN = os.path.join(AQUI, "token.json")  # no compartir: con esto se puede escribir y banear en el canal
BOT, CANAL, CLIENTE = CONFIG["bot"].lower(), CONFIG["canal"].lower(), CONFIG["client_id"]
TOKEN_KICK = os.path.join(AQUI, "token-kick.json")  # no compartir: además de la sesión, tiene la clave secreta de la app de Kick
KICK_BOT = CONFIG["kick_bot"].lower()
KICK_CANAL = CONFIG.get("kick_canal_slug", "").lower()
kick = {"activo": False, "estado": "sin conectar", "candado": threading.RLock()}  # el candado evita dos refrescos de sesión a la vez: el del timer y el del chat
twitch = {"activo": False, "estado": "sin conectar"}
follows = {"activo": False, "estado": "sin conectar"}  # los follows de Twitch no pasan por el chat: van por EventSub
candado_twitch = threading.Lock()  # el refresh token es de un solo uso: el chat y los follows no pueden refrescar a la vez
ESTADO = os.path.join(AQUI, "estado.json")  # lo lee el panel; "actualizado" viejo quiere decir que el bot no está corriendo
EVENTOS = os.path.join(AQUI, "eventos.json")  # lo lee la web: lo último del chat y las alertas, para la vista de chat y alertas.html
eventos = {"lista": collections.deque(maxlen=300), "ultimo": 0, "sucio": False, "candado": threading.Lock()}
EVENTSUB = "eventsub.wss.twitch.tv"
seguidores = set()  # seguir, dejar y volver a seguir no repite la alerta
IRC, PUERTO_IRC = "irc.chat.twitch.tv", 6697
PUERTO_CANDADO = 47613  # que no corran dos a la vez: duplicarían cada respuesta. También es por donde se lo reinicia
PUERTO_ORDENES = 47615  # la vista de chat manda por acá borrar, timeout y ban: las sesiones de moderador las tiene el bot
ids_twitch = {}  # tu canal y el bot, por nombre: los llena sesion()
log = logging.getLogger("chatbot")

# letras cirílicas y números que los spammers usan para esquivar filtros
PARECIDAS = str.maketrans("асеорхуіѕј" "013457" "@$", "aceopxyisj" "oieast" "as")
LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|net|org|gg|tv|ru|xyz|top|link|shop|store|site|online|me|io|ly)\b", re.I)
INMUNES = {"broadcaster", "moderator", "vip", "subscriber"}
MANDAN = {"broadcaster", "moderator"}  # los que pueden usar !clip


def limpiar(texto):
    texto = unicodedata.normalize("NFKD", texto).casefold().translate(PARECIDAS)
    texto = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", texto))
    # los signos se ignoran (stream.boo) y las letras sueltas se juntan (s t r e a m), pero los espacios entre palabras quedan: "buen stream, boo" no es spam
    return re.sub(r"(?<=\b\w) (?=\w\b)", "", texto)


def parsear(linea):
    m = re.match(r"@(\S+) :(\w+)!\S+ PRIVMSG #\w+ :(.*)", linea)
    if not m:
        return None
    tags = dict(t.partition("=")[::2] for t in m[1].split(";"))
    insignias = {i.split("/")[0] for i in tags.get("badges", "").split(",")}
    return {"usuario": m[2].lower(), "texto": m[3], "id": tags.get("id"), "user_id": tags.get("user-id"),
            "primero": tags.get("first-msg") == "1", "inmune": bool(insignias & INMUNES) or tags.get("mod") == "1",
            "manda": bool(insignias & MANDAN) or tags.get("mod") == "1",
            "nombre": tags.get("display-name") or m[2], "color": tags.get("color", ""), "bits": int(tags.get("bits") or 0),
            "emotes": tags.get("emotes", "")}  # dónde hay emotes de Twitch en el texto: id:inicio-fin,.../otro_id:...


NIVELES = {"1000": "1", "2000": "2", "3000": "3", "Prime": "Prime"}


def parsear_aviso(linea):
    """Subs, regalos y raids de Twitch: llegan al chat como USERNOTICE. Devuelve el evento o None."""
    m = re.match(r"@(\S+) :tmi\.twitch\.tv USERNOTICE #\w+(?: :(.*))?$", linea)
    if not m:
        return None
    t = dict(x.partition("=")[::2] for x in m[1].split(";"))
    quien, clase, numero = t.get("display-name") or t.get("login", ""), t.get("msg-id"), lambda k: int(t.get(k) or 0)
    if clase == "sub":
        return {"tipo": "sub", "usuario": quien, "nivel": NIVELES.get(t.get("msg-param-sub-plan"), "")}
    if clase == "resub":
        return {"tipo": "resub", "usuario": quien, "cantidad": numero("msg-param-cumulative-months"), "mensaje": m[2] or "", "emotes": t.get("emotes", "")}
    if clase == "submysterygift":
        return {"tipo": "regalo", "usuario": quien, "cantidad": numero("msg-param-mass-gift-count")}
    if clase == "subgift" and not t.get("msg-param-community-gift-id"):  # las de un regalo grupal ya salieron en su submysterygift
        return {"tipo": "regalo", "usuario": quien, "cantidad": 1}
    if clase == "raid":
        return {"tipo": "raid", "usuario": t.get("msg-param-displayName") or quien, "cantidad": numero("msg-param-viewerCount")}
    return None


def emitir(**evento):
    """Suma algo al chat de la web. El id crece siempre, aunque el bot se reinicie: así la web pide solo lo nuevo."""
    with eventos["candado"]:
        evento.update(id=max(eventos["ultimo"] + 1, time.time_ns() // 1000), t=round(time.time(), 1))
        if evento.get("tipo") == "chat":
            escribieron.setdefault(evento.get("plataforma"), {})[evento.get("usuario")] = evento["t"]
        eventos["ultimo"] = evento["id"]
        eventos["lista"].append(evento)
        eventos["sucio"] = True


def publicar_eventos():
    with eventos["candado"]:
        if not eventos["sucio"]:
            return
        datos, eventos["sucio"] = list(eventos["lista"]), False
    try:
        guardar_json(EVENTOS, datos)
    except OSError:  # la web justo lo está leyendo: sale en la próxima vuelta
        eventos["sucio"] = True


def cargar_eventos():
    try:
        with open(EVENTOS, encoding="utf-8") as f:
            viejos = json.load(f)
        eventos["lista"].extend(viejos)
        for e in viejos:  # quién escribió en este stream sigue aunque el bot se reinicie
            if e.get("tipo") == "chat":
                escribieron.setdefault(e.get("plataforma"), {})[e.get("usuario")] = e.get("t", 0)
        eventos["ultimo"] = viejos[-1]["id"] if viejos else 0
    except (OSError, ValueError, KeyError, IndexError, TypeError):  # sin historial no pasa nada: el chat arranca vacío
        pass


enviados = collections.deque(maxlen=30)  # lo último que dijo el bot en Kick: Kick se lo devuelve por el chat


def es_el_bot(m):
    """Lo que dijo el propio bot, para no contestarse. Con una cuenta aparte, todo lo de esa cuenta. Con la tuya, solo lo
    que mandó él: lo demás lo escribiste vos y tus comandos tienen que andar. Twitch no le devuelve al bot lo que dice."""
    if m["usuario"] == BOT and BOT != CANAL:
        return True
    return m["usuario"] == KICK_BOT and (KICK_BOT != KICK_CANAL or m["texto"] in enviados)


def decidir(m, ahora, usos):
    """Devuelve ("banear", None), ("borrar", None), ("clip", None), ("responder", texto) o None. Nunca repite texto del chat en la respuesta."""
    if es_el_bot(m):
        return None
    if not m["inmune"]:
        limpio = limpiar(m["texto"])
        for permitida in CONFIG["no_banear"]:
            limpio = limpio.replace(limpiar(permitida), "")
        if any((frase := limpiar(f)) and frase in limpio for f in CONFIG["banear_frases"]):  # una frase vacía estaría en todos los mensajes
            return ("banear", None)
        if m["primero"] and LINK.search(m["texto"]):  # un link como primer mensaje se borra sin ban: puede ser un espectador real
            return ("borrar", None)
    partes = m["texto"].split(maxsplit=1)
    comando = partes[0].lower() if partes else ""
    if comando == "!clip":  # vos y los mods, cada 30 s: un clip es de Twitch aunque se pida desde Kick
        if not m.get("manda") or ahora - usos.get(comando, -1e9) < 30:
            return None
        usos[comando] = ahora
        return ("clip", None)
    if comando == "!comandos":
        texto, espera = "Comandos: " + " ".join(CONFIG["comandos"]), CONFIG["espera_lista_comandos"]
    elif comando in CONFIG["comandos"]:
        texto, espera = CONFIG["comandos"][comando]["respuesta"], CONFIG["comandos"][comando]["espera"]
    else:
        return None
    if ahora - usos.get(comando, -1e9) < espera:
        return None
    usos[comando] = ahora
    return ("responder", texto)


def pedir(url, cuerpo=None, metodo=None, cabeceras=None):
    pedido = urllib.request.Request(url, data=cuerpo, method=metodo, headers={"User-Agent": "StreamKit", **(cabeceras or {})})
    with urllib.request.urlopen(pedido, timeout=15) as r:
        datos = r.read()
    return json.loads(datos) if datos else {}


def oauth(ruta, **campos):
    return pedir("https://id.twitch.tv/oauth2/" + ruta, urllib.parse.urlencode(campos).encode())


def guardar_json(ruta, datos):
    # el refresh token es de un solo uso: si este archivo queda a medias, hay que hacer el login de nuevo
    with open(ruta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(ruta + ".tmp", ruta)


def guardar_token(t):  # lo demás (la cuenta, su id) queda como estaba
    guardar_json(TOKEN, {**leer_token(), "access_token": t["access_token"], "refresh_token": t["refresh_token"]})


def leer_token():
    return json.load(open(TOKEN, encoding="utf-8"))




def refrescar():
    with candado_twitch:
        try:
            t = oauth("token", client_id=CLIENTE, grant_type="refresh_token", refresh_token=leer_token()["refresh_token"])
        except urllib.error.HTTPError as e:
            if e.code in (400, 401):  # solo se apaga Twitch, y reiniciar no lo arregla: Kick sigue
                twitch.update(activo=False, estado="vencida")
                log.error("Twitch rechazó la sesión del bot: volvé a conectarla en Configuración")
            raise
        guardar_token(t)


def helix(metodo, ruta, cuerpo=None, reintento=True):
    cabeceras = {"Authorization": "Bearer " + leer_token()["access_token"], "Client-Id": CLIENTE}
    if cuerpo:
        cabeceras["Content-Type"] = "application/json"
    try:
        return pedir("https://api.twitch.tv/helix/" + ruta, json.dumps(cuerpo).encode() if cuerpo else None, metodo, cabeceras)
    except urllib.error.HTTPError as e:
        if e.code == 401 and reintento:
            refrescar()
            return helix(metodo, ruta, cuerpo, False)
        raise


def crear_clip():
    """Clip de Twitch de lo último que salió (con el delay activo, de lo atrasado). Devuelve el texto para el chat."""
    try:
        if "clips:edit" not in alcances():
            log.warning("!clip necesita conectar de nuevo la cuenta de Twitch del bot (Configuración): le falta el permiso de clips")
            return "No pude clipear: el bot necesita el login de nuevo"
        clip = helix("POST", "clips?broadcaster_id=" + ids_twitch[CANAL])["data"][0]["id"]
    except urllib.error.HTTPError as e:
        log.warning("no pude crear el clip: HTTP %s", e.code)
        return "No pude clipear: el stream no está en vivo en Twitch" if e.code == 404 else "No pude clipear, probá de nuevo en un rato"
    except (OSError, KeyError, IndexError, ValueError) as e:
        log.warning("no pude crear el clip: %s", e)
        return "No pude clipear, probá de nuevo en un rato"
    log.info("clip %s", clip)
    return "Clip: https://clips.twitch.tv/" + clip


def moderar(accion, m, ids):
    consulta = urllib.parse.urlencode({"broadcaster_id": ids[CANAL], "moderator_id": ids[BOT]})
    try:
        if accion == "banear":
            helix("POST", "moderation/bans?" + consulta, {"data": {"user_id": m["user_id"], "reason": "Spam de viewbots (Stream Kit)"}})
        else:
            helix("DELETE", "moderation/chat?" + consulta + "&message_id=" + m["id"])
        log.info("%s a %s", accion, m["usuario"])
    except urllib.error.HTTPError as e:
        log.error("no pude %s a %s: HTTP %s%s", accion, m["usuario"], e.code, " (falta /mod %s)" % BOT if e.code == 403 else "")
    except OSError as e:
        log.error("no pude %s a %s: %s", accion, m["usuario"], e)


def ordenar(o):
    """Una acción de la vista de chat, ya revisada por la web. Devuelve "" si salió, o el error en palabras."""
    accion, plataforma = o["accion"], o["plataforma"]
    plataforma_nombre = plataforma.capitalize()
    try:
        if plataforma == "twitch":
            if not ids_twitch:
                ids_twitch.update({u["login"]: u["id"] for u in helix("GET", f"users?login={BOT}&login={CANAL}")["data"]})
            consulta = urllib.parse.urlencode({"broadcaster_id": ids_twitch[CANAL], "moderator_id": ids_twitch[BOT]})
            if accion == "borrar":
                helix("DELETE", f"moderation/chat?{consulta}&message_id={urllib.parse.quote(o['mid'])}")
            elif accion == "desbanear":
                helix("DELETE", f"moderation/bans?{consulta}&user_id={o['uid']}")
            else:
                ban = {"user_id": o["uid"], "reason": "Desde el chat de Stream Kit"}
                if accion == "timeout":
                    ban["duration"] = o["minutos"] * 60  # Twitch lo pide en segundos
                helix("POST", "moderation/bans?" + consulta, {"data": ban})
        else:
            base = {"broadcaster_user_id": CONFIG["kick_broadcaster_id"], "user_id": int(o.get("uid") or 0)}
            if accion == "borrar":
                kick_api("DELETE", "chat/" + urllib.parse.quote(o["mid"]))
            elif accion == "desbanear":
                kick_api("DELETE", "moderation/bans", base)
            else:
                kick_api("POST", "moderation/bans", {**base, "reason": "Desde el chat de Stream Kit", **({"duration": o["minutos"]} if accion == "timeout" else {})})
    except urllib.error.HTTPError as e:
        try:
            detalle = json.loads(e.read() or b"{}").get("message", "")
        except (ValueError, OSError, AttributeError):
            detalle = ""
        if e.code in (401, 403):
            detalle = ("falta el permiso de borrar mensajes: activalo en la app de Kick y volvé a conectar el bot de Kick en Configuración" if plataforma == "kick" and accion == "borrar"
                       else f"el bot no es moderador o venció su sesión. En tu chat: /mod {BOT if plataforma == 'twitch' else KICK_BOT}")
        log.error("no pude %s a %s en %s: HTTP %s %s", accion, o.get("usuario"), plataforma_nombre, e.code, detalle)
        return f"{plataforma_nombre} respondió {e.code}" + (f": {detalle}" if detalle else "")
    except (OSError, KeyError, ValueError) as e:
        log.error("no pude %s a %s en %s: %s", accion, o.get("usuario"), plataforma_nombre, e)
        return f"No pude hablar con {plataforma_nombre}: {e}"
    log.info("%s a %s en %s, desde la vista de chat", accion, o.get("usuario"), plataforma_nombre)
    emitir(tipo="moderado", plataforma=plataforma, accion=accion, usuario=o.get("usuario", ""), uid=o.get("uid"), mid=o.get("mid"), minutos=o.get("minutos"))
    return ""


def escuchar_ordenes():
    """Atiende la vista de chat de a una orden por vez. Solo escucha en esta PC."""
    try:
        servidor = socket.create_server(("127.0.0.1", PUERTO_ORDENES))
    except OSError as e:
        log.error("no pude abrir el puerto %s: el chat de la web no va a poder moderar (%s)", PUERTO_ORDENES, e)
        return
    while True:
        c, _ = servidor.accept()
        with c:
            try:
                c.settimeout(5)
                datos = b""
                while not datos.endswith(b"\n") and len(datos) < 4096:
                    parte = c.recv(4096)
                    if not parte:
                        break
                    datos += parte
                pedido = json.loads(datos)
                respuesta = {"error": "", "quienes": quienes()} if pedido.get("accion") == "quienes" else {"error": ordenar(pedido)}
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
                respuesta = {"error": f"Pedido inválido: {e}"}
            try:
                c.sendall((json.dumps(respuesta) + "\n").encode())
            except OSError:  # la web se cansó de esperar
                pass


def en_vivo(ids):
    try:
        return bool(helix("GET", "streams?user_id=" + ids[CANAL])["data"])
    except OSError as e:  # sin saberlo, mejor callarse
        log.warning("no pude ver si hay stream: %s", e)
        return False


# Kick: escribir y banear va por su API oficial. Leer el chat no se puede así desde una PC, porque la oficial solo avisa por webhooks a una dirección pública.
# Se lee del websocket de Pusher que usa la web de Kick. Si Kick cambia la clave, como en octubre de 2026, se cambia en config.json




def kick_refrescar():
    t = json.load(open(TOKEN_KICK, encoding="utf-8"))
    try:
        n = pedir("https://id.kick.com/oauth/token", urllib.parse.urlencode({
            "grant_type": "refresh_token", "refresh_token": t["refresh_token"], "client_id": CONFIG["kick_client_id"], "client_secret": t["client_secret"]}).encode())
    except urllib.error.HTTPError as e:
        if e.code in (400, 401):  # solo se apaga Kick: Twitch sigue
            kick.update(activo=False, estado="vencida")
            log.error("Kick rechazó la sesión del bot: volvé a conectarla en Configuración")
        raise
    guardar_json(TOKEN_KICK, {**t, "access_token": n["access_token"], "refresh_token": n.get("refresh_token") or t["refresh_token"]})


def kick_api(metodo, ruta, cuerpo=None, reintento=True):
    with kick["candado"]:
        cabeceras = {"Authorization": "Bearer " + json.load(open(TOKEN_KICK, encoding="utf-8"))["access_token"], "Content-Type": "application/json", "Accept": "application/json"}
        try:
            return pedir("https://api.kick.com/public/v1/" + ruta, json.dumps(cuerpo).encode() if cuerpo else None, metodo, cabeceras)
        except urllib.error.HTTPError as e:
            if e.code == 401 and reintento:
                kick_refrescar()
                return kick_api(metodo, ruta, cuerpo, False)
            raise


def kick_en_vivo():
    try:
        return bool(kick_api("GET", f"livestreams?broadcaster_user_id={CONFIG['kick_broadcaster_id']}")["data"])
    except OSError as e:  # sin saberlo, mejor callarse
        log.warning("no pude ver si hay stream en Kick: %s", e)
        return False


def kick_hablar(texto):
    enviados.append(texto)
    try:
        kick_api("POST", "chat", {"type": "user", "broadcaster_user_id": CONFIG["kick_broadcaster_id"], "content": texto})
    except OSError as e:
        log.error("no pude hablar en Kick: %s", e)


def kick_banear(m):
    try:
        kick_api("POST", "moderation/bans", {"broadcaster_user_id": CONFIG["kick_broadcaster_id"], "user_id": m["user_id"], "reason": "Spam de viewbots (Stream Kit)"})
        log.info("banear a %s en Kick", m["usuario"])
    except urllib.error.HTTPError as e:
        log.error("no pude banear a %s en Kick: HTTP %s%s", m["usuario"], e.code, " (falta /mod %s)" % KICK_BOT if e.code == 403 else "")
    except OSError as e:
        log.error("no pude banear a %s en Kick: %s", m["usuario"], e)


def ws_codificar(datos, op=1):
    mascara, n = os.urandom(4), len(datos)
    largo = bytes([0x80 | n]) if n < 126 else bytes([0xFE]) + n.to_bytes(2, "big")
    return bytes([0x80 | op]) + largo + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(datos))


def ws_cuadro(buf):
    """Saca un cuadro del websocket: (tipo, datos, resto), o None si falta que llegue más."""
    if len(buf) < 2:
        return None
    largo, pos = buf[1] & 0x7F, 2
    if largo >= 126:
        pos = 4 if largo == 126 else 10
        if len(buf) < pos:
            return None
        largo = int.from_bytes(buf[2:pos], "big")
    if len(buf) < pos + largo:
        return None
    return buf[0] & 0x0F, buf[pos:pos + largo], buf[pos + largo:]


def parsear_kick(evento):
    if "ChatMessageEvent" not in evento.get("event", ""):
        return None
    d = json.loads(evento["data"])
    insignias = {i.get("type") for i in d["sender"].get("identity", {}).get("badges", [])}
    # Kick no avisa cuál es el primer mensaje de alguien: acá no se borran links, solo se banean las frases
    return {"usuario": d["sender"]["slug"].lower(), "texto": d["content"], "id": d["id"], "user_id": d["sender"]["id"], "primero": False, "inmune": bool(insignias & INMUNES), "manda": bool(insignias & MANDAN),
            "nombre": d["sender"].get("username") or d["sender"]["slug"], "color": d["sender"].get("identity", {}).get("color", "")}


def aviso_kick(evento):
    """Subs, regalos, raids y kicks de Kick, como los manda Pusher. Los follows no llegan por acá: Kick solo los avisa por webhook."""
    nombre = evento.get("event", "")
    try:
        d = json.loads(evento.get("data") or "{}")
    except ValueError:
        return None
    if not isinstance(d, dict):
        return None
    if nombre == "App\\Events\\SubscriptionEvent":
        meses = int(d.get("months") or 1)
        a = {"tipo": "resub" if meses > 1 else "sub", "usuario": d.get("username"), "cantidad": meses}
    elif nombre == "App\\Events\\GiftedSubscriptionsEvent":
        a = {"tipo": "regalo", "usuario": d.get("gifter_username"), "cantidad": len(d.get("gifted_usernames") or []) or 1}
    elif nombre == "App\\Events\\StreamHostEvent":
        a = {"tipo": "raid", "usuario": d.get("host_username"), "cantidad": int(d.get("number_viewers") or 0)}
    elif nombre == "KicksGifted":
        a = {"tipo": "kicks", "usuario": (d.get("sender") or {}).get("username"), "cantidad": int((d.get("gift") or {}).get("amount") or 0), "mensaje": d.get("message") or ""}
    else:
        return None
    return a if a["usuario"] else None


def ws_conectar(host, ruta, extra=""):
    """Abre un websocket con TLS. Devuelve el socket y lo que ya llegó después del saludo."""
    s = ssl.create_default_context().wrap_socket(socket.create_connection((host, 443), 15), server_hostname=host)
    try:
        s.settimeout(30)
        s.sendall((f"GET {ruta} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\nSec-WebSocket-Version: 13\r\n{extra}User-Agent: StreamKit\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            datos = s.recv(4096)
            if not datos:
                raise ConnectionError(host + " cortó al conectar")
            buf += datos
        cabecera, _, buf = buf.partition(b"\r\n\r\n")
        if b" 101 " not in cabecera.split(b"\r\n")[0]:
            raise ConnectionError(cabecera.split(b"\r\n")[0].decode(errors="replace"))
        return s, buf
    except BaseException:
        s.close()
        raise


def kick_sesion():
    host = f"ws-{CONFIG['kick_pusher_cluster']}.pusher.com"
    s, buf = ws_conectar(host, f"/app/{CONFIG['kick_pusher_clave']}?protocol=7&client=js&version=8.4.0&flash=false", "Origin: https://kick.com\r\n")
    with s:
        enviar = lambda evento: s.sendall(ws_codificar(json.dumps(evento).encode()))
        # los subs y raids van a la sala del chat; los kicks, al canal (kick_canal es el id interno de kick.com/api/v2/channels/<tu canal>)
        canales = [f"chatrooms.{CONFIG['kick_chatroom']}.v2"] + ([f"channel.{CONFIG['kick_canal']}", f"channel_{CONFIG['kick_canal']}"] if CONFIG.get("kick_canal") else [])
        recientes, sin_usar = collections.deque(maxlen=20), set()  # el mismo aviso puede llegar por dos canales
        usos, ultimo = {}, time.monotonic()
        while kick["activo"]:
            try:
                datos = s.recv(65536)
                if not datos:
                    raise ConnectionError("Pusher cortó")
                ultimo, buf = time.monotonic(), buf + datos
                while c := ws_cuadro(buf):
                    tipo, cuerpo, buf = c
                    if tipo == 8:
                        raise ConnectionError("Pusher cerró la conexión")
                    if tipo == 9:
                        s.sendall(ws_codificar(cuerpo, 10))
                    if tipo != 1:  # shortcut: no arma mensajes partidos porque Pusher no los usa; si aparecen, reconecta y hay que armarlos
                        continue
                    e = json.loads(cuerpo)
                    if e.get("event") == "pusher:connection_established":
                        for canal in canales:
                            enviar({"event": "pusher:subscribe", "data": {"auth": "", "channel": canal}})
                    elif e.get("event") == "pusher_internal:subscription_succeeded":
                        if e.get("channel") == canales[0]:
                            kick["estado"] = "conectado"
                            log.info("conectado al chat de Kick")
                    elif e.get("event") == "pusher:ping":
                        enviar({"event": "pusher:pong", "data": {}})
                    elif e.get("event") == "pusher:error":
                        raise ConnectionError("Pusher: %s" % e.get("data"))  # si es 4001, Kick cambió la clave: va en config.json
                    elif m := parsear_kick(e):
                        emitir(tipo="chat", plataforma="kick", usuario=m["nombre"], color=m["color"], texto=m["texto"], mid=m["id"], uid=m["user_id"])
                        if d := decidir(m, time.monotonic(), usos):
                            if d[0] == "responder":
                                kick_hablar(d[1])
                            elif d[0] == "clip":
                                kick_hablar(crear_clip())
                            elif d[0] == "banear":
                                kick_banear(m)
                    elif (clave := (e.get("event"), e.get("data"))) not in recientes:
                        recientes.append(clave)
                        if a := aviso_kick(e):
                            emitir(plataforma="kick", **a)
                        elif clave[0] not in sin_usar:  # para saber qué más manda Kick, una vez por conexión
                            sin_usar.add(clave[0])
                            log.info("evento de Kick sin usar: %s", clave[0])
            except TimeoutError:
                pass
            if time.monotonic() - ultimo > 180:  # Pusher da señal cada 2 minutos
                raise ConnectionError("sin señal de Pusher")
            toca_timer("kick", kick_en_vivo, kick_hablar)


SEPARACION_TIMERS = 60  # si dos mensajes tocan a la vez, no salen pegados: el segundo espera
# cada plataforma lleva los suyos y mira su propio vivo: si una no está conectada, la otra igual habla
timers = {p: {"proximos": [time.monotonic() + t["minutos"] * 60 for t in CONFIG["timers"]], "ultimo": -1e9} for p in ("twitch", "kick")}


viewers = {}  # para la vista de chat: espectadores de cada plataforma; None sin stream, sin clave si no se pudo ver
inicio = {}  # cuándo arrancó el stream en cada plataforma
escribieron = {}  # plataforma -> {usuario: último mensaje}; aparte de eventos, que solo guarda los últimos 300


def fecha(texto):
    try:
        return datetime.datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 0


def contar_viewers():
    while True:
        for plataforma, pedir_lista in (("twitch", lambda: helix("GET", "streams?user_id=" + ids_twitch[CANAL])),
                                        ("kick", lambda: kick_api("GET", f"livestreams?broadcaster_user_id={CONFIG['kick_broadcaster_id']}"))):
            try:
                d = pedir_lista()["data"]
                viewers[plataforma] = d[0]["viewer_count"] if d else None
                inicio[plataforma] = fecha(d[0].get("started_at")) if d else None
            except (OSError, KeyError, ValueError):  # sin sesión todavía o sin internet: no se muestra
                viewers.pop(plataforma, None)
        time.sleep(30)


def quienes():
    """Para la vista de chat: en Twitch, quién está en el chat; Kick no lo da. En las dos, quién escribió en este stream."""
    r = {}
    if viewers.get("twitch") is not None:
        try:
            if "moderator:read:chatters" not in alcances():
                r["twitch"] = {"error": "Falta un permiso: volvé a conectar la cuenta de Twitch del bot en Configuración"}
            else:
                nombres, total, cursor = [], 0, ""
                for _ in range(5):  # hasta 5000 nombres: más no entran en la vista
                    consulta = urllib.parse.urlencode({"broadcaster_id": ids_twitch[CANAL], "moderator_id": ids_twitch[BOT], "first": 1000, "after": cursor})
                    d = helix("GET", "chat/chatters?" + consulta)
                    nombres += [c["user_name"] for c in d["data"]]
                    total, cursor = d.get("total", len(nombres)), d.get("pagination", {}).get("cursor")
                    if not cursor:
                        break
                r["twitch"] = {"usuarios": sorted(nombres, key=str.lower), "total": total}
        except (OSError, KeyError, ValueError) as e:
            r["twitch"] = {"error": f"No pude preguntarle a Twitch: {e}"}
    for plataforma in ("twitch", "kick"):
        if viewers.get(plataforma) is not None:
            desde = inicio.get(plataforma) or 0
            vistos = dict(escribieron.get(plataforma, {}))
            r.setdefault(plataforma, {})["escribieron"] = sorted((u for u, t in vistos.items() if u and t >= desde), key=str.lower)
    return r


def toca_timer(plataforma, vivo, hablar):
    t, ahora = timers[plataforma], time.monotonic()
    if ahora - t["ultimo"] < SEPARACION_TIMERS:
        return
    for i, timer in enumerate(CONFIG["timers"]):
        if ahora >= t["proximos"][i]:
            t["proximos"][i] = ahora + timer["minutos"] * 60
            if vivo():
                hablar(timer["texto"])
                t["ultimo"] = ahora
            return


def sesion():
    refrescar()
    ids = {u["login"]: u["id"] for u in helix("GET", f"users?login={BOT}&login={CANAL}")["data"]}
    ids_twitch.update(ids)
    usos = {}
    crudo = socket.create_connection((IRC, PUERTO_IRC), 15)
    with ssl.create_default_context().wrap_socket(crudo, server_hostname=IRC) as s:
        s.settimeout(30)
        enviar = lambda texto: s.sendall((texto + "\r\n").encode())

        def hablar(texto):  # Twitch no le devuelve al bot lo que dice: se suma a mano a la web
            enviar(f"PRIVMSG #{CANAL} :{texto}")
            emitir(tipo="chat", plataforma="twitch", usuario=BOT, color="", texto=texto)
        enviar("CAP REQ :twitch.tv/tags twitch.tv/commands")
        enviar("PASS oauth:" + leer_token()["access_token"])
        enviar("NICK " + BOT)
        enviar("JOIN #" + CANAL)
        resto, ultimo = b"", time.monotonic()
        while twitch["activo"]:
            try:
                datos = s.recv(4096)
                if not datos:
                    raise ConnectionError("Twitch cortó")
                ultimo = time.monotonic()
                *lineas, resto = (resto + datos).split(b"\r\n")
                for linea in lineas:
                    linea = linea.decode(errors="replace")
                    if linea.startswith("PING"):
                        enviar("PONG" + linea[4:])
                    elif " ROOMSTATE #" in linea:  # Twitch confirma que entró al canal
                        twitch["estado"] = "conectado"
                        log.info("conectado a #%s", CANAL)
                    elif " RECONNECT" in linea[:40] or "Login authentication failed" in linea:
                        raise ConnectionError(linea[:80])
                    elif m := parsear(linea):
                        emitir(tipo="chat", plataforma="twitch", usuario=m["nombre"], color=m["color"], texto=m["texto"], mid=m["id"], uid=m["user_id"], emotes=m["emotes"])
                        if m["bits"]:
                            emitir(tipo="bits", plataforma="twitch", usuario=m["nombre"], cantidad=m["bits"], mensaje=m["texto"], emotes=m["emotes"])
                        if d := decidir(m, time.monotonic(), usos):
                            if d[0] == "responder":
                                hablar(d[1])
                            elif d[0] == "clip":
                                hablar(crear_clip())
                            else:
                                moderar(d[0], m, ids)
                    elif a := parsear_aviso(linea):
                        emitir(plataforma="twitch", **a)
            except TimeoutError:
                pass
            ahora = time.monotonic()
            if ahora - ultimo > 360:  # Twitch manda PING cada 5 minutos
                raise ConnectionError("sin señal de Twitch")
            toca_timer("twitch", lambda: en_vivo(ids), hablar)


def alcances():
    validar = lambda: pedir("https://id.twitch.tv/oauth2/validate", cabeceras={"Authorization": "OAuth " + leer_token()["access_token"]})["scopes"]
    try:
        return validar()
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
        refrescar()
        return validar()


def revisar_lista(canal_id, ahora=None):
    """Twitch no avisa por EventSub los follows de cuentas que marca como spam, pero igual las suma a la lista de seguidores.
    La primera vuelta solo anota a los que ya estaban; después avisa a los nuevos de los últimos 10 minutos."""
    ahora = ahora or time.time()
    lista = helix("GET", f"channels/followers?broadcaster_id={canal_id}&first=20")["data"]
    for f in reversed(lista):  # Twitch los manda del más nuevo al más viejo
        if f["user_id"] in seguidores:
            continue
        seguidores.add(f["user_id"])
        # si alguien deja de seguir, entra a la lista uno viejo: por la fecha no sale como nuevo
        if follows.get("lista_leida") and ahora - datetime.datetime.fromisoformat(f["followed_at"]).timestamp() < 600:
            log.info("follow que Twitch no avisó: %s", f["user_name"])
            emitir(tipo="follow", plataforma="twitch", usuario=f["user_name"])
    follows["lista_leida"] = True


def follows_sesion():
    """Follows de Twitch por EventSub. Necesita moderator:read:followers: las sesiones de antes del 8/11/2026 no lo tienen."""
    if "moderator:read:followers" not in alcances():
        if follows["estado"] != "falta permiso":
            log.warning("los follows de Twitch necesitan conectar de nuevo la cuenta del bot (Configuración): le falta un permiso")
        follows["estado"] = "falta permiso"
        return  # reintentar vuelve a mirar cada 5 minutos: después del login arranca solo
    ids = {u["login"]: u["id"] for u in helix("GET", f"users?login={BOT}&login={CANAL}")["data"]}
    s, buf = ws_conectar(EVENTSUB, "/ws")
    with s:
        s.settimeout(5)
        limite, ultimo, proxima_lista = 30, time.monotonic(), 0
        while follows["activo"]:
            if time.monotonic() >= proxima_lista:
                proxima_lista = time.monotonic() + 60
                try:
                    revisar_lista(ids[CANAL])
                except (OSError, KeyError, ValueError) as e:  # que falle la lista no corta EventSub
                    log.warning("no pude leer la lista de seguidores: %s", e)
            while c := ws_cuadro(buf):
                tipo, cuerpo, buf = c
                if tipo == 8:
                    raise ConnectionError("EventSub cerró la conexión")
                if tipo == 9:
                    s.sendall(ws_codificar(cuerpo, 10))
                if tipo != 1:
                    continue
                m = json.loads(cuerpo)
                clase, p = m["metadata"]["message_type"], m.get("payload", {})
                if clase == "session_welcome":  # hay 10 segundos para suscribirse
                    limite = p["session"]["keepalive_timeout_seconds"] + 10
                    helix("POST", "eventsub/subscriptions", {"type": "channel.follow", "version": "2",
                                                             "condition": {"broadcaster_user_id": ids[CANAL], "moderator_user_id": ids[BOT]},
                                                             "transport": {"method": "websocket", "session_id": p["session"]["id"]}})
                    follows["estado"] = "conectado"
                    log.info("escuchando los follows de Twitch")
                elif clase == "notification" and p["subscription"]["type"] == "channel.follow" and p["event"]["user_id"] not in seguidores:
                    seguidores.add(p["event"]["user_id"])
                    emitir(tipo="follow", plataforma="twitch", usuario=p["event"]["user_name"])
                elif clase in ("session_reconnect", "revocation"):  # shortcut: reconecta de cero en vez de usar reconnect_url; se pueden perder unos segundos
                    raise ConnectionError("EventSub pidió " + clase)
            if time.monotonic() - ultimo > limite:
                raise ConnectionError("sin señal de EventSub")
            try:
                datos = s.recv(65536)
                if not datos:
                    raise ConnectionError("EventSub cortó")
                ultimo, buf = time.monotonic(), buf + datos
            except TimeoutError:
                pass


def reintentar(hacer, plataforma):
    espera = 5
    while plataforma["activo"]:
        inicio = time.monotonic()
        try:
            hacer()
        except (OSError, KeyError, ValueError) as e:  # internet caído o respuesta rara: reintenta, nunca se muere solo
            log.warning("%s cortada: %s", hacer.__name__, e)
            if plataforma["activo"]:
                plataforma["estado"] = "reconectando"
        espera = 5 if time.monotonic() - inicio > 60 else min(espera * 2, 300)
        if plataforma["activo"]:
            time.sleep(espera)


def publicar_estado():
    try:
        guardar_json(ESTADO, {"actualizado": time.time(), "twitch": twitch["estado"], "kick": kick["estado"], "follows": follows["estado"], "viewers": viewers,
                                "ids": {"twitch": ids_twitch.get(CANAL), "kick": CONFIG.get("kick_broadcaster_id")}})  # para los emotes de BTTV, FFZ y 7TV
    except OSError:  # el panel justo lo está leyendo: sale en la próxima vuelta
        pass


def caida(a):
    # sin esto, un error inesperado apaga una sola plataforma en silencio. Así se reinicia todo el bot
    log.critical("se cayó el bot", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))
    os._exit(1)


def correr():
    candado = socket.socket()
    try:
        candado.bind(("127.0.0.1", PUERTO_CANDADO))
    except OSError:
        sys.exit("El bot ya está corriendo")
    candado.listen(1)

    def esperar_parar():
        candado.accept()
        log.info("reinicio pedido")
        os._exit(0)
    threading.Thread(target=esperar_parar, daemon=True).start()

    log.addHandler(logging.handlers.RotatingFileHandler(os.path.join(AQUI, "bot.log"), maxBytes=200_000, backupCount=1, encoding="utf-8"))
    log.handlers[0].setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.setLevel(logging.INFO)
    threading.excepthook = caida
    cargar_eventos()
    threading.Thread(target=escuchar_ordenes, daemon=True).start()
    threading.Thread(target=contar_viewers, daemon=True).start()
    for plataforma, hacer, token in ((twitch, sesion, TOKEN), (follows, follows_sesion, TOKEN), (kick, kick_sesion, TOKEN_KICK)):
        if os.path.exists(token):
            plataforma.update(activo=True, estado="conectando")
            threading.Thread(target=reintentar, args=(hacer, plataforma), daemon=True).start()
    while True:
        publicar_estado()
        for _ in range(20):  # el chat sale a la web en un cuarto de segundo; el estado, cada 5
            publicar_eventos()
            time.sleep(0.25)


def main():
    if "--reiniciar" in sys.argv:
        try:
            socket.create_connection(("127.0.0.1", PUERTO_CANDADO), 2).close()
            print("Bot reiniciando")
        except OSError:
            print("El bot no estaba corriendo")
    else:
        correr()


if __name__ == "__main__":
    main()
