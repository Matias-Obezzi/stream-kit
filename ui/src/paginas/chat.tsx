// El chat de Twitch y Kick junto: eventos, emotes (con /emotes.js), la campanita y el menú para moderar.
// También va como panel angosto de OBS: la lista ocupa todo el alto que queda.
import { BellIcon, BellOffIcon, ChevronRightIcon, UsersIcon } from 'lucide-react'
import * as React from 'react'
import { Encabezado, Seccion } from '@/components/pagina'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { toast } from '@/components/ui/toast'
import { ApiError, cargarScript, get, post } from '@/lib/api'
import { useEstado } from '@/lib/estado'
import { numero } from '@/lib/formato'
import { cn } from '@/lib/utils'

type Plataforma = 'twitch' | 'kick'

interface Evento {
  tipo: string
  plataforma: Plataforma
  t: number
  usuario: string
  texto?: string
  mensaje?: string
  color?: string
  emotes?: string
  mid?: string
  uid?: string | number
  nivel?: string
  cantidad?: number
  accion?: string
  minutos?: number
  por?: string // quién borró o baneó: un moderador, "el bot" o "Stream Kit"; vacío si la plataforma no lo dice
}

interface Linea {
  id: number
  e: Evento
  borrado: boolean
}

interface Quien {
  error?: string
  usuarios?: string[]
  total?: number
  escribieron?: string[]
}

// lo que deja /emotes.js en window
interface EmotesApi {
  cargar: (api: string) => Promise<void>
  pintar: (texto: unknown, plataforma: string, emotes?: string) => DocumentFragment
}
const emotes = () => (window as unknown as { Emotes?: EmotesApi }).Emotes

const GUARDADO = 'mz-chat'
const NOMBRES: Record<Plataforma, string> = { twitch: 'Twitch', kick: 'Kick' }
const norm = (s: unknown) =>
  String(s || '')
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
const terminos = (s: string) =>
  norm(s)
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
// Kick manda los emotes como [emote:id:nombre]: queda el nombre
const textoVisible = (e: Evento) => String(e.texto).replace(/\[emote:\d+:([^\]]+)\]/g, '$1')
const nombres = (lista: string[]) => (lista.length ? lista.join(', ') : 'nadie todavía')

const EVENTOS: Record<string, (e: Evento) => [string, string]> = {
  follow: () => ['Nuevo seguidor', ''],
  sub: (e) => ['Nueva sub', e.nivel === 'Prime' ? 'con Prime' : e.nivel ? 'nivel ' + e.nivel : ''],
  resub: (e) => ['Resub', e.cantidad ? e.cantidad + ' meses' : ''],
  regalo: (e) => ['Regaló subs', (e.cantidad || 1) + ((e.cantidad || 1) === 1 ? ' sub' : ' subs')],
  raid: (e) => ['Raid', e.cantidad ? 'con ' + e.cantidad + ' espectadores' : ''],
  bits: (e) => ['Bits', e.cantidad + ' bits'],
  kicks: (e) => ['Kicks', e.cantidad + ' kicks'],
  moderado: (e) => [
    ({ borrar: 'Mensaje borrado', timeout: 'Timeout', banear: 'Ban', desbanear: 'Desbaneado' } as Record<string, string>)[e.accion ?? ''] ||
      String(e.accion),
    [e.accion === 'timeout' ? e.minutos + ' min' : '', 'por ' + (e.por || 'un moderador')].filter(Boolean).join(' · '),
  ],
}

interface Ajustes {
  campana: boolean
  alertas: boolean
  si: string
  no: string
}

function leerAjustes(): Ajustes {
  const a: Ajustes = { campana: false, alertas: true, si: '', no: '' }
  try {
    Object.assign(a, JSON.parse(localStorage.getItem(GUARDADO) ?? 'null') || {})
  } catch {
    /* sin almacenamiento: los de siempre */
  }
  return a
}

/** El texto con los emotes como imagen. Emotes.pintar arma nodos (nunca HTML con el texto). */
function Pintado({ texto, plataforma, lista, version }: { texto: unknown; plataforma: Plataforma; lista?: string; version: number }) {
  const ref = React.useRef<HTMLSpanElement>(null)
  React.useLayoutEffect(() => {
    const E = emotes()
    ref.current?.replaceChildren(E ? E.pintar(texto, plataforma, lista) : String(texto ?? ''))
  }, [texto, plataforma, lista, version])
  return <span ref={ref} />
}

