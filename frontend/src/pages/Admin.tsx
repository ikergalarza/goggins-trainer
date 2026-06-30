import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import { useAuth, type AuthUser } from '../auth/AuthContext'

interface AdminUser extends AuthUser {
  goals_count: number
  workouts_count: number
  last_activity: string | null
}

export default function Admin() {
  const { user, setViewAs } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  // Formulario de alta
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [creating, setCreating] = useState(false)

  const load = () => {
    setLoading(true)
    api.get('/api/auth/users')
      .then((r) => setUsers(r.data))
      .catch((e) => setMsg({ text: e?.response?.data?.detail || 'Error cargando usuarios', ok: false }))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setMsg(null)
    try {
      await api.post('/api/auth/users', { name, email, password })
      setMsg({ text: `Usuario ${email} creado`, ok: true })
      setName(''); setEmail(''); setPassword('')
      load()
    } catch (err: any) {
      setMsg({ text: err?.response?.data?.detail || 'No se pudo crear', ok: false })
    } finally {
      setCreating(false)
    }
  }

  const verComo = (u: AdminUser) => {
    setViewAs(u.id === user?.id ? null : u)
    navigate('/')
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-black tracking-tight">🛡️ Administración</h1>
        <p className="text-gray-500 text-sm mt-1">Usuarios de la plataforma. Solo el maestro ve esto.</p>
      </div>

      {msg && <p className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>}

      {/* Crear usuario */}
      <form onSubmit={createUser} className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <h2 className="text-sm font-bold text-gray-300">Crear usuario</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required placeholder="email"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
          <input value={password} onChange={(e) => setPassword(e.target.value)} type="text" required placeholder="contraseña"
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm" />
        </div>
        <button type="submit" disabled={creating}
          className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-bold">
          {creating ? 'Creando...' : 'Crear usuario'}
        </button>
      </form>

      {/* Lista de usuarios */}
      {loading ? (
        <p className="text-sm text-gray-500">Cargando...</p>
      ) : (
        <div className="space-y-2">
          {users.map((u) => (
            <div key={u.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold">{u.name}</span>
                  {u.is_master && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-red-500/15 text-red-300">Maestro</span>}
                  {u.strava_connected && <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-300">Strava</span>}
                </div>
                <p className="text-xs text-gray-500">{u.email}</p>
                <p className="text-xs text-gray-600 mt-1">
                  {u.goals_count} objetivos · {u.workouts_count} entrenos
                  {u.last_activity && ` · última actividad ${new Date(u.last_activity).toLocaleDateString('es-ES')}`}
                </p>
              </div>
              <button onClick={() => verComo(u)}
                className="bg-gray-800 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-bold shrink-0">
                👁️ Ver como
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
