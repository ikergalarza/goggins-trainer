import { useEffect, useState } from 'react'
import api from '../api'

const USER_ID = 1

export default function Profile() {
  const [status, setStatus] = useState<{ connected: boolean; athlete_id: string | null } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/api/strava/status/${USER_ID}`)
      .then(r => setStatus(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleConnect = () => {
    window.location.href = `/api/strava/auth?user_id=${USER_ID}`
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Perfil</h1>
        <p className="text-gray-500 text-sm mt-1">Configura tu cuenta y conexiones</p>
      </div>

      {/* Conectar Strava con OAuth */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
        <div>
          <h2 className="font-semibold">Conectar Strava</h2>
          <p className="text-sm text-gray-500 mt-1">
            Conecta tu cuenta de Strava para sincronizar actividades automáticamente.
          </p>
        </div>

        {loading ? (
          <p className="text-sm text-gray-600">Cargando...</p>
        ) : status?.connected ? (
          <div className="space-y-3">
            <p className="text-sm text-green-400">
              Strava conectado (Athlete ID: {status.athlete_id})
            </p>
            <button
              onClick={handleConnect}
              className="bg-gray-700 hover:bg-gray-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Reconectar Strava
            </button>
          </div>
        ) : (
          <button
            onClick={handleConnect}
            className="bg-orange-500 hover:bg-orange-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
          >
            Conectar con Strava
          </button>
        )}
      </div>

      {/* Placeholder datos físicos */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="font-semibold mb-2">Datos físicos</h2>
        <p className="text-sm text-gray-500">Próximamente — edad, peso, FC máxima y zonas cardíacas.</p>
      </div>
    </div>
  )
}
