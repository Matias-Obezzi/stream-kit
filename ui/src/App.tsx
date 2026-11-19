import * as React from 'react'
import { Marco } from '@/components/marco'
import { Spinner } from '@/components/ui/spinner'
import { PAGINAS } from '@/rutas'
import { useRuta } from '@/lib/router'

export default function App() {
  const ruta = useRuta()
  const pagina = PAGINAS.find((p) => p.ruta === ruta)
  React.useEffect(() => {
    document.title = `${pagina?.titulo ?? 'No existe'} · Stream Kit`
  }, [pagina])
  const Pagina = pagina?.componente
  return (
    <Marco>
      <React.Suspense fallback={<Spinner className="mx-auto mt-10" />}>
        {Pagina ? <Pagina /> : <p className="text-muted-foreground">Esta página no existe.</p>}
      </React.Suspense>
    </Marco>
  )
}
