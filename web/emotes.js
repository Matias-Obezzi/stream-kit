// Emotes en el chat y en las alertas: los de Twitch y Kick, y los de BTTV, FFZ y 7TV (globales y de tu canal).
// Uso: Emotes.cargar('http://127.0.0.1:8080') una vez, y Emotes.pintar(texto, plataforma, emotes) devuelve el texto con
// las imágenes, para sumar a un elemento. Nunca arma HTML con el texto: los nombres y mensajes van como texto.
(function () {
  const mapas = { twitch: {}, kick: {} };  // nombre -> imagen; los del canal pisan a los globales
  const json = url => fetch(url).then(r => (r.ok ? r.json() : null)).catch(() => null);
  const bttv = e => 'https://cdn.betterttv.net/emote/' + e.id + '/1x';
  const ffz = e => e.images && e.images['1x'];
  const stv = e => 'https://cdn.7tv.app/emote/' + e.id + '/1x.webp';
  function sumar(plataformas, lista, url) {
    for (const e of Array.isArray(lista) ? lista : []) {
      const nombre = e.code || e.name, imagen = url(e);
      if (nombre && typeof imagen === 'string') plataformas.forEach(p => { mapas[p][nombre] = imagen; });
    }
  }

  async function cargar(api) {
    let ids = {};
    try { ids = (await (await fetch(api + '/api/bot')).json()).bot.ids || {}; } catch {}
    const t = ids.twitch, k = ids.kick;
    const [bg, fg, sg, bc, fc, st, sk] = await Promise.all([
      json('https://api.betterttv.net/3/cached/emotes/global'),
      json('https://api.betterttv.net/3/cached/frankerfacez/emotes/global'),
      json('https://7tv.io/v3/emote-sets/global'),
      t && json('https://api.betterttv.net/3/cached/users/twitch/' + t),
      t && json('https://api.betterttv.net/3/cached/frankerfacez/users/twitch/' + t),
      t && json('https://7tv.io/v3/users/twitch/' + t),
      k && json('https://7tv.io/v3/users/kick/' + k),
    ]);
    // BTTV y FFZ son de Twitch; 7TV también anda en Kick
    sumar(['twitch'], fg, ffz);
    sumar(['twitch'], bg, bttv);
    sumar(['twitch', 'kick'], sg && sg.emotes, stv);
    sumar(['twitch'], fc, ffz);
    sumar(['twitch'], bc && [...(bc.channelEmotes || []), ...(bc.sharedEmotes || [])], bttv);
    sumar(['twitch'], st && st.emote_set && st.emote_set.emotes, stv);
    sumar(['kick'], sk && sk.emote_set && sk.emote_set.emotes, stv);
    if (!t && !k) setTimeout(() => cargar(api), 60000);  // el bot todavía no arrancó: los del canal llegan después
  }

  function imagen(url, nombre) {
    const i = document.createElement('img');
    i.className = 'emote'; i.src = url; i.alt = nombre; i.title = nombre;
    return i;
  }

  // Twitch dice dónde está cada emote: "25:0-4,12-16/1902:6-10", en caracteres (no en UTF-16 como JS)
  function deTwitch(texto, emotes) {
    const letras = Array.from(texto), lugares = [], trozos = [];
    for (const parte of String(emotes || '').split('/')) {
      const [id, posiciones] = parte.split(':');
      if (!/^[\w-]+$/.test(id || '')) continue;
      for (const p of (posiciones || '').split(',')) {
        const [a, b] = p.split('-').map(Number);
        if (Number.isInteger(a) && Number.isInteger(b) && a <= b && b < letras.length) lugares.push([a, b, id]);
      }
    }
    lugares.sort((x, y) => x[0] - y[0]);
    let desde = 0;
    for (const [a, b, id] of lugares) {
      if (a < desde) continue;
      trozos.push(letras.slice(desde, a).join(''),
        { url: 'https://static-cdn.jtvnw.net/emoticons/v2/' + id + '/default/dark/1.0', nombre: letras.slice(a, b + 1).join('') });
      desde = b + 1;
    }
    trozos.push(letras.slice(desde).join(''));
    return trozos;
  }

  // Kick los manda adentro del texto: [emote:37226:KEKW]
  function deKick(texto) {
    const trozos = [];
    let desde = 0;
    for (const m of texto.matchAll(/\[emote:(\d+):([^\]]*)\]/g)) {
      trozos.push(texto.slice(desde, m.index), { url: 'https://files.kick.com/emotes/' + m[1] + '/fullsize', nombre: m[2] });
      desde = m.index + m[0].length;
    }
    trozos.push(texto.slice(desde));
    return trozos;
  }

  function pintar(texto, plataforma, emotes) {
    texto = String(texto || '');
    const f = document.createDocumentFragment(), mapa = mapas[plataforma] || {};
    for (const t of plataforma === 'kick' ? deKick(texto) : deTwitch(texto, emotes)) {
      if (typeof t !== 'string') { f.append(imagen(t.url, t.nombre)); continue; }
      for (const palabra of t.split(/(\s+)/)) {  // en lo que queda, las palabras que son emotes de BTTV, FFZ o 7TV
        if (Object.prototype.hasOwnProperty.call(mapa, palabra)) f.append(imagen(mapa[palabra], palabra));
        else if (palabra) f.append(palabra);
      }
    }
    return f;
  }

  window.Emotes = { cargar, pintar, mapas };
})();
