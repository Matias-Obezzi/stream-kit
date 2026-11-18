# Stream Kit

Herramientas para streamear en **Twitch y Kick** desde Windows, todo en tu PC, sin servidores ni cuentas de terceros:

- **Delay a demanda y multistream**: OBS transmite una vez a la app y la app reenvía, sin recodificar, a Twitch, Kick,
  YouTube, Facebook, TikTok, Instagram, X o cualquier RTMP, todas con el mismo delay. Con un botón, un atajo o una tecla
  de Stream Deck o StreamDock le ponés delay sin cortar el stream.
- **Bot de chat** en Twitch y Kick a la vez: comandos, mensajes automáticos, ban a los bots que venden viewers y
  `!clip`.
- **Chat unificado** de las dos plataformas, con follows, subs, raids y bits, campanita con filtros y moderación con
  click derecho. Muestra los emotes de Twitch, Kick, BTTV, FFZ y 7TV (los globales y los de tu canal). Muestra cuántos miran y, al tocarlo, quiénes están en el chat. Sirve como panel de OBS.
- **Pantallas para OBS**: armás cada escena en un lienzo, arrastrando piezas (chat, alertas, marcos de ventana,
  textos, título del stream, espectadores, metas, último seguidor, cuenta regresiva y lluvia de emojis), y la sumás a
  OBS con un solo link.
- **Título, categoría y etiquetas** cambiados de una vez en Twitch y Kick.
- **Consumo**: cuánta CPU, memoria y red usa cada parte (el delay, el bot, cada envío a una plataforma).
- **Se configura solo**: un botón deja OBS listo, otros suman el panel y el chat adentro de OBS, y otro instala la tecla
  de delay en Stream Deck o StreamDock.

