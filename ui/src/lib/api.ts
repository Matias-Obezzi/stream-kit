// Habla con streamkit/panel.py. Los POST llevan X-Panel: una página web ajena no puede mandarlo sin permiso (CORS).
import * as React from 'react'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function leer<T>(r: Response): Promise<T> {
  const texto = await r.text()
  let datos: unknown = null
  try {
    datos = texto ? JSON.parse(texto) : null
  } catch {
    datos = texto
  }
  if (!r.ok) {
    const conError = datos && typeof datos === 'object' && 'error' in datos ? String((datos as { error: unknown }).error) : ''
    const msg = conError || (typeof datos === 'string' && datos) || `Error ${r.status}`
    throw new ApiError(msg, r.status)
  }
  return datos as T
}

export function get<T>(ruta: string, init?: RequestInit): Promise<T> {
  return fetch(ruta, { cache: 'no-store', ...init }).then((r) => leer<T>(r))
}

export function post<T = unknown>(ruta: string, cuerpo?: unknown): Promise<T> {
  return fetch(ruta, {
    method: 'POST',
    headers: { 'X-Panel': '1', 'Content-Type': 'application/json' },
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  }).then((r) => leer<T>(r))
}

/** Pide `ruta` cada `cada` ms (y al volver a la pestaña). `null` no pide nada. */
export function usePoll<T>(ruta: string | null, cada = 3000) {
  const [datos, setDatos] = React.useState<T | undefined>()
  const [error, setError] = React.useState<ApiError | Error | undefined>()
  const [vuelta, setVuelta] = React.useState(0)
  const refrescar = React.useCallback(() => setVuelta((v) => v + 1), [])
  React.useEffect(() => {
    if (!ruta) return
    let vivo = true
    const pedir = () =>
      get<T>(ruta).then(
        (d) => vivo && (setDatos(d), setError(undefined)),
        (e: Error) => vivo && setError(e),
      )
    pedir()
    const t = setInterval(() => !document.hidden && pedir(), cada)
    const visible = () => !document.hidden && pedir()
    document.addEventListener('visibilitychange', visible)
    return () => {
      vivo = false
      clearInterval(t)
      document.removeEventListener('visibilitychange', visible)
    }
  }, [ruta, cada, vuelta])
  return { datos, error, refrescar, setDatos }
}

/** Carga una vez un script clásico del panel (piezas.js, emotes.js, plataformas.js), que deja globales en window. */
const scripts = new Map<string, Promise<void>>()
export function cargarScript(src: string): Promise<void> {
  let p = scripts.get(src)
  if (!p) {
    p = new Promise((ok, mal) => {
      const s = document.createElement('script')
      s.src = src
      s.onload = () => ok()
      s.onerror = () => mal(new Error(`No cargó ${src}`))
      document.head.append(s)
    })
    scripts.set(src, p)
  }
  return p
}

export const esLocal = ['127.0.0.1', 'localhost'].includes(location.hostname)

/** Abre un link en el navegador de siempre de la PC (en un panel de OBS, target=_blank abre una ventanita de OBS).
 *  Desde el celular abre ahí mismo, en otra pestaña. */
export function abrirAfuera(url: string) {
  if (!esLocal) return void window.open(url, '_blank', 'noopener')
  post('/api/abrir', { url }).catch(() => window.open(url, '_blank', 'noopener'))
}

/** Los links a otra página (o con target=_blank) van al navegador de siempre: se instala una vez, para todas las páginas. */
export function linksAfuera() {
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    const a = (e.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
    if (!a || !/^https?:/.test(a.href)) return
    if (new URL(a.href).origin === location.origin && a.target !== '_blank') return
    e.preventDefault()
    abrirAfuera(a.href)
  })
}
