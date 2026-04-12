import { useEffect, useMemo, useState } from 'react'
import api from '../api'

const USER_ID = 1

interface Goal {
  id: number
  description: string
  type: string
  sport?: string
  target_race_date?: string | null
  is_active: boolean
}

interface Workout {
  id: number
  goal_id: number | null
  date: string
  week_index: number | null
  day_of_week: number | null
  type: string
  status: string
  planned_distance_km: number | null
  planned_duration_min: number | null
  planned_heart_rate_zone: string | null
  instructions: string | null
  actual_distance_km: number | null
  actual_duration_min: number | null
  actual_avg_heart_rate: number | null
  perceived_effort: number | null
  notes: string | null
  strava_activity_id: string | null
}

const TYPE_LABELS: Record<string, string> = {
  easy_run: 'Suave',
  tempo: 'Tempo',
  intervals: 'Series',
  long_run: 'Tirada larga',
  recovery: 'Recuperación',
  fartlek: 'Fartlek',
  hill_repeats: 'Cuestas',
  hyrox_sim: 'Sim Hyrox',
  hyrox_stations: 'Estaciones',
  strength_upper: 'Fuerza tren sup',
  strength_lower: 'Fuerza tren inf',
  strength_full: 'Fuerza full body',
  cross_training: 'Cross-training',
  rest: 'Descanso',
}

const TYPE_COLORS: Record<string, string> = {
  easy_run: 'bg-green-900/40 border-green-700/40 text-green-300',
  tempo: 'bg-yellow-900/40 border-yellow-700/40 text-yellow-300',
  intervals: 'bg-red-900/40 border-red-700/40 text-red-300',
  long_run: 'bg-blue-900/40 border-blue-700/40 text-blue-300',
  recovery: 'bg-cyan-900/40 border-cyan-700/40 text-cyan-300',
  fartlek: 'bg-orange-900/40 border-orange-700/40 text-orange-300',
  hill_repeats: 'bg-rose-900/40 border-rose-700/40 text-rose-300',
  hyrox_sim: 'bg-purple-900/40 border-purple-700/40 text-purple-300',
  hyrox_stations: 'bg-fuchsia-900/40 border-fuchsia-700/40 text-fuchsia-300',
  strength_upper: 'bg-amber-900/40 border-amber-700/40 text-amber-300',
  strength_lower: 'bg-amber-900/40 border-amber-700/40 text-amber-300',
  strength_full: 'bg-amber-900/40 border-amber-700/40 text-amber-300',
  cross_training: 'bg-teal-900/40 border-teal-700/40 text-teal-300',
  rest: 'bg-gray-800/60 border-gray-700/40 text-gray-400',
}

const DAY_NAMES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

