// Las piezas de las pantallas para OBS. Las usan el editor (/pantallas, con datos de muestra) y cada pantalla
// (/pantalla/<id>, en vivo). Qué opciones tiene cada pieza está en piezas.json (lo usan también la app y el MCP, para
// revisar lo que se guarda); la app lo sirve adentro de este archivo como window.PIEZAS_ESQUEMA. Acá, cómo se dibuja
// cada una. Todo lo que viene del chat va como texto.
(function () {
  const FORMATOS = { horizontal: [1920, 1080], vertical: [1080, 1920] };
  const FUENTES = {
    sistema: 'system-ui, "Segoe UI", sans-serif', mono: 'Consolas, "Cascadia Mono", monospace',
    impacto: 'Impact, "Arial Black", sans-serif', serif: 'Georgia, "Times New Roman", serif',
  };

  // valores sanos aunque la config esté rota
  const num = (v, min, max, def) => (Number.isFinite(Number(v)) ? Math.min(max, Math.max(min, Number(v))) : def);
  const color = (v, def) => (/^#[0-9a-f]{6}$/i.test(v || '') ? v : def);
  const rgba = (c, opacidad) => {
    c = color(c, '#000000');
    return `rgba(${parseInt(c.slice(1, 3), 16)}, ${parseInt(c.slice(3, 5), 16)}, ${parseInt(c.slice(5, 7), 16)}, ${num(opacidad, 0, 100, 0) / 100})`;
  };
  const el = (etiqueta, clase, texto) => {
    const e = document.createElement(etiqueta);
    if (clase) e.className = clase;
    if (texto !== undefined) e.textContent = texto;
    return e;
  };
  // una fuente de Google se pide una sola vez por página (en OBS hace falta internet, como para los emotes)
  const pedidas = new Set();
  function deGoogle(nombre) {
    nombre = String(nombre || '').trim();
    if (!/^[A-Za-z0-9 ]{1,60}$/.test(nombre)) return null;
    if (!pedidas.has(nombre)) {
      pedidas.add(nombre);
      const l = el('link');
      l.rel = 'stylesheet';
      l.href = 'https://fonts.googleapis.com/css2?family=' + nombre.replace(/ /g, '+') + '&display=swap';
      document.head.append(l);
    }
    return '"' + nombre + '", system-ui, sans-serif';
  }
  function letra(e, o) {
    e.style.fontFamily = (o.fuente === 'google' && deGoogle(o.fuente_google)) || FUENTES[o.fuente] || FUENTES.sistema;
    e.style.fontSize = num(o.tamano, 8, 300, 24) + 'px';
    e.style.color = color(o.color, '#ffffff');
  }
  const cifra = n => Number(n || 0).toLocaleString('es-AR');
  // {tema} → el texto compartido "tema". Antes de los primeros datos queda vacío; en el editor, uno que no existe se ve
  // como {tema}, así se nota que falta crearlo
  const rellenar = (texto, textos, demo) => String(texto || '').replace(/\{([a-z0-9_]{1,30})\}/g,
    (todo, k) => (textos && Object.prototype.hasOwnProperty.call(textos, k) ? textos[k] : demo ? todo : ''));
  const tieneTextos = texto => /\{[a-z0-9_]{1,30}\}/.test(texto || '');

  // Animaciones de entrada y salida (opciones entrada, salida, velocidad y retraso de cada pieza). La salida es la misma
  // animación al revés: "abajo" entra desde abajo y sale hacia abajo. Con "reducir movimiento" en Windows, nada se mueve.
  const MOVIMIENTOS = {
    aparecer: [{ opacity: 0 }, { opacity: 1 }],
    abajo: [{ opacity: 0, transform: 'translateY(24px)' }, { opacity: 1, transform: 'none' }],
    arriba: [{ opacity: 0, transform: 'translateY(-24px)' }, { opacity: 1, transform: 'none' }],
    izquierda: [{ opacity: 0, transform: 'translateX(-60px)' }, { opacity: 1, transform: 'none' }],
    derecha: [{ opacity: 0, transform: 'translateX(60px)' }, { opacity: 1, transform: 'none' }],
    zoom: [{ opacity: 0, transform: 'scale(.8)' }, { opacity: 1, transform: 'none' }],
    rebote: [{ opacity: 0, transform: 'scale(.5)' }, { opacity: 1, transform: 'scale(1.08)', offset: 0.6 },
             { opacity: 1, transform: 'scale(.97)', offset: 0.8 }, { opacity: 1, transform: 'none' }],
    abrir: [{ clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)' }],
  };
  const quieto = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hayAnimacion = nombre => !quieto && !!MOVIMIENTOS[nombre];
  /** Anima la entrada (o la salida, con sale) de un elemento. Devuelve cuándo termina. */
  function animar(e, o, sale, demora) {
    const nombre = sale ? o.salida : o.entrada;
    if (!hayAnimacion(nombre)) return Promise.resolve();
    return e.animate(MOVIMIENTOS[nombre], {
      duration: num(o.velocidad, 100, 3000, 400), delay: demora || 0, easing: 'cubic-bezier(.2, .9, .2, 1)',
      direction: sale ? 'reverse' : 'normal', fill: sale ? 'forwards' : 'backwards',
    }).finished.catch(() => {});
  }
  // un renglón que entra o sale de una lista (el chat): el lugar se abre o se cierra suave, así los demás no saltan
  function lugar(e, abre, ms) {
    if (quieto) return Promise.resolve();
    const alto = e.offsetHeight + 'px', cerrado = { height: '0px', marginTop: '-6px', paddingTop: '0px', paddingBottom: '0px' };
    return e.animate(abre ? [cerrado, { height: alto }] : [{ height: alto }, cerrado],
                     { duration: Math.min(ms, 300), easing: 'ease-out', fill: abre ? 'none' : 'forwards' }).finished.catch(() => {});
  }
  const conEmotes = (texto, plataforma, emotes) => (window.Emotes ? Emotes.pintar(texto, plataforma, emotes)
    : document.createTextNode(String(texto || '').replace(/\[emote:\d+:([^\]]+)\]/g, '$1')));

  // datos de muestra para el editor
  const MUESTRA = {
    viewers: { twitch: 128, kick: 45 }, seguidores: { twitch: 1520, kick: 310 }, en_vivo: true,
    stream: { follows: 12, subs: 3, bits: 500, kicks: 200 }, titulo: { twitch: 'Título de tu stream', kick: 'Título de tu stream' },
    textos: {}, demo: true,  // el editor pone acá los textos compartidos de verdad
  };
  const ahora = () => Date.now() / 1000;
  const CHAT_MUESTRA = [
    { tipo: 'chat', plataforma: 'twitch', usuario: 'espectador_uno', color: '#ff7f50', texto: 'Kappa qué jugada', emotes: '25:0-4' },
    { tipo: 'chat', plataforma: 'kick', usuario: 'desde_kick', color: '#53fc18', texto: 'buenísimo [emote:37226:KEKW]' },
    { tipo: 'chat', plataforma: 'twitch', usuario: 'otra_persona', color: '#1e90ff', texto: 'hola a todos 👋' },
    { tipo: 'chat', plataforma: 'twitch', usuario: 'un_mod', color: '#9acd32', texto: 'acuérdense de seguir el canal' },
  ];

  // cómo se lee cada alerta
  const ALERTAS = {
    follow: e => ['Nuevo seguidor', 'Ya es parte'],
    sub: e => ['Nueva sub', e.nivel === 'Prime' ? 'Con Prime' : e.nivel ? 'Nivel ' + e.nivel : ''],
    resub: e => ['Resub', e.cantidad ? cifra(e.cantidad) + ' meses' : ''],
    regalo: e => ['Regaló subs', cifra(e.cantidad || 1) + ((e.cantidad || 1) === 1 ? ' sub regalada' : ' subs regaladas')],
    raid: e => ['Raid', e.cantidad ? 'Llega con ' + cifra(e.cantidad) + ' espectadores' : 'Llega el raid'],
    bits: e => ['Bits', cifra(e.cantidad) + ' bits'],
    kicks: e => ['Kicks', cifra(e.cantidad) + ' kicks'],
  };
  const GRUPO = { follow: 'follows', sub: 'subs', resub: 'subs', regalo: 'subs', raid: 'raids', bits: 'apoyos', kicks: 'apoyos' };
  let audio;
  function sonar(fuerte) {
    try {
      audio = audio || new AudioContext();
      [523.25, 659.25, fuerte ? 1046.5 : 783.99].forEach((f, k) => {
        const o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + k * 0.07;
        o.type = 'triangle'; o.frequency.value = f;
        g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(0.16, t + 0.02); g.gain.exponentialRampToValueAtTime(0.001, t + 0.6);
        o.connect(g).connect(audio.destination); o.start(t); o.stop(t + 0.65);
      });
    } catch { /* sin audio, la alerta sale igual */ }
  }

  const EMOJI = /\p{Extended_Pictographic}(?:️|‍\p{Extended_Pictographic})*/gu;

  const PIEZAS = {
    chat: {
      crear(caja, o, ctx) {
        const lista = el('ol', 'pz-chat');
        caja.append(lista);
        const duracion = num(o.duracion, 0, 3600, 0) * 1000;
        function sacar(li) {
          if (!li.isConnected || li.classList.contains('pz-sale')) return;
          li.classList.add('pz-sale');
          const ms = num(o.velocidad, 100, 3000, 400);
          animar(li, o, true).then(() => (hayAnimacion(o.salida) ? lugar(li, false, ms) : null)).then(() => li.remove());
        }
        function agregar(e, viejo) {
          if (o.comandos && /^\s*!/.test(e.texto || '')) return;
          const li = el('li', 'pz-mensaje ' + (e.plataforma === 'kick' ? 'kick' : 'twitch'));
          li.mensaje = e;
          li.style.background = rgba(o.fondo, o.opacidad);
          li.style.borderRadius = num(o.radio, 0, 40, 6) + 'px';
          letra(li, o);
          if (o.plataforma) li.classList.add('pz-rayita');
          const quien = el('span', 'pz-quien', e.usuario);
          quien.style.color = o.nombres === 'fijo' ? color(o.color_nombre, '#a78bfa') : color(e.color, color(o.color_nombre, '#a78bfa'));
          li.append(quien, conEmotes(e.texto, e.plataforma, e.emotes));
          lista.append(li);
          if (!viejo && hayAnimacion(o.entrada)) {  // lo que ya estaba al abrir aparece quieto
            lugar(li, true, num(o.velocidad, 100, 3000, 400));
            animar(li, o);
          }
          while (lista.children.length > 60) lista.firstChild.remove();
          if (duracion && !ctx.demo) setTimeout(() => sacar(li), Math.max(0, duracion - (Date.now() - (e.t || ahora()) * 1000)));
        }
        if (ctx.demo) CHAT_MUESTRA.forEach(e => agregar(e, true));
        let muestra = 0;
        return {
          probar() {  // en el editor: un mensaje que entra y, a los 2 s, sale
            const e = Object.assign({}, CHAT_MUESTRA[muestra++ % CHAT_MUESTRA.length], { t: ahora() });
            agregar(e);
            const li = lista.lastChild;
            setTimeout(() => sacar(li), 2000);
          },
          evento(e, viejo) {
            if (e.tipo === 'chat' && e.usuario) {
              if (!viejo || !duracion || Date.now() - e.t * 1000 < duracion) agregar(e, viejo);
            } else if (e.tipo === 'moderado' && e.accion !== 'desbanear') {  // lo borrado o baneado se va de la pantalla
              [...lista.children].forEach(li => {
                const m = li.mensaje;
                if (m && m.plataforma === e.plataforma && (e.accion === 'borrar' ? m.mid === e.mid : String(m.uid) === String(e.uid))) sacar(li);
              });
            }
          },
          emotes() {  // BTTV, FFZ y 7TV llegaron: lo que ya está se vuelve a dibujar
            [...lista.children].forEach(li => {
              const q = li.querySelector('.pz-quien');
              if (li.mensaje) li.replaceChildren(q, conEmotes(li.mensaje.texto, li.mensaje.plataforma, li.mensaje.emotes));
            });
          },
        };
      },
    },

    alertas: {
      crear(caja, o, ctx) {
        const cola = [];
        let ocupada = false, reloj;
        const dura = num(o.duracion, 2, 60, 7) * 1000;
        function mostrar(e, fija) {
          const [tipo, detalle] = ALERTAS[e.tipo](e);
          const acento = color(o.acento, '#8b5cf6');
          const a = el('div', 'pz-alerta');
          a.style.background = rgba(o.fondo, o.opacidad);
          a.style.borderColor = acento;
          const cab = el('div', 'pz-alerta-tipo');
          cab.append(el('span', '', tipo), el('span', '', e.plataforma === 'kick' ? 'Kick' : 'Twitch'));
          cab.style.color = acento;
          const quien = el('div', 'pz-alerta-quien', e.usuario);
          letra(quien, o);
          const det = el('div', 'pz-alerta-detalle', detalle);
          det.style.color = color(o.color, '#ffffff');
          a.append(cab, quien, det);
          if (e.mensaje) {
            const m = el('div', 'pz-alerta-mensaje');
            m.style.color = color(o.color, '#ffffff');
            m.append(conEmotes(e.mensaje, e.plataforma, e.emotes));
            a.append(m);
          }
          caja.replaceChildren(a);
          if (!fija) animar(a, o);
          return a;
        }
        function sale(a) {
          return animar(a, o, true).then(() => a.remove());
        }
        function siguiente() {
          if (ocupada || !cola.length) return;
          ocupada = true;
          const e = cola.shift();
          const a = mostrar(e);
          if (o.sonido) sonar(e.tipo !== 'follow');
          reloj = setTimeout(() => sale(a).then(() => { ocupada = false; siguiente(); }), dura);
        }
        const DEMO = { tipo: 'resub', plataforma: 'twitch', usuario: 'espectador_uno', cantidad: 7, mensaje: 'vamos Kappa', emotes: '25:6-10' };
        if (ctx.demo) mostrar(DEMO, true);
        return {
          probar() {  // en el editor: la alerta entra, queda 2 s y sale
            clearTimeout(reloj);
            const a = mostrar(DEMO);
            reloj = setTimeout(() => sale(a).then(() => { if (!caja.firstChild) mostrar(DEMO, true); }), 2000);
          },
          evento(e, viejo) {
            if (viejo || !ALERTAS[e.tipo] || !e.usuario || !o[GRUPO[e.tipo]]) return;
            cola.push(e);
            siguiente();
          },
          quitar() { clearTimeout(reloj); },
        };
      },
    },

    marco: {
      crear(caja, o) {
        let t;
        const m = el('div', 'pz-marco');
        const radio = num(o.radio, 0, 200, 12);
        m.style.border = num(o.grosor, 0, 60, 4) + 'px solid ' + color(o.borde, '#8b5cf6');
        m.style.borderRadius = radio + 'px';
        if (o.sombra) m.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.55)';
        caja.append(m);
        if (o.titulo) {
          t = el('div', 'pz-marco-titulo', rellenar(o.titulo));
          letra(t, o);
          t.style.background = rgba(o.fondo, o.opacidad);
          t.style.borderRadius = Math.min(radio, 12) + 'px';
          caja.append(t);
        }
        return tieneTextos(o.titulo) ? { datos(d) { t.textContent = rellenar(o.titulo, d.textos, d.demo); } } : {};
      },
    },

    texto: {
      crear(caja, o) {
        const b = bloque(o, rellenar(o.texto));
        caja.append(b);
        return tieneTextos(o.texto) ? { datos(d) { b.firstChild.textContent = rellenar(o.texto, d.textos, d.demo); } } : {};
      },
    },

    titulo: {
      crear(caja, o) {
        const b = bloque(o, '');
        caja.append(b);
        return { datos(d) { b.firstChild.textContent = (d.titulo || {})[o.plataforma] || ''; } };
      },
    },

    viewers: {
      crear(caja, o) {
        const b = bloque(o, '');
        caja.append(b);
        return {
          datos(d) {
            const v = d.viewers || {}, hay = ['twitch', 'kick'].filter(p => typeof v[p] === 'number');
            let texto = '';
            if (o.mostrar === 'suma' && hay.length) texto = cifra(hay.reduce((s, p) => s + v[p], 0));
            else if (o.mostrar === 'twitch' || o.mostrar === 'kick') texto = typeof v[o.mostrar] === 'number' ? cifra(v[o.mostrar]) : '';
            else texto = hay.map(p => (p === 'kick' ? 'Kick ' : 'Twitch ') + cifra(v[p])).join(' · ');
            b.firstChild.textContent = texto ? [o.etiqueta, texto].filter(Boolean).join(': ') : '';
            b.style.visibility = texto ? '' : 'hidden';  // sin stream no se ve
          },
        };
      },
    },

    meta: {
      crear(caja, o) {
        const m = el('div', 'pz-meta');
        m.style.background = rgba(o.fondo, o.opacidad);
        m.style.borderRadius = num(o.radio, 0, 60, 10) + 'px';
        letra(m, o);
        const arriba = el('div', 'pz-meta-arriba'), titulo = el('span', 'pz-meta-titulo', rellenar(o.titulo)), cuenta = el('span', 'pz-meta-cuenta');
        arriba.append(titulo, cuenta);
        const barra = el('div', 'pz-meta-barra'), lleno = el('i');
        lleno.style.background = color(o.barra, '#22c55e');
        barra.append(lleno);
        m.append(arriba, barra);
        caja.append(m);
        const objetivo = num(o.objetivo, 1, 1e8, 100);
        function poner(n) {
          cuenta.textContent = cifra(n) + ' / ' + cifra(objetivo);
          lleno.style.width = Math.min(100, (n / objetivo) * 100) + '%';
        }
        poner(o.fuente_meta === 'manual' ? num(o.actual, 0, 1e8, 0) : 0);
        return {
          datos(d) {
            if (tieneTextos(o.titulo)) titulo.textContent = rellenar(o.titulo, d.textos, d.demo);
            if (o.fuente_meta === 'manual') return;
            const s = d.seguidores || {}, st = d.stream || {};
            const n = o.fuente_meta === 'seguidores' ? (s.twitch || 0) + (s.kick || 0)
              : o.fuente_meta === 'seguidores_twitch' ? s.twitch : o.fuente_meta === 'seguidores_kick' ? s.kick : st[o.fuente_meta];
            poner(Number(n) || 0);
          },
        };
      },
    },

    lluvia: {
      crear(caja, o, ctx) {
        caja.classList.add('pz-lluvia');
        const tam = num(o.tamano, 16, 300, 56), dura = num(o.duracion, 1, 20, 4);
        function soltar(cosa) {
          const g = el('div', 'pz-gota');
          g.append(cosa);
          g.style.left = Math.random() * Math.max(0, caja.clientWidth - tam) + 'px';
          g.style.fontSize = tam + 'px';
          g.style.setProperty('--alto', caja.clientHeight + tam * 2 + 'px');
          g.style.setProperty('--giro', (Math.random() * 60 - 30) + 'deg');
          g.style.animationDuration = dura * (0.8 + Math.random() * 0.4) + 's';
          g.style.animationDelay = Math.random() * 0.6 + 's';
          caja.append(g);
          g.addEventListener('animationend', () => g.remove());
        }
        function llover(e) {
          const cosas = [];
          if (o.emotes) {
            const f = conEmotes(e.texto, e.plataforma, e.emotes);
            f.querySelectorAll && f.querySelectorAll('img').forEach(i => { i.style.height = tam + 'px'; cosas.push(i); });
          }
          if (o.emojis) (String(e.texto || '').replace(/\[emote:[^\]]*\]/g, '').match(EMOJI) || []).forEach(x => cosas.push(document.createTextNode(x)));
          cosas.slice(0, num(o.cantidad, 1, 30, 6)).forEach(soltar);
        }
        let demo;
        if (ctx.demo) {
          const ejemplos = ['🎉', '🔥', '😂', '👏', '💜', '🙌'];
          demo = setInterval(() => soltar(document.createTextNode(ejemplos[Math.floor(Math.random() * ejemplos.length)])), 700);
        }
        return {
          evento(e, viejo) { if (!viejo && e.tipo === 'chat') llover(e); },
          quitar() { clearInterval(demo); },
        };
      },
    },

    ultimo: {
      crear(caja, o, ctx) {
        const b = bloque(o, '');
        caja.append(b);
        const TIPOS = { follow: ['follow'], sub: ['sub', 'resub', 'regalo'], apoyo: ['bits', 'kicks'] };
        TIPOS.todo = [...TIPOS.follow, ...TIPOS.sub, ...TIPOS.apoyo];
        const poner = nombre => { b.firstChild.textContent = [o.etiqueta, nombre].filter(Boolean).join(': '); b.style.visibility = nombre ? '' : 'hidden'; };
        let actual = ctx.demo ? 'nombre_de_ejemplo' : '', cambio = Promise.resolve();
        poner(actual);
        function cambiar(nombre) {  // uno atrás del otro: si llegan dos juntos, se ven los dos
          cambio = cambio.then(() => (actual ? animar(b, o, true) : null)).then(() => { actual = nombre; poner(nombre); return animar(b, o); });
        }
        return {
          probar() { cambiar(actual === 'nombre_de_ejemplo' ? 'otro_nombre' : 'nombre_de_ejemplo'); },
          evento(e, viejo) {
            if (!(TIPOS[o.que] || TIPOS.follow).includes(e.tipo) || !e.usuario) return;
            if (viejo) { actual = e.usuario; poner(e.usuario); } else cambiar(e.usuario);
          },
        };
      },
    },

    cuenta: {
      crear(caja, o, ctx) {
        const b = bloque(o, '');
        caja.append(b);
        const fin = Date.now() + num(o.minutos, 1, 600, 10) * 60000;
        let textos, demo;
        function tic() {
          const falta = Math.max(0, Math.ceil((fin - Date.now()) / 1000));
          const reloj = Math.floor(falta / 60) + ':' + String(falta % 60).padStart(2, '0');
          b.firstChild.textContent = falta ? [rellenar(o.etiqueta, textos, demo), reloj].filter(Boolean).join(' ') : rellenar(o.final, textos, demo);
        }
        tic();
        const t = ctx.demo ? null : setInterval(tic, 250);
        return { quitar() { clearInterval(t); }, datos(d) { textos = d.textos; demo = d.demo; tic(); } };
      },
    },

    imagen: {
      crear(caja, o) {
        const v = String(o.imagen || '');
        if (!v) {
          const vacia = el('div', 'pz-imagen-vacia', 'Elegí o subí una imagen');
          caja.append(vacia);
          return {};
        }
        const i = el('img', 'pz-imagen');
        i.alt = '';
        i.src = /^https:\/\//.test(v) ? v : '/imagenes/' + encodeURIComponent(v);
        i.style.objectFit = { cubrir: 'cover', estirar: 'fill' }[o.ajuste] || 'contain';
        i.style.opacity = num(o.opacidad, 0, 100, 100) / 100;
        i.style.borderRadius = num(o.radio, 0, 500, 0) + 'px';
        caja.append(i);
        return {};
      },
    },
  };

  // un bloque de texto de una línea, con fondo y alineación
  function bloque(o, texto) {
    const b = el('div', 'pz-bloque');
    b.append(el('span', '', texto));
    letra(b, o);
    b.style.background = rgba(o.fondo, o.opacidad);
    b.style.justifyContent = { centro: 'center', derecha: 'flex-end' }[o.alinear] || 'flex-start';
    b.style.textAlign = { centro: 'center', derecha: 'right' }[o.alinear] || 'left';
    b.style.fontWeight = o.negrita ? '700' : '400';
    if (o.mayusculas) b.style.textTransform = 'uppercase';
    return b;
  }

  function predeterminadas(tipo) {
    const o = {};
    PIEZAS[tipo].opciones.forEach(x => { o[x.clave] = x.def; });
    return o;
  }

  // pone una pieza en el lienzo. ctx.demo: datos de muestra, para el editor
  function montar(lienzo, pieza, ctx) {
    const def = PIEZAS[pieza.tipo];
    const caja = el('div', 'pz-caja');
    caja.dataset.tipo = pieza.tipo;  // para el CSS propio: [data-tipo="chat"] o la clase que le pongas
    if (/^[a-zA-Z][\w-]{0,39}$/.test(pieza.clase || '')) caja.classList.add(pieza.clase);
    Object.assign(caja.style, { left: pieza.x + 'px', top: pieza.y + 'px', width: pieza.w + 'px', height: pieza.h + 'px' });
    lienzo.append(caja);
    if (!def) return { caja };
    const o = Object.assign(predeterminadas(pieza.tipo), pieza.op);
    const viva = Object.assign({ caja }, def.crear(caja, o, ctx || {}));
    if (ctx && ctx.demo && viva.datos) viva.datos(MUESTRA);
    // las fijas (las que tienen "retraso") entran enteras cuando carga la pantalla, después de su espera
    if (def.opciones.some(x => x.clave === 'retraso')) {
      const entrar = () => animar(caja, o, false, num(o.retraso, 0, 10000, 0));
      if (!(ctx && ctx.quieta)) entrar();
      if (!viva.probar) viva.probar = entrar;
    }
    return viva;
  }

  const estilo = document.createElement('style');
  estilo.textContent = `
    .pz-caja { position: absolute; overflow: hidden; }
    .pz-chat { position: absolute; inset: 0; margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column;
               justify-content: flex-end; gap: 6px; }
    .pz-mensaje { flex: none; padding: 8px 12px; line-height: 1.4; overflow-wrap: anywhere; overflow: hidden; }
    .pz-mensaje.pz-rayita.twitch { box-shadow: inset 4px 0 #9146ff; padding-left: 14px; }
    .pz-mensaje.pz-rayita.kick { box-shadow: inset 4px 0 #53fc18; padding-left: 14px; }
    .pz-quien { font-weight: 700; margin-right: 8px; }
    .pz-caja .emote { height: 1.6em; vertical-align: middle; margin: -0.25em 0; }
    .pz-alerta { position: absolute; inset: 0; box-sizing: border-box; border: 2px solid; border-radius: 10px; padding: 16px 22px;
                 display: flex; flex-direction: column; justify-content: center; gap: 4px; overflow: hidden; font-family: system-ui, sans-serif;
                 box-shadow: 0 18px 44px rgba(0, 0, 0, .55); }
    .pz-alerta-tipo { display: flex; justify-content: space-between; font-size: 14px; font-weight: 700; letter-spacing: .2em; text-transform: uppercase; }
    .pz-alerta-quien { font-weight: 800; line-height: 1.05; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .pz-alerta-detalle { font-size: 18px; opacity: .85; }
    .pz-alerta-mensaje { font-size: 16px; opacity: .85; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .pz-marco { position: absolute; inset: 0; box-sizing: border-box; }
    .pz-marco-titulo { position: absolute; left: 16px; top: 0; transform: translateY(-50%); padding: 4px 12px; white-space: nowrap; font-weight: 700; }
    .pz-caja:has(.pz-marco-titulo) { overflow: visible; }
    .pz-bloque { position: absolute; inset: 0; display: flex; align-items: center; padding: 0 16px; box-sizing: border-box; white-space: nowrap; overflow: hidden; }
    .pz-bloque span { overflow: hidden; text-overflow: ellipsis; }
    .pz-meta { position: absolute; inset: 0; box-sizing: border-box; padding: 14px 18px; display: flex; flex-direction: column; justify-content: center; gap: 10px; }
    .pz-meta-arriba { display: flex; justify-content: space-between; gap: 12px; font-weight: 700; white-space: nowrap; }
    .pz-meta-titulo { overflow: hidden; text-overflow: ellipsis; }
    .pz-meta-barra { height: 14px; border-radius: 7px; background: rgba(255, 255, 255, .15); overflow: hidden; }
    .pz-meta-barra i { display: block; height: 100%; width: 0; border-radius: 7px; transition: width .8s ease; }
    .pz-gota { position: absolute; top: 0; line-height: 1; animation: pz-cae linear forwards; transform: translateY(-120%); }
    .pz-gota img { display: block; }
    .pz-imagen { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
    .pz-imagen-vacia { position: absolute; inset: 0; display: grid; place-items: center; border: 2px dashed rgba(255, 255, 255, .35);
                       color: rgba(255, 255, 255, .7); font: 600 20px system-ui, sans-serif; background: rgba(0, 0, 0, .35); }
    @keyframes pz-cae { from { transform: translateY(-120%) rotate(0); } to { transform: translateY(var(--alto)) rotate(var(--giro)); } }
`;
  document.head.append(estilo);

  // El CSS propio de una pantalla queda adentro del lienzo (raiz): en el editor no cambia el resto de la página, y se ve
  // igual que en OBS. body, html y :root apuntan al lienzo. @import queda arriba, donde tiene que estar.
  function css(texto, raiz) {
    texto = String(texto || '');
    const IMPORT = /@import\s+[^;]+;/g;
    const imports = (texto.match(IMPORT) || []).join('\n');
    const hoja = new CSSStyleSheet();
    try { hoja.replaceSync(texto.replace(IMPORT, '')); } catch { return imports; }
    const alcance = sel => sel.split(',').map(s => {
      s = s.trim();
      const r = s.replace(/^(html|body|:root)(?![\w-])/, raiz);
      return r === s ? raiz + ' ' + s : r;
    }).join(', ');
    const reglas = lista => [...lista].map(r => {
      if (r instanceof CSSStyleRule) return alcance(r.selectorText) + r.cssText.slice(r.selectorText.length);
      if (r instanceof CSSMediaRule) return '@media ' + r.conditionText + ' {\n' + reglas(r.cssRules) + '\n}';
      if (r instanceof CSSSupportsRule) return '@supports ' + r.conditionText + ' {\n' + reglas(r.cssRules) + '\n}';
      return r.cssText;  // @font-face, @keyframes
    }).join('\n');
    return imports + '\n' + reglas(hoja.cssRules);
  }
  function ponerCss(texto, raiz) {
    let s = document.getElementById('css-propio');
    if (!s) { s = el('style'); s.id = 'css-propio'; document.head.append(s); }
    s.textContent = css(texto, raiz);
  }

  // qué opciones tiene cada pieza: de piezas.json, que la app pone antes de este archivo
  const ESQUEMA = window.PIEZAS_ESQUEMA || {};
  Object.keys(PIEZAS).forEach(t => Object.assign(PIEZAS[t], ESQUEMA[t] || { nombre: t, w: 400, h: 200, opciones: [] }));

  window.Piezas = { PIEZAS, FORMATOS, MUESTRA, montar, predeterminadas, css, ponerCss, rellenar };
})();
