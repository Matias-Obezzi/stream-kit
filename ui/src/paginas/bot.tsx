// Bot: comandos, mensajes automáticos y frases que banean. Se carga una vez y se guarda todo junto.
import * as React from 'react'
import { Columnas, Encabezado, Seccion } from '@/components/pagina'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ApiError, post } from '@/lib/api'
import { type BotEstado, useEstado } from '@/lib/estado'
import { Enlace } from '@/lib/router'
import { cn } from '@/lib/utils'

interface Config {
  comandos: Record<string, { respuesta: string; espera: number }>
  espera_lista_comandos: number
  timers: { texto: string; minutos: number }[]
  banear_frases: string[]
  no_banear: string[]
}
interface Info {
  bot: BotEstado & { aviso?: string }
  config: Config | null
  error: string
}

// los números van como texto mientras se editan: vacío no es 0, que lo rechace al guardar
interface Comando {
  id: number
  nombre: string
  respuesta: string
  espera: string
  nuevo?: boolean
}
interface Timer {
  id: number
  texto: string
  minutos: string
  nuevo?: boolean
}

let sig = 0
const numero = (v: string) => (v === '' ? null : +v)
const lineasDe = (t: string) =>
  t
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
const codigo = 'rounded bg-muted px-1 font-mono text-xs text-foreground'

function Estado({ nombre, valor, info }: { nombre: string; valor?: string; info?: Info }) {
  const vivo = info?.bot.vivo
  const tono = !info ? '' : !vivo ? 'err' : valor === 'conectado' ? 'on' : valor === 'conectando' || valor === 'reconectando' ? 'medio' : 'err'
  const texto = !info ? nombre : !vivo ? `${nombre}: bot caído` : valor === 'vencida' ? `${nombre}: sesión vencida` : `${nombre}: ${valor || 'sin datos'}`
  return (
    <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
      <span
        aria-hidden
        className={cn(
          'size-2 rounded-full',
          tono === 'on' ? 'bg-exito' : tono === 'medio' ? 'bg-aviso' : tono === 'err' ? 'bg-destructive' : 'bg-muted-foreground/50',
        )}
      />
      {texto}
    </span>
  )
}

function Tiempo({
  valor,
  min,
  max,
  unidad,
  ayuda,
  onChange,
}: {
  valor: string
  min: number
  max: number
  unidad: string
  ayuda: string
  onChange: (v: string) => void
}) {
  return (
    <label className="flex items-center gap-1.5 text-sm whitespace-nowrap text-muted-foreground">
      <Input type="number" min={min} max={max} step={1} value={valor} aria-label={ayuda} className="w-20" onChange={(e) => onChange(e.target.value)} />
      {unidad}
    </label>
  )
}

const fila = 'flex flex-wrap items-center gap-2 border-b pb-3 last:border-b-0 sm:border-b-0 sm:pb-0'
const quitar = (onClick: () => void) => (
  <Button variant="ghost" className="ml-auto text-destructive hover:text-destructive sm:ml-0" onClick={onClick}>
    Quitar
  </Button>
)

