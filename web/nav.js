// Barra de estado arriba y menú de pantallas abajo, en todas las páginas del panel (no en las de OBS).
(() => {
  const local = ['127.0.0.1', 'localhost'].includes(location.hostname);  // Configuración solo se abre desde esta PC
  const PAGINAS = [
    ['/', 'Inicio', 'M3 11l9-8 9 8M5 9.5V21h5v-6h4v6h5V9.5'],
    ['/delay', 'Delay', 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2'],
    ['/chat', 'Chat', 'M4 5h16v11H9l-5 4z'],
    ['/canal', 'Título', 'M4 20h4L19 9l-4-4L4 16zM13 7l4 4'],
    ['/pantallas', 'Pantallas', 'M3 4h18v16H3zM3 9h18M9 9v11'],
    ['/bot', 'Bot', 'M5 9h14v11H5zM12 4v5M9 14v1M15 14v1'],
    ...(local ? [['/config', 'Config', 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M16 4v4M10 10v4M18 16v4']] : []),
  ];
  const svg = d => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;

  const nav = document.createElement('nav');
  nav.className = 'nav-abajo';
  nav.setAttribute('aria-label', 'Páginas');
  for (const [href, nombre, icono] of PAGINAS) {
    const a = document.createElement('a');
    a.href = href;
    a.title = nombre;
    a.innerHTML = svg(icono) + `<span>${nombre}</span>`;
    if (location.pathname === href) a.setAttribute('aria-current', 'page');
    nav.append(a);
  }
  const barra = document.createElement('div');
  barra.className = 'estado-fijo';
  barra.setAttribute('role', 'status');
  document.body.prepend(barra);
  document.body.append(nav);
  document.body.classList.add('con-nav');

  const item = (clase, texto, titulo) => {
    const s = document.createElement('span');
    s.className = clase;
    s.textContent = texto;
    if (titulo) s.title = titulo;
    return s;
  };
  async function tick() {
    let s, info;
    try {
      [s, info] = await Promise.all(['/api/state', '/api/bot'].map(u => fetch(u).then(r => r.json())));
    } catch {
      barra.replaceChildren(item('dot err', 'Stream Kit no contesta'));
      return;
    }
    const activas = s.destinations.filter(d => d.enabled);
    const enVivo = activas.some(d => d.state === 'live');
    const modo = { live: 'Sin delay', filler: `Activando · ${s.filler_left} s`, delayed: `Delay ${Math.round(s.delay)} s` }[s.mode];
    const bot = info.bot, chats = [bot.twitch, bot.kick];
    const v = bot.viewers || {}, viendo = Object.entries(v).filter(([, n]) => typeof n === 'number');
    const total = viendo.reduce((a, [, n]) => a + n, 0);
    barra.replaceChildren(
      item('pill ' + (enVivo ? 'mal' : ''), enVivo ? 'En vivo' : 'Fuera del aire'),
      item('pill ' + s.mode, modo),
      item('dot ' + (s.obs ? 'on' : ''), 'OBS'),
      ...activas.map(d => item('dot ' + (d.state === 'live' ? 'on' : d.state === 'error' ? 'err' : ''), d.name, d.error || '')),
      item('dot ' + (!bot.vivo ? 'err' : chats.every(c => c === 'conectado') ? 'on' : 'medio'), 'Bot',
        bot.vivo ? `Twitch: ${bot.twitch || 'sin datos'} · Kick: ${bot.kick || 'sin datos'}` : 'El bot no está corriendo'),
      ...(viendo.length ? [item('viendo', `${total.toLocaleString('es-AR')} viendo`,
        viendo.map(([p, n]) => `${p[0].toUpperCase() + p.slice(1)}: ${n}`).join(' · '))] : []),
    );
  }
  tick();
  setInterval(tick, 3000);
})();
