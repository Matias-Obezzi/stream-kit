// Inicio: cómo están el delay y el bot, lo que falta para arrancar, la versión y el link para el celular.
import * as React from 'react'
import { Encabezado, Seccion } from '@/components/pagina'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { CopyButton } from '@/components/ui/copy-button'
import { Input } from '@/components/ui/input'
import { esLocal, post, usePoll } from '@/lib/api'
import { type BotEstado, type Estado, useEstado } from '@/lib/estado'
import { Enlace } from '@/lib/router'
import { cn } from '@/lib/utils'
import { PAGINAS } from '@/rutas'

type Tono = 'on' | 'medio' | 'err' | ''
type Linea = [Tono, string]
type TonoPill = 'bien' | 'medio' | 'mal' | ''

interface Reinicios {
  reinicios?: number
  ultimo_fallo?: string
}
interface Info {
  bot: BotEstado & Reinicios & { follows?: string; moderacion?: string }
  delay: Reinicios
  guardian: boolean
}
interface Config {
  config: { client_id?: string; kick_client_id?: string }
  cuentas: Record<string, { conectada?: boolean }>
}
interface Version {
  actual: string
  congelado: boolean
  descarga: { estado: string; error: string; version: string }
  servicios: Record<string, string>
  nucleo_pendiente: boolean
  ultima?: { version: string } | null
  error?: string
}

const TEXTOS: Record<string, string> = {
  conectado: 'conectado',
  conectando: 'conectando',
  reconectando: 'reconectando',
  vencida: 'sesión vencida: hay que hacer el login',
  'sin conectar': 'sin conectar',
  'falta permiso': 'falta hacer el login de nuevo',
  error: 'Twitch no lo dejó escuchar',
}

const PUNTO: Record<Tono, string> = { on: 'bg-exito', medio: 'bg-aviso', err: 'bg-destructive', '': 'bg-muted-foreground/50' }
const codigo = 'rounded bg-muted px-1 font-mono text-xs text-foreground'

function Lineas({ items }: { items: Linea[] }) {
  return (
    <ul className="space-y-1 text-sm text-muted-foreground">
      {items.map(([tono, texto], i) => (
        <li key={i} className="flex gap-2">
          <span aria-hidden className={cn('mt-1.5 size-2 shrink-0 rounded-full', PUNTO[tono])} />
          <span className="min-w-0">{texto}</span>
        </li>
      ))}
    </ul>
  )
}

function Pill({ tono, children }: { tono: TonoPill; children: React.ReactNode }) {
  return (
    <Badge
      variant={tono === 'mal' ? 'destructive' : 'secondary'}
      className={cn(tono === 'bien' && 'bg-exito text-exito-foreground', tono === 'medio' && 'bg-aviso text-aviso-foreground')}
    >
      {children}
    </Badge>
  )
}

function Servicio({ href, titulo, pill, items, ir }: { href: string; titulo: string; pill?: React.ReactNode; items: Linea[]; ir: string }) {
  const Icono = PAGINAS.find((p) => p.ruta === href)?.icono
  return (
    <Enlace href={href} className="group rounded-xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
      <Card className="h-full gap-3 p-4 shadow-none transition-colors group-hover:border-primary/60 group-hover:bg-accent/40">
        <div className="flex flex-wrap items-center gap-2.5">
          {Icono && (
            <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
              <Icono aria-hidden className="size-4" />
            </span>
          )}
          <h2 className="mr-auto font-semibold">{titulo}</h2>
          {pill}
        </div>
        <Lineas items={items} />
        <span className="mt-auto text-sm font-medium text-primary">{ir} →</span>
      </Card>
    </Enlace>
  )
}

const reinicios = (s?: Reinicios): Linea[] =>
  s?.reinicios ? [['medio', `Se reinició ${s.reinicios} ${s.reinicios === 1 ? 'vez' : 'veces'} · última: ${s.ultimo_fallo}`]] : []

function plataforma(nombre: string, valor?: string): Linea {
  const tono: Tono = valor === 'conectado' ? 'on' : valor === 'conectando' || valor === 'reconectando' ? 'medio' : 'err'
  return [tono, `${nombre}: ${(valor && TEXTOS[valor]) || 'sin datos'}`]
}

// lo que falta para arrancar: desaparece cuando está todo. La config solo se lee desde la PC (desde el celular no)
function pasos(delay: Estado, config?: Config): Linea[] {
  const items: Linea[] = []
  if (!delay.ffmpeg)
    items.push(['err', 'Falta instalar ffmpeg. En una terminal: winget install ffmpeg. Después cerrá Stream Kit desde la bandeja y abrilo de nuevo.'])
  if (config) {
    const c = config.config
    const cuentas = Object.values(config.cuentas)
    if (!c.client_id && !c.kick_client_id) items.push(['err', 'Cargá las claves de tu app de Twitch o de Kick en Configuración.'])
    else if (!cuentas.some((x) => x.conectada)) items.push(['medio', 'Conectá tus cuentas en Configuración.'])
  }
  if (!delay.destinations.length)
    items.push(['medio', 'Poné tu clave de transmisión en Configuración, en la pestaña de cada plataforma (Transmisión).'])
  if (!delay.obs && !delay.destinations.some((d) => d.state === 'live'))
    items.push(['', 'Configurá OBS para Stream Kit: en Configuración está el botón Autoconfigurar OBS.'])
  return items
}

