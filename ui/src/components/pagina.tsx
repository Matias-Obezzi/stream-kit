// Piezas comunes de las páginas: el título con su ayuda a mano (un botón, no un bloque en cada pantalla) y las secciones.
import { CircleHelpIcon } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/** Título de la página, acciones a la derecha y un botón "Cómo se usa" que abre el tutorial de la pantalla. */
export function Encabezado({ titulo, acciones, ayuda }: { titulo: React.ReactNode; acciones?: React.ReactNode; ayuda?: React.ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-center gap-3">
      <h1 className="text-xl font-bold tracking-tight md:text-2xl">{titulo}</h1>
      {ayuda && (
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="ghost" size="icon" className="size-8 text-muted-foreground" aria-label="Cómo se usa" title="Cómo se usa">
              <CircleHelpIcon />
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>Cómo se usa: {titulo}</DialogTitle>
            </DialogHeader>
            <DialogBody className="space-y-2 text-sm text-muted-foreground [&_b]:text-foreground [&_strong]:text-foreground">{ayuda}</DialogBody>
          </DialogContent>
        </Dialog>
      )}
      <div className="ml-auto flex flex-wrap items-center gap-2">{acciones}</div>
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
    <Card className={cn('gap-3 py-4 shadow-none', className)}>
      {(titulo || acciones) && (
        <CardHeader className="flex flex-wrap items-start gap-2 px-4">
          <div className="mr-auto space-y-1">
            {titulo && <CardTitle className="text-sm font-semibold tracking-wide uppercase">{titulo}</CardTitle>}
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
