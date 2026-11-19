// La barra de arriba: en vivo, delay, OBS, cada plataforma (Mb/s, atraso, saltos), la pérdida de la red y el bot.
import * as React from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { type Destino, useEstado } from '@/lib/estado'
import { hace, mbps, numero, segundos } from '@/lib/formato'
import { cn } from '@/lib/utils'

type Tono = 'ok' | 'medio' | 'mal' | 'apagado'

const punto: Record<Tono, string> = {
  ok: 'bg-exito',
  medio: 'bg-aviso',
  mal: 'bg-destructive',
  apagado: 'bg-muted-foreground/50',
}

function Chip({ tono, children, detalle, className }: { tono: Tono; children: React.ReactNode; detalle?: React.ReactNode; className?: string }) {
  const cuerpo = (
    <span
      tabIndex={detalle ? 0 : undefined}
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-full px-1.5 py-0.5 text-xs whitespace-nowrap text-muted-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
        className,
      )}
    >
      <span aria-hidden className={cn('size-2 rounded-full', punto[tono])} />
      {children}
    </span>
  )
  if (!detalle) return cuerpo
  return (
    <Tooltip>
      <TooltipTrigger asChild>{cuerpo}</TooltipTrigger>
      <TooltipContent className="max-w-72">{detalle}</TooltipContent>
    </Tooltip>
  )
}

function Pastilla({ tono, children }: { tono: 'vivo' | 'apagado' | 'live' | 'filler' | 'delayed'; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        'shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap',
        tono === 'vivo' && 'bg-destructive text-primary-foreground dark:text-foreground',
        tono === 'apagado' && 'bg-muted text-muted-foreground',
        tono === 'live' && 'bg-exito text-exito-foreground',
        tono === 'filler' && 'bg-aviso text-aviso-foreground',
        tono === 'delayed' && 'bg-diferido text-diferido-foreground',
      )}
    >
      {children}
    </span>
  )
}

function ChipDestino({ d }: { d: Destino }) {
  if (d.state !== 'live' || d.kbps === undefined)
    return (
      <Chip tono={d.state === 'error' ? 'mal' : 'apagado'} detalle={d.error || undefined}>
        {d.name}
      </Chip>
    )
  const salto = !!d.ultimo_descarte && Date.now() / 1000 - d.ultimo_descarte < 120
  const atrasado = (d.atraso ?? 0) >= 2
  return (
    <Chip
      tono={salto ? 'mal' : atrasado ? 'medio' : 'ok'}
      detalle={
        <>
          Manda {mbps(d.kbps)}
          {d.recomprime && d.bitrate ? ` (recomprimido a ${mbps(d.bitrate)})` : ''}. Atrasado {segundos(d.atraso ?? 0)}: a los 10 s se tira
          lo atrasado y la imagen salta. Saltos: {d.descartes ?? 0}
          {d.descartes && d.ultimo_descarte ? `, el último ${hace(d.ultimo_descarte)}` : ''}.
        </>
      }
    >
      {d.name} {mbps(d.kbps)}
      {salto ? ' · saltó' : atrasado ? ` · ${segundos(d.atraso ?? 0)} atrás` : ''}
    </Chip>
  )
}

export function BarraEstado() {
  const { estado: s, bot: info, caido } = useEstado()
  if (caido || !s)
    return (
      <Chip tono={caido ? 'mal' : 'apagado'}>{caido ? 'Stream Kit no contesta (o se está actualizando)' : 'Cargando…'}</Chip>
    )
  const activas = s.destinations.filter((d) => d.enabled)
  const enVivo = activas.some((d) => d.state === 'live')
  const modo = { live: 'Sin delay', filler: `Activando · ${s.filler_left} s`, delayed: `Delay ${Math.round(s.delay)} s` }[s.mode]
  const red = s.red
  const perdida = red?.perdida
  const bot = info?.bot
  const chats = bot ? [bot.twitch, bot.kick] : []
  const viendo = Object.entries(bot?.viewers ?? {}).filter((e): e is [string, number] => typeof e[1] === 'number')
  const total = viendo.reduce((a, [, n]) => a + n, 0)
  return (
    <>
      <Pastilla tono={enVivo ? 'vivo' : 'apagado'}>{enVivo ? 'En vivo' : 'Fuera del aire'}</Pastilla>
      <Pastilla tono={s.mode}>{modo}</Pastilla>
      <Chip tono={s.obs ? 'ok' : 'apagado'} detalle={s.obs ? 'Lo que manda OBS a Stream Kit' : 'OBS no está transmitiendo'}>
        OBS{s.obs && red?.entrada_kbps ? ` ${mbps(red.entrada_kbps)}` : ''}
      </Chip>
      {activas.map((d) => (
        <ChipDestino key={d.id} d={d} />
      ))}
      {s.sending && perdida != null && (
        <Chip
          tono={perdida < 0.1 ? 'ok' : perdida < 0.3 ? 'medio' : 'mal'}
          detalle="Paquetes que la PC tuvo que volver a mandar en los últimos 10 s. Con más de 0,3 % la subida no da abasto y las plataformas se atrasan."
        >
          Pérdida {numero(perdida, 2)} %
        </Chip>
      )}
      {bot && (
        <Chip
          tono={!bot.vivo ? 'mal' : chats.every((c) => c === 'conectado') ? 'ok' : 'medio'}
          detalle={bot.vivo ? `Twitch: ${bot.twitch || 'sin datos'} · Kick: ${bot.kick || 'sin datos'}` : 'El bot no está corriendo'}
        >
          Bot
        </Chip>
      )}
      {viendo.length > 0 && (
        <Chip
          tono="apagado"
          className="[&>span:first-child]:hidden"
          detalle={viendo.map(([p, n]) => `${p[0].toUpperCase() + p.slice(1)}: ${n}`).join(' · ')}
        >
          {numero(total)} viendo
        </Chip>
      )}
    </>
  )
}
