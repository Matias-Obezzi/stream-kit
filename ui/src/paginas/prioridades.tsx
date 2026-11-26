// Prioridades (en Configuración): la plataforma principal y el piso de las demás, el bitrate de cada una y la prueba de
// subida que dice cuánto usar.
import { GaugeIcon } from 'lucide-react'
import * as React from 'react'
import { Columnas, Seccion } from '@/components/pagina'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { NumberField } from '@/components/ui/number-field'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { toast } from '@/components/ui/toast'
import { post } from '@/lib/api'
import { type Destino, type Estado, useEstado } from '@/lib/estado'
import { hace, numero } from '@/lib/formato'

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

// una plataforma principal: si se atrasa, la app les baja el bitrate a las demás hasta el piso y se lo
// devuelve cuando la principal anda bien
function Prioridad({ s, refrescar }: { s: Estado; refrescar: () => void }) {
  const actual = s.prioridad ?? { principal: '', piso: 2500 }
  const [piso, setPiso] = React.useState<number | null>(actual.piso)
  const guardar = async (principal: string, kbps: number) => {
    try {
      await post('/api/destinations/prioridad', { principal, piso: kbps })
      const nombre = s.destinations.find((d) => d.id === principal)?.name
      toast.success(nombre ? `${nombre} es la principal` : 'Sin plataforma principal')
      refrescar()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const sinPrincipal = !s.destinations.some((d) => d.id === actual.principal)
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <Label htmlFor="principal" className="text-xs font-normal text-muted-foreground">
            Plataforma principal
          </Label>
          <Select value={sinPrincipal ? 'ninguna' : actual.principal} onValueChange={(v) => guardar(v === 'ninguna' ? '' : v, piso || actual.piso)}>
            <SelectTrigger id="principal" className="h-8 w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ninguna">Ninguna</SelectItem>
              {s.destinations.map((d) => (
                <SelectItem key={d.id} value={d.id}>
                  {d.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {!sinPrincipal && (
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (piso) guardar(actual.principal, piso)
            }}
          >
            <div className="grid gap-1">
              <Label htmlFor="piso" className="text-xs font-normal text-muted-foreground">
                Piso de las demás (kbps)
              </Label>
              <NumberField id="piso" className="h-8 w-36" value={piso} onValueChange={setPiso} min={500} max={20000} step={250} locale="es-AR" />
            </div>
            <Button type="submit" size="sm" variant="secondary" disabled={!piso || piso === actual.piso}>
              Aplicar
            </Button>
          </form>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {sinPrincipal
          ? 'Elegí una y la app la cuida: si se atrasa, les baja el bitrate a las demás.'
          : 'Si la principal se atrasa, las demás bajan al piso; cuando anda bien 3 minutos, vuelven a lo suyo. Cada cambio corta a esa plataforma unos segundos, por eso va de un salto. Si bajarlas no ayuda, vuelven y no se insiste.'}
      </p>
    </div>
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
    <div className="space-y-3 border-t pt-4" id="prueba">
      <div className="flex flex-wrap items-center gap-2">
        <GaugeIcon aria-hidden className="size-4 text-primary" />
        <span className="mr-auto text-sm font-medium">Prueba de subida</span>
        <Button size="sm" variant="secondary" onClick={empezar} disabled={probando || enStream} title={enStream ? 'Se prueba sin stream' : undefined}>
          {probando ? 'Probando…' : 'Probar la subida'}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Manda 20 s a Twitch en su modo de prueba (no sale en vivo) y mide cuánto pasa por una conexión, como la de cada plataforma. Hacela antes de
        empezar: con el stream andando no se puede.
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
            Hasta Twitch pasan {p.tope ? 'más de ' : ''}
            {numero(p.mbps, 1)} Mb/s {p.hora ? <span className="font-normal text-muted-foreground">({hace(p.hora)})</span> : null}
          </AlertTitle>
          <AlertDescription>
            {p.tope ? (
              <p>
                Tu conexión no es el límite. Con {p.plataformas ?? 1} plataforma(s) activa(s), usá hasta <b>{numero(p.recomendado ?? 0)} kbps</b> en
                OBS (Ajustes → Salida → Bitrate de video).
              </p>
            ) : (
              <>
                <p>
                  Cada plataforma va por su propia conexión y ninguna va a pasar de eso: usá hasta <b>{numero(p.recomendado ?? 0)} kbps</b> en OBS
                  (Ajustes → Salida → Bitrate de video).
                </p>
                <p>
                  Un speedtest da más porque usa muchas conexiones a la vez a un servidor cercano. Si da mucho más que esto, en el camino a Twitch se
                  pierden paquetes y cada conexión se frena: suele ser del proveedor y cambia según la hora.
                </p>
              </>
            )}
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

export function Prioridades() {
  const { estado: s, refrescar } = useEstado()
  if (!s) return <Spinner className="mx-auto" />
  return (
    <Columnas>
      <Seccion titulo="Plataforma principal" descripcion="La que tiene que andar siempre bien.">
        {s.destinations.length > 1 ? (
          <Prioridad s={s} refrescar={refrescar} />
        ) : (
          <p className="text-sm text-muted-foreground">Sirve con dos plataformas o más: agregá otra en Plataformas.</p>
        )}
      </Seccion>
      <Seccion titulo="Bitrate de cada plataforma" descripcion="Igual que OBS, o uno propio: esa plataforma se recomprime con la placa de video.">
        <div className="space-y-4">
          {s.destinations.length ? (
            <ul className="divide-y">
              {s.destinations.map((d) => (
                <li key={d.id} className="space-y-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                    {d.name}
                    {d.id === s.prioridad?.principal && (
                      <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-primary uppercase">
                        Principal
                      </span>
                    )}
                    {!!d.bajado && <span className="text-xs font-normal text-aviso">bajada a {numero(d.bajado)} kbps por la principal</span>}
                  </div>
                  <Bitrate d={d} refrescar={refrescar} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Todavía no hay ninguna: agregá tu clave en Plataformas.</p>
          )}
          <PruebaSubida s={s} refrescar={refrescar} />
        </div>
      </Seccion>
    </Columnas>
  )
}
