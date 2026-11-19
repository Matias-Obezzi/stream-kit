// Las páginas del panel. Cada una se carga recién al abrirla, así el panel de OBS baja poco.
import {
  ActivityIcon,
  BotIcon,
  HouseIcon,
  LayoutTemplateIcon,
  MessageSquareIcon,
  PenLineIcon,
  SlidersHorizontalIcon,
  TimerIcon,
  type LucideIcon,
} from 'lucide-react'
import * as React from 'react'

export interface Pagina {
  ruta: string
  nombre: string
  titulo: string
  icono: LucideIcon
  abajo: boolean // en el menú de abajo de las pantallas angostas
  soloLocal?: boolean // claves y sesiones: solo desde esta PC
  componente: React.LazyExoticComponent<React.ComponentType>
}

export const PAGINAS: Pagina[] = [
  { ruta: '/', nombre: 'Inicio', titulo: 'Inicio', icono: HouseIcon, abajo: true, componente: React.lazy(() => import('@/paginas/inicio')) },
  { ruta: '/delay', nombre: 'Delay', titulo: 'Delay', icono: TimerIcon, abajo: true, componente: React.lazy(() => import('@/paginas/delay')) },
  { ruta: '/chat', nombre: 'Chat', titulo: 'Chat', icono: MessageSquareIcon, abajo: true, componente: React.lazy(() => import('@/paginas/chat')) },
  { ruta: '/canal', nombre: 'Título', titulo: 'Título y categoría', icono: PenLineIcon, abajo: true, componente: React.lazy(() => import('@/paginas/canal')) },
  { ruta: '/pantallas', nombre: 'Pantallas', titulo: 'Pantallas para OBS', icono: LayoutTemplateIcon, abajo: true, componente: React.lazy(() => import('@/paginas/pantallas')) },
  { ruta: '/bot', nombre: 'Bot', titulo: 'Bot', icono: BotIcon, abajo: true, componente: React.lazy(() => import('@/paginas/bot')) },
  { ruta: '/metricas', nombre: 'Consumo', titulo: 'Consumo y red', icono: ActivityIcon, abajo: false, componente: React.lazy(() => import('@/paginas/metricas')) },
  { ruta: '/config', nombre: 'Config', titulo: 'Configuración', icono: SlidersHorizontalIcon, abajo: true, soloLocal: true, componente: React.lazy(() => import('@/paginas/config')) },
]
