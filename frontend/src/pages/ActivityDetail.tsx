import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import api from '../api'
import { useAuth } from '../auth/AuthContext'

interface StreamData {
  data?: number[]
  series_type?: string
  original_size?: number
  resolution?: string
}

interface ActivityDetailResponse {
  activity: {
    id: number
    strava_id: number
    name: string
    type: string
    distance_km: number | null
    moving_time_min: number | null
    elapsed_time_s: number | null
    elevation_gain_m: number | null
    average_heartrate: number | null
    max_heartrate: number | null
    average_speed_ms: number | null
    max_speed_ms: number | null
    start_date: string
    average_cadence_spm?: number | null
    max_cadence_spm?: number | null
    average_stride_m?: number | null
    calories?: number | null
    suffer_score?: number | null
    relative_effort?: number | null
    average_temp_c?: number | null
    average_watts?: number | null
    max_watts?: number | null
    weighted_average_watts?: number | null
    kilojoules?: number | null
    device_name?: string | null
    gear_id?: string | null
    pr_count?: number | null
    achievement_count?: number | null
    kudos_count?: number | null
    description?: string | null
    is_run?: boolean
  }
  streams: Record<string, StreamData>
  laps: any[]
  segment_efforts: any[]
  fetched_at: string | null
}

function paceFromSpeed(ms: number | null | undefined): string {
  if (!ms || ms <= 0.1) return '—'
  const secPerKm = 1000 / ms
  const m = Math.floor(secPerKm / 60)
  const s = Math.round(secPerKm % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSeconds(s: number | null | undefined): string {
  if (s == null) return '—'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function downsample<T>(arr: T[], target: number): T[] {
  if (arr.length <= target) return arr
  const step = arr.length / target
  const out: T[] = []
  for (let i = 0; i < target; i++) {
    out.push(arr[Math.floor(i * step)])
  }
  return out
}

export default function ActivityDetail() {
  const { effectiveUserId } = useAuth()
  const { activityId } = useParams<{ activityId: string }>()
  const [data, setData] = useState<ActivityDetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = (refresh = false) => {
    if (!activityId) return
    if (effectiveUserId == null) return
    setLoading(true)
    setError(null)
    api.get(`/api/strava/activity/${effectiveUserId}/${activityId}${refresh ? '?refresh=true' : ''}`)
      .then(r => setData(r.data))
      .catch(e => setError(e?.response?.data?.detail || e?.message || 'Error'))
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  }

  useEffect(() => {
    load(false)
  }, [activityId, effectiveUserId])

  if (loading && !refreshing) return <p className="text-gray-500">Cargando detalle...</p>
  if (error) return (
    <div className="space-y-4">
      <p className="text-red-400">Error: {error}</p>
      <Link to="/activities" className="text-red-400 hover:underline text-sm">← Volver</Link>
    </div>
  )
  if (!data) return null

  const a = data.activity
  const streams = data.streams || {}

  // Construir datos para el gráfico (HR + altitud sobre distancia)
  const distance = streams.distance?.data || []
  const heartrate = streams.heartrate?.data || []
  const altitude = streams.altitude?.data || []
  const velocity = streams.velocity_smooth?.data || []
  const cadenceStream = streams.cadence?.data || []
  const isRun = a.is_run ?? (a.type || '').toLowerCase().startsWith('run')

  const chartPoints: any[] = []
  if (distance.length > 0) {
    const len = Math.min(distance.length, heartrate.length || Infinity, altitude.length || Infinity)
    for (let i = 0; i < len; i++) {
      const rawCad = cadenceStream[i]
      // Strava devuelve cadencia por pierna en carrera → ×2 para pasos/min
      const cad = rawCad != null ? (isRun ? rawCad * 2 : rawCad) : null
      chartPoints.push({
        km: +(distance[i] / 1000).toFixed(2),
        hr: heartrate[i] ?? null,
        elev: altitude[i] ?? null,
        pace: velocity[i] ? +(1000 / velocity[i] / 60).toFixed(2) : null,
        cad,
      })
    }
  }
  const chartData = downsample(chartPoints, 250)
  const hasCadenceStream = chartData.some(p => p.cad != null)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <Link to="/activities" className="text-xs text-gray-500 hover:text-gray-300">← Actividades</Link>
          <h1 className="text-2xl font-black tracking-tight mt-1">{a.name}</h1>
          <p className="text-xs text-gray-500 mt-1">
            {new Date(a.start_date).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
            {' · '}{a.type}
          </p>
        </div>
        <button
          onClick={() => { setRefreshing(true); load(true) }}
          disabled={refreshing}
          className="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 px-3 py-2 rounded-lg text-xs font-bold"
        >
          {refreshing ? '⏳' : '🔄'} Refrescar
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] text-gray-500 uppercase">Distancia</p>
          <p className="text-xl font-black text-red-400 mt-1">{a.distance_km?.toFixed(2)} km</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] text-gray-500 uppercase">Tiempo</p>
          <p className="text-xl font-black mt-1">{a.moving_time_min?.toFixed(0)}'</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] text-gray-500 uppercase">Ritmo medio</p>
          <p className="text-xl font-black text-blue-400 mt-1">{paceFromSpeed(a.average_speed_ms)} /km</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] text-gray-500 uppercase">Desnivel +</p>
          <p className="text-xl font-black text-green-400 mt-1">{Math.round(a.elevation_gain_m || 0)} m</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <p className="text-[10px] text-gray-500 uppercase">FC media / máx</p>
          <p className="text-xl font-black text-pink-400 mt-1">
            {a.average_heartrate ? Math.round(a.average_heartrate) : '—'}
            {' / '}
            {a.max_heartrate ? Math.round(a.max_heartrate) : '—'}
          </p>
        </div>
      </div>

      {/* Stats extra: cadencia, zancada, calorías, esfuerzo, potencia, temperatura */}
      {(a.average_cadence_spm || a.average_stride_m || a.calories || a.relative_effort != null ||
        a.suffer_score != null || a.average_watts || a.average_temp_c != null) && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          {a.average_cadence_spm != null && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Cadencia media</p>
              <p className="text-xl font-black text-orange-400 mt-1">{Math.round(a.average_cadence_spm)} <span className="text-xs text-gray-500 font-normal">spm</span></p>
              {a.max_cadence_spm != null && (
                <p className="text-[10px] text-gray-600 mt-0.5">Máx {Math.round(a.max_cadence_spm)}</p>
              )}
            </div>
          )}
          {a.average_stride_m != null && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Zancada media</p>
              <p className="text-xl font-black text-amber-400 mt-1">{a.average_stride_m.toFixed(2)} <span className="text-xs text-gray-500 font-normal">m</span></p>
            </div>
          )}
          {a.calories != null && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Calorías</p>
              <p className="text-xl font-black text-yellow-400 mt-1">{Math.round(a.calories)} <span className="text-xs text-gray-500 font-normal">kcal</span></p>
            </div>
          )}
          {(a.relative_effort != null || a.suffer_score != null) && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Esfuerzo relativo</p>
              <p className="text-xl font-black text-red-400 mt-1">{Math.round((a.relative_effort ?? a.suffer_score) as number)}</p>
            </div>
          )}
          {a.average_watts != null && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Potencia media</p>
              <p className="text-xl font-black text-purple-400 mt-1">{Math.round(a.average_watts)} <span className="text-xs text-gray-500 font-normal">W</span></p>
              {a.max_watts != null && (
                <p className="text-[10px] text-gray-600 mt-0.5">Máx {Math.round(a.max_watts)} W</p>
              )}
            </div>
          )}
          {a.average_temp_c != null && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-[10px] text-gray-500 uppercase">Temperatura</p>
              <p className="text-xl font-black text-cyan-400 mt-1">{Math.round(a.average_temp_c)}° <span className="text-xs text-gray-500 font-normal">C</span></p>
            </div>
          )}
        </div>
      )}

      {/* Gráfico HR + altitud */}
      {chartData.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="font-black text-sm mb-3">📈 Frecuencia cardíaca y altitud</h2>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 5 }}>
              <defs>
                <linearGradient id="elevGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22c55e" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="km"
                stroke="#6b7280"
                fontSize={10}
                tickFormatter={v => `${v}km`}
                tickLine={false}
                axisLine={{ stroke: '#1f2937' }}
              />
              <YAxis
                yAxisId="hr"
                stroke="#ec4899"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={35}
              />
              <YAxis
                yAxisId="elev"
                orientation="right"
                stroke="#22c55e"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={35}
              />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(value: any, name: any) => {
                  if (value == null) return ['—', name]
                  if (name === 'hr') return [`${Math.round(value)} bpm`, 'FC']
                  if (name === 'elev') return [`${Math.round(value)} m`, 'Altitud']
                  return [value, String(name)]
                }}
                labelFormatter={(v: any) => `${v} km`}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
                formatter={v => v === 'hr' ? 'FC (bpm)' : v === 'elev' ? 'Altitud (m)' : v}
              />
              <Area
                yAxisId="elev"
                type="monotone"
                dataKey="elev"
                stroke="#22c55e"
                strokeWidth={1.5}
                fill="url(#elevGradient)"
              />
              <Line
                yAxisId="hr"
                type="monotone"
                dataKey="hr"
                stroke="#ec4899"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Gráfico de cadencia */}
      {hasCadenceStream && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="font-black text-sm mb-3">👟 Cadencia (spm)</h2>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 5 }}>
              <CartesianGrid stroke="#1f2937" vertical={false} />
              <XAxis
                dataKey="km"
                stroke="#6b7280"
                fontSize={10}
                tickFormatter={v => `${v}km`}
                tickLine={false}
                axisLine={{ stroke: '#1f2937' }}
              />
              <YAxis
                stroke="#fb923c"
                fontSize={10}
                tickLine={false}
                axisLine={false}
                width={35}
                domain={[140, 'dataMax + 10']}
              />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }}
                formatter={(value: any) => value == null ? ['—', 'Cadencia'] : [`${Math.round(value)} spm`, 'Cadencia']}
                labelFormatter={(v: any) => `${v} km`}
              />
              <Line
                type="monotone"
                dataKey="cad"
                stroke="#fb923c"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Splits */}
      {data.laps && data.laps.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="font-black text-sm mb-3">📊 Splits ({data.laps.length})</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] text-gray-500 uppercase border-b border-gray-800">
                  <th className="text-left py-2 px-2">Lap</th>
                  <th className="text-right py-2 px-2">Dist</th>
                  <th className="text-right py-2 px-2">Tiempo</th>
                  <th className="text-right py-2 px-2">Ritmo</th>
                  <th className="text-right py-2 px-2">FC</th>
                  <th className="text-right py-2 px-2">Cad</th>
                  <th className="text-right py-2 px-2">Zancada</th>
                  <th className="text-right py-2 px-2">Desnivel</th>
                </tr>
              </thead>
              <tbody>
                {data.laps.map((lap, i) => {
                  const cadSpm = lap.average_cadence != null
                    ? (isRun ? lap.average_cadence * 2 : lap.average_cadence)
                    : null
                  const stride = (cadSpm && lap.average_speed)
                    ? (lap.average_speed * 60) / cadSpm
                    : null
                  return (
                    <tr key={i} className="border-b border-gray-800/60">
                      <td className="py-2 px-2 text-gray-400">{lap.lap_index ?? i + 1}</td>
                      <td className="py-2 px-2 text-right">{(lap.distance / 1000).toFixed(2)} km</td>
                      <td className="py-2 px-2 text-right">{formatSeconds(lap.moving_time)}</td>
                      <td className="py-2 px-2 text-right text-blue-400 font-semibold">{paceFromSpeed(lap.average_speed)} /km</td>
                      <td className="py-2 px-2 text-right text-pink-400">{lap.average_heartrate ? Math.round(lap.average_heartrate) : '—'}</td>
                      <td className="py-2 px-2 text-right text-orange-400">{cadSpm != null ? Math.round(cadSpm) : '—'}</td>
                      <td className="py-2 px-2 text-right text-amber-400">{stride != null ? `${stride.toFixed(2)} m` : '—'}</td>
                      <td className="py-2 px-2 text-right text-green-400">+{Math.round(lap.total_elevation_gain || 0)} m</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Segmentos */}
      {data.segment_efforts && data.segment_efforts.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="font-black text-sm mb-3">🏁 Segmentos ({data.segment_efforts.length})</h2>
          <div className="space-y-2">
            {data.segment_efforts.map((s, i) => {
              const isPR = s.pr_rank === 1
              const isTop = s.kom_rank != null && s.kom_rank <= 10
              return (
                <div
                  key={i}
                  className="bg-black/30 rounded-lg p-3 flex items-center justify-between gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-gray-200 truncate">{s.name || s.segment?.name || 'Segmento'}</p>
                    <p className="text-xs text-gray-500">
                      {s.distance ? `${(s.distance / 1000).toFixed(2)} km` : ''}
                      {s.average_grade != null && ` · ${s.average_grade.toFixed(1)}%`}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-black text-red-400">{formatSeconds(s.elapsed_time)}</p>
                    <p className="text-xs text-gray-500">{paceFromSpeed(s.distance && s.elapsed_time ? s.distance / s.elapsed_time : null)} /km</p>
                  </div>
                  <div className="flex flex-col gap-1 items-end">
                    {isPR && <span className="text-[10px] bg-yellow-900/40 text-yellow-300 px-2 py-0.5 rounded font-bold">🏆 PR</span>}
                    {isTop && <span className="text-[10px] bg-orange-900/40 text-orange-300 px-2 py-0.5 rounded font-bold">KOM #{s.kom_rank}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