const nueva = (a: string, b: string) => {
  const n = (v: string) => v.split('.').map(Number)
  const [x, y] = [n(a), n(b)]
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0)
  return false
}

// versión: se actualiza sin cortar el stream (la web y el bot al toque, el núcleo de transmisión cuando cortás)
function SeccionVersion() {
  const [cada, setCada] = React.useState(60000)
  const { datos: v, error, refrescar } = usePoll<Version>('/api/version', cada)
  const [enviando, setEnviando] = React.useState(false)
  const [fallo, setFallo] = React.useState<{ msg: string; para?: Version }>()
  const d = v?.descarga
  const bajando = !!d && ['Bajando…', 'Descomprimiendo…'].includes(d.estado)
  const ritmo = error ? 5000 : bajando || d?.estado === 'Instalada' ? 2000 : 60000
  if (ritmo !== cada) setCada(ritmo) // el ritmo depende de lo que contestó: rápido mientras baja, a los 5 s si no contesta
  if (!v || !d) return null
  const hay = !!v.ultima && nueva(v.ultima.version, v.actual)
  const texto =
    fallo && fallo.para === v
      ? fallo.msg
      : !v.congelado
        ? 'Desde el código fuente: actualizá con git pull.'
        : bajando
          ? `${d.estado} la ${d.version}. No hace falta cortar el stream.`
          : d.estado === 'Instalada'
            ? `Instalada la ${d.version}: la web se reinicia en unos segundos.`
            : d.error
              ? d.error
              : v.nucleo_pendiente
                ? `La web y el bot ya están en la ${v.servicios.web}. La parte que transmite se pasa sola cuando cortes el stream.`
                : hay
                  ? 'Hay una versión nueva. Se instala sin cortar el stream: si cambia la parte que transmite, esa se pasa sola cuando cortes.'
                  : v.error || 'Estás en la última versión.'
  const actualizar = async () => {
    setEnviando(true)
    try {
      await post('/api/actualizar', {})
      refrescar()
    } catch (e) {
      setFallo({ msg: (e as Error).message, para: v })
    }
    setEnviando(false)
  }
  return (
    <Seccion
      titulo={`Stream Kit ${v.actual}`}
      acciones={
        v.congelado &&
        hay &&
        !bajando &&
        d.estado !== 'Instalada' && (
          <Button loading={enviando} onClick={actualizar}>
            {`Actualizar a la ${v.ultima!.version}`}
          </Button>
        )
      }
    >
      <p className="text-sm text-muted-foreground" role="status">
        {texto}
      </p>
    </Seccion>
  )
}

