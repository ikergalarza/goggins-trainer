import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StatCard from '../components/StatCard'
import api from '../api'

const USER_ID = 1

const HR_ZONES = [
  { zone: 'Z1', label: 'Recuperación', color: 'bg-blue-500', max: 60 },
  { zone: 'Z2', label: 'Base aeróbica', color: 'bg-green-500', max: 70 },
  { zone: 'Z3', label: 'Tempo', color: 'bg-yellow-500', max: 80 },
  { zone: 'Z4', label: 'Umbral', color: 'bg-orange-500', max: 90 },
  { zone: 'Z5', label: 'VO2 Max', color: 'bg-red-500', max: 100 },
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
  const [syncMsg, setSyncMsg] = useState<{ text: string; ok: boolean } | null>(null)
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
      const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000)
      return d >= weekAgo
    })
    .reduce((sum, a) => sum + (a.distance_km ?? 0), 0)

  const handleSync = async (syncAll = false) => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const url = `/api/strava/sync/${USER_ID}${syncAll ? '?all=true' : ''}`
      const syncRes = await api.post(url)
      const r = await api.get(`/api/strava/activities/${USER_ID}?limit=5`)
      setActivities(r.data)
      setSyncMsg({ text: `Sincronización OK: ${syncRes.data.new_activities} nuevas actividades`, ok: true })
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'Error desconocido'
      setSyncMsg({ text: `Error: ${detail}`, ok: false })
      console.error('Sync error:', e?.response?.data || e)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black tracking-tight">
            ⚡ Dashboard
          </h1>
          <p className="text-gray-500 text-sm mt-1">No excuses. No days off.</p>
        </div>
        {stravaConnected ? (
          <div className="flex gap-2">
            <button
              onClick={() => handleSync(false)}
              disabled={syncing}
              className="flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-lg shadow-red-900/40"
            >
              {syncing ? '⏳ Sincronizando...' : '🔄 Sincronizar'}
            </button>
            <button
              onClick={() => handleSync(true)}
              disabled={syncing}
              className="flex items-center gap-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              📥 Todo el historial
            </button>
          </div>
        ) : (
          <Link
            to="/profile"
            className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white px-5 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-lg shadow-red-900/40"
          >
            ⚡ Conectar Strava
          </Link>
        )}
      </div>

      {syncMsg && (
        <p className={`text-sm ${syncMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{syncMsg.text}</p>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Km esta semana" value={weeklyKm.toFixed(1)} unit="km" color="red" />
        <StatCard label="Actividades" value={activities.length} unit="recientes" color="blue" />
        <StatCard label="Strava" value={stravaConnected ? '✅ Conectado' : '❌ Off'} color={stravaConnected ? 'green' : 'red'} />
        <StatCard label="Objetivos" value="—" sub="Configura en Objetivos" color="purple" />
      </div>

      {/* Zonas cardíacas */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="font-black text-lg mb-5">❤️ Zonas Cardíacas</h2>
        <div className="space-y-3">
          {HR_ZONES.map(z => (
            <div key={z.zone} className="flex items-center gap-3">
              <span className="text-xs font-black text-gray-500 w-6">{z.zone}</span>
              <span className="text-sm text-gray-400 w-28">{z.label}</span>
              <div className="flex-1 bg-gray-800 rounded-full h-2.5">
                <div className={`${z.color} h-2.5 rounded-full opacity-30`} style={{ width: `${z.max}%` }} />
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-4">
          Configura tu FC máxima en{' '}
          <Link to="/profile" className="text-red-400 hover:underline">Perfil</Link>
          {' '}para calcular las zonas.
        </p>
      </div>

      {/* Últimas actividades */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-black text-lg">🏃 Últimas Actividades</h2>
          <Link to="/activities" className="text-sm text-red-400 hover:underline font-medium">Ver todas →</Link>
        </div>
        {loading ? (
          <p className="text-gray-600 text-sm">Cargando...</p>
        ) : activities.length === 0 ? (
          <p className="text-gray-600 text-sm">
            {stravaConnected
              ? 'Sin actividades. Pulsa "Sincronizar Strava".'
              : 'Ve a Perfil y conecta Strava para ver tus actividades.'}
          </p>
        ) : (
          <div className="space-y-1">
            {activities.map(a => (
              <div key={a.id} className="flex items-center justify-between py-3 border-b border-gray-800/60 last:border-0">
                <div>
                  <p className="text-sm font-semibold">{a.name}</p>
                  <p className="text-xs text-gray-500">{new Date(a.start_date).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' })}</p>
                </div>
                <div className="flex gap-5 text-right">
                  <div>
                    <p className="text-sm font-black text-red-400">{a.distance_km?.toFixed(1)} km</p>
                    <p className="text-xs text-gray-500">{a.moving_time_min?.toFixed(0)} min</p>
                  </div>
                  {a.average_heartrate && (
                    <div>
                      <p className="text-sm font-black text-pink-400">{Math.round(a.average_heartrate)} bpm</p>
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
