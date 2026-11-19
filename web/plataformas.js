// Las plataformas a las que transmite el delay: cómo se reconoce cada destino, su servidor y dónde está su clave.
// Lo usan Configuración (una pestaña por plataforma) y Delay (el estado de cada una).
const PLATAFORMAS = {
  twitch: {
    nombre: 'Twitch', servidor: 'rtmp://live.twitch.tv/app', es: d => d.url.includes('twitch.tv'),
    pasos: 'En <a href="https://dashboard.twitch.tv/settings/stream" target="_blank" rel="noopener">el panel de Twitch → Configuración → Transmisión</a>, copiá la <b>clave de transmisión principal</b>.',
  },
  kick: {
    nombre: 'Kick', servidor: '', es: d => /kick|live-video\.net/i.test(d.name + ' ' + d.url),
    pasos: 'En <a href="https://kick.com/dashboard/settings/stream" target="_blank" rel="noopener">kick.com → Configuración → Stream</a> están la <b>URL del stream</b> y la <b>clave</b>. La URL cambia en cada cuenta: copiala tal cual.',
  },
  youtube: {
    nombre: 'YouTube', servidor: 'rtmp://a.rtmp.youtube.com/live2', es: d => d.url.includes('youtube.com'),
    pasos: 'En <a href="https://studio.youtube.com" target="_blank" rel="noopener">YouTube Studio → Emitir en vivo</a>, copiá la <b>clave de transmisión</b>. Usá la <b>predeterminada</b> (o una que crees y guardes): es fija y no cambia entre directos. Si al crear un directo elegís <b>Crear una clave nueva</b>, YouTube da otra y hay que cambiarla acá. La primera vez, YouTube puede tardar un día en habilitar los directos.',
  },
  facebook: {
    nombre: 'Facebook', servidor: 'rtmps://live-api-s.facebook.com:443/rtmp/', es: d => d.url.includes('facebook.com'),
    pasos: 'En <a href="https://www.facebook.com/live/producer" target="_blank" rel="noopener">facebook.com/live/producer</a>, elegí <b>Software de transmisión</b> y copiá la <b>clave</b>. Activá la <b>clave persistente</b> para no tener que cambiarla en cada directo.',
  },
  tiktok: {
    nombre: 'TikTok', servidor: '', es: d => /tiktok/i.test(d.name + ' ' + d.url),
    pasos: 'TikTok da URL y clave solo a las cuentas que tienen habilitado transmitir con software. Si la tuya lo tiene, las generás en <a href="https://www.tiktok.com/live" target="_blank" rel="noopener">TikTok LIVE</a> desde la compu. Cambian en cada directo: antes de empezar, tocá <b>Cambiar clave</b> y pegá las nuevas.',
  },
  instagram: {
    nombre: 'Instagram', servidor: '', es: d => /instagram|fbcdn\.net/i.test(d.name + ' ' + d.url),
    pasos: 'Desde <a href="https://www.instagram.com" target="_blank" rel="noopener">instagram.com</a> en la compu: <b>Crear → En vivo</b>, elegí transmitir con software y copiá la URL y la clave. Cambian en cada directo: antes de empezar, tocá <b>Cambiar clave</b> y pegá las nuevas.',
  },
  x: {
    nombre: 'X', servidor: '', es: d => /pscp\.tv|periscope|twitter/i.test(d.url) || /^(x|twitter)$/i.test(d.name.trim()),
    pasos: 'En <a href="https://studio.x.com" target="_blank" rel="noopener">studio.x.com</a> → <b>Producer → Fuentes</b>, creá una fuente RTMP y copiá la URL y la clave.',
  },
};

// la pestaña de un destino: la de su plataforma, u "otras" si no es ninguna conocida
function plataformaDe(d) {
  return Object.keys(PLATAFORMAS).find(k => PLATAFORMAS[k].es(d)) || 'otras';
}
