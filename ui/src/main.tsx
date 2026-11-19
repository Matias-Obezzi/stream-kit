import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Toaster } from '@/components/ui/toast'
import { TooltipProvider } from '@/components/ui/tooltip'
import { linksAfuera } from '@/lib/api'
import { EstadoProvider } from '@/lib/estado'
import { LabelsProvider } from '@/lib/labels'
import { es } from '@/lib/labels-es'
import App from './App.tsx'
import './index.css'

// oscuro salvo que el sistema pida claro: es lo que mejor queda en OBS
const claro = matchMedia('(prefers-color-scheme: light)')
const tema = () => document.documentElement.classList.toggle('dark', !claro.matches)
tema()
claro.addEventListener('change', tema)
linksAfuera()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LabelsProvider labels={es} locale="es-AR">
      <TooltipProvider delayDuration={300}>
        <EstadoProvider>
          <App />
          <Toaster position="top-center" />
        </EstadoProvider>
      </TooltipProvider>
    </LabelsProvider>
  </StrictMode>,
)