function formatDayKey(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function startOfWeek(d: Date): Date {
  const out = new Date(d)
  const day = (out.getDay() + 6) % 7 // 0 = lunes
  out.setDate(out.getDate() - day)
  out.setHours(0, 0, 0, 0)
  return out
}

export default function Plan() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(null)
  const [workouts, setWorkouts] = useState<Workout[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [selectedWorkout, setSelectedWorkout] = useState<Workout | null>(null)

  // Carga inicial
  useEffect(() => {
    api.get(`/api/goals/${USER_ID}?active_only=true`)
      .then(r => {
        setGoals(r.data)
        if (r.data.length > 0) setSelectedGoalId(r.data[0].id)
      })
      .catch(() => {})
  }, [])

  const fetchWorkouts = (goalId: number | null) => {
    setLoading(true)
    const url = goalId
      ? `/api/plans/${USER_ID}?goal_id=${goalId}`
      : `/api/plans/${USER_ID}`
    api.get(url)
      .then(r => setWorkouts(r.data))
      .catch(() => setWorkouts([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (selectedGoalId !== null) fetchWorkouts(selectedGoalId)
  }, [selectedGoalId])

  const handleGenerate = async () => {
    if (!selectedGoalId) return
    setGenerating(true)
    setMsg(null)
    try {
      const r = await api.post(`/api/plans/generate/${USER_ID}/${selectedGoalId}`)
      setMsg({ text: `Plan creado: ${r.data.workouts_created} entrenos`, ok: true })
      fetchWorkouts(selectedGoalId)
    } catch (e: any) {
      setMsg({ text: `Error: ${e?.response?.data?.detail || e?.message}`, ok: false })
    } finally {
      setGenerating(false)
    }
  }

  const handleMatch = async () => {
    setMsg(null)
    try {
      const r = await api.post(`/api/plans/match_strava/${USER_ID}`)
      setMsg({ text: `${r.data.matched} entrenos emparejados con Strava`, ok: true })
      if (selectedGoalId) fetchWorkouts(selectedGoalId)
    } catch (e: any) {
      setMsg({ text: `Error: ${e?.response?.data?.detail || e?.message}`, ok: false })
    }
  }

  const updateWorkout = async (id: number, patch: Partial<Workout>) => {
    try {
      const r = await api.patch(`/api/plans/workout/${id}`, patch)
      setWorkouts(ws => ws.map(w => (w.id === id ? r.data : w)))
      if (selectedWorkout?.id === id) setSelectedWorkout(r.data)
    } catch (e) {
      console.error(e)
    }
  }

  // Agrupa workouts por semana (lunes)
  const weeks = useMemo(() => {
    if (workouts.length === 0) return []
    const map = new Map<string, Workout[]>()
    for (const w of workouts) {
      if (!w.date) continue
      const d = new Date(w.date)
      const monday = startOfWeek(d)
      const key = formatDayKey(monday)
      const arr = map.get(key) || []
      arr.push(w)
      map.set(key, arr)
    }
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([key, items]) => ({ weekStart: key, items }))
  }, [workouts])

  const selectedGoal = goals.find(g => g.id === selectedGoalId) || null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-black tracking-tight">🗓️ Plan de Entrenamiento</h1>
          <p className="text-gray-500 text-sm mt-1">Periodización generada por IA basada en tu objetivo.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleMatch}
            className="bg-gray-800 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-bold"
          >
            🔗 Emparejar Strava
          </button>
          <button
            onClick={handleGenerate}
            disabled={generating || !selectedGoalId}
            className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-bold"
          >
            {generating ? '⏳ Generando...' : workouts.length > 0 ? '🔄 Regenerar plan' : '⚡ Generar plan'}
          </button>
        </div>
      </div>

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
      )}

      {/* Selector de objetivo */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        {goals.length === 0 ? (
          <p className="text-sm text-gray-500">
            No tienes objetivos activos. Crea uno en la sección{' '}
            <a href="/goals" className="text-red-400 hover:underline">Objetivos</a>.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {goals.map(g => (
              <button
                key={g.id}
                onClick={() => setSelectedGoalId(g.id)}
                className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${
                  selectedGoalId === g.id
                    ? 'bg-red-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {g.description}
                {g.target_race_date && (
                  <span className="ml-2 text-xs opacity-70">
                    {new Date(g.target_race_date).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {selectedGoal && workouts.length === 0 && !loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-400 mb-2">Aún no hay plan para este objetivo.</p>
          <p className="text-xs text-gray-600">Pulsa "Generar plan" para que la IA cree uno periodizado.</p>
        </div>
      )}

      {loading && <p className="text-sm text-gray-500">Cargando...</p>}

      {/* Calendario semanal */}
      {weeks.length > 0 && (
        <div className="space-y-4">
          {weeks.map((wk, idx) => {
            const monday = new Date(wk.weekStart)
            return (
              <div key={wk.weekStart} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-bold text-gray-300">
                    Semana {idx + 1}
                    <span className="text-gray-600 font-normal ml-2">
                      {monday.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}
                    </span>
                  </h3>
                  <span className="text-xs text-gray-500">
                    {wk.items
                      .filter(w => w.planned_distance_km)
                      .reduce((s, w) => s + (w.planned_distance_km || 0), 0)
                      .toFixed(1)}{' '}
                    km
                  </span>
                </div>
                <div className="grid grid-cols-7 gap-2">
                  {DAY_NAMES.map((dn, i) => {
                    const dayDate = new Date(monday)
                    dayDate.setDate(dayDate.getDate() + i)
                    const dayKey = formatDayKey(dayDate)
                    const workoutsToday = wk.items.filter(w => w.date === dayKey)
                    const isToday = formatDayKey(new Date()) === dayKey
                    return (
                      <div
                        key={i}
                        className={`min-h-[90px] rounded-lg p-2 ${
                          isToday ? 'border-2 border-red-500/60 bg-gray-950' : 'bg-gray-950/60 border border-gray-800'
                        }`}
                      >
                        <div className="text-[10px] text-gray-500 uppercase font-bold mb-1">
                          {dn} {dayDate.getDate()}
                        </div>
                        <div className="space-y-1">
                          {workoutsToday.map(w => (
                            <button
                              key={w.id}
                              onClick={() => setSelectedWorkout(w)}
                              className={`block w-full text-left text-[10px] rounded border px-1.5 py-1 ${
                                TYPE_COLORS[w.type] || 'bg-gray-800 border-gray-700 text-gray-300'
                              } ${w.status === 'completed' ? 'ring-1 ring-green-500/60' : ''}`}
                            >
                              <div className="font-bold truncate">{TYPE_LABELS[w.type] || w.type}</div>
                              {w.planned_distance_km && (
                                <div className="opacity-80">{w.planned_distance_km} km</div>
                              )}
                              {!w.planned_distance_km && w.planned_duration_min && (
                                <div className="opacity-80">{w.planned_duration_min}'</div>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal detalle workout */}
      {selectedWorkout && (
        <div
          className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedWorkout(null)}
        >
          <div
            className="bg-gray-900 border border-gray-800 rounded-xl p-6 max-w-md w-full space-y-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-black">{TYPE_LABELS[selectedWorkout.type] || selectedWorkout.type}</h3>
                <p className="text-xs text-gray-500">
                  {new Date(selectedWorkout.date).toLocaleDateString('es-ES', {
                    weekday: 'long',
                    day: 'numeric',
                    month: 'long',
                  })}
                </p>
              </div>
              <button
                onClick={() => setSelectedWorkout(null)}
                className="text-gray-500 hover:text-white text-xl leading-none"
              >
                ×
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              {selectedWorkout.planned_distance_km != null && (
                <div className="bg-black/30 rounded-lg p-2">
                  <p className="text-xs text-gray-500">Distancia</p>
                  <p className="font-bold text-red-400">{selectedWorkout.planned_distance_km} km</p>
                </div>
              )}
              {selectedWorkout.planned_duration_min != null && (
                <div className="bg-black/30 rounded-lg p-2">
                  <p className="text-xs text-gray-500">Duración</p>
                  <p className="font-bold text-red-400">{selectedWorkout.planned_duration_min}'</p>
                </div>
              )}
              {selectedWorkout.planned_heart_rate_zone && (
                <div className="bg-black/30 rounded-lg p-2">
                  <p className="text-xs text-gray-500">Zona</p>
                  <p className="font-bold text-red-400">{selectedWorkout.planned_heart_rate_zone}</p>
                </div>
              )}
            </div>

            {selectedWorkout.instructions && (
              <div>
                <p className="text-xs text-gray-500 uppercase mb-1">Instrucciones</p>
                <p className="text-sm text-gray-300 whitespace-pre-wrap">{selectedWorkout.instructions}</p>
              </div>
            )}

            {selectedWorkout.actual_distance_km != null && (
              <div className="bg-green-900/20 border border-green-900/40 rounded-lg p-3">
                <p className="text-xs text-green-400 uppercase font-bold mb-1">✓ Completado (Strava)</p>
                <p className="text-sm text-gray-300">
                  {selectedWorkout.actual_distance_km} km · {selectedWorkout.actual_duration_min}'
                  {selectedWorkout.actual_avg_heart_rate && ` · ${selectedWorkout.actual_avg_heart_rate} bpm`}
                </p>
              </div>
            )}

            <div className="flex gap-2">
              <select
                value={selectedWorkout.status}
                onChange={e => updateWorkout(selectedWorkout.id, { status: e.target.value })}
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              >
                <option value="planned">Planificado</option>
                <option value="completed">Completado</option>
                <option value="skipped">Saltado</option>
              </select>
              <button
                onClick={async () => {
                  if (!confirm('¿Eliminar este entreno?')) return
                  try {
                    await api.delete(`/api/plans/workout/${selectedWorkout.id}`)
                    setWorkouts(ws => ws.filter(w => w.id !== selectedWorkout.id))
                    setSelectedWorkout(null)
                  } catch (e) {
                    console.error(e)
                  }
                }}
                className="bg-red-900/50 hover:bg-red-900 text-red-300 px-3 py-2 rounded-lg text-sm"
              >
                🗑
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
