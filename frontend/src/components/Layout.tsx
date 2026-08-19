import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import BottomNav from './BottomNav'
import GogginsBubble from './GogginsBubble'

// Nav superior de escritorio. Marcas y Objetivos ya no están aquí: se accede
// a ellos desde Perfil. En móvil la navegación es la barra inferior (BottomNav).
const baseNav = [
  { to: '/', label: '🏠 Dashboard' },
  { to: '/plan', label: '🗓️ Plan' },
  { to: '/chat', label: '💀 Goggins' },
  { to: '/activities', label: '⚡ Actividades' },
  { to: '/social', label: '🏆 Social' },
  { to: '/profile', label: '👤 Perfil' },
]

export default function Layout() {
  const { user, isMaster, viewAs, setViewAs, logout } = useAuth()

  const nav = isMaster ? [...baseNav, { to: '/admin', label: '🛡️ Admin' }] : baseNav

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Banner de impersonación del maestro */}
      {viewAs && (
        <div className="bg-amber-600 text-black text-sm font-bold px-4 py-2 flex items-center justify-between gap-3">
          <span>👁️ Viendo como <strong>{viewAs.name}</strong> ({viewAs.email})</span>
          <button
            onClick={() => setViewAs(null)}
            className="bg-black/20 hover:bg-black/30 active:bg-black/40 min-h-11 px-3 rounded-lg text-xs"
          >
            Volver a mi cuenta
          </button>
        </div>
      )}

      {/* Header: en móvil queda fino (solo logo); la navegación es la barra inferior */}
      <header className="border-b border-red-900/40 bg-gray-950/90 backdrop-blur px-4 sm:px-6 py-4 sticky top-0 z-20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl">⚡</span>
            <span className="text-lg sm:text-xl font-black tracking-tight text-white">GOGGINS</span>
            <span className="text-lg sm:text-xl font-black tracking-tight text-red-500">TRAINER</span>
          </div>

          {/* Nav escritorio */}
          <nav className="hidden md:flex items-center gap-1">
            {nav.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-red-600 text-white shadow-lg shadow-red-900/50'
                      : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
            <button
              onClick={logout}
              title={user?.email}
              className="ml-1 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 hover:text-white hover:bg-gray-800 transition-colors"
            >
              ⎋ Salir
            </button>
          </nav>
        </div>
      </header>

      {/* pb-24 en móvil: deja sitio a la barra inferior fija para que no tape contenido */}
      <main className="max-w-5xl mx-auto px-4 sm:px-6 pt-6 sm:pt-8 pb-24 md:pb-8">
        <Outlet />
      </main>

      {/* Barra inferior (solo móvil) y burbuja de chat con Goggins */}
      <BottomNav />
      <GogginsBubble />
    </div>
  )
}
