// Consumo: CPU, memoria y red de cada parte de Stream Kit, y la red de los últimos 30 minutos (bitrate, atraso,
// pérdida y saltos) para ver cuándo empezó un problema.
import * as React from 'react'
import { Encabezado, Seccion } from '@/components/pagina'
import { LineChart } from '@/components/ui/line-chart'
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePoll } from '@/lib/api'
import { numero } from '@/lib/formato'

interface Parte {
  nombre: string
  detalle: string
  cpu: number | null
  ram: number
  kbps: number | null
}
interface Metricas {
  partes: Parte[]
  total: { cpu: number | null; ram: number }
  pc: { cpu: number | null; ram: number; ram_total: number }
}
interface Historial {
  muestras: { t: number; in: number; perdida: number | null; d: Record<string, [number, number]> }[]
  saltos: [number, string][]
  destinos: Record<string, string>
}

const cpu = (v: number | null | undefined) => (v == null ? '…' : `${numero(v, 1)} %`)
const mb = (b: number) => (b >= 1e9 ? `${numero(b / 1e9, 1)} GB` : `${Math.round(b / 1e6)} MB`)
const red = (k: number | null | undefined) => (k == null ? '' : k >= 1000 ? `${numero(k / 1000, 1)} Mbps` : `${k} kbps`)
const hora = (t: number) => new Date(t * 1000).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })

/** Promedia de a `paso` segundos: 30 min en 180 puntos, liviano en el panel de OBS. */
function agrupar(h: Historial, paso = 10) {
  const grupos = new Map<number, Historial['muestras']>()
  for (const m of h.muestras) {
    const k = Math.floor(m.t / paso) * paso
    grupos.set(k, [...(grupos.get(k) ?? []), m])
  }
  const prom = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
  return [...grupos].map(([t, ms]) => {
    const fila: Record<string, unknown> = { t: new Date(t * 1000), OBS: prom(ms.map((m) => m.in / 1000)) }
    const perdidas = ms.map((m) => m.perdida).filter((p): p is number => p != null)
    fila.perdida = prom(perdidas)
    for (const id of Object.keys(h.destinos)) {
      const vals = ms.map((m) => m.d[id]).filter(Boolean)
      if (vals.length) {
        fila[id] = prom(vals.map((v) => v[0] / 1000))
        fila[`${id}-atraso`] = Math.max(...vals.map((v) => v[1]))
      }
    }
    return fila
  })
}

