# python tests/test_chatbot.py: sin internet ni token, prueba cómo lee el chat y qué decide
import os as _os, sys as _sys
_RAIZ = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, _os.path.join(_RAIZ, 'streamkit'))  # el código está en streamkit/
import io, json, os, sys, tempfile, urllib.error
os.environ["STREAMKIT_DATOS"] = tempfile.mkdtemp()  # config de ejemplo en una carpeta aparte: no toca la tuya
os.makedirs(os.path.join(os.environ["STREAMKIT_DATOS"], "bot"))
_ejemplo = json.load(open(os.path.join(_RAIZ, "recursos", "ejemplos", "bot", "config.json"), encoding="utf-8"))
_ejemplo.update(bot="tubot", canal="tucanal", kick_bot="tubot", kick_broadcaster_id=123, client_id="cid", kick_client_id="kid")
_ejemplo["comandos"]["!kick"] = {"respuesta": "https://kick.com/tucanal", "espera": 15}
json.dump(_ejemplo, open(os.path.join(os.environ["STREAMKIT_DATOS"], "bot", "config.json"), "w", encoding="utf-8"))
import chatbot as b

TAGS = "@badge-info=;badges={b};color=#FF0000;display-name=Alguien;first-msg={f};id=abc-123;mod=0;user-id=42 "
def linea(texto, badges="", primero=0, usuario="alguien"):
    return TAGS.format(b=badges, f=primero) + f":{usuario}!{usuario}@{usuario}.tmi.twitch.tv PRIVMSG #tucanal :{texto}"
def que(texto, usos=None, ahora=1000.0, **k):
    return b.decidir(b.parsear(linea(texto, **k)), ahora, {} if usos is None else usos)

m = b.parsear(linea("hola: qué tal", badges="subscriber/3", primero=1))
assert (m["usuario"], m["texto"], m["id"], m["user_id"], m["primero"], m["inmune"]) == ("alguien", "hola: qué tal", "abc-123", "42", True, True)
assert b.parsear("PING :tmi.twitch.tv") is None
assert b.parsear(":tmi.twitch.tv 001 tubot :Welcome, GLHF!") is None

for spam in ["Best viewers on streamboo .com", "STREAMBOO", "str3amb00 punto com", "stream.boo", "s t r e a m b o o", "ѕtrеаmbоо", "ｓｔｒｅａｍｂｏｏ",
             "Hello! Wanna become famous? Buy followers", "best viewers on example dot com", "stream boo .com", "Buy followers, primes and viewers"]:
    assert que(spam) == ("banear", None), spam
for normal in ["el stream boost de twitch está bueno", "probá streamboost", "buen stream, boo a ese ace", "stream boots nuevos", "a b c d"]:
    assert que(normal) is None, normal

for jefe in ["broadcaster/1", "moderator/1", "vip/1", "subscriber/0"]:
    assert que("streamboo", badges=jefe) is None, jefe
assert que("streamboo", usuario="tubot") is None

assert que("mirá https://algo.xyz/x", primero=1) == ("borrar", None)
assert que("mirá vlr.gg/123", primero=1) == ("borrar", None)
assert que("mirá vlr.gg/123", primero=0) is None
assert que("hola, primera vez acá. Son las 10.30", primero=1) is None

assert que("!REDES y algo más") == ("responder", b.CONFIG["comandos"]["!redes"]["respuesta"])
assert que("!noexiste") is None and que("") is None and que("   ") is None
ayuda = que("!comandos")[1]
assert all(c in ayuda for c in b.CONFIG["comandos"])

# cada comando espera lo suyo, sin frenar a los otros, y !comandos tiene su propia espera
reales = {k: b.CONFIG[k] for k in ("comandos", "espera_lista_comandos", "timers")}
b.CONFIG.update(comandos={"!corto": {"respuesta": "a", "espera": 5}, "!largo": {"respuesta": "b", "espera": 60}, "!libre": {"respuesta": "c", "espera": 0}}, espera_lista_comandos=30)
usos = {}
assert que("!corto", usos) and que("!largo", usos) and que("!comandos", usos), "uno no frena a otro"
assert que("!corto", usos, ahora=1004.0) is None and que("!corto", usos, ahora=1005.0) == ("responder", "a")
assert que("!largo", usos, ahora=1059.0) is None and que("!largo", usos, ahora=1060.0) == ("responder", "b")
assert que("!comandos", usos, ahora=1029.0) is None and que("!comandos", usos, ahora=1030.0)
assert que("!libre", usos) and que("!libre", usos), "con 0 contesta siempre"
b.CONFIG.update(reales)

