// El marco de todas las páginas: menú al costado en pantallas anchas y abajo en las angostas (un panel de OBS, el
// celular), con la barra de estado siempre arriba.
import * as React from 'react'
import { BarraEstado } from '@/components/barra-estado'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarLink,
  SidebarMenu,
  SidebarMenuItem,
  SidebarProvider,
} from '@/components/ui/sidebar'
import { PAGINAS } from '@/rutas'
import { Enlace, useRuta } from '@/lib/router'
import { cn } from '@/lib/utils'
import { esLocal, usePoll } from '@/lib/api'

const visibles = PAGINAS.filter((p) => !p.soloLocal || esLocal)

function MenuAbajo({ ruta }: { ruta: string }) {
  return (
    <nav
      aria-label="Páginas"
      className="fixed inset-x-0 bottom-0 z-(--z-sticky,40) flex border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {visibles
        .filter((p) => p.abajo)
        .map((p) => {
          const activa = p.ruta === ruta
          return (
            <Enlace
              key={p.ruta}
              href={p.ruta}
              aria-current={activa ? 'page' : undefined}
              title={p.nombre}
              className={cn(
                'flex h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 aria-[current=page]:text-foreground',
              )}
            >
              <p.icono aria-hidden className={cn('size-5', activa && 'text-primary')} />
              <span className="max-w-full truncate max-[420px]:sr-only">{p.nombre}</span>
            </Enlace>
          )
        })}
    </nav>
  )
}

function Version() {
  const { datos } = usePoll<{ actual: string; ultima?: { version: string } | null }>('/api/version', 60000)
  if (!datos) return null
  const nueva = datos.ultima && datos.ultima.version !== datos.actual
  return (
    <Enlace href="/" className="block px-2 text-xs text-muted-foreground hover:text-foreground">
      Stream Kit {datos.actual}
      {nueva ? ` · hay ${datos.ultima!.version}` : ''}
    </Enlace>
  )
}

export function Marco({ children }: { children: React.ReactNode }) {
  const ruta = useRuta()
  return (
    <SidebarProvider collapsible="none" breakpoint="md" width={208} keyboardShortcut={false} cookieName={false}>
      <div className="flex min-h-svh">
      <Sidebar label="Páginas" className="max-md:hidden">
        <SidebarHeader>
          <Enlace href="/" className="px-2 py-1 text-base font-semibold">
            Stream Kit
          </Enlace>
        </SidebarHeader>
        <SidebarContent>
          <SidebarMenu>
            {visibles.map((p) => (
              <SidebarMenuItem key={p.ruta}>
                <SidebarLink asChild active={p.ruta === ruta} icon={<p.icono aria-hidden />}>
                  <Enlace href={p.ruta} aria-current={p.ruta === ruta ? 'page' : undefined}>
                    {p.nombre}
                  </Enlace>
                </SidebarLink>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarContent>
        <SidebarFooter>
          <Version />
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="min-w-0">
        <div
          role="status"
          className="sticky top-0 z-(--z-sticky,40) flex h-10 items-center gap-2 overflow-x-auto border-b bg-background/95 px-3 backdrop-blur [scrollbar-width:none]"
        >
          <BarraEstado />
        </div>
        <div className="mx-auto w-full max-w-6xl p-3 pb-20 sm:p-4 sm:pb-20 md:p-6 md:pb-8">{children}</div>
      </SidebarInset>
      </div>
      <MenuAbajo ruta={ruta} />
    </SidebarProvider>
  )
}
