// Configuración: OBS, la botonera, las apps y cuentas de Twitch y Kick, y la clave de transmisión de cada plataforma.
// Antes: web/config.html.
import { ChevronRightIcon } from 'lucide-react'
import * as React from 'react'
import { Columnas, Encabezado, Seccion } from '@/components/pagina'
import { Confirmer, confirm } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { toast } from '@/components/ui/toast'
import { abrirAfuera, cargarScript, esLocal, get, post, usePoll } from '@/lib/api'
import { type Destino, useEstado } from '@/lib/estado'
import { cn } from '@/lib/utils'

// globales de /plataformas.js (un script clásico): se leen recién después de cargarlo
interface Plataforma {
  nombre: string
  servidor: string
  pasos: string
  es: (d: Destino) => boolean
}
declare const PLATAFORMAS: Record<string, Plataforma>
declare function plataformaDe(d: Destino): string

interface Cuenta {
  cuenta?: string
  estado?: string
  mensaje?: string
  conectada?: boolean
  como?: string
  codigo?: string
  link?: string
}
interface ConfigResp {
  config: Record<string, string>
  kick_secreto: boolean
  cuentas: Record<string, Cuenta>
}
interface Obs {
  instalado: boolean
  configurado: boolean
  a_la_app: boolean
  transmitiendo: boolean
  abierto: boolean
  dock_panel: boolean
  dock_chat: boolean
}

const CAMPOS = ['client_id', 'canal', 'bot', 'kick_client_id', 'kick_canal_slug', 'kick_bot']
const CUENTAS: Record<string, [string, string, string]> = {
  canal_twitch: ['twitch', 'Tu cuenta', 'para cambiar título y categoría'],
  bot_twitch: ['twitch', 'El bot', 'para hablar, moderar y clipear'],
  canal_kick: ['kick', 'Tu cuenta', 'para cambiar título y categoría'],
  bot_kick: ['kick', 'El bot', 'para hablar y moderar'],
}

type Tono = 'on' | 'err' | 'medio' | ''
const color: Record<Tono, string> = { on: 'bg-exito', err: 'bg-destructive', medio: 'bg-aviso', '': 'bg-muted-foreground/50' }

function Punto({ tono, children, className }: { tono: Tono; children?: React.ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex min-w-0 items-center gap-1.5 text-sm text-muted-foreground', className)}>
      <span aria-hidden className={cn('size-2 shrink-0 rounded-full', color[tono])} />
      {children}
    </span>
  )
}