# lo que escribe el chat nunca vuelve en una respuesta: así nadie le hace mandar /ban u otra cosa
assert "/ban" not in que("!redes /ban tucanal")[1]

# !clip: solo vos y los mods, cada 30 s; un sub o un VIP no
usos = {}
assert que("!clip", badges="subscriber/3") is None and que("!clip", badges="vip/1") is None
assert que("!clip", usos, badges="broadcaster/1") == ("clip", None)
assert que("!clip", usos, ahora=1029.0, badges="moderator/1") is None and que("!clip", usos, ahora=1030.0, badges="moderator/1") == ("clip", None)
reales_clip = (b.alcances, b.helix)
b.ids_twitch["tucanal"] = "2"
pedidos = []
b.alcances = lambda: ["clips:edit"]
b.helix = lambda metodo, ruta, cuerpo=None: pedidos.append((metodo, ruta)) or {"data": [{"id": "Clip-Lindo", "edit_url": "x"}]}
assert b.crear_clip() == "Clip: https://clips.twitch.tv/Clip-Lindo" and pedidos == [("POST", "clips?broadcaster_id=2")]
def falla(codigo):
    def f(*a, **k):
        raise urllib.error.HTTPError("u", codigo, "x", {}, io.BytesIO(b"{}"))
    return f
b.helix = falla(404)
assert "no está en vivo" in b.crear_clip()
b.helix = falla(500)
assert "probá de nuevo" in b.crear_clip()
b.alcances = lambda: ["chat:read"]
assert "login" in b.crear_clip()
b.alcances, b.helix = reales_clip
for t in ("Clip: https://clips.twitch.tv/x", "No pude clipear: el stream no está en vivo en Twitch"):
    assert "¿" not in t and not t.endswith(".")

# Kick: así llega un mensaje real de Pusher
def evento_kick(slug="alguien", insignias=(), contenido="hola"):
    datos = {"id": "uuid-1", "chatroom_id": 1, "content": contenido, "type": "message", "created_at": "x", "metadata": {},
             "sender": {"id": 77, "username": slug, "slug": slug, "identity": {"color": "#fff", "badges": [{"type": t, "text": t} for t in insignias]}}}
    return {"event": "App\\Events\\ChatMessageEvent", "channel": "chatrooms.1.v2", "data": json.dumps(datos)}

# el bot con tu propia cuenta: tus comandos andan, pero lo que dijo el bot (Kick se lo devuelve) no se contesta
assert b.decidir(b.parsear_kick(evento_kick(slug="tubot", contenido="!redes")), 1000.0, {}) is None, "con cuenta aparte, todo lo del bot se ignora"
b.BOT = b.CANAL = b.KICK_BOT = b.KICK_CANAL = "tucanal"
assert que("!clip", usuario="tucanal", badges="broadcaster/1") == ("clip", None)
assert b.decidir(b.parsear_kick(evento_kick(slug="tucanal", insignias=["broadcaster"], contenido="!redes")), 1000.0, {})[0] == "responder"
b.enviados.append("Todas mis redes")
assert b.decidir(b.parsear_kick(evento_kick(slug="tucanal", insignias=["broadcaster"], contenido="Todas mis redes")), 1000.0, {}) is None
b.BOT, b.CANAL, b.KICK_BOT, b.KICK_CANAL = "tubot", "tucanal", "tubot", ""
b.enviados.clear()
m = b.parsear_kick(evento_kick(contenido="streamboo"))
assert (m["usuario"], m["texto"], m["id"], m["user_id"], m["primero"], m["inmune"]) == ("alguien", "streamboo", "uuid-1", 77, False, False)
assert b.decidir(m, 1000.0, {}) == ("banear", None)
assert b.parsear_kick(evento_kick(insignias=["moderator"]))["inmune"] and b.parsear_kick(evento_kick(insignias=["broadcaster"]))["inmune"]
assert not b.parsear_kick(evento_kick(insignias=["og"]))["inmune"]
assert b.parsear_kick(evento_kick(insignias=["moderator"]))["manda"] and not b.parsear_kick(evento_kick(insignias=["vip"]))["manda"]
assert b.decidir(b.parsear_kick(evento_kick(insignias=["moderator"], contenido="streamboo")), 1000.0, {}) is None
assert b.decidir(b.parsear_kick(evento_kick(slug="tubot", contenido="streamboo")), 1000.0, {}) is None
assert b.decidir(b.parsear_kick(evento_kick(contenido="!kick")), 1000.0, {}) == ("responder", b.CONFIG["comandos"]["!kick"]["respuesta"])
assert b.parsear_kick({"event": "pusher_internal:subscription_succeeded", "data": "{}"}) is None
assert b.parsear_kick({"event": "App\\Events\\UserBannedEvent", "data": "{}"}) is None

