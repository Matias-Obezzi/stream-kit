// El estado del stream y del bot, pedido una sola vez cada 3 s para todo el panel.
import * as React from 'react'
import { toast } from '@/components/ui/toast'
import { usePoll } from '@/lib/api'

export interface Destino {
  id: string
  name: string
  url: string
  enabled: boolean
  state: 'live' | 'idle' | 'error' | 'off'
  error: string
  bitrate?: number // kbps propios (se recomprime); 0 o ausente: lo mismo que manda OBS
  kbps?: number
  atraso?: number
  descartes?: number
  ultimo_descarte?: number
  recomprime?: boolean
}

export interface Estado {
  mode: 'live' | 'filler' | 'delayed'
  delay: number
  filler_left: number
  obs: boolean
  sending: boolean
  ffmpeg: boolean
  destinations: Destino[]
  filler: { mode: string; file: string; loops: number; text: string; seconds: number }
  busy: string
  files: { name: string; duration: number | null }[]
  phone?: string
  red?: { entrada_kbps: number; perdida: number | null }
  prueba?: PruebaSubida
}

export interface PruebaSubida {
  estado: '' | 'probando' | 'listo' | 'error'
  mbps?: number
  recomendado?: number
  tope?: boolean
  plataformas?: number
  error?: string
  hora?: number
  progreso?: number
}

export interface BotEstado {
  vivo: boolean
  twitch?: string
  kick?: string
  viewers?: Record<string, number | null>
  [k: string]: unknown
}

export interface BotInfo {
  bot: BotEstado
  [k: string]: unknown
}

interface Ctx {
  estado?: Estado
  bot?: BotInfo
  caido: boolean
  refrescar: () => void
}

const EstadoCtx = React.createContext<Ctx>({ caido: false, refrescar: () => {} })

const SONIDO = 'streamkit.avisoSonido'
export function sonidoActivado() {
  try {
    return localStorage.getItem(SONIDO) !== '0'
  } catch {
    return true
  }
}
export function activarSonido(si: boolean) {
  try {
    localStorage.setItem(SONIDO, si ? '1' : '0')
  } catch {
    /* sin almacenamiento: queda como está */
  }
}

function pitido() {
  if (!sonidoActivado()) return
  try {
    const ctx = new AudioContext()
    for (const [i, f] of [880, 660].entries()) {
      const o = ctx.createOscillator()
      const g = ctx.createGain()
      o.frequency.value = f
      g.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.18)
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.18 + 0.16)
      o.connect(g).connect(ctx.destination)
      o.start(ctx.currentTime + i * 0.18)
      o.stop(ctx.currentTime + i * 0.18 + 0.17)
    }
    setTimeout(() => ctx.close(), 800)
  } catch {
    /* el navegador no deja sonar sin un toque antes: queda el cartel */
  }
}

/** Avisa con un cartel y un sonido cuando una plataforma salta (se tiró lo atrasado). */
function useAvisoSaltos(estado?: Estado) {
  const antes = React.useRef<Record<string, number>>({})
  React.useEffect(() => {
    if (!estado) return
    for (const d of estado.destinations) {
      const n = d.descartes ?? 0
      const previo = antes.current[d.id]
      if (previo !== undefined && n > previo) {
        toast.warning(`${d.name} saltó`, {
          id: `salto-${d.id}`,
          description: 'La subida no da abasto: se tiró lo atrasado y la imagen saltó. Si se repite, bajá el bitrate o apagá una plataforma.',
          duration: 10000,
        })
        pitido()
      }
      antes.current[d.id] = n
    }
  }, [estado])
}

export function EstadoProvider({ children }: { children: React.ReactNode }) {
  const s = usePoll<Estado>('/api/state', 3000)
  const b = usePoll<BotInfo>('/api/bot', 3000)
  useAvisoSaltos(s.datos)
  const refrescarS = s.refrescar
  const refrescarB = b.refrescar
  const valor = React.useMemo<Ctx>(
    () => ({
      estado: s.datos,
      bot: b.datos,
      caido: !!s.error,
      refrescar: () => {
        refrescarS()
        refrescarB()
      },
    }),
    [s.datos, b.datos, s.error, refrescarS, refrescarB],
  )
  return <EstadoCtx.Provider value={valor}>{children}</EstadoCtx.Provider>
}

export const useEstado = () => React.useContext(EstadoCtx)
