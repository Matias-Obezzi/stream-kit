// El editor de pantallas para OBS. Las piezas las dibuja /piezas.js (el mismo que usa cada pantalla en OBS), así que el
// lienzo se maneja a mano, por fuera de React; React se ocupa de la barra, el panel de opciones y el CSS propio.
import { ChevronRightIcon, PlayIcon, PlusIcon, SaveIcon, Trash2Icon, XIcon } from 'lucide-react'
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
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ColorPicker } from '@/components/ui/color-picker'
import { CopyButton } from '@/components/ui/copy-button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { ApiError, cargarScript, get, post } from '@/lib/api'
import { navegar } from '@/lib/router'
import { cn } from '@/lib/utils'

interface Opcion {
  clave: string
  nombre: string
  tipo: string
  def?: unknown
  min?: number
  max?: number
  valores?: [string, string][]
}
interface DefPieza {
  nombre: string
  w: number
  h: number
  opciones: Opcion[]
}
interface Pieza {
  tipo: string
  x: number
  y: number
  w: number
  h: number
  op?: Record<string, unknown>
  clase?: string
}
interface Pantalla {
  id: string
  nombre: string
  formato: string
  css?: string
  tema?: string
  piezas: Pieza[]
}
interface Tema {
  id?: string
  nombre: string
  colores: Record<string, string>
  letra: string
  clave?: number // solo en el editor, para las listas de React
}
interface Viva {
  caja: HTMLElement
  quitar?: () => void
  emotes?: () => void
  probar?: () => void
}
interface PiezasApi {
  PIEZAS: Record<string, DefPieza>
  FORMATOS: Record<string, [number, number]>
  montar(lienzo: HTMLElement, pieza: Pieza, ctx: { demo: boolean }): Viva
  predeterminadas(tipo: string): Record<string, unknown>
  ponerCss(texto: string | undefined, raiz: string): void
  MUESTRA: { textos: Record<string, string> }
  ponerTema(t: Tema | null): void
  color(v: unknown, def: string): string
}
// Globales de /piezas.js y /emotes.js. Sin `declare global`: otras páginas pueden declararlas a su manera.
const Piezas = () => (window as unknown as { Piezas: PiezasApi }).Piezas
const Emotes = () => (window as unknown as { Emotes: { cargar(api: string): Promise<unknown> } }).Emotes

const NUEVA = '__nueva__' // el Select no acepta '' como valor
const SIN_TEMA = '__sin_tema__'
const ANIMACION = ['entrada', 'salida', 'velocidad', 'retraso'] // van juntas, abajo, con el botón para probarlas
// los colores de un tema: fijos, así cualquier tema le sirve a cualquier pantalla (los mismos que en pantallas.py)
const COLORES_TEMA: [string, string][] = [['texto', 'Texto'], ['fondo', 'Fondo'], ['acento', 'Acento'], ['acento2', 'Segundo acento']]
const TEMA_NUEVO = (): Tema => ({ nombre: 'Mi tema', letra: '', colores: { texto: '#ffffff', fondo: '#0f1115', acento: '#8b5cf6', acento2: '#22c55e' } })
const nueva = (cuantas: number): Pantalla => ({ id: '', nombre: 'Pantalla ' + (cuantas + 1), formato: 'horizontal', piezas: [] })

// Clases para las cajas que crea piezas.js (Tailwind las encuentra igual en el texto). La caja elegida lleva `elegida`.
const CAJA = cn(
  'cursor-move touch-none outline-1 outline-dashed outline-foreground/25 [&>:not(.asa)]:pointer-events-none',
  '[&.elegida]:z-1000 [&.elegida]:overflow-visible! [&.elegida]:outline-3 [&.elegida]:outline-solid [&.elegida]:outline-primary',
  '[&.elegida]:after:pointer-events-none [&.elegida]:after:absolute [&.elegida]:after:-top-[34px] [&.elegida]:after:left-0 [&.elegida]:after:whitespace-nowrap',
  '[&.elegida]:after:rounded-md [&.elegida]:after:bg-primary [&.elegida]:after:px-2.5 [&.elegida]:after:py-1 [&.elegida]:after:font-sans',
  '[&.elegida]:after:text-[20px] [&.elegida]:after:leading-normal [&.elegida]:after:font-semibold [&.elegida]:after:text-primary-foreground',
  '[&.elegida]:after:content-[attr(data-nombre)]',
)
const ASA =
  'asa absolute -right-3.5 -bottom-3.5 hidden size-7 cursor-nwse-resize touch-none rounded-full border-3 border-primary-foreground bg-primary in-[.elegida]:block'

interface Pregunta {
  titulo: string
  descripcion?: string
  accion: string
  peligro?: boolean
  responder: (si: boolean) => void
}