# websocket: lo que recibe, con los tres tamaños de largo, incompleto y con dos cuadros pegados
for n in (5, 125, 126, 300, 70000):
    if n < 126: cabecera = bytes([0x81, n])
    elif n < 65536: cabecera = bytes([0x81, 126]) + n.to_bytes(2, "big")
    else: cabecera = bytes([0x81, 127]) + n.to_bytes(8, "big")
    cuadro = cabecera + b"x" * n
    assert b.ws_cuadro(cuadro + b"\x89\x00") == (1, b"x" * n, b"\x89\x00")
    assert b.ws_cuadro(cuadro[:-1]) is None and b.ws_cuadro(cuadro[:1]) is None
# y lo que manda: el servidor lo desenmascara y tiene que dar lo mismo
for n in (5, 125, 126, 300):
    c = b.ws_codificar(b"y" * n)
    assert c[0] == 0x81 and c[1] & 0x80
    inicio = 2 if n < 126 else 4
    mascara, cuerpo = c[inicio:inicio + 4], c[inicio + 4:]
    assert bytes(x ^ mascara[i % 4] for i, x in enumerate(cuerpo)) == b"y" * n

# sesión de Kick sin internet: con 401 refresca una vez, conserva la clave secreta y reintenta; si Kick rechaza el refresco, se apaga solo Kick
carpeta = tempfile.mkdtemp()
b.TOKEN_KICK = os.path.join(carpeta, "token-kick.json")
json.dump({"access_token": "viejo", "refresh_token": "r1", "client_secret": "s"}, open(b.TOKEN_KICK, "w"))
pedidos, respuestas = [], []
def falso(url, cuerpo=None, metodo=None, cabeceras=None):
    pedidos.append((url, cuerpo, metodo, cabeceras))
    r = respuestas.pop(0)
    if isinstance(r, int):
        raise urllib.error.HTTPError(url, r, "x", {}, io.BytesIO(b""))
    return r
b.pedir = falso
b.kick["activo"] = True
respuestas[:] = [401, {"access_token": "nuevo", "refresh_token": "r2"}, {"data": {"is_sent": True}}]
b.kick_hablar("hola")
assert json.load(open(b.TOKEN_KICK)) == {"access_token": "nuevo", "refresh_token": "r2", "client_secret": "s"}
assert "refresh_token=r1" in pedidos[1][1].decode() and "client_secret=s" in pedidos[1][1].decode()
assert pedidos[2][3]["Authorization"] == "Bearer nuevo"
assert json.loads(pedidos[2][1]) == {"type": "user", "broadcaster_user_id": b.CONFIG["kick_broadcaster_id"], "content": "hola"}
pedidos.clear(); respuestas[:] = [{}]
b.kick_banear({"usuario": "alguien", "user_id": 77})
assert pedidos[0][0].endswith("/moderation/bans") and json.loads(pedidos[0][1])["user_id"] == 77
respuestas[:] = [401, 401]
b.kick_hablar("chau")
assert b.kick["activo"] is False, "sesión vencida: Kick se apaga"
assert json.load(open(b.TOKEN_KICK))["refresh_token"] == "r2", "no pisa la sesión guardada"
respuestas[:] = [403]
b.kick_banear({"usuario": "alguien", "user_id": 77})  # sin ser mod: no se cae

