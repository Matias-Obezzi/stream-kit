const num = (n: number, decimales = 0) =>
  n.toLocaleString('es-AR', { maximumFractionDigits: decimales, minimumFractionDigits: 0 })

export const numero = num
export const mbps = (kbps: number) => `${num(kbps / 1000, 1)} Mb/s`
export const segundos = (s: number) => `${num(s, 1)} s`

/** "hace 12 s", "hace 3 min", "hace 2 h" desde un tiempo en segundos (epoch). */
export function hace(epoch: number) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - epoch))
  if (s < 60) return `hace ${s} s`
  if (s < 3600) return `hace ${Math.round(s / 60)} min`
  return `hace ${Math.round(s / 3600)} h`
}

export const bytes = (b: number) =>
  b >= 1e9 ? `${num(b / 1e9, 1)} GB` : b >= 1e6 ? `${num(b / 1e6, 1)} MB` : `${num(b / 1e3)} KB`
