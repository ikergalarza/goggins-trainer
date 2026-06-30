import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StatCard from '../components/StatCard'
import WeeklyChart from '../components/WeeklyChart'
import api from '../api'
import { useAuth } from '../auth/AuthContext'

const HR_ZONES_META = [
  { zone: 'Z1', label: 'Recuperación', color: 'bg-blue-500' },
  { zone: 'Z2', label: 'Base aeróbica', color: 'bg-green-500' },
  { zone: 'Z3', label: 'Tempo', color: 'bg-yellow-500' },
  { zone: 'Z4', label: 'Umbral', color: 'bg-orange-500' },
  { zone: 'Z5', label: 'VO2 Max', color: 'bg-red-500' },
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
  const { effectiveUserId } = useAuth()
  const [activities, setActivities] = useState<Activity[]>([])
  const [stravaConnected, setStravaConnected] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [loading, setLoading] = useState(true)
  const [profile, setProfile] = useState<any>(null)
  const [insight, setInsight] = useState<any>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [weeklyStats, setWeeklyStats] = useState<any[]>([])
  const [chartWeeks, setChartWeeks] = useState(12)

  useEffect(() => {
    if (effectiveUserId == null) return
    api.get(`/api/strava/status/${effectiveUserId}`)
      .then(r => setStravaConnected(r.data.connected))
      .catch(() => {})
    api.get(`/api/strava/activities/${effectiveUserId}?limit=5`)
      .then(r => setActivities(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
    api.get(`/api/profile/${effectiveUserId}`).then(r => setProfile(r.data)).catch(() => {})
    api.get(`/api/ai/insights/${effectiveUserId}?kind=fitness_state`).then(r => setInsight(r.data)).catch(() => {})
  }, [effectiveUserId])

  useEffect(() => {
    if (effectiveUserId == null) return
    api.get(`/api/strava/weekly_stats/${effectiveUserId}?weeks=${chartWeeks}`)
      .then(r => setWeeklyStats(r.data))
      .catch(() => {})
  }, [chartWeeks, effectiveUserId])

  const handleAnalyze = async () => {
    if (effectiveUserId == null) return
    setAnalyzing(true)
    setAiError(null)
    try {
      const r = await api.post(`/api/ai/analyze/${effectiveUserId}`)
      setInsight(r.data)
    } catch (e: any) {
      setAiError(e?.response?.data?.detail || e?.message || 'Error desconocido')
    } finally {
      setAnalyzing(false)
    }
  }

  const weeklyKm = weeklyStats.length > 0
    ? weeklyStats[weeklyStats.length - 1].km
    : 0

  const avg4wKm = weeklyStats.length >= 4
    ? weeklyStats.slice(-4).reduce((s, w) => s + w.km, 0) / 4
    : weeklyStats.reduce((s, w) => s + w.km, 0) / Math.max(weeklyStats.length, 1)

  const total12wKm = weeklyStats.reduce((s, w) => s + w.km, 0)
  const total12wMin = weeklyStats.reduce((s, w) => s + w.time_min, 0)

  const handleSync = async (syncAll = false) => {
    if (effectiveUserId == null) return
    setSyncing(true)
    setSyncMsg(null)
    try {
      const url = `/api/strava/sync/${effectiveUserId}${syncAll ? '?all=true' : ''}`
      const syncRes = await api.post(url)
      const r = await api.get(`/api/strava/activities/${effectiveUserId}?limit=5`)
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
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight">
            ⚡ Dashboard
          </h1>
          <p className="text-gray-500 text-sm mt-1">No excuses. No days off.</p>
        </div>
        {stravaConnected ? (
          <div className="flex flex-wrap gap-2">
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
        <StatCard label="Media 4 sem" value={avg4wKm.toFixed(1)} unit="km/sem" color="blue" />
        <StatCard label="Total 12 sem" value={total12wKm.toFixed(0)} unit="km" color="green" />
        <StatCard label="Tiempo 12 sem" value={(total12wMin / 60).toFixed(0)} unit="horas" color="purple" />
      </div>

      {/* Gráficas volumen semanal */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
          <h2 className="font-black text-lg">📊 Volumen semanal</h2>
          <div className="flex gap-1">
            {[6, 12, 26, 52].map(n => (
              <button
                key={n}
                onClick={() => setChartWeeks(n)}
                className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                  chartWeeks === n
                    ? 'bg-red-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {n}s
              </button>
            ))}
          </div>
        </div>

        {weeklyStats.length === 0 ? (
          <p className="text-sm text-gray-600">Sin datos todavía. Sincroniza Strava.</p>
        ) : (
          <div className="space-y-8">
            <WeeklyChart
              title="Kilómetros / semana"
              data={weeklyStats.map(w => ({
                label: new Date(w.week_start).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
                date: w.week_start,
                value: w.km,
              }))}
              unit=" km"
              barColor="#ef4444"
              lineColor="#38bdf8"
              movingAverageWindow={4}
              height={300}
            />

            <WeeklyChart
              title="Minutos / semana"
              data={weeklyStats.map(w => ({
                label: new Date(w.week_start).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
                date: w.week_start,
                value: w.time_min,
              }))}
              unit=" min"
              barColor="#3b82f6"
              lineColor="#fbbf24"
              movingAverageWindow={4}
              height={240}
            />
          </div>
        )}
      </div>

      {/* Análisis IA */}
      <div className="bg-gradient-to-br from-gray-900 to-gray-900/60 border border-red-900/30 rounded-xl p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h2 className="font-black text-lg">🧠 Análisis IA del estado físico</h2>
            {insight?.created_at && (
              <p className="text-xs text-gray-500 mt-1">
                Último análisis: {new Date(insight.created_at).toLocaleString('es-ES', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
              </p>
            )}
          </div>
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-bold"
          >
            {analyzing ? '⏳ Analizando...' : insight ? '🔄 Re-analizar' : '⚡ Analizar ahora'}
          </button>
        </div>

        {aiError && <p className="text-sm text-red-400 mb-3">Error: {aiError}</p>}

        {!insight && !analyzing && (
          <p className="text-sm text-gray-500">
            Genera un diagnóstico completo de tu estado físico basado en tu histórico, marcas y objetivos.
          </p>
        )}

        {insight?.data && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <div className="bg-black/30 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Nivel</p>
                <p className="font-bold text-red-400 mt-0.5 capitalize">{insight.data.fitness_level || '—'}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Forma</p>
                <p className="font-bold text-red-400 mt-0.5 capitalize">{insight.data.current_form || '—'}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Volumen</p>
                <p className="font-bold text-red-400 mt-0.5">{insight.data.weekly_km_current ?? '—'} km/sem</p>
              </div>
              <div className="bg-black/30 rounded-lg p-3">
                <p className="text-xs text-gray-500 uppercase">Tendencia</p>
                <p className="font-bold text-red-400 mt-0.5 capitalize">{insight.data.trend || '—'}</p>
              </div>
            </div>

            {insight.data.target_paces && (
              <div>
                <p className="text-xs text-gray-500 uppercase mb-2">Ritmos objetivo</p>
                <div className="flex flex-wrap gap-3 text-sm">
                  {Object.entries(insight.data.target_paces).map(([k, v]: [string, any]) => (
                    <div key={k} className="bg-black/30 px-3 py-1.5 rounded-lg">
                      <span className="text-gray-500 capitalize">{k}: </span>
                      <span className="font-bold text-gray-200">{v} /km</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {insight.data.strengths?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase mb-1">Fortalezas</p>
                <ul className="text-sm text-gray-300 list-disc list-inside space-y-0.5">
                  {insight.data.strengths.map((s: string, i: number) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}

            {insight.data.weaknesses?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 uppercase mb-1">A mejorar</p>
                <ul className="text-sm text-gray-300 list-disc list-inside space-y-0.5">
                  {insight.data.weaknesses.map((s: string, i: number) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            )}

            {insight.data.next_focus && (
              <div className="bg-red-900/20 border border-red-900/40 rounded-lg p-3">
                <p className="text-xs text-red-400 uppercase font-bold mb-1">Próximo foco</p>
                <p className="text-sm text-gray-200">{insight.data.next_focus}</p>
              </div>
            )}

            {insight.summary && (
              <details className="bg-black/30 rounded-lg p-3">
                <summary className="text-xs text-gray-500 uppercase cursor-pointer">Ver análisis completo</summary>
                <p className="text-sm text-gray-300 mt-2 whitespace-pre-wrap">{insight.summary}</p>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Zonas cardíacas */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-6">
        <h2 className="font-black text-lg mb-5">❤️ Zonas Cardíacas</h2>
        {profile?.hr_zones ? (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 mb-3">
              FCmáx {profile.hr_zones.hr_max} · FCrep {profile.hr_zones.hr_rest} · Karvonen
            </p>
            {HR_ZONES_META.map(z => {
              const range = profile.hr_zones.zones?.[z.zone]
              if (!range) return null
              const pace = profile.target_paces?.[z.zone]
              return (
                <div key={z.zone} className="flex items-center gap-2 sm:gap-3 flex-wrap">
                  <span className="text-xs font-black text-gray-500 w-6">{z.zone}</span>
                  <span className="text-sm text-gray-400 w-24 sm:w-28">{z.label}</span>
                  <span className="text-sm text-gray-300 font-semibold w-24">{range[0]}–{range[1]} bpm</span>
                  {pace && <span className="text-xs text-gray-500">{pace.pace_fast}–{pace.pace_slow} /km</span>}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="space-y-3">
            {HR_ZONES_META.map(z => (
              <div key={z.zone} className="flex items-center gap-3">
                <span className="text-xs font-black text-gray-500 w-6">{z.zone}</span>
                <span className="text-sm text-gray-400 w-28">{z.label}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-2.5">
                  <div className={`${z.color} h-2.5 rounded-full opacity-30`} style={{ width: '100%' }} />
                </div>
              </div>
            ))}
            <p className="text-xs text-gray-600 mt-4">
              Configura tu edad y FC máx en{' '}
              <Link to="/profile" className="text-red-400 hover:underline">Perfil</Link>
              {' '}para calcular las zonas.
            </p>
          </div>
        )}
      </div>

      {/* Últimas actividades */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-6">
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