# si hay stream en Kick: pregunta sin cuerpo, y si no puede saberlo se calla
pedidos.clear(); respuestas[:] = [{"data": [{"slug": "tucanal"}]}, {"data": []}, 500]
assert b.kick_en_vivo() is True and pedidos[0][1] is None and "broadcaster_user_id=" in pedidos[0][0]
assert b.kick_en_vivo() is False
assert b.kick_en_vivo() is False

# timers: cada mensaje espera su hora con su propio tiempo, sin stream no habla y vuelve a esperar, y cada plataforma lleva los suyos
dichos, ahora = [], b.time.monotonic()
b.CONFIG["timers"] = [{"texto": "a", "minutos": 5}, {"texto": "b", "minutos": 20}]
kt = b.timers["kick"]
kt.update(proximos=[ahora + 999, ahora + 999], ultimo=-1e9)
b.toca_timer("kick", lambda: True, dichos.append)
assert dichos == []
kt["proximos"][0] = 0
b.toca_timer("kick", lambda: False, dichos.append)
assert dichos == [] and 290 < kt["proximos"][0] - ahora < 310 and kt["ultimo"] == -1e9
kt["proximos"][0] = 0
b.toca_timer("kick", lambda: True, dichos.append)
assert dichos == ["a"] and 290 < kt["proximos"][0] - ahora < 310 and kt["proximos"][1] == ahora + 999
assert b.timers["twitch"]["ultimo"] == -1e9, "Twitch no se entera"

# si dos tocan a la vez salen separados y ninguno se pierde; cada uno vuelve a su propio tiempo
dichos.clear()
kt.update(proximos=[0, 0], ultimo=-1e9)
b.toca_timer("kick", lambda: True, dichos.append)
b.toca_timer("kick", lambda: True, dichos.append)
assert dichos == ["a"], "el segundo espera"
assert kt["proximos"][1] == 0
kt["ultimo"] = b.time.monotonic() - b.SEPARACION_TIMERS
b.toca_timer("kick", lambda: True, dichos.append)
assert dichos == ["a", "b"] and 1190 < kt["proximos"][1] - ahora < 1210 and 290 < kt["proximos"][0] - ahora < 310

# sin mensajes cargados no habla ni pregunta si hay stream
b.CONFIG["timers"] = []
kt.update(proximos=[], ultimo=-1e9)
b.toca_timer("kick", lambda: 1 / 0, dichos.append)
b.CONFIG.update(reales)

# una frase que al limpiarla queda vacía no banea a todo el chat
guardadas, b.CONFIG["banear_frases"] = b.CONFIG["banear_frases"], ["..."]
assert que("hola") is None
b.CONFIG["banear_frases"] = guardadas

# si Twitch rechaza la sesión se apaga solo Twitch, y no reintenta
b.TOKEN = os.path.join(carpeta, "token.json")
json.dump({"access_token": "a", "refresh_token": "r"}, open(b.TOKEN, "w"))
b.twitch.update(activo=True, estado="conectado")
respuestas[:] = [400]
b.reintentar(b.refrescar, b.twitch)
assert b.twitch == {"activo": False, "estado": "vencida"}

# un corte de internet avisa "reconectando" y vuelve a intentar
b.twitch.update(activo=True, estado="conectado")
intentos = []
def cortada():
    intentos.append(b.twitch["estado"])
    if len(intentos) == 2:
        b.twitch["activo"] = False
        return
    raise ConnectionError("x")
dormir, b.time.sleep = b.time.sleep, lambda s: None
b.reintentar(cortada, b.twitch)
b.time.sleep = dormir
assert intentos == ["conectado", "reconectando"]

# Twitch: subs, regalos y raids llegan como USERNOTICE
def aviso(clase, extra="", texto=""):
    return f"@display-name=Pepe;login=pepe;msg-id={clase}{extra} :tmi.twitch.tv USERNOTICE #tucanal" + (f" :{texto}" if texto else "")