export default function Pagina() {
  const [pantallas, setPantallas] = React.useState<Pantalla[]>([])
  const [listo, setListo] = React.useState(false)
  const [abierta, setAbierta] = React.useState(0) // cambia en cada abrir(): rearma la barra
  const [link, setLink] = React.useState<{ url: string; tam: string } | null>(null)
  const [elegida, setElegida] = React.useState(-1)
  const [panel, setPanel] = React.useState(0) // cambia en cada elegir(): rearma el panel de opciones
  const [sucio, setSucio] = React.useState(false)
  const [aviso, setAviso] = React.useState('')
  const [pregunta, setPregunta] = React.useState<Pregunta>()
  const [temas, setTemasEstado] = React.useState<Tema[]>([])
  const temasRef = React.useRef<Tema[]>([])
  const [preguntando, setPreguntando] = React.useState(false)

  // Lo que usa el lienzo: refs, porque piezas.js y los eventos del puntero viven fuera de React
  const actual = React.useRef<Pantalla | null>(null)
  const vivas = React.useRef<Viva[]>([])
  const escala = React.useRef(1)
  const elegidaRef = React.useRef(-1)
  const sucioRef = React.useRef(false)
  const contenedor = React.useRef<HTMLDivElement>(null)
  const marcoRef = React.useRef<HTMLDivElement>(null)
  const lienzoRef = React.useRef<HTMLDivElement>(null)
  const pos = React.useRef<Record<string, HTMLInputElement | null>>({})

  const avisar = (texto: string) => setAviso(texto)
  const marcar = (s: boolean) => {
    sucioRef.current = s
    setSucio(s)
  }
  const preguntar = (p: Omit<Pregunta, 'responder'>) =>
    new Promise<boolean>((responder) => {
      setPregunta({ ...p, responder })
      setPreguntando(true)
    })
  const descartar = async () =>
    !sucioRef.current || preguntar({ titulo: 'Hay cambios sin guardar. ¿Los descartás?', accion: 'Descartar' })

  // --- el tema de la pantalla abierta: sus colores y su letra llegan a las piezas ---
  const temaDe = (id?: string) => (id ? temasRef.current.find((t) => t.id === id) || null : null)
  function aplicarTema() {
    Piezas().ponerTema(temaDe(actual.current?.tema))
  }
  function setTemas(lista: Tema[]) { // al editar un tema, el lienzo lo muestra al toque
    temasRef.current = lista
    setTemasEstado(lista)
    if (!actual.current) return
    aplicarTema()
    dibujar()
    setPanel((n) => n + 1)
  }
  function elegirTema(id: string) {
    const a = actual.current!
    if (id) a.tema = id
    else delete a.tema
    aplicarTema()
    dibujar()
    setPanel((n) => n + 1)
    marcar(true)
  }

  // --- el lienzo ---
  const medidas = () => Piezas().FORMATOS[actual.current!.formato] || Piezas().FORMATOS.horizontal
  function ajustar() {
    const c = contenedor.current, m = marcoRef.current, l = lienzoRef.current
    if (!c || !m || !l || !actual.current) return
    const [ancho, alto] = medidas()
    escala.current = Math.max(0.05, Math.min(c.clientWidth / ancho, (innerHeight * 0.75) / alto))
    Object.assign(m.style, { width: ancho * escala.current + 'px', height: alto * escala.current + 'px' })
    Object.assign(l.style, { width: ancho + 'px', height: alto + 'px', transform: `scale(${escala.current})` })
  }

  function dibujar() {
    const lienzo = lienzoRef.current!
    vivas.current.forEach((v) => v.quitar?.())
    lienzo.replaceChildren()
    vivas.current = actual.current!.piezas.map((p, i) => preparar(Piezas().montar(lienzo, p, { demo: true }), i))
    ajustar()
  }
  function redibujar(i: number) { // una sola pieza, cuando cambian sus opciones
    const vieja = vivas.current[i]
    vieja.quitar?.()
    const otra = preparar(Piezas().montar(lienzoRef.current!, actual.current!.piezas[i], { demo: true }), i)
    vieja.caja.replaceWith(otra.caja)
    vivas.current[i] = otra
  }
  function preparar(viva: Viva, i: number) {
    const caja = viva.caja, p = actual.current!.piezas[i]
    caja.dataset.nombre = Piezas().PIEZAS[p.tipo].nombre
    caja.classList.add(...CAJA.split(' '))
    caja.classList.toggle('elegida', i === elegidaRef.current)
    const asa = document.createElement('div')
    asa.className = ASA
    caja.append(asa)
    caja.addEventListener('pointerdown', (ev) => arrastrar(ev, actual.current!.piezas.indexOf(p), ev.target === asa))
    return viva
  }
  function posicionar(i: number) {
    const p = actual.current!.piezas[i]
    Object.assign(vivas.current[i].caja.style, { left: p.x + 'px', top: p.y + 'px', width: p.w + 'px', height: p.h + 'px' })
    for (const k of ['x', 'y', 'w', 'h'] as const) {
      const c = pos.current[k]
      if (c && document.activeElement !== c) c.value = String(p[k])
    }
  }

  // arrastrar para mover; desde la bolita, para cambiar el tamaño. Se pega a una grilla de 10 px (con Alt, no)
  function arrastrar(ev: PointerEvent, i: number, tamano: boolean) {
    ev.preventDefault()
    elegir(i)
    const p = actual.current!.piezas[i], x0 = ev.clientX, y0 = ev.clientY, inicio = { ...p }
    const [ancho, alto] = medidas()
    const caja = vivas.current[i].caja
    caja.setPointerCapture(ev.pointerId)
    const mover = (e: PointerEvent) => {
      const grilla = (v: number) => (e.altKey ? Math.round(v) : Math.round(v / 10) * 10)
      const dx = (e.clientX - x0) / escala.current, dy = (e.clientY - y0) / escala.current
      if (tamano) {
        p.w = Math.max(20, grilla(inicio.w + dx))
        p.h = Math.max(20, grilla(inicio.h + dy))
      } else {
        p.x = Math.min(ancho - 10, Math.max(10 - p.w, grilla(inicio.x + dx)))
        p.y = Math.min(alto - 10, Math.max(10 - p.h, grilla(inicio.y + dy)))
      }
      posicionar(i)
      if (p.x !== inicio.x || p.y !== inicio.y || p.w !== inicio.w || p.h !== inicio.h) marcar(true)
    }
    const soltar = () => {
      caja.removeEventListener('pointermove', mover)
      caja.removeEventListener('pointerup', soltar)
      caja.removeEventListener('pointercancel', soltar)
      if (tamano) redibujar(i) // algunas piezas se acomodan a su tamaño
    }
    caja.addEventListener('pointermove', mover)
    caja.addEventListener('pointerup', soltar)
    caja.addEventListener('pointercancel', soltar)
  }

  // --- el panel de opciones ---
  function elegir(i: number) {
    elegidaRef.current = i
    vivas.current.forEach((v, k) => v.caja.classList.toggle('elegida', k === i))
    setElegida(i)
    setPanel((n) => n + 1)
  }
  function mover(paso: number) { // el orden: lo de más adelante en la lista queda arriba
    const piezas = actual.current!.piezas, i = elegidaRef.current, j = i + paso
    if (j < 0 || j >= piezas.length) return
    ;[piezas[i], piezas[j]] = [piezas[j], piezas[i]]
    elegidaRef.current = j
    dibujar()
    elegir(j)
    marcar(true)
  }
  function quitar() {
    actual.current!.piezas.splice(elegidaRef.current, 1)
    elegidaRef.current = -1
    dibujar()
    elegir(-1)
    marcar(true)
  }
  function duplicar() {
    const piezas = actual.current!.piezas
    const copia: Pieza = JSON.parse(JSON.stringify(piezas[elegidaRef.current]))
    copia.x += 20
    copia.y += 20
    piezas.push(copia)
    dibujar()
    elegir(piezas.length - 1)
    marcar(true)
  }
  function sumar(tipo: string, def: DefPieza) {
    const [ancho, alto] = medidas()
    const w = Math.min(def.w, ancho), h = Math.min(def.h, alto)
    const piezas = actual.current!.piezas
    piezas.push({ tipo, x: Math.round((ancho - w) / 20) * 10, y: Math.round((alto - h) / 20) * 10, w, h, op: Piezas().predeterminadas(tipo) })
    dibujar()
    elegir(piezas.length - 1)
    marcar(true)
  }

  // --- guardar, elegir y borrar pantallas ---
  function abrir(p: Pantalla) {
    const a: Pantalla = JSON.parse(JSON.stringify(p))
    actual.current = a
    elegidaRef.current = -1
    Piezas().ponerCss(a.css, '#lienzo')
    aplicarTema()
    setLink(
      a.id
        ? {
            url: `http://127.0.0.1:${location.port || 80}/pantalla/${a.id}`,
            tam: a.formato === 'vertical' ? 'Tamaño en OBS: 1080 × 1920' : 'Tamaño en OBS: 1920 × 1080',
          }
        : null,
    )
    setAbierta((n) => n + 1)
    dibujar()
    elegir(-1)
    marcar(false)
  }
  async function cambiarPantalla(id: string) {
    if (!(await descartar())) return
    const p = pantallas.find((x) => x.id === id)
    if (p) abrir(p)
  }
  async function crear() {
    if (!(await descartar())) return
    abrir(nueva(pantallas.length))
    marcar(true)
  }
  async function guardar() {
    avisar('')
    let d: Pantalla
    try {
      d = await post<Pantalla>('/api/pantallas/guardar', actual.current)
    } catch (e) {
      return avisar(e instanceof ApiError ? e.message : 'La app no contestó.')
    }
    setPantallas((ps) => (ps.some((x) => x.id === d.id) ? ps.map((x) => (x.id === d.id ? d : x)) : [...ps, d]))
    const sel = elegidaRef.current
    abrir(d)
    if (sel >= 0 && sel < actual.current!.piezas.length) elegir(sel)
  }
  async function borrar() {
    const a = actual.current!
    if (!a.id || !(await preguntar({ titulo: `¿Borrás la pantalla "${a.nombre}"?`, descripcion: 'En OBS va a quedar vacía.', accion: 'Borrar', peligro: true }))) return
    try {
      await post('/api/pantallas/borrar', { id: a.id })
    } catch (e) {
      return avisar(e instanceof ApiError ? e.message : 'No se pudo borrar.')
    }
    const resto = pantallas.filter((x) => x.id !== a.id)
    setPantallas(resto)
    abrir(resto[0] || nueva(resto.length))
  }

  // al entrar: las piezas, las pantallas y los emotes. Al salir, el CSS propio y los relojes de las piezas se van.
  React.useEffect(() => {
    let vivo = true
    Promise.all([cargarScript('/emotes.js'), cargarScript('/piezas.js')]).then(
      async () => {
        let lista: Pantalla[] = []
        try {
          lista = await get<Pantalla[]>('/api/pantallas')
        } catch {
          avisar('No pude leer las pantallas.')
        }
        try {
          Piezas().MUESTRA.textos = await get<Record<string, string>>('/api/pantallas/textos')
        } catch {
          /* sin textos: las piezas muestran {nombre} */
        }
        try {
          const t = await get<Tema[]>('/api/pantallas/temas')
          temasRef.current = t
          setTemasEstado(t)
        } catch {
          avisar('No pude leer los temas.')
        }
        if (!vivo) return
        setPantallas(lista)
        setListo(true)
        abrir(lista[0] || nueva(0))
        if (!lista.length) marcar(true)
        Emotes().cargar('').then(() => vivas.current.forEach((v) => v.emotes?.()))
      },
      (e: Error) => vivo && avisar(e.message),
    )
    const observador = new ResizeObserver(ajustar)
    observador.observe(contenedor.current!)
    return () => {
      vivo = false
      observador.disconnect()
      vivas.current.forEach((v) => v.quitar?.())
      vivas.current = []
      ;(window as unknown as { Piezas?: PiezasApi }).Piezas?.ponerCss('', '#lienzo')
      ;(window as unknown as { Piezas?: PiezasApi }).Piezas?.ponerTema(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- una vez; lo que usa vive en refs
  }, [])

  // el teclado: flechas para mover de a 1 px (con Shift, de a 10), Supr para quitar y Esc para soltar
  React.useEffect(() => {
    const tecla = (ev: KeyboardEvent) => {
      const foco = document.activeElement as HTMLElement | null
      if (elegidaRef.current < 0 || ev.defaultPrevented || !actual.current) return
      if (foco && (/INPUT|SELECT|TEXTAREA/.test(foco.tagName) || foco.isContentEditable || foco.closest('[role=combobox],[role=slider],[role=switch],[role=dialog],[role=listbox],[role=menu]'))) return
      const paso = ev.shiftKey ? 10 : 1, p = actual.current.piezas[elegidaRef.current]
      const mov = ({ ArrowLeft: [-paso, 0], ArrowRight: [paso, 0], ArrowUp: [0, -paso], ArrowDown: [0, paso] } as Record<string, number[]>)[ev.key]
      if (mov) {
        ev.preventDefault()
        p.x += mov[0]
        p.y += mov[1]
        posicionar(elegidaRef.current)
        marcar(true)
      } else if (ev.key === 'Delete') quitar()
      else if (ev.key === 'Escape') elegir(-1)
    }
    document.addEventListener('keydown', tecla)
    return () => document.removeEventListener('keydown', tecla)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- usa refs
  }, [])

  // cambios sin guardar: avisa al cerrar la pestaña y al ir a otra página del panel
  React.useEffect(() => {
    const salir = (ev: BeforeUnloadEvent) => {
      if (sucioRef.current) ev.preventDefault()
    }
    const clic = (ev: MouseEvent) => {
      if (!sucioRef.current || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return
      const a = (ev.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null
      if (!a || a.target || a.origin !== location.origin || a.pathname === location.pathname) return
      ev.preventDefault()
      ev.stopPropagation()
      void descartar().then((si) => si && navegar(a.pathname + a.search))
    }
    addEventListener('beforeunload', salir)
    document.addEventListener('click', clic, true)
    return () => {
      removeEventListener('beforeunload', salir)
      document.removeEventListener('click', clic, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- usa refs
  }, [])

  const a = actual.current
  const pieza = a && elegida >= 0 ? a.piezas[elegida] : undefined
  const def = pieza && Piezas().PIEZAS[pieza.tipo]

  return (
    <>
      <Encabezado
        titulo="Pantallas para OBS"
        ayuda={
          <>
            <ol className="list-decimal space-y-1 pl-5">
              <li>
                Creá una pantalla, sumale piezas (chat, alertas, marcos, metas…) y acomodalas arrastrando. La bolita de la
                esquina cambia el tamaño. Con las flechas del teclado la movés de a 1 px (con Shift, de a 10).
              </li>
              <li>
                Tocá una pieza para cambiar sus colores y textos en el panel de la derecha. Lo que ves es una muestra: en
                OBS sale con el chat y los datos reales.
              </li>
              <li>
                Guardá y copiá el link. En OBS: <b>Fuente → Navegador</b>, pegá el link y poné el tamaño de la pantalla
                (1920 × 1080, o 1080 × 1920 si es vertical). Va arriba de tu juego o tu cámara: lo vacío queda
                transparente.
              </li>
              <li>Si después cambiás algo y guardás, OBS lo toma solo en unos segundos.</li>
              <li>
                <b>Animaciones</b>: cada pieza tiene cómo entra y, el chat, las alertas y el último seguidor, cómo sale.
                Las demás entran cuando carga la pantalla, después de la espera que les pongas: con esperas distintas
                entran una atrás de otra. Para que se vean cada vez que cambiás de escena, en la fuente de OBS tildá{' '}
                <b>Actualizar navegador cuando la escena se activa</b>. <b>Probar animación</b> la muestra en el lienzo.
              </li>
              <li>
                <b>Letra</b>: además de las de siempre, cualquier fuente de Google Fonts: elegí <b>De Google Fonts</b> y
                escribí su nombre tal cual figura en fonts.google.com (por ejemplo, Bebas Neue).
              </li>
              <li>
                <b>Temas</b>: una paleta de cuatro colores (texto, fondo, acento y segundo acento) y una letra de Google.
                Elegí el tema de la pantalla arriba y, en cada color de una pieza, tocá uno del tema en vez de un color
                fijo. Si después cambiás el tema, cambian todas las pantallas que lo usan. Con <b>Copiar</b> lo pasás
                como texto a otra persona, y ella lo trae con <b>Importar</b>.
              </li>
              <li>
                <b>Textos compartidos</b>: escribí <code>{'{tema}'}</code> en un texto, un título de marco o meta, o la
                cuenta regresiva, y muestra lo que pongas en <b>tema</b> abajo. Lo cambiás una vez y cambia en todas las
                pantallas (OBS lo toma en unos 15 segundos).
              </li>
              <li>
                El <b>marco de ventana</b> es solo el borde: poné la cámara o la captura de la ventana debajo de esta
                fuente, en el mismo lugar.
              </li>
            </ol>
            <h3 className="pt-2 font-medium text-foreground">Armarlas con una IA (MCP)</h3>
            <p>
              Stream Kit tiene un servidor MCP en <code>http://127.0.0.1:8080/mcp</code>: un agente de IA puede ver qué
              piezas hay, armar y cambiar pantallas (también su CSS), borrarlas y leer los datos en vivo. Solo contesta a
              esta PC y mientras la app está abierta.
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>
                <b>Claude Code</b>: <code className="break-all">claude mcp add --transport http stream-kit http://127.0.0.1:8080/mcp</code>
              </li>
              <li>
                <b>Otros</b> (Claude Desktop, Cursor, VS Code…): agregá un servidor MCP de tipo HTTP con esa dirección.
              </li>
              <li>
                <b>Sin MCP</b>: pasale al agente{' '}
                <a href="/llms.txt" target="_blank" className="text-primary underline-offset-4 hover:underline">
                  /llms.txt
                </a>
                , la guía para IAs con todo lo que puede hacer, cada pieza y sus opciones.
              </li>
            </ul>
            <p>
              Después pedile, por ejemplo: "armá una pantalla de juego con el chat abajo a la derecha que se borre a los
              15 segundos y un marco violeta para la cámara arriba a la izquierda". Si la tenés abierta acá, tocá otra
              pantalla y volvé para ver los cambios.
            </p>
          </>
        }
      />

      <div className="space-y-4">
        <Seccion>
          <div key={abierta} className="flex flex-wrap items-end gap-2">
            <div className="grid gap-1.5">
              <Label htmlFor="pantalla-elegir" className="text-muted-foreground">Pantalla</Label>
              <Select value={a ? a.id || NUEVA : ''} onValueChange={(v) => void cambiarPantalla(v)} disabled={!listo}>
                <SelectTrigger id="pantalla-elegir" className="w-48 max-w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {pantallas.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.nombre}</SelectItem>
                  ))}
                  {a && !a.id && <SelectItem value={NUEVA}>{a.nombre} (nueva)</SelectItem>}
                </SelectContent>
              </Select>
            </div>
            <Button variant="outline" onClick={() => void crear()} disabled={!listo}>
              <PlusIcon aria-hidden /> Nueva
            </Button>
            <div className="grid gap-1.5">
              <Label htmlFor="pantalla-nombre" className="text-muted-foreground">Nombre</Label>
              <Input
                id="pantalla-nombre"
                maxLength={60}
                className="w-48 max-w-full"
                defaultValue={a?.nombre}
                disabled={!listo}
                onChange={(e) => {
                  a!.nombre = e.target.value
                  marcar(true)
                }}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pantalla-formato" className="text-muted-foreground">Formato</Label>
              <Select
                defaultValue={a?.formato}
                disabled={!listo}
                onValueChange={(v) => {
                  a!.formato = v
                  dibujar()
                  marcar(true)
                }}
              >
                <SelectTrigger id="pantalla-formato" className="w-52 max-w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="horizontal">Horizontal 1920 × 1080</SelectItem>
                  <SelectItem value="vertical">Vertical 1080 × 1920</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pantalla-tema" className="text-muted-foreground">Tema</Label>
              <Select value={a?.tema && temas.some((t) => t.id === a.tema) ? a.tema : SIN_TEMA} disabled={!listo} onValueChange={(v) => elegirTema(v === SIN_TEMA ? '' : v)}>
                <SelectTrigger id="pantalla-tema" className="w-44 max-w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_TEMA}>Sin tema</SelectItem>
                  {temas.filter((t) => t.id).map((t) => (
                    <SelectItem key={t.id} value={t.id!}>{t.nombre}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={() => void guardar()} disabled={!listo}>
              <SaveIcon aria-hidden /> Guardar
            </Button>
            <Button variant="destructive" onClick={() => void borrar()} disabled={!a?.id}>
              <Trash2Icon aria-hidden /> Borrar
            </Button>
            {sucio && <Badge variant="secondary" className="mb-2">Sin guardar</Badge>}
          </div>
          {link && (
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              Link para OBS:
              <code className="rounded-md border bg-muted px-2 py-1 font-mono text-xs break-all">{link.url}</code>
              <CopyButton value={link.url} variant="outline" size="sm" onCopyError={() => avisar('El navegador no dejó copiar: seleccioná el link a mano.')}>
                Copiar
              </CopyButton>
              <span className="text-muted-foreground">{link.tam}</span>
            </p>
          )}
          <p role="status" className={cn('text-sm text-destructive', aviso && 'mt-3')}>{aviso}</p>
        </Seccion>

        <Seccion titulo="Sumar una pieza">
          <div className="flex flex-wrap gap-2">
            {listo &&
              Object.entries(Piezas().PIEZAS).map(([tipo, d]) => (
                <Button key={tipo} variant="outline" size="sm" onClick={() => sumar(tipo, d)}>
                  <PlusIcon aria-hidden /> {d.nombre}
                </Button>
              ))}
          </div>
        </Seccion>

        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Seccion className="min-w-0">
            <div ref={contenedor} className="w-full">
              {/* el damero muestra lo transparente, como queda en OBS */}
              <div
                ref={marcoRef}
                className="relative mx-auto overflow-hidden rounded-lg ring-1 ring-border"
                style={{ background: 'repeating-conic-gradient(var(--muted) 0 25%, var(--background) 0 50%) 0 0 / 32px 32px' }}
                onPointerDown={(ev) => {
                  if (ev.target === lienzoRef.current || ev.target === marcoRef.current) elegir(-1)
                }}
              >
                <div ref={lienzoRef} id="lienzo" className="absolute top-0 left-0 origin-top-left" />
              </div>
            </div>
          </Seccion>

          <Seccion titulo={def?.nombre}>
            {!pieza || !def ? (
              <p className="text-sm text-muted-foreground">Tocá una pieza para cambiarla.</p>
            ) : (
              <div key={panel} className="grid gap-3">
                <div className="grid grid-cols-4 gap-1.5">
                  {([['x', 'X'], ['y', 'Y'], ['w', 'Ancho'], ['h', 'Alto']] as const).map(([k, n]) => (
                    <div key={k} className="grid min-w-0 gap-1.5">
                      <Label htmlFor={'pos-' + k} className="text-muted-foreground">{n}</Label>
                      <Input
                        id={'pos-' + k}
                        type="number"
                        className="px-2"
                        defaultValue={pieza[k]}
                        ref={(c) => {
                          pos.current[k] = c
                          if (!c) return
                          // el change nativo (al soltar el campo o con Enter), como antes; el de React es por tecla
                          c.onchange = () => {
                            const v = Math.round(Number(c.value))
                            if (!Number.isFinite(v)) return
                            pieza[k] = k === 'w' || k === 'h' ? Math.max(20, v) : v
                            posicionar(elegida)
                            redibujar(elegida)
                            marcar(true)
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>
                {(() => {
                  const valores = { ...Piezas().predeterminadas(pieza.tipo), ...pieza.op }
                  const campo = (x: Opcion) => (
                    <Campo
                      key={x.clave}
                      x={x}
                      tema={temaDe(a?.tema)}
                      valor={valores[x.clave]}
                      cambiar={(v) => {
                        pieza.op = { ...pieza.op, [x.clave]: v }
                        redibujar(elegida)
                        marcar(true)
                        if (x.clave === 'fuente') setPanel((n) => n + 1) // aparece o se va el nombre de la fuente de Google
                      }}
                    />
                  )
                  const visibles = def.opciones.filter((x) => x.clave !== 'fuente_google' || valores.fuente === 'google')
                  const anim = visibles.filter((x) => ANIMACION.includes(x.clave))
                  return (
                    <>
                      {visibles.filter((x) => !ANIMACION.includes(x.clave)).map(campo)}
                      {anim.length > 0 && (
                        <div className="grid gap-3 border-t pt-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">Animación</span>
                            <Button variant="outline" size="sm" onClick={() => vivas.current[elegida]?.probar?.()}>
                              <PlayIcon aria-hidden /> Probar animación
                            </Button>
                          </div>
                          {anim.map(campo)}
                        </div>
                      )}
                    </>
                  )
                })()}
                <Campo
                  x={{ clave: 'clase', tipo: 'texto', nombre: 'Clase CSS (para el CSS propio)' }}
                  valor={pieza.clase || ''}
                  cambiar={(v) => {
                    const t = String(v).trim()
                    if (t && !/^[a-zA-Z][\w-]{0,39}$/.test(t)) return avisar('La clase va con letras, números, - y _, y empieza con una letra.')
                    avisar('')
                    if (t) pieza.clase = t
                    else delete pieza.clase
                    redibujar(elegida)
                    marcar(true)
                  }}
                />
                <div className="flex flex-wrap gap-1.5">
                  <Button variant="outline" size="sm" onClick={() => mover(1)}>Al frente</Button>
                  <Button variant="outline" size="sm" onClick={() => mover(-1)}>Atrás</Button>
                  <Button variant="outline" size="sm" onClick={duplicar}>Duplicar</Button>
                  <Button variant="destructive" size="sm" onClick={quitar}>Quitar</Button>
                </div>
              </div>
            )}
          </Seccion>
        </div>

        {listo && (
          <Temas
            temas={temas}
            setTemas={setTemas}
            enUso={a?.tema}
            usar={(id) => elegirTema(id)}
            avisarCopia={avisar}
          />
        )}

        {listo && (
          <Textos
            alGuardar={(t) => {
              Piezas().MUESTRA.textos = t
              dibujar()
            }}
          />
        )}

        <Collapsible className="rounded-xl border bg-card text-sm">
          <CollapsibleTrigger className="group flex w-full items-center gap-2 px-4 py-3 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
            <ChevronRightIcon aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-90" />
            CSS propio de esta pantalla
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 px-4 pb-4">
            <Textarea
              key={abierta}
              rows={12}
              spellCheck={false}
              aria-label="CSS propio de esta pantalla"
              className="min-h-64 resize-y font-mono text-[13px] leading-relaxed field-sizing-fixed"
              placeholder={'[data-tipo="chat"] .pz-mensaje { border-radius: 0; }\n.mi-marco .pz-marco { border-style: dashed !important; }'}
              defaultValue={a?.css || ''}
              disabled={!listo}
              onChange={(e) => {
                a!.css = e.target.value
                Piezas().ponerCss(a!.css, '#lienzo')
                marcar(true)
              }}
            />
            <p className="text-muted-foreground [&_code]:text-foreground">
              Se ve al toque en el lienzo y vale solo para esta pantalla. Cada pieza tiene <code>data-tipo</code> (
              <code>[data-tipo="chat"]</code>, <code>alertas</code>, <code>marco</code>, <code>texto</code>,{' '}
              <code>titulo</code>, <code>viewers</code>, <code>meta</code>, <code>lluvia</code>, <code>ultimo</code>,{' '}
              <code>cuenta</code>, <code>imagen</code>) y la clase que le pongas en su panel. Adentro: <code>.pz-mensaje</code>,{' '}
              <code>.pz-quien</code>, <code>.pz-alerta</code>, <code>.pz-alerta-quien</code>, <code>.pz-marco</code>,{' '}
              <code>.pz-marco-titulo</code>, <code>.pz-bloque</code>, <code>.pz-meta</code>, <code>.pz-meta-barra i</code>,{' '}
              <code>.pz-gota</code>, <code>.pz-imagen</code> y <code>.emote</code>. Los colores y tamaños del panel van directo en cada pieza: para
              pisarlos, usá <code>!important</code>. Se pueden usar fuentes de Google con <code>@import</code>.
            </p>
          </CollapsibleContent>
        </Collapsible>
      </div>

      <AlertDialog
        open={preguntando}
        onOpenChange={(o) => {
          if (o) return
          pregunta?.responder(false) // si ya respondió que sí, esto no cambia nada
          setPreguntando(false)
        }}
      >
        <AlertDialogContent {...(!pregunta?.descripcion && { 'aria-describedby': undefined })}>
          <AlertDialogHeader>
            <AlertDialogTitle>{pregunta?.titulo}</AlertDialogTitle>
            {pregunta?.descripcion && <AlertDialogDescription>{pregunta.descripcion}</AlertDialogDescription>}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction variant={pregunta?.peligro ? 'destructive' : 'default'} onClick={() => pregunta?.responder(true)}>
              {pregunta?.accion}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

/** Un campo de opciones, según el tipo que dice el esquema de la pieza. */
function Campo({ x, valor, cambiar, tema }: { x: Opcion; valor: unknown; cambiar: (v: unknown) => void; tema?: Tema | null }) {
  const id = React.useId()
  if (x.tipo === 'imagen') return <CampoImagen x={x} valor={String(valor || '')} cambiar={cambiar} />
  if (x.tipo === 'color') return <CampoColor id={id} x={x} valor={String(valor || '')} cambiar={cambiar} tema={tema} />
  if (x.tipo === 'si')
    return (
      <div className="flex items-center gap-2">
        <Switch id={id} defaultChecked={!!valor} onCheckedChange={cambiar} />
        <Label htmlFor={id} className="font-normal">{x.nombre}</Label>
      </div>
    )
  let control: React.ReactNode
  if (x.tipo === 'elegir')
    control = (
      <Select defaultValue={String(valor ?? '')} onValueChange={cambiar}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {(x.valores || []).map(([v, n]) => (
            <SelectItem key={v} value={v}>{n}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    )
  else
    control = (
      <Input
        id={id}
        type={x.tipo === 'numero' ? 'number' : 'text'}
        min={x.min}
        max={x.max}
        maxLength={x.tipo === 'texto' ? 300 : undefined}
        defaultValue={valor == null ? '' : String(valor)}
        onChange={(e) => {
          const v = e.target.value
          if (x.tipo !== 'numero') return cambiar(v)
          const n = Number(v)
          if (v !== '' && Number.isFinite(n)) cambiar(Math.min(x.max ?? n, Math.max(x.min ?? n, n)))
        }}
      />
    )
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground">{x.nombre}</Label>
      {control}
    </div>
  )
}

/** La imagen de la pieza: una subida (se elige de la lista o se sube acá) o un link https. */
function CampoImagen({ x, valor, cambiar }: { x: Opcion; valor: string; cambiar: (v: unknown) => void }) {
  const id = React.useId()
  const [lista, setLista] = React.useState<string[]>([])
  const [actual, setActual] = React.useState(valor)
  const [aviso, setAviso] = React.useState('')
  const [subiendo, setSubiendo] = React.useState(false)
  React.useEffect(() => {
    get<string[]>('/api/pantallas/imagenes').then(setLista, () => setAviso('No pude leer las imágenes subidas.'))
  }, [])
  const usar = (v: string) => {
    setActual(v)
    cambiar(v)
  }
  async function subir(archivo: File) {
    setAviso('')
    setSubiendo(true)
    try {
      const r = await fetch('/api/pantallas/imagen?' + encodeURIComponent(archivo.name), {
        method: 'POST',
        headers: { 'X-Panel': '1', 'Content-Type': 'application/octet-stream' },
        body: archivo,
      })
      const j = await r.json().catch(() => ({ error: `La app contestó ${r.status}.` }))
      if (!r.ok) return setAviso(j.error)
      setLista(j.imagenes)
      usar(j.nombre)
    } catch {
      setAviso('La app no contestó.')
    } finally {
      setSubiendo(false)
    }
  }
  const esLink = actual.startsWith('https://')
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground">{x.nombre}</Label>
      <Select value={esLink ? '' : actual} onValueChange={usar}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder={lista.length ? 'Elegí una imagen subida' : 'Todavía no subiste ninguna'} />
        </SelectTrigger>
        <SelectContent>
          {lista.map((n) => (
            <SelectItem key={n} value={n}>{n}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Label htmlFor={id + '-subir'} className="text-muted-foreground">Subir una (png, jpg, gif o webp, hasta 15 MB)</Label>
      <Input
        id={id + '-subir'}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        disabled={subiendo}
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void subir(f)
          e.target.value = ''
        }}
      />
      <Label htmlFor={id + '-link'} className="text-muted-foreground">O un link</Label>
      <Input
        id={id + '-link'}
        placeholder="https://…"
        defaultValue={esLink ? actual : ''}
        onChange={(e) => {
          const t = e.target.value.trim()
          if (/^https:\/\/\S+$/.test(t)) usar(t)
        }}
      />
      {aviso && <p role="status" className="text-sm text-destructive">{aviso}</p>}
    </div>
  )
}

/** Los textos compartidos: {tema} en cualquier pieza de cualquier pantalla muestra el de "tema". */
function Textos({ alGuardar }: { alGuardar: (t: Record<string, string>) => void }) {
  const [filas, setFilas] = React.useState<{ k: string; v: string; id: number }[]>([])
  const [aviso, setAviso] = React.useState<{ texto: string; error?: boolean }>()
  const [sucio, setSucio] = React.useState(false)
  const n = React.useRef(0)
  React.useEffect(() => {
    get<Record<string, string>>('/api/pantallas/textos').then(
      (t) => setFilas(Object.entries(t).map(([k, v]) => ({ k, v, id: n.current++ }))),
      () => setAviso({ texto: 'No pude leer los textos.', error: true }),
    )
  }, [])
  const cambiar = (id: number, campo: 'k' | 'v', valor: string) => {
    setFilas((fs) => fs.map((f) => (f.id === id ? { ...f, [campo]: valor } : f)))
    setSucio(true)
  }
  async function guardar() {
    setAviso(undefined)
    try {
      const t = await post<Record<string, string>>('/api/pantallas/textos', Object.fromEntries(filas.filter((f) => f.k.trim()).map((f) => [f.k.trim(), f.v])))
      setSucio(false)
      setAviso({ texto: 'Guardados. OBS los toma en unos 15 segundos.' })
      alGuardar(t)
    } catch (e) {
      setAviso({ texto: e instanceof ApiError ? e.message : 'La app no contestó.', error: true })
    }
  }
  return (
    <Seccion
      titulo="Textos compartidos"
      descripcion={<>Escribí <code>{'{tema}'}</code> en una pieza y muestra lo que pongas acá en tema, en todas las pantallas.</>}
    >
      <div className="grid gap-2">
        {filas.map((f) => (
          <div key={f.id} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] items-center gap-2">
            <Input aria-label="Nombre" placeholder="tema" maxLength={30} value={f.k} onChange={(e) => cambiar(f.id, 'k', e.target.value.toLowerCase())} />
            <Input aria-label={`Texto de ${f.k || 'este nombre'}`} placeholder="Ranked hasta Inmortal" maxLength={300} value={f.v} onChange={(e) => cambiar(f.id, 'v', e.target.value)} />
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Quitar ${f.k || 'este texto'}`}
              onClick={() => {
                setFilas((fs) => fs.filter((x) => x.id !== f.id))
                setSucio(true)
              }}
            >
              <XIcon />
            </Button>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setFilas((fs) => [...fs, { k: '', v: '', id: n.current++ }])} disabled={filas.length >= 30}>
            <PlusIcon aria-hidden /> Agregar texto
          </Button>
          <Button size="sm" onClick={() => void guardar()} disabled={!sucio}>
            <SaveIcon aria-hidden /> Guardar textos
          </Button>
          {aviso && (
            <p role="status" className={cn('text-sm', aviso.error ? 'text-destructive' : 'text-muted-foreground')}>{aviso.texto}</p>
          )}
        </div>
      </div>
    </Seccion>
  )
}

/** Un color: uno fijo o uno del tema de la pantalla (se guarda como "tema:acento" y cambia si cambia el tema). */
function CampoColor({ id, x, valor, cambiar, tema }: { id: string; x: Opcion; valor: string; cambiar: (v: unknown) => void; tema?: Tema | null }) {
  const [actual, setActual] = React.useState(valor)
  const delTema = actual.startsWith('tema:') ? actual.slice(5) : ''
  const usar = (v: string) => {
    setActual(v)
    cambiar(v)
  }
  const fijo = /^#[0-9a-f]{6}$/i.test(actual) ? actual : (tema && delTema && tema.colores[delTema]) || '#000000'
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-muted-foreground">{x.nombre}</Label>
      {tema && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={`${x.nombre}: colores del tema`}>
          {COLORES_TEMA.map(([c, n]) => (
            <button
              key={c}
              type="button"
              aria-pressed={delTema === c}
              title={`${n} del tema`}
              onClick={() => usar('tema:' + c)}
              className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-pressed:border-primary aria-pressed:bg-primary/10"
            >
              <span aria-hidden className="size-3.5 rounded-sm ring-1 ring-border" style={{ background: tema.colores[c] }} />
              {n}
            </button>
          ))}
        </div>
      )}
      {delTema ? (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span aria-hidden className="size-4 rounded-sm ring-1 ring-border" style={{ background: fijo }} />
          Del tema{tema ? '' : ' (esta pantalla no tiene tema: usa el de siempre)'}
          <Button variant="link" size="sm" className="h-auto p-0" onClick={() => usar(fijo)}>
            Usar un color fijo
          </Button>
        </p>
      ) : (
        <ColorPicker
          key={actual === fijo ? 'fijo' : actual}
          id={id}
          className="w-full"
          alpha={false}
          format="hex"
          defaultValue={fijo}
          // piezas.js solo lee #rrggbb: si eligen otro formato en el selector, no se toma
          onValueChange={(v) => /^#[0-9a-f]{6}$/i.test(v) && usar(v)}
        />
      )}
    </div>
  )
}

/** Los temas: se crean, se cambian, se copian como texto para compartirlos y se importan. */
function Temas({
  temas,
  setTemas,
  enUso,
  usar,
  avisarCopia,
}: {
  temas: Tema[]
  setTemas: (t: Tema[]) => void
  enUso?: string
  usar: (id: string) => void
  avisarCopia: (texto: string) => void
}) {
  const [sucio, setSucio] = React.useState(false)
  const [aviso, setAviso] = React.useState<{ texto: string; error?: boolean }>()
  const [importar, setImportar] = React.useState('')
  const n = React.useRef(0)
  const clave = (t: Tema) => t.id || 'nuevo-' + (t.clave ??= n.current++)
  const cambiar = (lista: Tema[]) => {
    setTemas(lista)
    setSucio(true)
    setAviso(undefined)
  }
  const editar = (i: number, cambio: Partial<Tema>) => cambiar(temas.map((t, k) => (k === i ? { ...t, ...cambio } : t)))
  async function guardar() {
    try {
      const lista = await post<Tema[]>('/api/pantallas/temas', temas.map(({ clave: _, ...t }) => t))
      setTemas(lista)
      setSucio(false)
      setAviso({ texto: 'Guardados. Las pantallas que los usan cambian en unos segundos.' })
    } catch (e) {
      setAviso({ texto: e instanceof ApiError ? e.message : 'La app no contestó.', error: true })
    }
  }
  function traer() {
    try {
      const t = JSON.parse(importar)
      if (!t || typeof t !== 'object' || typeof t.colores !== 'object') throw new Error()
      cambiar([...temas, { nombre: String(t.nombre || 'Importado'), letra: String(t.letra || ''), colores: { ...TEMA_NUEVO().colores, ...t.colores } }])
      setImportar('')
      setAviso({ texto: 'Importado. Guardá los temas para usarlo.' })
    } catch {
      setAviso({ texto: 'Eso no es un tema: pegá el texto que copió la otra persona con Copiar.', error: true })
    }
  }
  return (
    <Seccion
      titulo="Temas"
      descripcion="Una paleta de colores y una letra que comparten las piezas. Cambiás el tema y cambian todas las pantallas que lo usan."
    >
      <div className="grid gap-4">
        {temas.map((t, i) => (
          <div key={clave(t)} className="grid gap-3 rounded-lg border p-3">
            <div className="flex flex-wrap items-end gap-2">
              <div className="grid min-w-0 flex-1 gap-1.5">
                <Label htmlFor={'tema-nombre-' + clave(t)} className="text-muted-foreground">Nombre</Label>
                <Input id={'tema-nombre-' + clave(t)} maxLength={40} value={t.nombre} onChange={(e) => editar(i, { nombre: e.target.value })} />
              </div>
              <div className="grid min-w-0 flex-1 gap-1.5">
                <Label htmlFor={'tema-letra-' + clave(t)} className="text-muted-foreground">Letra (de Google Fonts)</Label>
                <Input id={'tema-letra-' + clave(t)} maxLength={60} placeholder="Anton" value={t.letra} onChange={(e) => editar(i, { letra: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {COLORES_TEMA.map(([c, nombre]) => (
                <div key={c} className="grid min-w-0 gap-1.5">
                  <Label htmlFor={`tema-${c}-${clave(t)}`} className="text-muted-foreground">{nombre}</Label>
                  <ColorPicker
                    id={`tema-${c}-${clave(t)}`}
                    className="w-full"
                    alpha={false}
                    format="hex"
                    defaultValue={t.colores[c]}
                    onValueChange={(v) => /^#[0-9a-f]{6}$/i.test(v) && editar(i, { colores: { ...t.colores, [c]: v } })}
                  />
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {t.id && t.id !== enUso && (
                <Button variant="outline" size="sm" onClick={() => usar(t.id!)}>Usar en esta pantalla</Button>
              )}
              {t.id === enUso && <Badge variant="secondary">En esta pantalla</Badge>}
              <CopyButton
                value={JSON.stringify({ nombre: t.nombre, letra: t.letra, colores: t.colores })}
                variant="outline"
                size="sm"
                onCopyError={() => avisarCopia('El navegador no dejó copiar el tema.')}
              >
                Copiar
              </CopyButton>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => cambiar(temas.filter((_, k) => k !== i))}>
                Quitar
              </Button>
            </div>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => cambiar([...temas, TEMA_NUEVO()])} disabled={temas.length >= 20}>
            <PlusIcon aria-hidden /> Nuevo tema
          </Button>
          <Button size="sm" onClick={() => void guardar()} disabled={!sucio}>
            <SaveIcon aria-hidden /> Guardar temas
          </Button>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid min-w-0 flex-1 gap-1.5">
            <Label htmlFor="tema-importar" className="text-muted-foreground">Importar un tema que te pasaron</Label>
            <Input id="tema-importar" placeholder='{"nombre": "…", "colores": {…}}' value={importar} onChange={(e) => setImportar(e.target.value)} />
          </div>
          <Button variant="outline" size="sm" onClick={traer} disabled={!importar.trim()}>Importar</Button>
        </div>
        {aviso && <p role="status" className={cn('text-sm', aviso.error ? 'text-destructive' : 'text-muted-foreground')}>{aviso.texto}</p>}
      </div>
    </Seccion>
  )
}
