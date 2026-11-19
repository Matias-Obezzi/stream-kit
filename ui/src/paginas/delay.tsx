// Delay: lo que ve la audiencia y lo que manda OBS, activar y sacar el delay, las plataformas (con su bitrate y la
// prueba de subida) y qué se muestra mientras se junta el delay.
import { EyeIcon, EyeOffIcon, GaugeIcon, RadioIcon, SettingsIcon, TimerIcon, VideoOffIcon } from 'lucide-react'
import * as React from 'react'
import { Encabezado, Seccion } from '@/components/pagina'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NumberField } from '@/components/ui/number-field'
import { Progress } from '@/components/ui/progress'
import { SegmentedControl, SegmentedControlItem } from '@/components/ui/segmented-control'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { toast } from '@/components/ui/toast'
import { cargarScript, post } from '@/lib/api'
import { type Destino, type Estado, useEstado } from '@/lib/estado'
import { hace, mbps, numero } from '@/lib/formato'
import { Enlace } from '@/lib/router'
import { cn } from '@/lib/utils'

const fmt = (s: number) => (s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s * 10) / 10} s`)

function leerPreview() {
  try {
    return localStorage.getItem('preview') !== 'off'
  } catch {
    return true
  }
}

// --- previews: cuadros JPG del núcleo; apagado no pide nada y el núcleo apaga los decodificadores a los 5 s ---
function Cuadro({ cual, titulo, sub, activo }: { cual: 'in' | 'out'; titulo: string; sub: string; activo: boolean }) {
  const [src, setSrc] = React.useState<string>()
  const [senal, setSenal] = React.useState(false)
  React.useEffect(() => {
    if (!activo) return
    let vivo = true
    let ultimo: string | undefined
    const pedir = async () => {
      if (!vivo) return
      if (!document.hidden) {
        const r = await fetch(`/snap/${cual}.jpg?t=${Date.now()}`).catch(() => null)
        if (r && r.status === 200) {
          const url = URL.createObjectURL(await r.blob())
          if (ultimo) URL.revokeObjectURL(ultimo)
          ultimo = url
          if (vivo) {
            setSrc(url)
            setSenal(true)
          }
        } else if (vivo) setSenal(false)
      }
      setTimeout(pedir, 40)
    }
    pedir()
    return () => {
      vivo = false
      if (ultimo) URL.revokeObjectURL(ultimo)
    }
  }, [cual, activo])
  return (
    <figure className="relative aspect-video min-w-0 overflow-hidden rounded-lg bg-black ring-1 ring-border">
      {senal && src ? (
        <img src={src} alt={titulo} className="absolute inset-0 size-full object-contain" />
      ) : (
        <span className="absolute inset-0 grid place-content-center justify-items-center gap-1.5 text-xs text-white/50">
          <VideoOffIcon aria-hidden className="size-5" />
          Sin señal
        </span>
      )}
      <figcaption title={sub} className="absolute top-1.5 left-1.5 rounded-md bg-black/70 px-2 py-1 text-xs font-semibold text-white backdrop-blur">
        {titulo} <span className="font-normal text-white/60 max-xl:hidden">· {sub}</span>
      </figcaption>
    </figure>
  )
}

function Pastilla({ s }: { s?: Estado }) {
  if (!s) return <span className="rounded-full bg-muted px-3 py-1 text-sm font-semibold">Conectando…</span>
  const [texto, clase] =
    s.mode === 'live'
      ? ['EN VIVO · sin delay', 'bg-exito text-exito-foreground']
      : s.mode === 'filler'
        ? [`ACTIVANDO DELAY · faltan ${s.filler_left} s`, 'bg-aviso text-aviso-foreground']
        : [`EN DIFERIDO · ${s.delay} s`, 'bg-diferido text-diferido-foreground']
  return (
    <span role="status" aria-live="polite" className={cn('rounded-full px-3 py-1 text-sm font-semibold', clase)}>
      {texto}
    </span>
  )
}

// --- plataformas ---
function plataformaDe(d: Destino): string {
  const f = (window as unknown as { plataformaDe?: (d: Destino) => string }).plataformaDe
  return f ? f(d) : ''
}

// el color de marca de cada plataforma: es un dato de la plataforma, no del tema
const MARCA: Record<string, string> = {
  twitch: '#9146ff',
  kick: '#53fc18',
  youtube: '#ff3b3b',
  facebook: '#1877f2',
  tiktok: '#ff0050',
  instagram: '#e1306c',
  x: '#a3a3a3',
}

function Logo({ d }: { d: Destino }) {
  const color = MARCA[plataformaDe(d)] ?? 'var(--muted-foreground)'
  return (
    <span
      aria-hidden
      className="grid size-9 shrink-0 place-items-center rounded-lg text-sm font-bold"
      style={{ color, background: `color-mix(in oklab, ${color} 16%, transparent)` }}
    >
      {d.name.trim()[0]?.toUpperCase()}
    </span>
  )
}

function Bitrate({ d, refrescar }: { d: Destino; refrescar: () => void }) {
  const [propio, setPropio] = React.useState<number | null>(d.bitrate || 6000)
  const usar = async (kbps: number) => {
    try {
      await post('/api/destinations/bitrate', { id: d.id, bitrate: kbps })
      toast.success(kbps ? `${d.name}: ${numero(kbps)} kbps` : `${d.name}: lo mismo que manda OBS`)
      refrescar()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="grid gap-1">
        <Label htmlFor={`br-${d.id}`} className="text-xs font-normal text-muted-foreground">
          Bitrate
        </Label>
        <Select value={d.bitrate ? 'propio' : 'obs'} onValueChange={(v) => usar(v === 'obs' ? 0 : propio || 6000)}>
          <SelectTrigger id={`br-${d.id}`} className="h-8 w-44" aria-label={`Bitrate de ${d.name}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="obs">Igual que OBS</SelectItem>
            <SelectItem value="propio">Propio (recomprime)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {!!d.bitrate && (
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (propio) usar(propio)
          }}
        >
          <div className="grid gap-1">
            <Label htmlFor={`kbps-${d.id}`} className="text-xs font-normal text-muted-foreground">
              kbps
            </Label>
            <NumberField
              id={`kbps-${d.id}`}
              className="h-8 w-36"
              value={propio}
              onValueChange={setPropio}
              min={500}
              max={20000}
              step={500}
              locale="es-AR"
            />
          </div>
          <Button type="submit" size="sm" variant="secondary" disabled={!propio || propio === d.bitrate}>
            Aplicar
          </Button>
        </form>
      )}
    </div>
  )
}