export default function Pagina() {
  const { bot } = useEstado()
  const [ajustes, setAjustes] = React.useState(leerAjustes)
  const ajustesRef = React.useRef(ajustes)
  ajustesRef.current = ajustes
  const [lineas, setLineas] = React.useState<Linea[]>([])
  const [version, setVersion] = React.useState(0)
  const [sonando, setSonando] = React.useState(false)
  const [menu, setMenu] = React.useState<{ id: number; e: Evento; x: number; y: number } | null>(null)
  const [banear, setBanear] = React.useState<Evento | null>(null)
  const [quienesAbierto, setQuienesAbierto] = React.useState(false)
  const [quienes, setQuienes] = React.useState<React.ReactNode>(null)
  const chatRef = React.useRef<HTMLOListElement>(null)
  const pegado = React.useRef(true)
  const ctx = React.useRef<AudioContext | null>(null)

  const cambiar = (cambio: Partial<Ajustes>) =>
    setAjustes((a) => {
      const nuevo = { ...a, ...cambio }
      try {
        localStorage.setItem(GUARDADO, JSON.stringify(nuevo))
      } catch {
        /* queda solo en esta pestaña */
      }
      return nuevo
    })

  // sonido sin archivos: un ding para los mensajes y el acorde de las alertas de OBS para los eventos
  const audio = React.useCallback(() => {
    try {
      if (!ctx.current) {
        const c = new AudioContext()
        ctx.current = c
        // el aviso sigue al sonido real: OBS suele dejar sonar sin tocar nada, el navegador no
        c.onstatechange = () => setSonando(c.state === 'running')
        setSonando(c.state === 'running')
      }
      if (ctx.current.state === 'suspended') void ctx.current.resume()
    } catch {
      /* sin audio */
    }
    return ctx.current
  }, [])

  React.useEffect(() => {
    audio()
    document.addEventListener('pointerdown', audio)
    return () => {
      document.removeEventListener('pointerdown', audio)
      void ctx.current?.close()
      ctx.current = null
    }
  }, [audio])

  const tono = React.useCallback(
    (notas: number[], paso: number, dura: number, volumen: number) => {
      const c = audio()
      if (!c || c.state !== 'running') return
      notas.forEach((f, k) => {
        const o = c.createOscillator()
        const g = c.createGain()
        const t = c.currentTime + k * paso
        o.type = 'triangle'
        o.frequency.value = f
        g.gain.setValueAtTime(0, t)
        g.gain.linearRampToValueAtTime(volumen, t + 0.02)
        g.gain.exponentialRampToValueAtTime(0.001, t + dura)
        o.connect(g).connect(c.destination)
        o.start(t)
        o.stop(t + dura + 0.05)
      })
    },
    [audio],
  )

  // emotes.js primero; los de BTTV, FFZ y 7TV pueden tardar unos segundos: cuando llegan, el chat se vuelve a dibujar
  const [listo, setListo] = React.useState(false)
  React.useEffect(() => {
    let vivo = true
    cargarScript('/emotes.js')
      .then(() =>
        emotes()
          ?.cargar('')
          .then(() => vivo && setVersion((v) => v + 1)),
      )
      .catch(() => {})
      .finally(() => vivo && setListo(true))
    return () => {
      vivo = false
    }
  }, [])

  // cada segundo, lo nuevo desde el último pedido
  React.useEffect(() => {
    if (!listo) return
    let vivo = true
    let desde: number | null = null
    let siguiente = 0
    let ultimoDing = 0
    let id = 0
    const suena = (e: Evento) => {
      const a = ajustesRef.current
      if (e.tipo === 'moderado') return false
      if (e.tipo !== 'chat') return a.alertas
      if (!a.campana) return false
      const texto = norm(e.usuario + ' ' + e.texto)
      if (terminos(a.no).some((t) => texto.includes(t))) return false
      const si = terminos(a.si)
      return !si.length || si.some((t) => texto.includes(t))
    }
    const sonar = (e: Evento) => {
      if (e.tipo !== 'chat') return tono([523.25, 659.25, e.tipo === 'follow' ? 783.99 : 1046.5], 0.07, 0.6, 0.16)
      if (Date.now() - ultimoDing < 1200) return // si entran muchos juntos, un solo ding
      ultimoDing = Date.now()
      tono([987.77, 1318.51], 0.09, 0.3, 0.12)
    }
    const traer = async () => {
      try {
        const d = await get<{ eventos: Evento[]; ultimo: number }>('/api/eventos' + (desde === null ? '' : '?desde=' + desde))
        if (!vivo) return
        const nuevos = desde !== null // lo que ya estaba al abrir la página no suena
        const chat = chatRef.current
        // si subiste a leer algo, no te lo mueve
        pegado.current = !chat || chat.scrollHeight - chat.scrollTop - chat.clientHeight < 80
        const llegan = d.eventos.map((e) => ({ id: ++id, e, borrado: false }))
        if (llegan.length)
          setLineas((antes) => {
            let lista = antes
            for (const l of llegan) {
              const e = l.e
              // lo borrado se tacha; con timeout o ban, todo lo de esa persona en esa plataforma
              if (e.tipo === 'moderado' && e.accion !== 'desbanear')
                lista = lista.map((x) =>
                  x.e.tipo === 'chat' &&
                  x.e.plataforma === e.plataforma &&
                  (e.accion === 'borrar' ? x.e.mid === e.mid : String(x.e.uid) === String(e.uid))
                    ? { ...x, borrado: true }
                    : x,
                )
              lista = [...lista, l]
            }
            return lista.slice(-400)
          })
        if (nuevos) d.eventos.forEach((e) => suena(e) && sonar(e))
        desde = d.ultimo
      } catch {
        /* sin respuesta: la barra de arriba avisa que Stream Kit no contesta */
      }
      if (vivo) siguiente = window.setTimeout(traer, 1000)
    }
    void traer()
    return () => {
      vivo = false
      clearTimeout(siguiente)
    }
  }, [listo, tono])

  React.useLayoutEffect(() => {
    const chat = chatRef.current
    if (chat && pegado.current) chat.scrollTop = chat.scrollHeight
  }, [lineas])

  // si el mensaje del menú se fue por arriba (más de 400), el menú se cierra
  React.useEffect(() => {
    if (menu && !lineas.some((l) => l.id === menu.id)) setMenu(null)
  }, [lineas, menu])

  const silenciado = (u: string) => terminos(ajustes.no).includes(norm(u))
  const silenciar = (u: string) => {
    const lista = ajustes.no
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    const resto = lista.filter((t) => norm(t) !== norm(u))
    cambiar({ no: (resto.length < lista.length ? resto : [...lista, u]).join(', ') })
  }

  const copiar = async (texto: string) => {
    try {
      await navigator.clipboard.writeText(texto)
    } catch {
      toast.error('El navegador no dejó copiar.')
    }
  }

  // moderar lo hace el bot, con su cuenta de moderador
  const moderar = async (e: Evento, accion: string, minutos?: number) => {
    toast.loading('Enviando…', { id: 'moderar' })
    try {
      await post('/api/chat/accion', { accion, minutos, plataforma: e.plataforma, mid: e.mid, uid: e.uid, usuario: e.usuario })
      toast.dismiss('moderar') // lo hecho aparece en el chat
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message || 'No se pudo.' : 'La web no contesta.', { id: 'moderar', duration: 8000 })
    }
  }

  // quién mira: Twitch da la lista del chat (los que están logueados, no los anónimos); Kick no da ninguna
  const preguntarQuienes = async () => {
    setQuienes('Buscando…')
    let datos: Partial<Record<Plataforma, Quien>>
    try {
      datos = await get('/api/chat/quienes')
    } catch (err) {
      setQuienes(err instanceof ApiError ? err.message : 'No pude preguntar.')
      return
    }
    const partes = (['twitch', 'kick'] as const).flatMap((clave) => {
      const p = datos?.[clave]
      if (!p) return []
      const nombre = NOMBRES[clave]
      return [
        <div key={clave} className="space-y-1">
          <h2 className="text-sm font-semibold">{!p.error && p.usuarios ? `${nombre} · ${p.total} en el chat` : nombre}</h2>
          <p className="[overflow-wrap:anywhere]">{p.error ? p.error : p.usuarios ? nombres(p.usuarios) : 'Kick no dice quién mira.'}</p>
          <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">Escribieron en este stream: {nombres(p.escribieron || [])}</p>
        </div>,
      ]
    })
    setQuienes(partes.length ? partes : 'Sin stream en vivo.')
  }

  const v = bot?.bot.viewers ?? {} // sin stream en una plataforma, no sale
  const viendo = (
    [
      ['Twitch', v.twitch],
      ['Kick', v.kick],
    ] as [string, number | null | undefined][]
  )
    .filter((x): x is [string, number] => typeof x[1] === 'number')
    .map(([p, n]) => `${p} ${numero(n)}`)

  const tocar = (ajustes.campana || ajustes.alertas) && !sonando
  const resumen = 'Campanita: ' + (ajustes.campana ? 'activada' : 'apagada') + (ajustes.alertas ? ' · alertas con sonido' : '')
  const e = menu?.e

  return (
    // alto de la pantalla menos la barra de arriba, el menú de abajo (en angosto) y los márgenes del marco
    <div className="flex h-[calc(100dvh-8.5rem)] flex-col gap-3 md:h-[calc(100dvh-5.5rem)]">
      <Encabezado
        titulo="Chat"
        acciones={
          viendo.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              aria-expanded={quienesAbierto}
              aria-controls="quienes"
              title="Espectadores ahora, se actualiza cada 30 segundos. Tocá para ver quiénes"
              onClick={() => {
                const abrir = !quienesAbierto
                setQuienesAbierto(abrir)
                if (abrir) void preguntarQuienes()
              }}
            >
              <UsersIcon aria-hidden />
              Viendo: {viendo.join(' · ')}
            </Button>
          )
        }
        ayuda={
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Los chats de Twitch y Kick llegan juntos, con los follows, subs, raids y bits marcados. Los emotes se ven como imagen: los de Twitch y
              Kick, y los de BTTV, FFZ y 7TV, los globales y los que sumes a tu canal.
            </li>
            <li>
              En OBS: Ver → Paneles → Paneles de navegador personalizados, y agregá <code>http://127.0.0.1:8080/chat</code>. Queda como un panel más.
            </li>
            <li>
              Tocá el contador de espectadores para ver quiénes están: en Twitch, los que están en el chat con su cuenta (los anónimos no salen). Kick
              no lo dice; de las dos se ve quién escribió desde que arrancó el stream.
            </li>
            <li>La campanita suena con cada mensaje; abajo elegís cuándo sí y cuándo no.</li>
            <li>
              Click derecho en un mensaje: copiarlo, silenciar a esa persona, borrarlo, timeout, ban y desban. Moderar lo hace el bot, así que tiene
              que ser moderador.
            </li>
            <li>
              Lo que se borra o se banea queda tachado, con quién fue: un moderador por su nombre, <b>el bot</b> (lo automático) o <b>Stream Kit</b>{' '}
              (desde acá). En Twitch, para ver el nombre del moderador, el bot necesita el login de nuevo en Configuración. Kick no dice qué moderador
              fue: sale "por un moderador".
            </li>
          </ol>
        }
      />

      <Collapsible className="shrink-0 rounded-lg border bg-card text-sm">
        <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
          <ChevronRightIcon aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-90" />
          {resumen}
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-3 px-3 pb-3">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant={ajustes.campana ? 'default' : 'outline'}
              size="sm"
              aria-pressed={ajustes.campana}
              onClick={() => {
                cambiar({ campana: !ajustes.campana })
                audio()
              }}
            >
              {ajustes.campana ? <BellIcon aria-hidden /> : <BellOffIcon aria-hidden />}
              {ajustes.campana ? 'Campanita activada' : 'Activar campanita'}
            </Button>
            <Label className="font-normal leading-snug">
              <Switch checked={ajustes.alertas} onCheckedChange={(alertas) => cambiar({ alertas })} />
              Sonar con follows, subs, bits, kicks y raids
            </Label>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="chat-si">Sonar solo si dice</Label>
              <Input id="chat-si" value={ajustes.si} placeholder="Vacío: suena con todos" onChange={(ev) => cambiar({ si: ev.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="chat-no">No sonar si dice</Label>
              <Input
                id="chat-no"
                value={ajustes.no}
                placeholder="Por ejemplo: el nombre de tu bot, !"
                onChange={(ev) => cambiar({ no: ev.target.value })}
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Separá con comas. Mira el nombre y el mensaje, sin importar mayúsculas ni tildes. Si un mensaje cumple los dos, no suena.
          </p>
        </CollapsibleContent>
      </Collapsible>

      {quienesAbierto && (
        <div id="quienes" aria-live="polite" className="shrink-0">
          <Seccion className="max-h-[40vh] overflow-y-auto text-sm">
            <div className="space-y-3">{quienes}</div>
          </Seccion>
        </div>
      )}

      {tocar && (
        <p className="shrink-0 rounded-lg border border-aviso bg-card px-3 py-2 text-sm">
          Tocá la página una vez para que el navegador deje sonar la campanita.
        </p>
      )}

      <ol
        ref={chatRef}
        role="log"
        tabIndex={0}
        aria-label="Mensajes de Twitch y Kick. Click derecho en un mensaje para moderar"
        onWheel={() => setMenu(null)} // no con scroll: el chat baja solo cuando llegan mensajes
        className="min-h-50 flex-1 overflow-y-auto rounded-lg border bg-card py-2 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 [&_img]:-my-[0.25em] [&_img]:inline [&_img]:h-[1.75em] [&_img]:align-middle"
      >
        {lineas.map(({ id, e, borrado }) => {
          const chat = e.tipo === 'chat'
          const moderado = e.tipo === 'moderado'
          const hora = new Date(e.t * 1000).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false })
          const [titulo, detalle] = chat ? ['', ''] : (EVENTOS[e.tipo] ?? (() => [e.tipo, '']))(e)
          return (
            <li
              key={id}
              title={NOMBRES[e.plataforma] ?? 'Twitch'}
              onContextMenu={
                chat // en las alertas queda el menú del navegador
                  ? (ev) => {
                      ev.preventDefault()
                      setMenu({ id, e, x: ev.clientX, y: ev.clientY })
                    }
                  : undefined
              }
              className={cn(
                'border-l-3 py-1 pr-3.5 pl-2.5 [overflow-wrap:anywhere]',
                e.plataforma === 'kick' ? 'border-l-chart-2' : 'border-l-chart-1',
                !chat && 'my-1 bg-primary/15 py-2',
                moderado && 'bg-transparent text-muted-foreground',
                menu?.id === id && 'bg-accent',
              )}
            >
              <span className="mr-2 text-xs text-muted-foreground tabular-nums">{hora}</span>
              {chat ? (
                <>
                  <span
                    className="mr-1.5 font-bold after:text-muted-foreground after:content-[':']"
                    style={/^#[0-9a-f]{6}$/i.test(e.color || '') ? { color: e.color } : undefined}
                  >
                    {e.usuario}
                  </span>
                  <span className={cn(borrado && 'line-through opacity-50')}>
                    <Pintado texto={e.texto} plataforma={e.plataforma} lista={e.emotes} version={version} />
                  </span>
                </>
              ) : (
                <>
                  <span className={cn('mr-2 text-xs font-bold tracking-wider uppercase', moderado ? 'text-diferido' : 'text-primary')}>{titulo}</span>
                  <span className="mr-1.5 font-bold">{e.usuario}</span>
                  <span>
                    {detalle && e.mensaje ? detalle + ' · ' : detalle}
                    {e.mensaje && <Pintado texto={e.mensaje} plataforma={e.plataforma} lista={e.emotes} version={version} />}
                  </span>
                </>
              )}
            </li>
          )
        })}
      </ol>

      {/* click derecho en un mensaje: copiar, campanita y moderar */}
      <DropdownMenu open={!!menu} onOpenChange={(abierto) => !abierto && setMenu(null)} modal={false}>
        <DropdownMenuTrigger asChild>
          <span aria-hidden tabIndex={-1} className="pointer-events-none fixed size-0" style={{ left: menu?.x, top: menu?.y }} />
        </DropdownMenuTrigger>
        {e && (
          <DropdownMenuContent
            align="start"
            sideOffset={0}
            collisionPadding={8}
            className="max-w-[calc(100vw-16px)] min-w-56"
            onCloseAutoFocus={(ev) => {
              ev.preventDefault()
              chatRef.current?.focus({ preventScroll: true })
            }}
          >
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground [overflow-wrap:anywhere]">
              {e.usuario} · {NOMBRES[e.plataforma]}
            </DropdownMenuLabel>
            <DropdownMenuItem onSelect={() => void copiar(textoVisible(e))}>Copiar mensaje</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void copiar(e.usuario)}>Copiar nombre</DropdownMenuItem>
            <DropdownMenuItem className="whitespace-normal" onSelect={() => silenciar(e.usuario)}>
              {silenciado(e.usuario) ? `Que vuelva a sonar con ${e.usuario}` : `Que la campanita no suene con ${e.usuario}`}
            </DropdownMenuItem>
            {!!e.uid && ( // los mensajes del bot en Twitch no traen id: ahí solo se copia
              <>
                <DropdownMenuSeparator />
                {e.mid && <DropdownMenuItem onSelect={() => void moderar(e, 'borrar')}>Borrar mensaje</DropdownMenuItem>}
                <DropdownMenuItem onSelect={() => void moderar(e, 'timeout', 1)}>Timeout de 1 minuto</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => void moderar(e, 'timeout', 10)}>Timeout de 10 minutos</DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={() => setBanear(e)}>
                  Banear
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => void moderar(e, 'desbanear')}>Desbanear</DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        )}
      </DropdownMenu>

      <AlertDialog open={!!banear} onOpenChange={(abierto) => !abierto && setBanear(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Banear a {banear?.usuario}</AlertDialogTitle>
            <AlertDialogDescription>En {banear ? NOMBRES[banear.plataforma] : ''}. Lo hace el bot; se deshace con Desbanear.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => banear && void moderar(banear, 'banear')}>
              Sí, banear a {banear?.usuario}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