assert b.parsear_aviso(aviso("sub", ";msg-param-sub-plan=Prime")) == {"tipo": "sub", "usuario": "Pepe", "nivel": "Prime"}
assert b.parsear_aviso(aviso("resub", ";msg-param-cumulative-months=7;msg-param-sub-plan=1000", "vamos: arriba")) == {"tipo": "resub", "usuario": "Pepe", "cantidad": 7, "mensaje": "vamos: arriba"}
assert b.parsear_aviso(aviso("submysterygift", ";msg-param-mass-gift-count=5")) == {"tipo": "regalo", "usuario": "Pepe", "cantidad": 5}
assert b.parsear_aviso(aviso("subgift", ";msg-param-community-gift-id=123")) is None, "ya salió en el submysterygift"
assert b.parsear_aviso(aviso("subgift", ";msg-param-recipient-display-name=Ana"))["cantidad"] == 1
assert b.parsear_aviso(aviso("raid", ";msg-param-displayName=KRU;msg-param-viewerCount=342")) == {"tipo": "raid", "usuario": "KRU", "cantidad": 342}
assert b.parsear_aviso(aviso("announcement", "", "hola")) is None and b.parsear_aviso(linea("hola")) is None
# bits, nombre como se muestra y color
m = b.parsear(TAGS.format(b="", f=0).replace("color=", "bits=100;color=") + ":alguien!alguien@alguien.tmi.twitch.tv PRIVMSG #tucanal :Cheer100 grande")
assert (m["bits"], m["nombre"], m["color"]) == (100, "Alguien", "#FF0000")
assert b.parsear(linea("hola"))["bits"] == 0

# Kick: subs, regalos, raids y kicks como los manda Pusher
def kick_ev(nombre, datos):
    return {"event": nombre, "data": json.dumps(datos)}
assert b.aviso_kick(kick_ev("App\\Events\\SubscriptionEvent", {"chatroom_id": 1, "username": "ana", "months": 1})) == {"tipo": "sub", "usuario": "ana", "cantidad": 1}
assert b.aviso_kick(kick_ev("App\\Events\\SubscriptionEvent", {"username": "ana", "months": 4}))["tipo"] == "resub"
assert b.aviso_kick(kick_ev("App\\Events\\GiftedSubscriptionsEvent", {"gifted_usernames": ["a", "b", "c"], "gifter_username": "rey", "gifter_total": 9})) == {"tipo": "regalo", "usuario": "rey", "cantidad": 3}
assert b.aviso_kick(kick_ev("App\\Events\\StreamHostEvent", {"host_username": "kru", "number_viewers": 50, "optional_message": ""}))["cantidad"] == 50
assert b.aviso_kick(kick_ev("KicksGifted", {"message": "grande", "sender": {"username": "clove"}, "gift": {"amount": 100}})) == {"tipo": "kicks", "usuario": "clove", "cantidad": 100, "mensaje": "grande"}
assert b.aviso_kick(kick_ev("App\\Events\\SubscriptionEvent", {})) is None and b.aviso_kick({"event": "KicksGifted", "data": "no json"}) is None
assert b.aviso_kick(evento_kick()) is None
assert b.parsear_kick(evento_kick(slug="Ana"))["nombre"] == "Ana"

# lo que va a la web: ids que siempre crecen, se guardan y siguen después de reiniciar
b.EVENTOS = os.path.join(carpeta, "eventos.json")
b.eventos.update(lista=b.collections.deque(maxlen=300), ultimo=0, sucio=False)
b.emitir(tipo="chat", plataforma="twitch", usuario="a", texto="1")
b.emitir(tipo="follow", plataforma="twitch", usuario="b")
ids = [e["id"] for e in b.eventos["lista"]]
assert ids[1] > ids[0] > 0
b.publicar_eventos()
assert not b.eventos["sucio"] and [e["usuario"] for e in json.load(open(b.EVENTOS, encoding="utf-8"))] == ["a", "b"]
b.eventos.update(lista=b.collections.deque(maxlen=300), ultimo=0)
b.cargar_eventos()
b.emitir(tipo="chat", plataforma="kick", usuario="c", texto="3")
assert len(b.eventos["lista"]) == 3 and b.eventos["lista"][-1]["id"] > ids[1]

