import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'No se pudo iniciar sesión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gray-950">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5"
      >
        <div className="text-center">
          <h1 className="text-2xl font-black tracking-tight">💀 GOGGINS TRAINER</h1>
          <p className="text-gray-500 text-sm mt-1">Stay hard. Inicia sesión.</p>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-400 uppercase font-bold">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-base"
            placeholder="tu@email.com"
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-400 uppercase font-bold">Contraseña</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-base"
            placeholder="••••••••"
          />
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white font-bold py-2.5 rounded-lg"
        >
          {loading ? 'Entrando...' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