export default function Pagina() {
  const { estado: delay, bot, caido } = useEstado()
  const info = bot as unknown as Info | undefined
  const { datos: config } = usePoll<Config>(esLocal ? '/api/config' : null, 10000)

  const aviso = caido
    ? 'El delay no contesta. Si se cayó o se está actualizando, el guardián lo levanta en unos segundos y esta página se actualiza sola.'
    : info && !info.guardian
      ? 'El guardián no está corriendo: si algo se cae, no se va a levantar solo. Cerrá Stream Kit desde la bandeja y abrilo de nuevo.'
      : ''

  const faltan = delay ? pasos(delay, config) : []
  const verPasos = !(faltan.length === 0 || (faltan.length === 1 && faltan[0][0] === '')) // solo "transmití desde OBS": ya está todo listo

  let delayPill: React.ReactNode = <Pill tono="">Conectando…</Pill>
  let delayLineas: Linea[] = []
  let botPill: React.ReactNode = <Pill tono="">Conectando…</Pill>
  let botLineas: Linea[] = []
  if (caido) {
    delayPill = <Pill tono="mal">Sin respuesta</Pill>
    botPill = <Pill tono="">Sin datos</Pill>
  } else {
    if (delay) {
      const [tono, texto] = (
        {
          live: ['bien', 'Sin delay'],
          filler: ['medio', `Activando · ${delay.filler_left} s`],
          delayed: ['medio', `En diferido · ${delay.delay} s`],
        } as const
      )[delay.mode]
      delayPill = <Pill tono={tono}>{texto}</Pill>
      delayLineas = [
        [delay.obs ? 'on' : '', delay.obs ? 'OBS conectado' : 'Esperando a OBS'],
        ...delay.destinations
          .filter((d) => d.enabled)
          .map(
            (d): Linea => [
              d.state === 'live' ? 'on' : d.state === 'error' ? 'err' : '',
              `${d.name}: ${d.state === 'live' ? 'transmitiendo' : d.state === 'error' ? d.error : 'en espera'}`,
            ],
          ),
        ...reinicios(info?.delay),
      ]
    }
    if (info) {
      const b = info.bot
      if (!b.vivo) {
        botPill = <Pill tono="mal">Caído</Pill>
        botLineas = [['err', info.guardian ? 'El guardián lo está levantando' : 'No está corriendo'], ...reinicios(b)]
      } else {
        const estados = [b.twitch, b.kick]
        const todo = estados.every((e) => e === 'conectado')
        const volviendo = estados.some((e) => e === 'conectando' || e === 'reconectando')
        const [tono, texto]: [TonoPill, string] = todo
          ? ['bien', 'Andando']
          : volviendo
            ? ['medio', 'Conectando']
            : estados.some((e) => e === 'conectado')
              ? ['medio', 'A medias']
              : ['mal', 'Sin chats']
        botPill = <Pill tono={tono}>{texto}</Pill>
        botLineas = [
          plataforma('Twitch', b.twitch),
          plataforma('Kick', b.kick),
          ...(b.follows ? [plataforma('Follows de Twitch', b.follows)] : []),
          ...(b.moderacion ? [plataforma('Quién borra y banea en Twitch', b.moderacion)] : []),
          ...reinicios(b),
        ]
      }
    }
  }

  return (
    <div className="space-y-4">
      <Encabezado
        titulo="Stream Kit"
        ayuda={
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              <b>Delay</b>: OBS transmite a esta app y la app a Twitch, Kick, YouTube o las que agregues. Con un botón le ponés delay al stream, sin
              cortarlo.
            </li>
            <li>
              <b>Bot</b>: comandos, mensajes automáticos, ban a los bots de publicidad y <code className={codigo}>!clip</code>, en Twitch y Kick a la
              vez.
            </li>
            <li>
              <b>Chat</b>: los dos chats juntos, con campanita y moderación con click derecho. Sirve como panel de OBS.
            </li>
            <li>
              <b>Título y categoría</b>: los cambiás una vez y se cambian en las dos plataformas.
            </li>
            <li>
              La app queda en la bandeja, al lado del reloj. <b>Salir</b> cierra todo. Para que arranque con Windows, poné un acceso directo a{' '}
              <code className={codigo}>StreamKit.exe</code> en la carpeta de inicio (Win+R → <code className={codigo}>shell:startup</code>
              ).
            </li>
          </ol>
        }
      />

      {aviso && (
        <Alert variant={caido ? 'destructive' : 'warning'}>
          <AlertDescription>{aviso}</AlertDescription>
        </Alert>
      )}

      {verPasos && (
        <Seccion titulo="Primeros pasos">
          <Lineas items={faltan} />
        </Seccion>
      )}

      <section aria-label="Servicios" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Servicio href="/delay" titulo="Delay" pill={delayPill} items={delayLineas} ir="Abrir delay" />
        <Servicio href="/bot" titulo="Bot" pill={botPill} items={botLineas} ir="Personalizar el bot" />
        <Servicio
          href="/chat"
          titulo="Chat"
          items={[
            ['', 'Twitch y Kick juntos, con las alertas'],
            ['', 'Campanita con filtros para cada mensaje'],
          ]}
          ir="Abrir chat"
        />
        <Servicio
          href="/pantallas"
          titulo="Pantallas para OBS"
          items={[
            ['', 'Chat, alertas, marcos, metas y más en un lienzo'],
            ['', 'Un link por pantalla para una fuente de navegador'],
          ]}
          ir="Armar pantallas"
        />
        <Servicio href="/canal" titulo="Título y categoría" items={[['', 'Lo cambiás una vez y se cambia en Twitch y Kick']]} ir="Cambiar título" />
        <Servicio href="/metricas" titulo="Consumo" items={[['', 'Cuánta CPU, memoria y red usa cada parte']]} ir="Ver consumo" />
        <Servicio href="/config" titulo="Configuración" items={[['', 'Claves de Twitch y Kick, y las cuentas conectadas']]} ir="Configurar" />
      </section>

      {delay?.phone && (
        <Seccion
          titulo="Desde el celular"
          descripcion="Con el celular en el mismo Wi-Fi, abrí este link (mandátelo por WhatsApp, por ejemplo). Lleva una clave: no lo compartas."
        >
          <div className="flex gap-2">
            <Input readOnly value={delay.phone} aria-label="Link para el celular" />
            <CopyButton value={delay.phone} variant="outline">
              Copiar
            </CopyButton>
          </div>
        </Seccion>
      )}

      <SeccionVersion />
    </div>
  )
}