# follows de Twitch sin internet: sin el permiso avisa y no conecta; con él, se suscribe en la bienvenida y avisa cada seguidor una vez
def cuadro(obj):
    d = json.dumps(obj).encode()
    return bytes([0x81, len(d)]) + d if len(d) < 126 else bytes([0x81, 126]) + len(d).to_bytes(2, "big") + d
class SocketFalso:
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def settimeout(self, s): pass
    def sendall(self, d): pass
    def recv(self, n): return b""  # después de lo que ya llegó, Twitch corta
llamadas, reales_tw = [], (b.alcances, b.helix, b.ws_conectar)
b.alcances = lambda: ["chat:read"]
b.follows.update(activo=True, estado="conectando")
assert b.follows_sesion() is None and b.follows["estado"] == "falta permiso"
def helix_falso(metodo, ruta, cuerpo=None):
    llamadas.append((metodo, ruta, cuerpo))
    if ruta.startswith("channels/followers"):
        return {"data": [{"user_id": "7", "user_name": "Viejo", "followed_at": "2026-01-01T00:00:00Z"}]}
    return {"data": [{"login": "tubot", "id": "1"}, {"login": "tucanal", "id": "2"}]} if metodo == "GET" else {}
seguir = lambda: {"metadata": {"message_type": "notification"}, "payload": {"subscription": {"type": "channel.follow"}, "event": {"user_id": "9", "user_name": "Nuevo"}}}
llegado = cuadro({"metadata": {"message_type": "session_welcome"}, "payload": {"session": {"id": "ses", "keepalive_timeout_seconds": 10}}}) + cuadro(seguir()) + cuadro(seguir())
b.alcances, b.helix, b.ws_conectar = (lambda: ["moderator:read:followers"]), helix_falso, (lambda host, ruta: (SocketFalso(), llegado))
antes = len(b.eventos["lista"])
try:
    b.follows_sesion()
    raise AssertionError("tenía que cortar")
except ConnectionError:
    pass
assert b.follows["estado"] == "conectado"
assert llamadas[1] == ("GET", "channels/followers?broadcaster_id=2&first=20", None), "la primera vuelta de la lista arranca con la sesión"
assert llamadas[2] == ("POST", "eventsub/subscriptions", {"type": "channel.follow", "version": "2", "condition": {"broadcaster_user_id": "2", "moderator_user_id": "1"},
                                                          "transport": {"method": "websocket", "session_id": "ses"}})
nuevos = list(b.eventos["lista"])[antes:]
assert [(e["tipo"], e["usuario"]) for e in nuevos] == [("follow", "Nuevo")], "dos follows de la misma persona: una alerta; los de la primera vuelta de la lista, ninguna"

# la lista atrapa los follows que EventSub no avisa: solo los nuevos y recientes, del más viejo al más nuevo, y nunca dos veces
ahora = b.datetime.datetime(2026, 11, 10, 6, 0, tzinfo=b.datetime.timezone.utc).timestamp()
b.helix = lambda metodo, ruta, cuerpo=None: {"data": [
    {"user_id": "12", "user_name": "Recien", "followed_at": "2026-11-10T05:59:30Z"},
    {"user_id": "9", "user_name": "Nuevo", "followed_at": "2026-11-10T05:59:00Z"},  # ya avisado por EventSub
    {"user_id": "11", "user_name": "Oculto", "followed_at": "2026-11-10T05:58:00Z"},
    {"user_id": "3", "user_name": "DeAntes", "followed_at": "2026-10-01T00:00:00Z"},  # alguien dejó de seguir y apareció uno viejo
    {"user_id": "7", "user_name": "Viejo", "followed_at": "2026-01-01T00:00:00Z"}]}
antes = len(b.eventos["lista"])
b.revisar_lista("2", ahora)
b.revisar_lista("2", ahora)
assert [e["usuario"] for e in list(b.eventos["lista"])[antes:]] == ["Oculto", "Recien"]
b.alcances, b.helix, b.ws_conectar = reales_tw
b.follows["activo"] = False