type Msg = { texto: string; error?: boolean }
function Estado({ msg }: { msg: Msg }) {
  return (
    <p role="status" className={cn('min-h-5 text-sm', msg.error ? 'text-destructive' : 'text-muted-foreground')}>
      {msg.texto}
    </p>
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

const hint = 'text-sm text-muted-foreground'
const enlace = 'text-foreground underline underline-offset-2'

function Pasos({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <Collapsible className="mt-4 rounded-lg border text-sm">
      <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
        <ChevronRightIcon aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-90" />
        {titulo}
      </CollapsibleTrigger>
      <CollapsibleContent className="px-3 pb-3 text-muted-foreground [&_b]:text-foreground [&_code]:text-foreground">
        <ol className="list-decimal space-y-1 pl-5">{children}</ol>
      </CollapsibleContent>
    </Collapsible>
  )
}

// cambiar la config de OBS pide cerrarlo: avisa, y avisa dos veces si está transmitiendo. true si se puede seguir
async function permisoParaCerrar(e: Obs) {
  if (!e.abierto) return true
  const si = await confirm(
    e.transmitiendo
      ? {
          title: '¿Lo cierro igual, lo cambio y lo vuelvo a abrir?',
          description:
            'OBS está TRANSMITIENDO. Para cambiar su configuración hay que cerrarlo, y eso corta el stream en todas las plataformas.',
          confirmText: 'Cerrar OBS igual',
          variant: 'destructive',
        }
      : {
          title: '¿Sigo?',
          description: 'OBS está abierto. Para cambiar su configuración hay que cerrarlo: lo cierro, lo cambio y lo vuelvo a abrir.',
          confirmText: 'Seguir',
        },
  )
  return (
    si &&
    (!e.transmitiendo ||
      confirm({ title: 'Última confirmación: se va a cortar el stream. ¿Cierro OBS?', confirmText: 'Cerrar OBS', variant: 'destructive' }))
  )
}

function SeccionObs() {
  const obs = usePoll<Obs>('/api/obs', 10000)
  const { refrescar } = useEstado()
  const [msg, setMsg] = React.useState<Msg>({ texto: '' })
  const [ocupado, setOcupado] = React.useState(false)
  const e = obs.datos

  async function revisar() {
    try {
      const d = await get<Obs>('/api/obs')
      obs.setDatos(d)
      return d
    } catch {
      return obs.datos
    }
  }

  async function agregarDock(cual: 'panel' | 'chat') {
    const e = await revisar()
    if (!e || !(await permisoParaCerrar(e))) return
    setMsg({ texto: e.abierto ? 'Cerrando OBS… Si te pregunta si querés salir, decile que sí.' : 'Agregando…' })
    try {
      const d = await post<{ ya_estaba?: boolean; reabierto?: boolean }>('/api/obs/dock', { cual, cerrar: e.abierto })
      setMsg({
        texto: d.ya_estaba
          ? 'Ese panel ya estaba en OBS: buscalo en Ver → Paneles.'
          : `Listo: el panel quedó agregado. ${d.reabierto ? 'Volví a abrir OBS.' : 'Abrí OBS.'} Si no lo ves, está en Ver → Paneles.`,
      })
    } catch (err) {
      setMsg({ texto: (err as Error).message, error: true })
    }
    revisar()
  }

  async function configurar() {
    const e = await revisar()
    if (!e || !(await permisoParaCerrar(e))) return
    setOcupado(true)
    setMsg({ texto: e.abierto ? 'Cerrando OBS… Si te pregunta si querés salir, decile que sí.' : 'Configurando…' })
    try {
      const d = await post<{ reabierto?: boolean; importado?: string }>('/api/obs/configurar', { cerrar: e.abierto })
      setMsg({
        texto: [
          'Listo: OBS quedó configurado.',
          d.reabierto ? 'Lo volví a abrir.' : 'Ya lo podés abrir.',
          d.importado ? `La clave de ${d.importado} que tenía OBS pasó a Stream Kit.` : '',
          'Para usar la pista de VOD de Twitch, en OBS: Ajustes → Salida → Emisión → Pista de VOD de Twitch.',
        ]
          .filter(Boolean)
          .join(' '),
      })
      refrescar()
    } catch (err) {
      setMsg({ texto: (err as Error).message, error: true })
    }
    setOcupado(false)
    revisar()
  }

  const [tono, texto]: [Tono, string] = !e
    ? ['', 'Revisando…']
    : !e.instalado
      ? ['err', 'No encontré OBS en esta PC']
      : e.configurado
        ? ['on', e.a_la_app ? 'Configurado y transmitiendo a Stream Kit' : 'Configurado para Stream Kit']
        : ['medio', e.transmitiendo ? 'Sin configurar, y está transmitiendo' : e.abierto ? 'Sin configurar (está abierto)' : 'Sin configurar']

  return (
    <Seccion titulo="OBS" acciones={<Punto tono={tono}>{texto}</Punto>}>
      <div className="grid gap-3">
        <p className={hint}>
          Deja OBS listo para Stream Kit: transmite a esta app (servidor <code className="text-foreground">rtmp://127.0.0.1:1935/live</code>, clave{' '}
          <code className="text-foreground">stream</code>), sin transmisión mejorada, y con la opción de la pista de VOD de Twitch para que el VOD
          salga sin música. Si OBS ya transmitía a una plataforma, su clave pasa a Stream Kit. Antes de cambiar nada, guarda una copia de la
          configuración de OBS.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button disabled={!e?.instalado || ocupado} onClick={configurar}>
            {e?.configurado ? 'Volver a configurar OBS' : 'Autoconfigurar OBS'}
          </Button>
          <Button variant="outline" disabled={!e?.instalado || e.dock_panel} onClick={() => agregarDock('panel')}>
            {e?.dock_panel ? 'El panel ya está en OBS' : 'Agregar el panel a OBS'}
          </Button>
          <Button variant="outline" disabled={!e?.instalado || e.dock_chat} onClick={() => agregarDock('chat')}>
            {e?.dock_chat ? 'El chat ya está en OBS' : 'Agregar el chat a OBS'}
          </Button>
        </div>
        <p className={hint}>
          Los paneles quedan adentro de OBS, en Ver → Paneles: el de Stream Kit es esta web entera; el del chat, los dos chats juntos con
          moderación.
        </p>
        <Estado msg={msg} />
      </div>
    </Seccion>
  )
}

function SeccionBotonera() {
  const [lista, setLista] = React.useState<{ nombre: string; instalado: boolean }[]>()
  const [msg, setMsg] = React.useState<Msg>({ texto: '' })
  const [ocupado, setOcupado] = React.useState(false)
  const revisar = () => get<{ nombre: string; instalado: boolean }[]>('/api/botonera').then(setLista, () => {})
  React.useEffect(() => {
    revisar()
  }, [])

  async function instalar() {
    setOcupado(true)
    setMsg({ texto: 'Instalando…' })
    try {
      const d = await post<{ nombre: string; reiniciada?: boolean }[]>('/api/botonera/instalar', {})
      setMsg({
        texto: !d.length
          ? 'No encontré Stream Deck ni StreamDock en esta PC.'
          : 'Listo: ' +
            d.map((a) => `${a.nombre} ${a.reiniciada ? '(lo reinicié)' : '(abrilo para que lo cargue)'}`).join(', ') +
            '. Buscá la categoría Stream Kit y arrastrá Delay on/off a una tecla.',
      })
    } catch (err) {
      setMsg({ texto: (err as Error).message, error: true })
    }
    setOcupado(false)
    revisar()
  }

  const todas = !!lista?.length && lista.every((a) => a.instalado)
  const estado = !lista ? (
    <Punto tono="">Revisando…</Punto>
  ) : (
    <Punto tono={!lista.length ? 'err' : todas ? 'on' : 'medio'}>
      {!lista.length
        ? 'No encontré Stream Deck ni StreamDock'
        : lista.map((a) => `${a.nombre}: ${a.instalado ? 'con el botón' : 'sin el botón'}`).join(' · ')}
    </Punto>
  )

  return (
    <Seccion titulo="Botonera" acciones={estado}>
      <div className="grid gap-3">
        <p className={hint}>
          Un botón para tu Stream Deck (Elgato) o StreamDock (Mirabox) que activa o saca el delay y muestra en la tecla cómo está: rojo sin
          delay, verde con los segundos de delay.
        </p>
        <div>
          <Button disabled={!lista?.length || ocupado} onClick={instalar}>
            {todas ? 'Volver a instalar el botón' : 'Instalar el botón'}
          </Button>
        </div>
        <p className={hint}>
          Se instala en las que encuentre en esta PC y se reinicia su programa para que lo cargue. Después, en la botonera, buscá la
          categoría <b className="text-foreground">Stream Kit</b> y arrastrá <b className="text-foreground">Delay on/off</b> a una tecla.
        </p>
        <Estado msg={msg} />
      </div>
    </Seccion>
  )
}

function Cuentas({ plataforma, datos, conectar }: { plataforma: string; datos?: ConfigResp; conectar: (tipo: string) => void }) {
  return (
    <Seccion titulo="Cuentas conectadas">
      <ul className="divide-y">
        {datos &&
          Object.entries(CUENTAS)
            .filter(([, [p]]) => p === plataforma)
            .map(([tipo, [, nombre, para]]) => {
              const c = datos.cuentas[tipo] ?? {}
              const esperando = c.estado === 'esperando'
              return (
                <li key={tipo} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0 flex-1 basis-48">
                    <div className="font-medium break-words">{nombre + (c.cuenta ? ` (${c.cuenta})` : '')}</div>
                    <div className={cn('text-sm break-words', c.estado === 'error' ? 'text-destructive' : 'text-muted-foreground')}>
                      {esperando || c.estado === 'error'
                        ? c.mensaje
                        : c.conectada
                          ? `Conectada${c.como ? ' como ' + c.como : ''}, ${para}`
                          : c.cuenta
                            ? `Sin conectar, ${para}`
                            : 'Escribí la cuenta arriba y guardá'}
                    </div>
                    {esperando && c.codigo && (
                      <div className="text-sm">
                        Código: <b className="font-mono">{c.codigo}</b> ·{' '}
                        <a className={enlace} href={c.link} target="_blank" rel="noopener">
                          abrir Twitch
                        </a>
                      </div>
                    )}
                  </div>
                  <Punto tono={esperando ? 'medio' : c.conectada ? 'on' : 'err'}>
                    {esperando ? 'Esperando' : c.conectada ? 'Conectada' : 'Falta'}
                  </Punto>
                  <Button variant={c.conectada ? 'outline' : 'default'} disabled={esperando || !c.cuenta} onClick={() => conectar(tipo)}>
                    {c.conectada ? 'Conectar de nuevo' : 'Conectar'}
                  </Button>
                </li>
              )
            })}
      </ul>
    </Seccion>
  )
}

// --- transmisión: la clave de cada plataforma es un destino del delay ---
function FilaDestino({ d, refrescar }: { d: Destino; refrescar: () => void }) {
  const [abierto, setAbierto] = React.useState(false)
  const [url, setUrl] = React.useState(d.url)
  const [clave, setClave] = React.useState('')
  const [error, setError] = React.useState('')
  const [tono, texto]: [Tono, string] = !d.enabled
    ? ['', 'Pausada']
    : d.state === 'live'
      ? ['on', 'Transmitiendo']
      : d.state === 'error'
        ? ['err', 'Error: ' + d.error]
        : ['', 'Lista: transmite cuando OBS mande']

  const fallo = (e: Error) => toast.error(e.message)

  async function quitar() {
    if (!(await confirm({ title: `¿Quitar ${d.name}?`, description: 'Deja de transmitir ahí y se borra su clave.', confirmText: 'Quitar', variant: 'destructive' })))
      return
    post('/api/destinations/delete', { id: d.id }).then(refrescar, fallo)
  }

  async function guardar() {
    try {
      await post('/api/destinations/update', { id: d.id, url, key: clave })
    } catch (e) {
      return setError((e as Error).message)
    }
    setAbierto(false)
    setClave('')
    setError('')
    refrescar()
  }

  return (
    <li className="grid gap-3 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span aria-hidden className={cn('size-2 shrink-0 rounded-full', color[tono])} />
        <div className="min-w-0 flex-1 basis-40">
          <div className="font-medium break-words">{d.name}</div>
          <div className={cn('text-sm break-all', tono === 'err' ? 'text-destructive' : 'text-muted-foreground')}>{`${texto} · ${d.url}`}</div>
        </div>
        <Label className="cursor-pointer">
          <Switch
            checked={d.enabled}
            aria-label={`Transmitir a ${d.name}`}
            onCheckedChange={(v) => post('/api/destinations/enable', { id: d.id, enabled: v }).then(refrescar, fallo)}
          />
          Activa
        </Label>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            aria-label={`Cambiar la clave de ${d.name}`}
            onClick={() => {
              setUrl(d.url)
              setAbierto(true)
            }}
          >
            Cambiar clave
          </Button>
          <Button variant="destructive" size="sm" aria-label={`Quitar ${d.name}`} onClick={quitar}>
            Quitar
          </Button>
        </div>
      </div>
      {abierto && (
        <div className="grid gap-2 rounded-lg border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo id={`url-${d.id}`} label="URL del servidor">
              <Input id={`url-${d.id}`} autoComplete="off" spellCheck={false} value={url} onChange={(e) => setUrl(e.target.value)} />
            </Campo>
            <Campo id={`clave-${d.id}`} label="Clave nueva">
              <Input
                id={`clave-${d.id}`}
                type="password"
                autoComplete="off"
                placeholder="Vacía: queda la que está"
                autoFocus
                value={clave}
                onChange={(e) => setClave(e.target.value)}
              />
            </Campo>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={guardar}>Guardar</Button>
            <Button
              variant="ghost"
              onClick={() => {
                setAbierto(false)
                setClave('')
                setError('')
              }}
            >
              Cancelar
            </Button>
          </div>
          <Estado msg={{ texto: error, error: true }} />
        </div>
      )}
    </li>
  )
}

function Agregar({ tab, p, refrescar }: { tab: string; p: Plataforma; refrescar: () => void }) {
  const otras = tab === 'otras'
  const [nombre, setNombre] = React.useState('')
  const [url, setUrl] = React.useState(p.servidor)
  const [clave, setClave] = React.useState('')
  const [error, setError] = React.useState('')

  async function agregar() {
    try {
      await post('/api/destinations/add', { name: otras ? nombre : p.nombre, url, key: clave })
    } catch (e) {
      return setError((e as Error).message)
    }
    refrescar()
  }

  return (
    <div className="grid gap-3">
      <p className={hint}>Todavía no hay clave: sin ella, Stream Kit no transmite a {p.nombre}.</p>
      <div className={cn('grid gap-3', otras ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
        {otras && (
          <Campo id={`nombre-${tab}`} label="Nombre">
            <Input id={`nombre-${tab}`} maxLength={40} autoComplete="off" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Campo>
        )}
        <Campo id={`url-${tab}`} label="URL del servidor">
          <Input
            id={`url-${tab}`}
            autoComplete="off"
            spellCheck={false}
            placeholder="rtmp://..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Campo>
        <Campo id={`clave-${tab}`} label="Clave de transmisión">
          <Input id={`clave-${tab}`} type="password" autoComplete="off" value={clave} onChange={(e) => setClave(e.target.value)} />
        </Campo>
      </div>
      <div>
        <Button onClick={agregar}>Agregar</Button>
      </div>
      <Estado msg={{ texto: error, error: true }} />
    </div>
  )
}

function Transmision({ tab }: { tab: string }) {
  const { estado, refrescar } = useEstado()
  const otras = tab === 'otras'
  const p: Plataforma = otras ? { nombre: 'otra plataforma', servidor: '', pasos: '', es: () => false } : PLATAFORMAS[tab]
  const suyos = (estado?.destinations ?? []).filter((d) => plataformaDe(d) === tab)
  return (
    <Seccion titulo="Transmisión">
      <div className="grid gap-3">
        {suyos.length > 0 && (
          <ul className="divide-y">
            {suyos.map((d) => (
              <FilaDestino key={d.id} d={d} refrescar={refrescar} />
            ))}
          </ul>
        )}
        {estado && !suyos.length && <Agregar tab={tab} p={p} refrescar={refrescar} />}
        {/* los pasos vienen escritos en HTML en /plataformas.js, nuestro */}
        {p.pasos && <p className={cn(hint, '[&_a]:text-foreground [&_a]:underline [&_b]:text-foreground')} dangerouslySetInnerHTML={{ __html: p.pasos }} />}
      </div>
    </Seccion>
  )
}

export default function Pagina() {
  const [listo, setListo] = React.useState<boolean | 'error'>(false)
  const [pestana, setPestana] = React.useState(() => location.hash.slice(1) || 'twitch')
  const [datos, setDatos] = React.useState<ConfigResp>()
  const [campos, setCampos] = React.useState<Record<string, string>>({})
  const [secreto, setSecreto] = React.useState('')
  const [secretoGuardado, setSecretoGuardado] = React.useState(false)
  const [msg, setMsg] = React.useState<Msg>({ texto: '' })
  const [guardando, setGuardando] = React.useState(false)

  const avisar = (texto: string, error = false) => setMsg({ texto, error })

  const leer = React.useCallback(async (llenar = false) => {
    let d: ConfigResp
    try {
      d = await get<ConfigResp>('/api/config')
    } catch (e) {
      return avisar((e as Error).message, true)
    }
    if (llenar) {
      setCampos(Object.fromEntries(CAMPOS.map((c) => [c, d.config[c] || ''])))
      setSecretoGuardado(d.kick_secreto)
    }
    setDatos(d)
  }, [])

  React.useEffect(() => {
    leer(true)
    cargarScript('/plataformas.js').then(
      () => setListo(true),
      () => setListo('error'),
    )
  }, [leer])

  // mientras una cuenta espera que la conectes en el navegador, se relee cada 2 s
  React.useEffect(() => {
    if (!datos || !Object.values(datos.cuentas).some((c) => c.estado === 'esperando')) return
    const t = setTimeout(() => leer(), 2000)
    return () => clearTimeout(t)
  }, [datos, leer])

  async function conectar(tipo: string) {
    // desde la PC, el login va al navegador de siempre (no a una ventanita de OBS). Desde otro lado, la pestaña se abre
    // ya, con el click: si se abre después de esperar al servidor, el navegador la bloquea
    const ventana = esLocal ? null : window.open('', '_blank')
    let d: { link: string }
    try {
      d = await post<{ link: string }>('/api/config/conectar', { tipo })
    } catch (e) {
      ventana?.close()
      return avisar((e as Error).message, true)
    }
    if (ventana) ventana.location = d.link
    else abrirAfuera(d.link)
    leer()
  }

  async function guardar() {
    setGuardando(true)
    avisar('Guardando…')
    try {
      await post('/api/config/guardar', { ...Object.fromEntries(CAMPOS.map((c) => [c, campos[c] ?? ''])), kick_client_secret: secreto })
    } catch (e) {
      setGuardando(false)
      return avisar((e as Error).message, true)
    }
    setGuardando(false)
    setSecreto('')
    avisar('Guardado. El bot se reinicia solo; el stream no se toca.')
    leer(true)
  }

  const campo = (c: string) => ({
    id: c,
    autoComplete: 'off',
    spellCheck: false,
    value: campos[c] ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setCampos((v) => ({ ...v, [c]: e.target.value })),
  })

  // las que solo reciben el stream (YouTube, Facebook...): una pestaña cada una, armada desde plataformas.js
  const solo = listo === true ? [...Object.keys(PLATAFORMAS).filter((p) => p !== 'twitch' && p !== 'kick'), 'otras'] : []
  const tabs = ['twitch', 'kick', ...solo]
  const tab = tabs.includes(pestana) ? pestana : 'twitch'
  const elegir = (p: string) => {
    setPestana(p)
    history.replaceState(null, '', '#' + p)
  }

  return (
    <>
      <Confirmer />
      <Encabezado
        titulo="Configuración"
        ayuda={
          <>
            <ol className="list-decimal space-y-1 pl-5 [&_code]:text-foreground">
              <li>Cada plataforma tiene su pestaña. Usá solo las que te sirvan y dejá las otras vacías.</li>
              <li>
                En Twitch y en Kick: creá una app (la pestaña dice cómo, son gratis), pegá sus claves, escribí tu canal y la cuenta del bot,
                y tocá <b>Guardar</b>. Después conectá las cuentas con los botones.
              </li>
              <li>
                En <b>Transmisión</b> de cada pestaña va tu clave de transmisión: OBS le manda el stream a esta app y la app a cada
                plataforma que tenga clave.
              </li>
              <li>
                Si el bot usa una cuenta aparte, hacelo moderador en tu chat: <code>/mod</code> y el nombre del bot. Su cuenta se conecta con
                la sesión de esa cuenta: conviene abrir el link en una ventana de incógnito.
              </li>
            </ol>
            <p>
              <b>¿Qué cuenta uso para el bot?</b> Podés poner tu propia cuenta, y el bot hace de mod y de bot con tu nombre: como sos el
              dueño del canal, no hace falta darle moderador. O podés crear una cuenta nueva y usarla de bot: así sus mensajes se distinguen
              de los tuyos en el chat. Cualquiera de las dos anda igual.
            </p>
            <p>Todo queda guardado en esta PC; las claves no se suben a ningún lado.</p>
          </>
        }
      />

      <div className="grid gap-4">
        <Columnas>
          <SeccionObs />
          <SeccionBotonera />
        </Columnas>

        {listo === 'error' ? (
          <p className="text-sm text-destructive" role="status">
            No cargó la lista de plataformas. Volvé a abrir la página.
          </p>
        ) : !listo ? (
          <Spinner className="mx-auto" />
        ) : (
          <Tabs value={tab} onValueChange={elegir}>
            <TabsList aria-label="Plataforma" className="h-auto w-full flex-wrap">
              {tabs.map((t) => (
                <TabsTrigger key={t} value={t} className="min-w-20">
                  {t === 'otras' ? 'Otras' : PLATAFORMAS[t].nombre}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="twitch">
              <Columnas>
                <Seccion titulo="App y cuentas">
                  <div className="grid gap-3">
                    <Campo id="client_id" label="Client ID de tu app">
                      <Input {...campo('client_id')} />
                    </Campo>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Campo id="canal" label="Tu canal">
                        <Input {...campo('canal')} placeholder="El que va en twitch.tv/..." />
                      </Campo>
                      <Campo id="bot" label="Cuenta del bot">
                        <Input {...campo('bot')} placeholder="Tu cuenta o una nueva para el bot" />
                      </Campo>
                    </div>
                  </div>
                  <Pasos titulo="Cómo crear la app de Twitch">
                    <li>
                      Entrá a{' '}
                      <a className={enlace} href="https://dev.twitch.tv/console/apps" target="_blank" rel="noopener">
                        dev.twitch.tv/console/apps
                      </a>{' '}
                      con tu cuenta. Twitch pide tener activada la verificación en dos pasos.
                    </li>
                    <li>
                      Tocá <b>Registrar tu aplicación</b>. Nombre: el que quieras. URL de redireccionamiento OAuth: <code>http://localhost</code>.
                      Categoría: <b>Chat Bot</b>. Tipo de cliente: <b>Público</b>.
                    </li>
                    <li>
                      Creala, entrá a <b>Administrar</b> y copiá el <b>ID de cliente</b> acá arriba.
                    </li>
                  </Pasos>
                </Seccion>
                <div className="grid min-w-0 content-start gap-4">
                  <Cuentas plataforma="twitch" datos={datos} conectar={conectar} />
                  <Transmision tab="twitch" />
                </div>
              </Columnas>
            </TabsContent>

            <TabsContent value="kick">
              <Columnas>
                <Seccion titulo="App y cuentas">
                  <div className="grid gap-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Campo id="kick_client_id" label="Client ID de tu app">
                        <Input {...campo('kick_client_id')} />
                      </Campo>
                      <Campo id="kick_client_secret" label="Clave secreta (Client Secret)">
                        <Input
                          id="kick_client_secret"
                          type="password"
                          autoComplete="off"
                          placeholder={secretoGuardado ? 'Guardada. Pegá otra para cambiarla' : ''}
                          value={secreto}
                          onChange={(e) => setSecreto(e.target.value)}
                        />
                      </Campo>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Campo id="kick_canal_slug" label="Tu canal">
                        <Input {...campo('kick_canal_slug')} placeholder="El que va en kick.com/..." />
                      </Campo>
                      <Campo id="kick_bot" label="Cuenta del bot">
                        <Input {...campo('kick_bot')} placeholder="Tu cuenta o una nueva para el bot" />
                      </Campo>
                    </div>
                  </div>
                  <Pasos titulo="Cómo crear la app de Kick">
                    <li>
                      En{' '}
                      <a className={enlace} href="https://kick.com/settings/developer" target="_blank" rel="noopener">
                        kick.com/settings/developer
                      </a>
                      , con tu cuenta, tocá <b>Crear app</b>. Kick pide tener activada la verificación en dos pasos.
                    </li>
                    <li>
                      Nombre: el que quieras. URL de redirección: <code>http://localhost:47614/callback</code>.
                    </li>
                    <li>
                      Activá estos permisos: leer la información del usuario, escribir en el chat, moderación (banear), moderación de mensajes del
                      chat, leer la información del canal y escribir la información del canal.
                    </li>
                    <li>
                      Copiá el <b>Client ID</b> y la <b>Client Secret</b> acá arriba. La clave secreta no se vuelve a mostrar: para cambiarla,
                      pegá la nueva.
                    </li>
                  </Pasos>
                </Seccion>
                <div className="grid min-w-0 content-start gap-4">
                  <Cuentas plataforma="kick" datos={datos} conectar={conectar} />
                  <Transmision tab="kick" />
                </div>
              </Columnas>
            </TabsContent>

            {solo.map((t) => (
              <TabsContent key={t} value={t} className="grid max-w-3xl gap-3">
                <Transmision tab={t} />
                <p className={hint}>
                  {t === 'otras'
                    ? 'Cualquier otra plataforma o servidor que acepte RTMP: ponele un nombre, la URL y la clave.'
                    : `En ${PLATAFORMAS[t].nombre}, Stream Kit transmite con el mismo delay que en las demás. El bot, el chat y el título todavía son solo de Twitch y Kick.`}
                </p>
              </TabsContent>
            ))}
          </Tabs>
        )}

        {/* en las demás pestañas no hay nada que guardar: la clave se agrega con su botón */}
        {listo === true && (tab === 'twitch' || tab === 'kick') && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3">
            <p role="status" className={cn('min-w-0 flex-1 basis-48 text-sm', msg.error ? 'text-destructive' : 'text-muted-foreground')}>
              {msg.texto}
            </p>
            <Button disabled={guardando} onClick={guardar}>
              Guardar
            </Button>
          </div>
        )}
      </div>
    </>
  )
}
