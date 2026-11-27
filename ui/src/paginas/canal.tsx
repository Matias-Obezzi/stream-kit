// Título y categoría de Twitch y Kick a la vez, con presets. Antes: web/canal.html.
import { XIcon } from 'lucide-react'
import * as React from 'react'
import { Columnas, Encabezado, Seccion } from '@/components/pagina'
import { Confirmer, confirm } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { get, post, usePoll } from '@/lib/api'
import { Enlace } from '@/lib/router'
import { cn } from '@/lib/utils'

type P = 'twitch' | 'kick'
const PL: P[] = ['twitch', 'kick']
const NOMBRES: Record<P, string> = { twitch: 'Twitch', kick: 'Kick' }
const IDIOMAS: Record<string, string> = { es: 'español', en: 'inglés', pt: 'portugués', other: 'otro' }
const DEJAR = 'dejar' // Radix Select no acepta '' como valor: esta es «Dejar la que está»

interface Cat {
  id: string | number
  nombre: string
}
interface Canal {
  error?: string
  titulo: string
  categoria: Cat
  idioma: string
  etiquetas: string[]
  en_vivo?: boolean
}
interface Preset {
  nombre: string
  titulo: string
  idioma: string
  etiquetas: string[]
  categorias: Partial<Record<P, Cat>>
}
type Busqueda = Record<P, Cat[]> & { error_twitch?: string; error_kick?: string }
interface Escenas {
  estado: 'conectando' | 'conectado' | 'desconectado' | 'apagado' | 'clave' | 'sin obs'
  escena: string
  escenas: string[]
  en_vivo: boolean
  reglas: Record<string, string>
  ultimo: { escena: string; preset: string; resultado: Partial<Record<P, { ok: boolean; error?: string }>> & { error?: string } } | null
}

const ESTADO_OBS: Record<Escenas['estado'], string> = {
  conectando: 'Buscando OBS…',
  desconectado: 'Esperando a OBS: abrilo y se conecta solo.',
  'sin obs': 'No encontré OBS en esta PC.',
  apagado: 'El servidor WebSocket de OBS está apagado: prendelo en OBS → Herramientas → Ajustes del servidor WebSocket.',
  clave: 'OBS no aceptó la contraseña del WebSocket: en OBS → Herramientas → Ajustes del servidor WebSocket, tocá Aplicar y probá de nuevo.',
  conectado: '',
}