function FilaDestino({ d, refrescar }: { d: Destino; refrescar: () => void }) {
  const [estadoTxt, tono] = !d.enabled
    ? ['Desactivada', 'apagado']
    : d.state === 'live'
      ? [`Transmitiendo${d.kbps !== undefined ? ` · ${mbps(d.kbps)}` : ''}`, 'ok']
      : d.state === 'error'
        ? [`Error: ${d.error}`, 'mal']
        : ['Esperando señal de OBS', 'apagado']
  const salto = !!d.ultimo_descarte && Date.now() / 1000 - d.ultimo_descarte < 120
  return (
    <li className="space-y-3 py-3 first:pt-0 last:pb-0">
      <div className="flex items-center gap-3">
        <Logo d={d} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 font-semibold">
            {d.name}
            <span
              aria-hidden
              className={cn('size-2 shrink-0 rounded-full', tono === 'ok' ? 'bg-exito' : tono === 'mal' ? 'bg-destructive' : 'bg-muted-foreground/40')}
            />
          </div>
          <div className={cn('truncate text-xs', tono === 'mal' ? 'text-destructive' : 'text-muted-foreground')} title={d.url}>
            {estadoTxt}
          </div>
        </div>
        <Switch
          checked={d.enabled}
          aria-label={`Transmitir a ${d.name}`}
          title={d.enabled ? 'Activa: tocá para pausarla' : 'Pausada: tocá para activarla'}
          onCheckedChange={(on) => post('/api/destinations/enable', { id: d.id, enabled: on }).then(refrescar, (e: Error) => toast.error(e.message))}
        />
      </div>
      {d.state === 'live' && ((d.atraso ?? 0) >= 2 || salto) && (
        <p className={cn('rounded-md px-2 py-1.5 text-xs', salto ? 'bg-destructive/10 text-destructive' : 'bg-aviso/10 text-aviso')}>
          {salto
            ? `Saltó ${d.ultimo_descarte ? hace(d.ultimo_descarte) : ''}: la subida no da abasto.`
            : `${numero(d.atraso ?? 0, 1)} s atrasada: la subida no da abasto.`}{' '}
          Bajale el bitrate a esta plataforma o a OBS.
        </p>
      )}
      <div className="flex flex-wrap items-end justify-between gap-2 pl-12">
        <Bitrate d={d} refrescar={refrescar} />
        <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
          <Enlace href={`/config#${plataformaDe(d)}`} aria-label={`Clave de ${d.name}`}>
            <SettingsIcon /> Clave
          </Enlace>
        </Button>
      </div>
    </li>
  )
}