# acciones de la vista de chat: cada una va al lugar justo, sale en el chat de la web y los errores vuelven en palabras
hechos, reales_ord = [], (b.helix, b.kick_api)
b.helix = lambda metodo, ruta, cuerpo=None: hechos.append(("twitch", metodo, ruta, cuerpo)) or {"data": [{"login": "tubot", "id": "1"}, {"login": "tucanal", "id": "2"}]}
b.kick_api = lambda metodo, ruta, cuerpo=None: hechos.append(("kick", metodo, ruta, cuerpo)) or {}
b.ids_twitch.clear()
antes = len(b.eventos["lista"])
assert b.ordenar({"accion": "borrar", "plataforma": "twitch", "mid": "abc-123", "usuario": "Ana"}) == ""
assert hechos[0][2].startswith("users?") and hechos[1][:2] == ("twitch", "DELETE") and hechos[1][2].endswith("broadcaster_id=2&moderator_id=1&message_id=abc-123")
assert b.ordenar({"accion": "timeout", "plataforma": "twitch", "uid": "42", "minutos": 10, "usuario": "Ana"}) == ""
assert hechos[2][3] == {"data": {"user_id": "42", "reason": "Desde el chat de Stream Kit", "duration": 600}}, "Twitch en segundos, sin volver a buscar los ids"
assert b.ordenar({"accion": "desbanear", "plataforma": "twitch", "uid": "42"}) == "" and hechos[3][1:3] == ("DELETE", "moderation/bans?broadcaster_id=2&moderator_id=1&user_id=42")
hechos.clear()
assert b.ordenar({"accion": "banear", "plataforma": "kick", "uid": 77}) == ""
assert hechos[0] == ("kick", "POST", "moderation/bans", {"broadcaster_user_id": b.CONFIG["kick_broadcaster_id"], "user_id": 77, "reason": "Desde el chat de Stream Kit"})
assert b.ordenar({"accion": "timeout", "plataforma": "kick", "uid": "77", "minutos": 10}) == "" and hechos[1][3]["duration"] == 10, "Kick en minutos"
assert b.ordenar({"accion": "borrar", "plataforma": "kick", "mid": "u-u-i-d"}) == "" and hechos[2][:3] == ("kick", "DELETE", "chat/u-u-i-d")
assert b.ordenar({"accion": "desbanear", "plataforma": "kick", "uid": "77"}) == "" and hechos[3][1:] == ("DELETE", "moderation/bans", {"broadcaster_user_id": b.CONFIG["kick_broadcaster_id"], "user_id": 77})
nuevos = list(b.eventos["lista"])[antes:]
assert [e["tipo"] for e in nuevos] == ["moderado"] * 7 and nuevos[0]["mid"] == "abc-123" and nuevos[1]["minutos"] == 10
def falla(codigo, cuerpo=b""):
    def f(*a, **k):
        raise urllib.error.HTTPError("u", codigo, "x", {}, io.BytesIO(cuerpo))
    return f
b.kick_api = falla(403)
assert "Configuración" in b.ordenar({"accion": "borrar", "plataforma": "kick", "mid": "x"})
assert "/mod tubot" in b.ordenar({"accion": "banear", "plataforma": "kick", "uid": "77"})
b.helix = falla(400, b'{"message": "The user specified in the user_id field is already banned."}')
assert b.ordenar({"accion": "banear", "plataforma": "twitch", "uid": "42"}) == "Twitch respondió 400: The user specified in the user_id field is already banned."
b.helix = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("sin internet"))
assert b.ordenar({"accion": "banear", "plataforma": "twitch", "uid": "42"}).startswith("No pude hablar con Twitch")
assert len(b.eventos["lista"]) == antes + 7, "lo que falló no sale como hecho"
b.helix, b.kick_api = reales_ord

textos = [t["texto"] for t in b.CONFIG["timers"]] + [c["respuesta"] for c in b.CONFIG["comandos"].values()] + [ayuda]
for t in textos:
    assert 0 < len(t) <= 500 and "\n" not in t and "¿" not in t and not t.endswith("."), t  # límite de Twitch y VOZ.md
print("ok")
