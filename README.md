# Stream Kit

Herramientas para streamear en **Twitch y Kick** desde Windows, todo en tu PC, sin servidores ni cuentas de terceros:

- **Delay a demanda y multistream**: OBS transmite una vez a la app y la app reenvía, sin recodificar, a Twitch, Kick,
  YouTube, Facebook, TikTok, Instagram, X o cualquier RTMP, todas con el mismo delay. Con un botón, un atajo o una tecla
  de Stream Deck o StreamDock le ponés delay sin cortar el stream.
- **Bot de chat** en Twitch y Kick a la vez: comandos, mensajes automáticos, ban a los bots que venden viewers y
  `!clip`.
- **Chat unificado** de las dos plataformas, con follows, subs, raids y bits, campanita con filtros y moderación con
  click derecho. Sirve como panel de OBS.
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

Pruebas, sin internet y sin tocar tu config ni tu OBS: `python test_chatbot.py`, `test_cuentas.py`, `test_panel.py`,
`test_canal.py`, `test_metricas.py`, `test_obs.py`, `test_deck.py` y `test_delay.py` (este último simula OBS durante
unos minutos).

Para armar el .exe en tu PC: `python -m pip install pyinstaller` y `python build.py`. Deja el zip en `dist/`, listo
para subir como release con `gh release create`.

## Licencia

MIT. Ver [LICENSE](LICENSE).
