import { NavLink, Outlet } from 'react-router-dom'

const nav = [
  { to: '/', label: '🏠 Dashboard' },
  { to: '/goals', label: '🎯 Objetivos' },
  { to: '/activities', label: '⚡ Actividades' },
  { to: '/profile', label: '👤 Perfil' },
]

export default function Layout() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-red-900/40 bg-gray-950/90 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">⚡</span>
          <span className="text-xl font-black tracking-tight text-white">GOGGINS</span>
          <span className="text-xl font-black tracking-tight text-red-500">TRAINER</span>
        </div>
        <nav className="flex gap-1">
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
        </nav>
      </header>
      <main className="max-w-5xl mx-auto px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
