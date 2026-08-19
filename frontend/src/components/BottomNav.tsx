import { NavLink } from 'react-router-dom'

// Pestañas de la barra inferior móvil. Marcas y Objetivos no están aquí:
// se accede a ellos desde Perfil. El chat vive en la burbuja flotante.
const TABS = [
  { to: '/', label: 'Inicio', icon: '⚡' },
  { to: '/plan', label: 'Plan', icon: '🗓️' },
  { to: '/activities', label: 'Actividades', icon: '🏃' },
  { to: '/social', label: 'Social', icon: '🏆' },
  { to: '/profile', label: 'Perfil', icon: '👤' },
]

// Barra de navegación fija inferior, solo en móvil (<md).
export default function BottomNav() {
  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-gray-950/95 backdrop-blur border-t border-gray-800"
      // Deja hueco a la barra del home del iPhone (safe area inferior).
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex">
        {TABS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex-1 min-h-11 py-1.5 flex flex-col items-center justify-center gap-0.5 transition-colors active:opacity-70 ${
                isActive ? 'text-red-400' : 'text-gray-500'
              }`
            }
          >
            <span className="text-xl leading-none">{icon}</span>
            <span className="text-[10px] font-medium leading-none">{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
