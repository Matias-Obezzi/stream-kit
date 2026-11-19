// Piezas comunes de las páginas: el título con su ayuda plegada y las secciones.
import { ChevronRightIcon } from 'lucide-react'
import * as React from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'

/** Título de la página, acciones a la derecha y un "Cómo se usa" plegado (el tutorial de cada pantalla). */
export function Encabezado({ titulo, acciones, ayuda }: { titulo: React.ReactNode; acciones?: React.ReactNode; ayuda?: React.ReactNode }) {
  return (
    <header className="mb-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold tracking-tight md:text-2xl">{titulo}</h1>
        {acciones}
      </div>
      {ayuda && (
        <Collapsible className="rounded-lg border bg-card text-sm">
          <CollapsibleTrigger className="group flex w-full items-center gap-2 px-3 py-2 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
            <ChevronRightIcon aria-hidden className="size-4 transition-transform group-data-[state=open]:rotate-90" />
            Cómo se usa
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 px-3 pb-3 text-muted-foreground [&_b]:text-foreground [&_strong]:text-foreground">
            {ayuda}
          </CollapsibleContent>
        </Collapsible>
      )}
    </header>
  )
}

/** Una tarjeta con título: la unidad de cada página. */
export function Seccion({
  titulo,
  descripcion,
  acciones,
  className,
  children,
}: {
  titulo?: React.ReactNode
  descripcion?: React.ReactNode
  acciones?: React.ReactNode
  className?: string
  children: React.ReactNode
}) {
  return (
    <Card className={cn('gap-3 py-4', className)}>
      {(titulo || acciones) && (
        <CardHeader className="flex flex-wrap items-start gap-2 px-4">
          <div className="mr-auto space-y-1">
            {titulo && <CardTitle className="text-base">{titulo}</CardTitle>}
            {descripcion && <CardDescription>{descripcion}</CardDescription>}
          </div>
          {acciones}
        </CardHeader>
      )}
      <CardContent className="px-4">{children}</CardContent>
    </Card>
  )
}

/** Columnas que se apilan en angosto: una sola en el panel de OBS, dos o más en pantalla grande. */
export function Columnas({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn('grid gap-4 *:min-w-0 lg:grid-cols-2', className)}>{children}</div>
}