function Red() {
  const { datos: h } = usePoll<Historial>('/api/red/historial', 10000)
  const filas = React.useMemo(() => (h ? agrupar(h) : []), [h])
  if (!h) return null
  const ids = Object.keys(h.destinos).filter((id) => filas.some((f) => f[id] != null))
  // cada plataforma con el mismo color en los tres gráficos; OBS con el primero
  const color = (id: string) => `var(--chart-${(Object.keys(h.destinos).indexOf(id) % 4) + 2})`
  const eje = (v: unknown) => (v instanceof Date ? hora(v.getTime() / 1000) : String(v))
  const vacio = <p className="py-8 text-center text-sm text-muted-foreground">Sin stream en los últimos 30 minutos.</p>
  return (
    <>
      <Seccion titulo="Bitrate" descripcion="Lo que entra de OBS y lo que sale a cada plataforma, cada 10 s. Si una plataforma queda abajo de OBS, la subida no le da.">
        <LineChart
            animate={false}
          data={filas}
          x="t"
          height={220}
          series={[{ key: 'OBS', label: 'OBS', color: 'var(--chart-1)' }, ...ids.map((id) => ({ key: id, label: h.destinos[id], color: color(id) }))]}
          yFormat={(v) => `${numero(v, 1)} Mb/s`}
          xFormat={eje}
          locale="es-AR"
          empty={vacio}
        />
      </Seccion>
      <div className="grid gap-4 lg:grid-cols-2">
        <Seccion titulo="Atraso" descripcion="Segundos que cada plataforma queda atrás del vivo. A los 10 s se tira lo atrasado (un salto).">
          <LineChart
            animate={false}
            data={filas}
            x="t"
            height={180}
            series={ids.map((id) => ({ key: `${id}-atraso`, label: h.destinos[id], color: color(id) }))}
            yFormat={(v) => `${numero(v, 1)} s`}
            xFormat={eje}
            empty={vacio}
          />
        </Seccion>
        <Seccion titulo="Pérdida de paquetes" descripcion="Lo que la PC tuvo que volver a mandar (toda la PC). Con más de 0,3 % la subida se traba.">
          <LineChart
            animate={false}
            data={filas}
            x="t"
            height={180}
            series={[{ key: 'perdida', label: 'Pérdida', color: 'var(--chart-5)' }]}
            yFormat={(v) => `${numero(v, 2)} %`}
            xFormat={eje}
            empty={vacio}
          />
        </Seccion>
      </div>
      <Seccion titulo="Saltos" descripcion="Cada vez que una plataforma se atrasó 10 s y se tiró lo atrasado.">
        {h.saltos.length ? (
          <ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
            {[...h.saltos].reverse().map(([t, id], i) => (
              <li key={i} className="flex gap-2">
                <span className="text-muted-foreground tabular-nums">{new Date(t * 1000).toLocaleTimeString('es-AR')}</span>
                {h.destinos[id] ?? id}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Ninguno desde que arrancó el núcleo.</p>
        )}
      </Seccion>
    </>
  )
}

export default function Consumo() {
  const { datos: d, error } = usePoll<Metricas>('/api/metricas', 2000)
  return (
    <>
      <Encabezado
        titulo="Consumo y red"
        acciones={
          <span className="rounded-full bg-muted px-3 py-1 text-sm font-semibold">
            {error ? 'Sin respuesta' : !d || d.total.cpu === null ? 'Midiendo…' : `${cpu(d.total.cpu)} de CPU · ${mb(d.total.ram)}`}
          </span>
        }
        ayuda={
          <>
            <ol className="list-decimal space-y-1.5 pl-5">
              <li>
                <b>CPU</b> es el porcentaje de toda la PC, igual que en el Administrador de tareas: 100 % sería la PC entera.
              </li>
              <li>
                <b>Memoria</b> es la RAM que usa cada parte ahora.
              </li>
              <li>
                <b>Red</b> es lo que entra de OBS y lo que sale a cada plataforma. Tiene que parecerse al bitrate de OBS; si una
                plataforma manda mucho menos, tu conexión no da abasto.
              </li>
              <li>
                Los ffmpeg aparecen solo mientras trabajan: la recepción y los envíos con OBS transmitiendo, y las vistas previas con
                el panel de Delay abierto.
              </li>
              <li>
                Los gráficos guardan los últimos 30 minutos con stream, en memoria: se borran al reiniciar el núcleo.
              </li>
            </ol>
            <p>Se actualiza cada 2 segundos. La primera medición de cada parte tarda un momento.</p>
          </>
        }
      />
      <div className="space-y-4">
        <Seccion>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Parte</TableHead>
                <TableHead className="text-right">CPU</TableHead>
                <TableHead className="text-right">Memoria</TableHead>
                <TableHead className="text-right">Red</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d?.partes.map((p, i) => (
                <TableRow key={i}>
                  <TableHead scope="row" className="h-auto py-2 font-normal whitespace-normal">
                    <div className="font-medium text-foreground">{p.nombre}</div>
                    <div className="text-xs text-muted-foreground">{p.detalle}</div>
                  </TableHead>
                  <TableCell className="text-right tabular-nums">{cpu(p.cpu)}</TableCell>
                  <TableCell className="text-right tabular-nums">{mb(p.ram)}</TableCell>
                  <TableCell className="text-right tabular-nums">{red(p.kbps)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            {d && (
              <TableFooter>
                <TableRow>
                  <TableHead scope="row">Todo Stream Kit</TableHead>
                  <TableCell className="text-right tabular-nums">{cpu(d.total.cpu)}</TableCell>
                  <TableCell className="text-right tabular-nums">{mb(d.total.ram)}</TableCell>
                  <TableCell />
                </TableRow>
                <TableRow>
                  <TableHead scope="row">Toda la PC</TableHead>
                  <TableCell className="text-right tabular-nums">{cpu(d.pc.cpu)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {mb(d.pc.ram)} de {mb(d.pc.ram_total)}
                  </TableCell>
                  <TableCell />
                </TableRow>
              </TableFooter>
            )}
          </Table>
        </Seccion>
        <Red />
      </div>
    </>
  )
}