function PruebaSubida({ s, refrescar }: { s: Estado; refrescar: () => void }) {
  const p = s.prueba
  const probando = p?.estado === 'probando'
  const enStream = s.obs || s.sending
  const empezar = async () => {
    try {
      await post('/api/red/prueba')
      refrescar()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  return (
    <div className="space-y-3 border-t pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <GaugeIcon aria-hidden className="size-4 text-primary" />
        <span className="mr-auto text-sm font-medium">Prueba de subida</span>
        <Button size="sm" variant="secondary" onClick={empezar} disabled={probando || enStream} title={enStream ? 'Se prueba sin stream' : undefined}>
          {probando ? 'Probando…' : 'Probar la subida'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Manda 20 s de prueba a Twitch en su modo de prueba (no sale en vivo) y mide cuánto sube tu conexión hoy. Hacela antes
        de empezar: con el stream andando no se puede.
      </p>
      {probando && (
        <div className="space-y-1">
          <Progress value={(p?.progreso ?? 0) * 100} aria-label="Avance de la prueba" />
          <p className="text-xs text-muted-foreground" aria-live="polite">
            Subiendo a {numero(p?.mbps ?? 0, 1)} Mb/s…
          </p>
        </div>
      )}
      {p?.estado === 'listo' && p.mbps !== undefined && (
        <Alert variant={(p.recomendado ?? 0) >= 6000 ? 'success' : 'warning'}>
          <AlertTitle>
            Tu subida: {(p as { tope?: boolean }).tope ? 'más de ' : ''}
            {numero(p.mbps, 1)} Mb/s {p.hora ? <span className="font-normal text-muted-foreground">({hace(p.hora)})</span> : null}
          </AlertTitle>
          <AlertDescription>
            Con {(p as { plataformas?: number }).plataformas ?? 1} plataforma(s) activa(s), usá hasta{' '}
            <b>{numero(p.recomendado ?? 0)} kbps</b> en OBS (Ajustes → Salida → Bitrate de video). Si querés más en una
            plataforma, dale bitrate propio a las otras.
          </AlertDescription>
        </Alert>
      )}
      {p?.estado === 'error' && (
        <Alert variant="destructive">
          <AlertDescription>{p.error}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

// --- qué se muestra mientras se activa el delay ---
type Modo = 'file' | 'text' | 'rewind'

function Relleno({ s, refrescar }: { s: Estado; refrescar: () => void }) {
  const [tocado, setTocado] = React.useState(false)
  const [modo, setModo] = React.useState<Modo>(s.filler.mode as Modo)
  const [archivo, setArchivo] = React.useState(s.filler.file)
  const [vueltas, setVueltas] = React.useState<number | null>(s.filler.loops)
  const [segs, setSegs] = React.useState<number | null>(s.filler.seconds)
  const [texto, setTexto] = React.useState(s.filler.text)
  const [msg, setMsg] = React.useState<{ texto: string; error?: boolean }>()
  const subida = React.useRef<HTMLInputElement>(null)
  const preparando = s.busy.startsWith('Preparando')

  // lo guardado manda mientras no estés cambiando algo (como el panel de antes)
  React.useEffect(() => {
    if (tocado || preparando) return
    setModo(s.filler.mode as Modo)
    setArchivo(s.filler.file)
    setVueltas(s.filler.loops)
    setSegs(s.filler.seconds)
    setTexto(s.filler.text)
  }, [s.filler, tocado, preparando])
  React.useEffect(() => {
    if (s.busy) setMsg({ texto: s.busy, error: !preparando })
    else setMsg((m) => (m?.texto.startsWith('Preparando') ? { texto: `Listo: delay de ${fmt(s.filler.seconds)}. Se usa la próxima vez que lo actives.` } : m))
  }, [s.busy, preparando, s.filler.seconds])

  const cambiar = <T,>(f: (v: T) => void) => (v: T) => {
    setTocado(true)
    f(v)
  }
  const f = s.files.find((x) => x.name === archivo)
  const video = modo === 'file' && !!f?.duration
  const estimado =
    modo === 'file' && !f
      ? s.files.length
        ? 'Elegí un archivo.'
        : 'Subí un video o una imagen.'
      : video
        ? `El video dura ${fmt(f!.duration!)} × ${vueltas || 0} = delay de ${fmt(f!.duration! * (vueltas || 0))}`
        : modo === 'rewind'
          ? `Delay de ${fmt(segs || 0)}: se repiten esos segundos al activarlo`
          : `Delay de ${fmt(segs || 0)}`

  const subir = async (file: File) => {
    setMsg({ texto: `Subiendo ${file.name}…` })
    const r = await fetch('/api/upload?' + encodeURIComponent(file.name), {
      method: 'POST',
      headers: { 'X-Panel': '1', 'Content-Type': 'application/octet-stream' },
      body: file,
    })
    const j = await r.json().catch(() => ({ error: `Error ${r.status}` }))
    if (!r.ok) return setMsg({ texto: j.error, error: true })
    setTocado(true)
    refrescar()
    setArchivo(j.name)
    if (subida.current) subida.current.value = ''
    setMsg({ texto: `${j.name} subido. Tocá Guardar para usarlo.` })
  }
  const guardar = async () => {
    try {
      await post('/api/settings', { mode: modo, file: archivo, loops: vueltas, seconds: segs, text: texto })
      setTocado(false)
      setMsg({ texto: 'Preparando el video de delay...' })
      refrescar()
    } catch (e) {
      setMsg({ texto: (e as Error).message, error: true })
    }
  }

  return (
    <Seccion titulo="Qué se muestra mientras se activa el delay" descripcion="Se aplica la próxima vez que actives el delay.">
      <div className="space-y-4">
        <SegmentedControl value={modo} onValueChange={cambiar((v: string) => setModo(v as Modo))} aria-label="Tipo" className="max-w-full">
          <SegmentedControlItem value="file">Video o imagen</SegmentedControlItem>
          <SegmentedControlItem value="text">Texto</SegmentedControlItem>
          <SegmentedControlItem value="rewind">Repetir al instante</SegmentedControlItem>
        </SegmentedControl>

        {modo === 'rewind' && (
          <p className="text-sm text-muted-foreground">
            Al activar el delay, tu audiencia vuelve a ver los últimos segundos y queda en diferido al instante, sin video de
            relleno. La app guarda esos segundos en memoria (~60 MB por minuto a 8000 kbps).
          </p>
        )}
        {modo === 'file' && (
          <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
            <div className="grid gap-1.5">
              <Label htmlFor="archivo">Archivo</Label>
              <Select value={archivo} onValueChange={cambiar(setArchivo)}>
                <SelectTrigger id="archivo" className="w-full">
                  <SelectValue placeholder="Elegí un archivo" />
                </SelectTrigger>
                <SelectContent>
                  {s.files.map((x) => (
                    <SelectItem key={x.name} value={x.name}>
                      {x.duration ? `${x.name} (${fmt(x.duration)})` : `${x.name} (imagen)`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {video && (
              <div className="grid gap-1.5">
                <Label htmlFor="vueltas">Veces en bucle</Label>
                <NumberField id="vueltas" className="w-32" value={vueltas} onValueChange={cambiar(setVueltas)} min={1} max={100} />
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="subir">Subir video o imagen</Label>
              <Input
                ref={subida}
                id="subir"
                type="file"
                accept="video/*,image/*"
                className="max-w-64"
                onChange={(e) => e.target.files?.[0] && subir(e.target.files[0])}
              />
            </div>
          </div>
        )}
        {modo === 'text' && (
          <div className="grid gap-1.5">
            <Label htmlFor="texto">Texto (se muestra como imagen fija; Enter para otra línea)</Label>
            <Textarea id="texto" maxLength={200} value={texto} onChange={(e) => cambiar(setTexto)(e.target.value)} />
          </div>
        )}
        {!video && (
          <div className="grid gap-1.5">
            <Label htmlFor="segs">Segundos de delay</Label>
            <NumberField id="segs" className="w-32" value={segs} onValueChange={cambiar(setSegs)} min={5} max={600} />
          </div>
        )}
        <p className="text-sm">{estimado}</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={guardar}>
            Guardar
          </Button>
          {msg && (
            <p aria-live="polite" className={cn('text-sm', msg.error ? 'text-destructive' : 'text-muted-foreground')}>
              {msg.texto}
            </p>
          )}
        </div>
      </div>
    </Seccion>
  )
}

export default function Delay() {
  const { estado: s, refrescar } = useEstado()
  const [preview, setPreview] = React.useState(leerPreview)
  const [, forzar] = React.useState(0)
  React.useEffect(() => {
    cargarScript('/plataformas.js').then(() => forzar((n) => n + 1), () => {})
  }, [])
  const cambiarPreview = () => {
    const on = !preview
    setPreview(on)
    try {
      localStorage.setItem('preview', on ? 'on' : 'off')
    } catch {
      /* sin almacenamiento: dura hasta recargar */
    }
  }
  const accion = (ruta: string) => post(ruta).then(refrescar, (e: Error) => toast.error(e.message))
  const puedeActivar = !!s && s.mode === 'live' && s.obs
  const puedeVolver = !!s && s.mode !== 'live'

  return (
    <>
      <Encabezado
        titulo="Delay"
        acciones={
          <>
            <Pastilla s={s} />
            <Button
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground"
              aria-pressed={preview}
              aria-label={preview ? 'Apagar las vistas previas' : 'Prender las vistas previas'}
              title={preview ? 'Apagar las vistas previas (ahorra CPU)' : 'Prender las vistas previas'}
              onClick={cambiarPreview}
            >
              {preview ? <EyeIcon /> : <EyeOffIcon />}
            </Button>
          </>
        }
        ayuda={
          <>
            <ol className="list-decimal space-y-1.5 pl-5">
              <li>
                Configurá OBS con el botón <b>Autoconfigurar OBS</b> de <Enlace href="/config" className="underline">Configuración</Enlace>. A
                mano: Ajustes → Emisión → Servicio <b>Personalizado</b>, servidor <code>rtmp://127.0.0.1:1935/live</code>, clave{' '}
                <code>stream</code>, sin transmisión mejorada (multipista) y con H.264.
              </li>
              <li>
                Poné tu clave de transmisión en <Enlace href="/config" className="underline">Configuración</Enlace>, en la pestaña de
                cada plataforma (Twitch, Kick, YouTube, Facebook, TikTok, Instagram, X u otras). Abajo, en <b>Plataformas</b>, se ve
                cómo está cada una. OBS manda una vez a esta app y la app transmite a todas.
              </li>
              <li>
                Transmitís desde OBS como siempre. Cuando quieras delay, tocá <b>Activar delay</b> (o <code>Ctrl+Shift+F9</code>):
                mientras junta los segundos, sale el video o el texto que elijas abajo. <b>Volver a vivo</b> (<code>Ctrl+Shift+F10</code>) lo
                saca.
              </li>
              <li>Poné en la config la misma resolución, FPS y bitrate que en OBS: el video de relleno se arma con esos valores.</li>
              <li>
                Si tu subida no da para todas las plataformas al mismo bitrate, dale a alguna un <b>bitrate propio</b>: la app la
                recomprime con la placa de video (o el procesador si no hay) y las demás siguen con lo que manda OBS. La{' '}
                <b>prueba de subida</b> te dice cuánto usar.
              </li>
            </ol>
            <p>
              Si usás la pista de VOD de Twitch (audio sin música para el VOD), la app se la manda solo a Twitch. Mirá el README para
              activarla en OBS.
            </p>
          </>
        }
      />

      <div className="space-y-4">
        <div className="grid items-start gap-4 *:min-w-0 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <Card className="gap-4 p-4 shadow-none">
            {preview && (
              <div className="grid grid-cols-2 gap-2 sm:gap-3">
                <Cuadro cual="out" titulo="En el stream" sub="lo que ve tu audiencia" activo={preview} />
                <Cuadro cual="in" titulo="OBS" sub="lo que manda ahora" activo={preview} />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Button
                size="lg"
                variant={puedeActivar ? 'default' : 'secondary'}
                className={cn('h-14 text-base', puedeActivar && 'bg-aviso text-aviso-foreground shadow-[0_0_24px_-6px] shadow-aviso hover:bg-aviso/90')}
                disabled={!puedeActivar}
                title={s && !s.obs ? 'Se activa cuando OBS está transmitiendo' : 'Ctrl+Shift+F9'}
                onClick={() => accion('/api/delay')}
              >
                <TimerIcon /> Activar delay
              </Button>
              <Button
                size="lg"
                variant={puedeVolver ? 'default' : 'secondary'}
                className={cn('h-14 text-base', puedeVolver && 'bg-exito text-exito-foreground shadow-[0_0_24px_-6px] shadow-exito hover:bg-exito/90')}
                disabled={!puedeVolver}
                title="Ctrl+Shift+F10"
                onClick={() => accion('/api/live')}
              >
                <RadioIcon /> Volver a vivo
              </Button>
            </div>
            {s && !s.obs && s.mode === 'live' && (
              <p className="text-center text-xs text-muted-foreground">El delay se activa cuando OBS está transmitiendo a Stream Kit.</p>
            )}
          </Card>

          <Seccion titulo="Plataformas" descripcion="El interruptor pausa una sin cortar las demás.">
            {s && (
              <div className="space-y-4">
                {s.destinations.length ? (
                  <ul className="divide-y">
                    {s.destinations.map((d) => (
                      <FilaDestino key={d.id} d={d} refrescar={refrescar} />
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Todavía no hay ninguna. Poné tu clave de transmisión en{' '}
                    <Enlace href="/config" className="underline">
                      Configuración
                    </Enlace>
                    , en la pestaña de cada plataforma.
                  </p>
                )}
                <PruebaSubida s={s} refrescar={refrescar} />
              </div>
            )}
          </Seccion>
        </div>
        {s && <Relleno s={s} refrescar={refrescar} />}
      </div>
    </>
  )
}