// cada escena de OBS con su preset: mientras transmitís, al quedarte 5 s en una escena se pone su preset
function SegunEscena({ presets }: { presets: Preset[] }) {
  const { datos, refrescar } = usePoll<Escenas>('/api/canal/escenas', 5000)
  const [error, setError] = React.useState('')
  if (!datos) return <p className="text-sm text-muted-foreground">Buscando OBS…</p>

  async function elegir(escena: string, preset: string) {
    setError('')
    try {
      await post('/api/canal/escenas/guardar', { reglas: { ...datos!.reglas, [escena]: preset } })
      refrescar()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const u = datos.ultimo
  const fallas = u
    ? [u.resultado.error, ...PL.map((p) => u.resultado[p] && !u.resultado[p]!.ok && `${NOMBRES[p]}: ${u.resultado[p]!.error}`)].filter(Boolean)
    : []
  return (
    <div className="grid gap-3">
      <ul className="space-y-2">
        <Linea tono={datos.estado === 'conectado' ? 'on' : datos.estado === 'desconectado' || datos.estado === 'conectando' ? 'medio' : 'err'}>
          {datos.estado === 'conectado'
            ? datos.en_vivo
              ? 'Conectado a OBS, en vivo: al quedarte 5 segundos en una escena se pone su preset.'
              : 'Conectado a OBS. Se aplica solo mientras transmitís.'
            : ESTADO_OBS[datos.estado]}
        </Linea>
        {u && (
          <Linea tono={fallas.length ? 'err' : 'on'}>
            {`Último: «${u.escena}» puso «${u.preset}»` + (fallas.length ? ` · ${fallas.join(' · ')}` : '')}
          </Linea>
        )}
      </ul>
      {datos.escenas.length > 0 &&
        (presets.length ? (
          <>
            <ul className="grid gap-3">
              {presets.map((p) => (
                <li key={p.nombre} className="grid gap-1.5">
                  <p className="text-sm font-medium">{p.nombre}</p>
                  <div role="group" aria-label={`Escenas de OBS con el preset ${p.nombre}`} className="flex flex-wrap gap-1.5">
                    {datos.escenas.map((e) => {
                      const puesta = datos.reglas[e] === p.nombre
                      return (
                        <Button
                          key={e}
                          size="sm"
                          variant={puesta ? 'default' : 'outline'}
                          aria-pressed={puesta}
                          title={
                            puesta
                              ? `Sacarle este preset a ${e}`
                              : `Poner este preset en ${e}` + (datos.reglas[e] ? ` (ahora tiene ${datos.reglas[e]})` : '')
                          }
                          className={cn('h-7 max-w-full px-2 text-xs', e === datos.escena && 'ring-1 ring-primary')}
                          onClick={() => elegir(e, puesta ? '' : p.nombre)}
                        >
                          <span className="truncate">{e}</span>
                        </Button>
                      )
                    })}
                  </div>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">
              {(() => {
                const libres = datos.escenas.filter((e) => !presets.some((p) => p.nombre === datos.reglas[e]))
                return libres.length ? `Sin preset, no cambian nada: ${libres.join(', ')}.` : 'Todas las escenas tienen preset.'
              })()}{' '}
              Cada escena va con un preset: si la marcás en otro, pasa a ese. La que tiene el borde es la de ahora.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Guardá algún preset arriba y después marcá en qué escenas va.</p>
        ))}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

const norm = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

function Linea({ tono, children }: { tono: 'on' | 'err' | 'medio'; children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <span
        aria-hidden
        className={cn('mt-1.5 size-2 shrink-0 rounded-full', tono === 'on' ? 'bg-exito' : tono === 'err' ? 'bg-destructive' : 'bg-aviso')}
      />
      <span className="min-w-0 break-words">{children}</span>
    </li>
  )
}

function Campo({ id, label, className, children }: { id: string; label: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn('grid min-w-0 gap-1.5', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}

export default function Pagina() {
  const [actual, setActual] = React.useState<Record<P, Canal>>()
  const [titulo, setTitulo] = React.useState('')
  const [busqueda, setBusqueda] = React.useState('')
  const [listas, setListas] = React.useState<Record<P, Cat[]>>({ twitch: [], kick: [] })
  const [cats, setCats] = React.useState<Record<P, string>>({ twitch: DEJAR, kick: DEJAR })
  const [idioma, setIdioma] = React.useState('es')
  const [etiquetas, setEtiquetas] = React.useState('')
  const [marcadas, setMarcadas] = React.useState<Record<P, boolean>>({ twitch: true, kick: true })
  const [nombrePreset, setNombrePreset] = React.useState('')
  const [presets, setPresets] = React.useState<Preset[]>([])
  const [msg, setMsg] = React.useState({ texto: '', error: false })
  const [cambiando, setCambiando] = React.useState(false)
  const barra = React.useRef<HTMLDivElement>(null)

  const mensaje = (texto: string, error = false) => setMsg({ texto, error })
  const conectada = (p: P) => !!actual?.[p] && !actual[p].error
  const elegidas = PL.filter((p) => marcadas[p] && conectada(p))
  const listaEtiquetas = () =>
    etiquetas
      .split(',')
      .map((e) => e.trim())
      .filter(Boolean)
  const catId = (p: P) => (cats[p] === DEJAR ? '' : cats[p])

  function opciones(p: P, lista: Cat[], elegida: string | number) {
    setListas((l) => ({ ...l, [p]: lista }))
    setCats((c) => ({ ...c, [p]: elegida === '' ? DEJAR : String(elegida) }))
  }

  async function leer() {
    mensaje('')
    let a: Record<P, Canal>
    try {
      a = await get<Record<P, Canal>>('/api/canal')
    } catch {
      return mensaje('La web no contesta.', true)
    }
    setActual(a)
    const ok = (p: P) => !!a[p] && !a[p].error
    // el formulario arranca con lo que tiene Twitch (o Kick, si Twitch no está conectado)
    const base = ok('twitch') ? a.twitch : ok('kick') ? a.kick : null
    if (base) {
      setTitulo(base.titulo)
      setEtiquetas(base.etiquetas.join(', '))
      if (IDIOMAS[base.idioma]) setIdioma(base.idioma)
    }
    for (const p of PL) opciones(p, ok(p) && a[p].categoria.id ? [a[p].categoria] : [], '')
    setMarcadas({ twitch: true, kick: true })
  }

  React.useEffect(() => {
    leer()
    get<Preset[]>('/api/canal/presets').then(setPresets, () => {})
  }, [])

  async function buscar() {
    const texto = busqueda.trim()
    if (texto.length < 3) return mensaje('Escribí al menos 3 letras para buscar.', true)
    mensaje('Buscando…')
    let r: Busqueda
    try {
      r = await get<Busqueda>('/api/canal/buscar?q=' + encodeURIComponent(texto))
    } catch (e) {
      return mensaje((e as Error).message, true)
    }
    for (const p of PL) {
      const lista = r[p]
      // la que se llama igual a lo que escribiste; si no hay, la primera
      const igual = lista.find((c) => norm(c.nombre) === norm(texto)) || lista[0]
      opciones(p, lista, igual ? igual.id : '')
    }
    const errores = [r.error_twitch, r.error_kick].filter(Boolean)
    mensaje(errores.length ? errores.join(' · ') : r.twitch.length || r.kick.length ? '' : 'No encontré nada con ese nombre.', errores.length > 0)
  }

  async function cambiar() {
    const estas = elegidas
    setCambiando(true)
    mensaje('Cambiando…')
    let d: Record<P, { ok: boolean; error?: string }>
    try {
      d = await post('/api/canal/guardar', {
        titulo,
        idioma,
        etiquetas: listaEtiquetas(),
        categorias: { twitch: catId('twitch'), kick: catId('kick') },
        plataformas: estas,
      })
    } catch (e) {
      setCambiando(false)
      return mensaje((e as Error).message, true)
    }
    const malas = estas.filter((p) => !d[p].ok)
    await leer()
    setCambiando(false)
    mensaje(
      malas.length ? malas.map((p) => d[p].error).join(' · ') : `Listo: cambiado en ${estas.map((p) => NOMBRES[p]).join(' y ')}.`,
      malas.length > 0,
    )
  }

  // presets: cargan el formulario; para cambiar el canal igual hay que tocar el botón de abajo
  function cargar(p: Preset) {
    setTitulo(p.titulo)
    setIdioma(p.idioma)
    setEtiquetas(p.etiquetas.join(', '))
    for (const pl of PL) {
      const c = p.categorias[pl]
      opciones(pl, c ? [c] : [], c ? c.id : '')
    }
    setNombrePreset(p.nombre)
    mensaje(`Cargado «${p.nombre}»: revisalo y tocá el botón de abajo para ponerlo en el canal.`)
    barra.current?.scrollIntoView({ block: 'nearest' })
  }

  async function borrar(p: Preset) {
    if (!(await confirm({ title: `¿Borrar el preset «${p.nombre}»?`, confirmText: 'Borrar', variant: 'destructive' }))) return
    try {
      setPresets(await post<Preset[]>('/api/canal/presets/borrar', { nombre: p.nombre }))
    } catch (e) {
      mensaje((e as Error).message, true)
    }
  }

  async function guardarPreset() {
    const categorias: Partial<Record<P, Cat>> = {}
    for (const p of PL) {
      // con «Dejar la que está», el preset se lleva la que tiene puesta ahora
      if (cats[p] !== DEJAR) categorias[p] = { id: cats[p], nombre: listas[p].find((c) => String(c.id) === cats[p])?.nombre ?? '' }
      else if (actual && conectada(p) && actual[p].categoria.id) categorias[p] = actual[p].categoria
    }
    try {
      setPresets(
        await post<Preset[]>('/api/canal/presets/guardar', {
          nombre: nombrePreset,
          titulo,
          idioma,
          etiquetas: listaEtiquetas(),
          categorias,
        }),
      )
    } catch (e) {
      return mensaje((e as Error).message, true)
    }
    mensaje(`Preset «${nombrePreset.trim()}» guardado.` + (Object.keys(categorias).length ? '' : ' Sin categoría: al cargarlo deja la que esté.'))
  }

  return (
    <>
      <Confirmer />
      <Encabezado
        titulo="Título y categoría"
        acciones={
          <Button variant="outline" onClick={leer}>
            Volver a leer
          </Button>
        }
        ayuda={
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Conectá tu cuenta de Twitch y la de Kick en{' '}
              <Enlace href="/config" className="text-foreground underline underline-offset-2">
                Configuración
              </Enlace>
              . Son las tuyas, no las del bot: Twitch y Kick no dejan que un moderador cambie el título.
            </li>
            <li>Escribí el título, buscá la categoría y revisá que en las dos plataformas haya quedado la misma.</li>
            <li>
              Tocá <b>Cambiar en las dos</b>, o destildá una para cambiar solo la otra.
            </li>
            <li>
              Si repetís el mismo título y la misma categoría, guardalos como <b>preset</b>: con un toque se cargan en el formulario.
            </li>
            <li>
              En <b>Según la escena de OBS</b>, marcá en qué escenas va cada preset: uno puede ir en varias, y las que no marques (pausa, final) no
              cambian nada. Mientras transmitís, al pasar a esa escena y quedarte 5 segundos, se pone su preset en Twitch y Kick solo. Pasar de largo
              por una escena no cambia nada, y una escena sin preset deja lo que estaba. Usa el servidor WebSocket de OBS, que viene prendido: la
              contraseña la lee de OBS.
            </li>
          </ol>
        }
      />
      <Columnas>
        <div className="grid min-w-0 content-start gap-4">
          <Seccion titulo="Cómo está ahora">
            <ul className="space-y-2">
              {!actual ? (
                <Linea tono="medio">Leyendo Twitch y Kick…</Linea>
              ) : (
                PL.map((p) => {
                  const c = actual[p]
                  return (
                    <Linea key={p} tono={c.error ? 'err' : 'on'}>
                      {c.error
                        ? `${NOMBRES[p]}: ${c.error}`
                        : p === 'kick' && !c.en_vivo && !c.titulo
                          ? 'Kick: conectado. Sin stream en vivo, Kick no muestra el título ni la categoría'
                          : `${NOMBRES[p]}: «${c.titulo}» · ${c.categoria.nombre || 'sin categoría'} · ${IDIOMAS[c.idioma] || c.idioma || 'idioma sin datos'}` +
                            (c.etiquetas.length ? ' · ' + c.etiquetas.join(', ') : '')}
                    </Linea>
                  )
                })
              )}
            </ul>
          </Seccion>

          <Seccion titulo="Presets">
            {presets.length ? (
              <ul className="flex flex-wrap gap-2">
                {presets.map((p) => (
                  <li key={p.nombre} className="flex min-w-0 items-center rounded-lg border">
                    <Button variant="ghost" size="sm" className="min-w-0 rounded-r-none" title={p.titulo} onClick={() => cargar(p)}>
                      <span className="truncate">{p.nombre}</span>
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-l-none border-l px-2 text-muted-foreground hover:text-destructive"
                      title={`Borrar el preset ${p.nombre}`}
                      aria-label={`Borrar el preset ${p.nombre}`}
                      onClick={() => borrar(p)}
                    >
                      <XIcon aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                Todavía no hay. Armá el título y la categoría abajo y guardalos con un nombre, por ejemplo «Ranked» o «Torneo»: después los cargás con
                un toque.
              </p>
            )}
          </Seccion>

          <Seccion titulo="Según la escena de OBS">
            <SegunEscena presets={presets} />
          </Seccion>
        </div>

        <Seccion titulo="Cambiar" className="min-w-0">
          <div className="grid gap-4">
            <Campo
              id="titulo"
              label={
                <>
                  Título <span className="font-normal text-muted-foreground">{titulo.length}/140</span>
                </>
              }
            >
              <Input id="titulo" maxLength={140} autoComplete="off" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
            </Campo>

            <div className="flex min-w-0 items-end gap-2">
              <Campo id="busqueda" label="Categoría" className="flex-1">
                <Input
                  id="busqueda"
                  placeholder="Por ejemplo: valorant"
                  autoComplete="off"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      buscar()
                    }
                  }}
                />
              </Campo>
              <Button variant="outline" type="button" onClick={buscar}>
                Buscar
              </Button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {PL.map((p) => (
                <Campo key={p} id={'cat-' + p} label={'En ' + NOMBRES[p]}>
                  <Select value={cats[p]} onValueChange={(v) => setCats((c) => ({ ...c, [p]: v }))}>
                    <SelectTrigger id={'cat-' + p} className="w-full min-w-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={DEJAR}>Dejar la que está</SelectItem>
                      {listas[p].map((c) => (
                        <SelectItem key={c.id} value={String(c.id)}>
                          {c.nombre}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Campo>
              ))}
            </div>
            <p className="-mt-2 text-sm text-muted-foreground">
              Cada plataforma tiene su propia lista de categorías: al buscar, se elige sola la que coincide con el nombre. Revisá que sean la misma.
            </p>

            <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
              <Campo id="idioma" label="Idioma">
                <Select value={idioma} onValueChange={setIdioma}>
                  <SelectTrigger id="idioma" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="es">Español</SelectItem>
                    <SelectItem value="en">Inglés</SelectItem>
                    <SelectItem value="pt">Portugués</SelectItem>
                    <SelectItem value="other">Otro</SelectItem>
                  </SelectContent>
                </Select>
              </Campo>
              <Campo id="etiquetas" label="Etiquetas, separadas con comas">
                <Input
                  id="etiquetas"
                  placeholder="Por ejemplo: Argentina, Español, Ranked"
                  autoComplete="off"
                  value={etiquetas}
                  onChange={(e) => setEtiquetas(e.target.value)}
                />
              </Campo>
            </div>
            <p className="-mt-2 text-sm text-muted-foreground">
              Hasta 10 etiquetas, sin espacios ni signos. Kick no deja cambiar el idioma desde afuera: ahí queda el que tenga el canal.
            </p>

            <div className="flex flex-wrap gap-x-6 gap-y-3">
              {PL.map((p) => (
                <Label key={p} className="cursor-pointer">
                  <Switch
                    checked={marcadas[p] && conectada(p)}
                    disabled={!conectada(p)}
                    onCheckedChange={(v) => setMarcadas((m) => ({ ...m, [p]: v }))}
                  />
                  {NOMBRES[p]}
                </Label>
              ))}
            </div>

            <div className="flex min-w-0 flex-wrap items-end gap-2">
              <Campo id="preset-nombre" label="Guardar esto como preset" className="min-w-40 flex-1">
                <Input
                  id="preset-nombre"
                  maxLength={40}
                  placeholder="Nombre del preset"
                  autoComplete="off"
                  value={nombrePreset}
                  onChange={(e) => setNombrePreset(e.target.value)}
                />
              </Campo>
              <Button variant="outline" type="button" onClick={guardarPreset}>
                Guardar preset
              </Button>
            </div>

            <div ref={barra} className="flex flex-wrap items-center gap-3 border-t pt-4">
              <p role="status" className={cn('min-w-0 flex-1 basis-48 text-sm', msg.error ? 'text-destructive' : 'text-muted-foreground')}>
                {msg.texto}
              </p>
              <Button disabled={!elegidas.length || cambiando} onClick={cambiar}>
                {elegidas.length === 2 ? 'Cambiar en las dos' : elegidas.length ? 'Cambiar en ' + NOMBRES[elegidas[0]] : 'Elegí una plataforma'}
              </Button>
            </div>
          </div>
        </Seccion>
      </Columnas>
    </>
  )
}