Todo se maneja desde una web local (http://127.0.0.1:8080), con un tutorial en cada pantalla.

## Instalar

1. Bajá el último `StreamKit-…-windows.zip` de [Releases](../../releases) y descomprimilo donde quieras, por ejemplo
   en `Documentos\StreamKit`.
2. Instalá **ffmpeg**. En una terminal: `winget install ffmpeg`.
3. Abrí `StreamKit.exe`. Queda un ícono en la bandeja, al lado del reloj, y se abre el panel en el navegador.

Windows puede avisar que el programa no es conocido, porque no está firmado: **Más información → Ejecutar de todas
formas**. Algunos antivirus desconfían de los programas hechos con PyInstaller; si te lo frena, podés correrlo desde el
código fuente (más abajo).

Para que arranque con Windows, poné un acceso directo a `StreamKit.exe` en la carpeta de inicio (`Win + R` →
`shell:startup`). Para actualizar, descomprimí la versión nueva encima: tu config y tus sesiones no se pisan.

## Configurar

Todo desde el panel, sin terminal:

1. **Configuración**: tiene una pestaña por plataforma. En Twitch y en Kick, creá una app (la pantalla explica cómo,
   son gratis) y pegá sus claves.
   Después conectá las cuentas: la tuya, para cambiar el título, y la del bot, para que hable y modere. El bot puede
   usar tu propia cuenta, y hace de mod y de bot con tu nombre, o una cuenta nueva solo para él, así sus mensajes se
   distinguen de los tuyos. Si solo usás una plataforma, dejá la otra vacía.
2. En la misma pantalla, cada plataforma (Twitch, Kick, YouTube, Facebook, TikTok, Instagram, X) tiene su pestaña con
   su **Transmisión**: pegá ahí tu clave de transmisión. **Cambiar clave** la reemplaza sin quitarla, para las
   plataformas que dan una nueva en cada directo. Cualquier otro servidor RTMP va en la pestaña **Otras**. En
   **Delay → Plataformas** se ve cómo está cada una y se pausa la que quieras sin cortar las demás.
3. **OBS**: tocá **Autoconfigurar OBS** en Configuración. Deja OBS transmitiendo a Stream Kit, sin transmisión mejorada
   y con la pista de VOD de Twitch disponible. Si OBS está abierto, avisa (y avisa dos veces si está transmitiendo,
   porque cerrarlo corta el stream), lo cierra, lo configura y lo vuelve a abrir. Si OBS ya transmitía a una
   plataforma, esa clave pasa a Stream Kit. Antes guarda una copia en `%APPDATA%\obs-studio\stream-kit-respaldo`.
   A mano: Ajustes → Emisión → Servicio **Personalizado**, servidor `rtmp://127.0.0.1:1935/live`, clave `stream`, sin
   transmisión mejorada (multipista) y con H.264.
4. Si el bot usa una cuenta aparte, hacelo moderador en tu chat: `/mod` y el nombre del bot, en Twitch y en Kick.

Poné en `config.json` (al lado del .exe) la misma resolución, FPS y bitrate que en OBS: el video que se muestra
mientras se activa el delay se arma con esos valores.

### Pista de VOD de Twitch (opcional)

Para que el VOD de Twitch salga sin la música que pasás en vivo, OBS tiene que mandar la pista de VOD, y con un servidor
personalizado no la ofrece. **Autoconfigurar OBS** la habilita (agrega `EnableCustomServerVodTrack=true` en `[General]`
de `global.ini` y de `user.ini`). Después, en OBS: Ajustes → Salida → Emisión, marcá **Pista de VOD de Twitch** y elegí
qué pista usa, una que no tenga la música. La app se la manda solo a Twitch; las demás plataformas reciben el audio
principal.

## Pantallas para OBS

En **Pantallas** armás lo que va arriba de tu juego o tu cámara. Cada pantalla es un lienzo de 1920 × 1080 (o
1080 × 1920 para vertical) donde sumás piezas y las acomodás arrastrando; la bolita de la esquina cambia el tamaño y el
panel de la derecha, los colores y los textos.

| Pieza | Qué hace |
| --- | --- |
| Chat | Twitch y Kick juntos, con emotes. Se puede borrar solo a los X segundos; lo que borra o banea un mod se va |
| Alertas | Follows, subs, regalos, raids, bits y kicks, con sonido opcional |
| Marco de ventana | Un borde con título para la cámara o una ventana que va debajo en OBS |
| Texto y título del stream | Un texto libre o el título actual de Twitch o Kick |
| Espectadores | Cuántos miran en cada plataforma, o la suma |
| Meta | Seguidores, o follows, subs, bits o kicks de este stream, o una cuenta a mano |
| Último seguidor o sub | El nombre del último que siguió, se suscribió o mandó bits o kicks |
| Cuenta regresiva | Para la pantalla de "empezando" |
| Lluvia de emojis | Los emojis y emotes del chat caen por la pantalla |

Guardá y copiá el link: en OBS, **Fuente → Navegador**, pegalo y poné el mismo tamaño que la pantalla. Lo vacío queda
transparente. Si después la cambiás y guardás, OBS la actualiza solo en unos segundos.

**CSS propio**: cada pantalla tiene su CSS, que vale solo adentro de ella y se ve al toque en el editor. Cada pieza
tiene `data-tipo` (`[data-tipo="chat"]`) y la clase que le pongas en su panel; adentro hay clases como `.pz-mensaje`,
`.pz-alerta` o `.pz-meta-barra i` (la lista está en la pantalla). Para pisar los colores del panel, `!important`.

### Con una IA (MCP)

La app sirve un MCP en `http://127.0.0.1:8080/mcp`, así un agente puede armar y cambiar las pantallas por vos: ve qué
piezas y opciones hay, crea, cambia (también el CSS) y borra pantallas, y lee los datos en vivo. Solo contesta a esta
PC. En Claude Code:

```
claude mcp add --transport http stream-kit http://127.0.0.1:8080/mcp
```

En otros clientes, agregá un servidor MCP de tipo HTTP con esa dirección.

Para agentes también está [llms.txt](llms.txt): qué pueden hacer, cómo es una pantalla, el CSS y los endpoints para
overlays propios. Con la app abierta, http://127.0.0.1:8080/llms.txt suma la lista de cada pieza con sus opciones.

## Controles del delay

- **Bandeja**: clic izquierdo abre el panel; clic derecho, activar delay, volver a vivo o salir. **Salir** cierra todo.
- **Atajos**: `Ctrl+Shift+F9` activa el delay y `Ctrl+Shift+F10` vuelve a vivo (se cambian en `config.json`).
- **Stream Deck o StreamDock**: en Configuración → **Botonera**, tocá **Instalar el botón**. Se instala en las que
  encuentre y reinicia su programa. Después arrastrá **Stream Kit → Delay on/off** a una tecla: muestra el estado del
  delay y al tocarla lo activa o lo saca.
- **Adentro de OBS**: en Configuración → OBS, **Agregar el panel a OBS** y **Agregar el chat a OBS** los suman como paneles
  (Ver → Paneles). Igual que Autoconfigurar OBS, si está abierto avisa, lo cierra y lo vuelve a abrir.
- **Desde el celular**: con `"panel_lan": true` en `config.json`, el inicio muestra un link con clave para abrir el
  panel desde el celular en el mismo Wi-Fi. La configuración de claves y cuentas solo se abre desde la PC.

Mientras se activa el delay se muestra un video, una imagen o un texto, o se repiten los últimos segundos (modo
repetir). **Volver a vivo** corta al instante y tu audiencia salta al presente.

## Qué queda en tu PC

La config, las sesiones de Twitch y Kick y los logs quedan al lado del .exe (`config.json` y la carpeta `bot/`). No se
suben a ningún lado; no los compartas, porque con ellos se puede escribir en tu chat y cambiar tu canal.
Para guardarlos en otra carpeta, abrí el .exe con `--datos=CARPETA` (por ejemplo, en el acceso directo).

Usa los puertos 8080 (panel), 1935 (OBS) y 47612 a 47615 (internos), solo en esta PC.

## Desde el código fuente

Necesita Python 3.11 o más nuevo y ffmpeg. No usa dependencias.

```
pythonw app.py
```

| Carpeta | Qué tiene |
| --- | --- |
| `app.py` | Lo que arranca todo: el guardián, el delay o el bot según la opción |
| `streamkit/` | El código: `delay.py` (OBS, delay y la web), `chatbot.py` (el bot), `guardian.py`, `cuentas.py` (claves y logins), `canal.py` (título), `pantallas.py`, `mcp.py`, `obs.py`, `deck.py`, `metricas.py` |
| `web/` | Las pantallas del panel |
| `recursos/` | Íconos, el botón de Stream Deck y StreamDock, y las configs de ejemplo |
| `tests/` | Las pruebas |
| `datos/` | Tu config, tus sesiones y los logs cuando corrés desde el código. No se sube |

Pruebas, sin internet y sin tocar tu config ni tu OBS: `python tests/test_chatbot.py`, y lo mismo con `test_cuentas`,
`test_panel`, `test_pantallas`, `test_mcp`, `test_canal`, `test_metricas`, `test_obs`, `test_deck` y `test_delay` (este último simula OBS durante unos
minutos).

Para armar el .exe en tu PC: `python -m pip install pyinstaller` y `python build.py`. Deja el zip en `dist/`, listo
para subir como release con `gh release create`.

## Licencia

MIT. Ver [LICENSE](LICENSE).