export default function Pagina() {
  const { bot } = useEstado()
  const info = bot as unknown as Info | undefined
  const [comandos, setComandos] = React.useState<Comando[]>([])
  const [esperaLista, setEsperaLista] = React.useState('')
  const [timers, setTimers] = React.useState<Timer[]>([])
  const [frases, setFrases] = React.useState('')
  const [excepciones, setExcepciones] = React.useState('')
  const [sucio, setSucio] = React.useState(false)
  const [cargado, setCargado] = React.useState(false)
  const [msg, setMsg] = React.useState({ texto: 'Al guardar, el bot se reinicia en un par de segundos. El stream no se toca.', error: false })
  const [guardando, setGuardando] = React.useState(false)
  const say = (texto: string, error = false) => setMsg({ texto, error })
  const marcar = () => setSucio(true)

  React.useEffect(() => {
    if (!info) return
    if (info.error) say(info.error, true)
    else if (!cargado && info.config) {
      const c = info.config
      setComandos(Object.entries(c.comandos).map(([nombre, d]) => ({ id: sig++, nombre, respuesta: d.respuesta, espera: String(d.espera) })))
      setEsperaLista(String(c.espera_lista_comandos))
      setTimers(c.timers.map((t) => ({ id: sig++, texto: t.texto, minutos: String(t.minutos) })))
      setFrases(c.banear_frases.join('\n'))
      setExcepciones(c.no_banear.join('\n'))
      setSucio(false)
      setCargado(true)
    }
  }, [info, cargado])

  React.useEffect(() => {
    if (!sucio) return
    const avisar = (e: BeforeUnloadEvent) => e.preventDefault()
    addEventListener('beforeunload', avisar)
    return () => removeEventListener('beforeunload', avisar)
  }, [sucio])

  const cambiarComando = (id: number, cambio: Partial<Comando>) => {
    setComandos((cs) => cs.map((c) => (c.id === id ? { ...c, ...cambio } : c)))
    marcar()
  }
  const cambiarTimer = (id: number, cambio: Partial<Timer>) => {
    setTimers((ts) => ts.map((t) => (t.id === id ? { ...t, ...cambio } : t)))
    marcar()
  }

  const reiniciar = async () => {
    await post('/api/bot/reiniciar').catch(() => null)
    say('Reiniciando el bot…')
  }

  const guardar = async () => {
    const lista: Record<string, { respuesta: string; espera: number | null }> = {}
    for (const c of comandos) {
      const n = c.nombre.trim().toLowerCase()
      if (Object.hasOwn(lista, n)) return say(`${n} está dos veces.`, true)
      lista[n] = { respuesta: c.respuesta, espera: numero(c.espera) }
    }
    setGuardando(true)
    try {
      const j = await post<{ cambio: boolean }>('/api/bot/guardar', {
        comandos: lista,
        espera_lista_comandos: numero(esperaLista),
        timers: timers.map((t) => ({ texto: t.texto, minutos: numero(t.minutos) })),
        banear_frases: lineasDe(frases),
        no_banear: lineasDe(excepciones),
      })
      setSucio(false)
      say(j.cambio ? 'Guardado. El bot se está reiniciando.' : 'No había nada para guardar.')
    } catch (e) {
      say(e instanceof ApiError ? e.message : 'El panel no contesta: probá de nuevo en unos segundos.', true)
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="space-y-4">
      <Encabezado
        titulo="Bot"
        acciones={
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Estado nombre="Twitch" valor={info?.bot.twitch} info={info} />
            <Estado nombre="Kick" valor={info?.bot.kick} info={info} />
            <Button variant="outline" onClick={reiniciar}>
              Reiniciar bot
            </Button>
          </div>
        }
        ayuda={
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Primero conectá las cuentas del bot en{' '}
              <Enlace href="/config" className="text-primary underline underline-offset-4">
                Configuración
              </Enlace>
              . Puede ser tu propia cuenta o una nueva para el bot. Si es una cuenta aparte, hacela moderadora en tu chat (
              <code className={codigo}>/mod</code> y su nombre): sin eso habla, pero no puede banear ni borrar.
            </li>
            <li>
              <b>Comandos</b>: alguien escribe <code className={codigo}>!redes</code> y el bot contesta en ese chat.{' '}
              <code className={codigo}>!comandos</code> lista todos solo. <code className={codigo}>!clip</code> crea un clip en Twitch: lo
              pueden usar vos y tus mods.
            </li>
            <li>
              <b>Mensajes automáticos</b>: salen cada tantos minutos, solo mientras estás en vivo.
            </li>
            <li>
              <b>Moderación</b>: banea al toque a quien escriba una de esas frases, como las de los bots que venden viewers.
            </li>
            <li>
              Tocá <b>Guardar</b>: el bot se reinicia en un par de segundos y el stream no se toca.
            </li>
          </ol>
        }
      />

      <Seccion titulo="Comandos">
        <div className="space-y-3">
          {comandos.map((c) => (
            <div key={c.id} className={fila}>
              <Input
                value={c.nombre}
                placeholder="!comando"
                aria-label="!comando"
                maxLength={31}
                autoFocus={c.nuevo}
                className="w-full sm:w-40"
                onChange={(e) => cambiarComando(c.id, { nombre: e.target.value })}
              />
              <Input
                value={c.respuesta}
                placeholder="Lo que contesta"
                aria-label="Lo que contesta"
                maxLength={500}
                className="basis-full sm:min-w-56 sm:flex-1 sm:basis-0"
                onChange={(e) => cambiarComando(c.id, { respuesta: e.target.value })}
              />
              <Tiempo
                valor={c.espera}
                min={0}
                max={3600}
                unidad="seg"
                ayuda="Espera del comando, en segundos"
                onChange={(espera) => cambiarComando(c.id, { espera })}
              />
              {quitar(() => {
                setComandos((cs) => cs.filter((x) => x.id !== c.id))
                marcar()
              })}
            </div>
          ))}
          <div className={fila}>
            <Input value="!comandos" disabled aria-label="Nombre del comando" className="w-full sm:w-40" />
            <span className="basis-full text-sm text-muted-foreground sm:min-w-56 sm:flex-1 sm:basis-0">La lista la arma el bot solo</span>
            <Tiempo
              valor={esperaLista}
              min={0}
              max={3600}
              unidad="seg"
              ayuda="Espera de !comandos, en segundos"
              onChange={(v) => {
                setEsperaLista(v)
                marcar()
              }}
            />
            {/* no se puede quitar: solo guarda el lugar para que quede alineada */}
            <Button variant="ghost" aria-hidden tabIndex={-1} className="invisible max-sm:hidden">
              Quitar
            </Button>
          </div>
        </div>
        <Button
          variant="outline"
          className="mt-3"
          onClick={() => {
            setComandos((cs) => [...cs, { id: sig++, nombre: '!', respuesta: '', espera: '15', nuevo: true }])
            marcar()
          }}
        >
          Agregar comando
        </Button>
        <p className="mt-3 text-sm text-muted-foreground">
          Los segundos son cuánto tarda ese comando en volver a contestar en cada chat. Con 0 contesta siempre. Las respuestas no pueden empezar
          con / ni con punto.
        </p>
      </Seccion>

      <Columnas>
        <Seccion titulo="Mensajes automáticos">
          <div className="space-y-3">
            {timers.map((t) => (
              <div key={t.id} className={fila}>
                <Input
                  value={t.texto}
                  placeholder="Lo que manda"
                  aria-label="Lo que manda"
                  maxLength={500}
                  autoFocus={t.nuevo}
                  className="basis-full sm:min-w-56 sm:flex-1 sm:basis-0"
                  onChange={(e) => cambiarTimer(t.id, { texto: e.target.value })}
                />
                <Tiempo
                  valor={t.minutos}
                  min={1}
                  max={240}
                  unidad="min"
                  ayuda="Cada cuántos minutos sale"
                  onChange={(minutos) => cambiarTimer(t.id, { minutos })}
                />
                {quitar(() => {
                  setTimers((ts) => ts.filter((x) => x.id !== t.id))
                  marcar()
                })}
              </div>
            ))}
          </div>
          <Button
            variant="outline"
            className={cn(timers.length > 0 && 'mt-3')}
            onClick={() => {
              setTimers((ts) => [...ts, { id: sig++, texto: '', minutos: '10', nuevo: true }])
              marcar()
            }}
          >
            Agregar mensaje
          </Button>
          <p className="mt-3 text-sm text-muted-foreground">
            Cada mensaje sale con su propio tiempo, en los chats que estén en vivo. Si dos tocan a la vez, salen con un minuto de diferencia. Al
            guardar, los tiempos vuelven a contar desde cero.
          </p>
        </Seccion>

        <Seccion titulo="Moderación">
          <div className="space-y-2">
            <Label htmlFor="frases" className="leading-snug">
              Frases que banean, una por línea
            </Label>
            <Textarea
              id="frases"
              value={frases}
              className="min-h-36"
              onChange={(e) => {
                setFrases(e.target.value)
                marcar()
              }}
            />
            <p className="text-sm text-muted-foreground">
              Ban directo y sin aviso, sin importar mayúsculas ni signos. Evitá palabras comunes. No toca al dueño, a los mods, a los VIP ni a los
              subs.
            </p>
          </div>
          <div className="mt-4 space-y-2">
            <Label htmlFor="excepciones" className="leading-snug">
              Excepciones: lo que se ignora antes de buscar esas frases
            </Label>
            <Textarea
              id="excepciones"
              value={excepciones}
              onChange={(e) => {
                setExcepciones(e.target.value)
                marcar()
              }}
            />
          </div>
        </Seccion>
      </Columnas>

      <div className="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.5rem)] flex flex-wrap items-center gap-3 rounded-xl border bg-card p-3 shadow-sm md:bottom-4 [@media(max-height:600px)]:static">
        <Button disabled={!sucio} loading={guardando} onClick={guardar} className="max-sm:w-full">
          Guardar
        </Button>
        <p aria-live="polite" className={cn('min-w-48 flex-1 text-sm', msg.error ? 'text-destructive' : 'text-muted-foreground')}>
          {msg.texto}
        </p>
      </div>
      {info?.bot.aviso && <p className="text-sm text-muted-foreground">Último aviso del bot: {info.bot.aviso}</p>}
    </div>
  )
}
