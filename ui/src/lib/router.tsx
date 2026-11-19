// Navegación sin recargar: el servidor devuelve la misma página para cada ruta del panel.
import * as React from 'react'

const escuchas = new Set<() => void>()
function avisar() {
  for (const f of escuchas) f()
}
window.addEventListener('popstate', avisar)

export function navegar(a: string) {
  if (a === location.pathname + location.search) return
  history.pushState(null, '', a)
  window.scrollTo(0, 0)
  avisar()
}

export function useRuta() {
  return React.useSyncExternalStore(
    (f) => {
      escuchas.add(f)
      return () => escuchas.delete(f)
    },
    () => location.pathname,
  )
}

/** Un <a> de verdad (se abre en otra pestaña con el medio o Ctrl) que dentro del panel navega sin recargar. */
export function Enlace({ href, onClick, ...props }: React.ComponentProps<'a'> & { href: string }) {
  return (
    <a
      href={href}
      onClick={(e) => {
        onClick?.(e)
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
        e.preventDefault()
        navegar(href)
      }}
      {...props}
    />
  )
}
