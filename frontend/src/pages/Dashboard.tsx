import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StatCard from '../components/StatCard'
import api from '../api'

const USER_ID = 1

const HR_ZONES = [
  { zone: 'Z1', label: 'Recuperación', color: 'bg-blue-500', pct: 0 },
  { zone: 'Z2', label: 'Base aeróbica', color: 'bg-green-500', pct: 0 },
  { zone: 'Z3', label: 'Tempo', color: 'bg-yellow-500', pct: 0 },
  { zone: 'Z4', label: 'Umbral', color: 'bg-orange-500', pct: 0 },
  { zone: 'Z5', label: 'VO2 Max', color: 'bg-red-500', pct: 0 },
]

interface Activity {
  id: number
  name: string
  type: string
  distance_km: number
  moving_time_min: number
  average_heartrate: number
  start_date: string
}

export default function Dashboard() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [stravaConnected, setStravaConnected] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/api/strava/status/${USER_ID}`)
      .then(r => setStravaConnected(r.data.connected))
      .catch(() => {})

    api.get(`/api/strava/activities/${USER_ID}?limit=5`)
      .then(r => setActivities(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const weeklyKm = activities
    .filter(a => {
      const d = new Date(a.start_date)
      const now = new Date()
      const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      return d >= weekAgo
    })
    .reduce((sum, a) => sum + (a.distance_km ?? 0), 0)

  const handleSync = async () => {
    setSyncing(true)
    try {
      await api.post(`/api/strava/sync/${USER_ID}`)
      const r = await api.get(`/api/strava/activities/${USER_ID}?limit=5`)
      setActivities(r.data)
    } catch (e) {
      console.error(e)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Tu resumen de entrenamiento</p>
        </div>
        {stravaConnected ? (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            {syncing ? 'Sincronizando...' : 'Sincronizar Strava'}
          </button>
        ) : (
          <a
            href={`/api/strava/auth?user_id=${USER_ID}`}
            className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            Conectar Strava
          </a>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Km esta semana" value={weeklyKm.toFixed(1)} unit="km" color="orange" />
        <StatCard label="Actividades" value={activities.length} unit="recientes" color="blue" />
        <StatCard label="Strava" value={stravaConnected ? 'Conectado' : 'Desconectado'} color={stravaConnected ? 'green' : 'red'} />
        <StatCard label="Objetivos activos" value="—" sub="Ve a Objetivos" color="purple" />
      </div>

      {/* Zonas cardíacas */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="font-semibold mb-4">Zonas cardíacas</h2>
        <div className="space-y-3">
          {HR_ZONES.map(z => (
            <div key={z.zone} className="flex items-center gap-3">
              <span className="text-xs font-mono text-gray-500 w-6">{z.zone}</span>
              <span className="text-sm text-gray-400 w-28">{z.label}</span>
              <div className="flex-1 bg-gray-800 rounded-full h-2">
                <div className={`${z.color} h-2 rounded-full`} style={{ width: `${z.pct}%` }} />
              </div>
              <span className="text-xs text-gray-600 w-8 text-right">{z.pct}%</span>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-4">
          Configura tu FC máxima en <Link to="/profile" className="text-orange-400 hover:underline">Perfil</Link> para calcular las zonas automáticamente.
        </p>
      </div>

      {/* Últimas actividades */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Últimas actividades</h2>
          <Link to="/activities" className="text-sm text-orange-400 hover:underline">Ver todas</Link>
        </div>
        {loading ? (
          <p className="text-gray-600 text-sm">Cargando...</p>
        ) : activities.length === 0 ? (
          <p className="text-gray-600 text-sm">
            {stravaConnected ? 'Sin actividades. Pulsa "Sincronizar Strava".' : 'Conecta Strava para ver tus actividades.'}
          </p>
        ) : (
          <div className="space-y-3">
            {activities.map(a => (
              <div key={a.id} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
                <div>
                  <p className="text-sm font-medium">{a.name}</p>
                  <p className="text-xs text-gray-500">{new Date(a.start_date).toLocaleDateString('es-ES')}</p>
                </div>
                <div className="flex gap-4 text-right">
                  <div>
                    <p className="text-sm font-semibold text-orange-400">{a.distance_km?.toFixed(1)} km</p>
                    <p className="text-xs text-gray-500">{a.moving_time_min?.toFixed(0)} min</p>
                  </div>
                  {a.average_heartrate && (
                    <div>
                      <p className="text-sm font-semibold text-red-400">{Math.round(a.average_heartrate)} bpm</p>
                      <p className="text-xs text-gray-500">FC media</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
