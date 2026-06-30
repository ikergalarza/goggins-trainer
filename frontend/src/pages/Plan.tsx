import { useEffect, useMemo, useState } from 'react'
import api from '../api'
import WorkoutCard from '../components/WorkoutCard'
import {
  TYPE_LABELS,
  STATUS_LABELS,
  disciplineOf,
  themeOf,
  parseIntervals,
  DISCIPLINE_ICONS,
  DISCIPLINE_LABELS,
  DISCIPLINE_THEME,
  type Discipline,
} from '../components/workoutMeta'
import { parseLocalDate, formatDayKey, startOfWeek } from '../lib/date'

const USER_ID = 1

// Disciplinas mostradas en la leyenda (orden lógico de un triatlón + fuerza/descanso).
const LEGEND_DISCIPLINES: Discipline[] = ['swim', 'bike', 'run', 'brick', 'strength', 'mobility', 'rest']

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

const DAY_NAMES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

// Los helpers de fecha (parseLocalDate / formatDayKey / startOfWeek) viven en
// ../lib/date para poder testearlos de forma aislada. Ver la nota sobre el bug
// de zona horaria allí.

export default function Plan() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [selectedGoalId, setSelectedGoalId] = useState<number | null>(null)
  const [workouts, setWorkouts] = useState<Workout[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressMsg, setProgressMsg] = useState('')
  const [streamChars, setStreamChars] = useState(0)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [selectedWorkout, setSelectedWorkout] = useState<Workout | null>(null)
  const [draggingId, setDraggingId] = useState<number | null>(null)
  const [dragOverKey, setDragOverKey] = useState<string | null>(null)

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

  // Escucha mutaciones del plan desde otras páginas (p.ej. chat Goggins) y
  // recarga también al volver el foco/visibilidad a la pestaña, por si la
  // mutación ocurrió mientras el Plan no estaba montado o en otra pestaña.
  useEffect(() => {
    const reload = () => {
      if (selectedGoalId !== null) fetchWorkouts(selectedGoalId)
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') reload()
    }
    window.addEventListener('plan-mutated', reload)
    window.addEventListener('focus', reload)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('plan-mutated', reload)
      window.removeEventListener('focus', reload)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [selectedGoalId])

  const handleGenerate = async () => {
    if (!selectedGoalId) return
    setGenerating(true)
    setProgress(0)
    setProgressMsg('Iniciando...')
    setStreamChars(0)
    setMsg(null)

    const baseUrl = (import.meta.env.VITE_API_URL as string | undefined) || ''
    const url = `${baseUrl}/api/plans/generate_stream/${USER_ID}/${selectedGoalId}`

    try {
      let res: Response
      try {
        res = await fetch(url, { method: 'POST' })
      } catch (netErr: any) {
        throw new Error(
          `No se pudo conectar con el backend (${url}). ` +
          `¿Está el servidor arrancado y VITE_API_URL configurada? Detalle: ${netErr?.message || netErr}`
        )
      }
      if (!res.ok || !res.body) {
        let body = ''
        try { body = await res.text() } catch { /* noop */ }
        throw new Error(`HTTP ${res.status} ${res.statusText}${body ? ` — ${body.slice(0, 200)}` : ''}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let receivedChars = 0
      // Estimación inicial del tamaño total — se va recalibrando
      const expectedChars = 5000

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const ev of events) {
          const line = ev.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          let payload: any
          try {
            payload = JSON.parse(line.slice(6))
          } catch {
            continue
          }

          if (payload.phase === 'context') {
            setProgress(5)
            setProgressMsg(payload.message || 'Analizando perfil...')
          } else if (payload.phase === 'calling_ai') {
            setProgress(10)
            setProgressMsg(payload.message || 'Pidiendo plan a Claude...')
          } else if (payload.phase === 'streaming') {
            receivedChars = payload.chars || receivedChars
            setStreamChars(receivedChars)
            // Crece asintóticamente entre 10% y 88%
            const ratio = Math.min(1, receivedChars / expectedChars)
            const pct = 10 + ratio * 78
            setProgress(pct)
            setProgressMsg(`Recibiendo plan de Claude (${receivedChars} caracteres)`)
          } else if (payload.phase === 'parsing') {
            setProgress(90)
            setProgressMsg(payload.message || 'Procesando plan...')
          } else if (payload.phase === 'saving') {
            setProgress(95)
            setProgressMsg(payload.message || 'Guardando entrenos...')
          } else if (payload.phase === 'done') {
            setProgress(100)
            setProgressMsg(`✓ Plan creado: ${payload.workouts_created} entrenos`)
            setMsg({ text: `Plan creado: ${payload.workouts_created} entrenos`, ok: true })
            fetchWorkouts(selectedGoalId)
          } else if (payload.phase === 'error') {
            throw new Error(payload.detail || 'Error desconocido')
          }
        }
      }
    } catch (e: any) {
      setMsg({ text: `Error: ${e?.message || e}`, ok: false })
    } finally {
      // Pequeño delay para que el usuario vea el 100%
      setTimeout(() => {
        setGenerating(false)
        setProgress(0)
        setProgressMsg('')
        setStreamChars(0)
      }, 800)
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

  const handleDropOnDay = (targetDateKey: string) => {
    const id = draggingId
    setDraggingId(null)
    setDragOverKey(null)
    if (id == null) return
    const w = workouts.find(x => x.id === id)
    if (!w || w.date === targetDateKey) return
    // Optimistic
    setWorkouts(ws => ws.map(x => (x.id === id ? { ...x, date: targetDateKey } : x)))
    updateWorkout(id, { date: targetDateKey })
  }

  // Agrupa workouts por semana (lunes)
  const weeks = useMemo(() => {
    if (workouts.length === 0) return []
    const map = new Map<string, Workout[]>()
    for (const w of workouts) {
      if (!w.date) continue
      // Parse LOCAL para que el lunes de la semana sea correcto (ver parseLocalDate)
      const d = parseLocalDate(w.date)
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

      {msg && !generating && (
        <p className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
      )}

      {/* Leyenda de disciplinas (código de color) */}
      {weeks.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-gray-400">
          {LEGEND_DISCIPLINES.map(d => (
            <span key={d} className="flex items-center gap-1.5">
              <span className={`inline-block w-2.5 h-2.5 rounded-full ${DISCIPLINE_THEME[d].dot}`} />
              <span className="opacity-80">{DISCIPLINE_ICONS[d]}</span>
              {DISCIPLINE_LABELS[d]}
            </span>
          ))}
        </div>
      )}

      {/* Barra de progreso de generación */}
      {generating && (
        <div className="bg-gray-900 border border-red-900/40 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="font-bold text-gray-200">{progressMsg || 'Generando plan...'}</span>
            <span className="font-mono text-xs text-gray-500">{progress.toFixed(0)}%</span>
          </div>
          <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-red-600 to-red-400 transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          {streamChars > 0 && (
            <p className="text-[11px] text-gray-600 font-mono">
              ⏳ Streaming desde Claude · {streamChars} caracteres recibidos
            </p>
          )}
        </div>
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
            // wk.weekStart es 'YYYY-MM-DD'; parsear LOCAL para no desfasar el día
            const monday = parseLocalDate(wk.weekStart)
            return (
              <div key={wk.weekStart} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
                <div className="flex items-start justify-between gap-3 mb-3 flex-wrap">
                  <h3 className="text-sm font-bold text-gray-300">
                    Semana {idx + 1}
                    <span className="text-gray-600 font-normal ml-2">
                      {monday.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}
                    </span>
                  </h3>
                  <div className="flex items-center gap-2 text-xs">
                    {/* Desglose de km por disciplina */}
                    {(() => {
                      const byDisc = new Map<Discipline, number>()
                      for (const w of wk.items) {
                        if (!w.planned_distance_km) continue
                        const d = disciplineOf(w.type)
                        byDisc.set(d, (byDisc.get(d) || 0) + w.planned_distance_km)
                      }
                      const total = Array.from(byDisc.values()).reduce((s, v) => s + v, 0)
                      return (
                        <>
                          {LEGEND_DISCIPLINES.filter(d => byDisc.has(d)).map(d => (
                            <span
                              key={d}
                              className={`px-1.5 py-0.5 rounded font-semibold ${DISCIPLINE_THEME[d].chipBg}`}
                              title={DISCIPLINE_LABELS[d]}
                            >
                              {DISCIPLINE_ICONS[d]} {(byDisc.get(d) || 0).toFixed(1)}
                            </span>
                          ))}
                          {total > 0 && (
                            <span className="text-gray-400 font-bold">{total.toFixed(1)} km</span>
                          )}
                        </>
                      )
                    })()}
                  </div>
                </div>
                <div className="grid grid-cols-7 gap-2">
                  {DAY_NAMES.map((dn, i) => {
                    const dayDate = new Date(monday)
                    dayDate.setDate(dayDate.getDate() + i)
                    const dayKey = formatDayKey(dayDate)
                    const workoutsToday = wk.items.filter(w => w.date === dayKey)
                    const isToday = formatDayKey(new Date()) === dayKey
                    const isDragOver = dragOverKey === dayKey
                    return (
                      <div
                        key={i}
                        onDragOver={e => {
                          if (draggingId != null) {
                            e.preventDefault()
                            if (dragOverKey !== dayKey) setDragOverKey(dayKey)
                          }
                        }}
                        onDragLeave={() => {
                          if (dragOverKey === dayKey) setDragOverKey(null)
                        }}
                        onDrop={e => {
                          e.preventDefault()
                          handleDropOnDay(dayKey)
                        }}
                        className={`min-h-[90px] rounded-lg p-2 transition-colors ${
                          isDragOver
                            ? 'border-2 border-red-400 bg-red-950/30'
                            : isToday
                              ? 'border-2 border-red-500/60 bg-gray-950'
                              : 'bg-gray-950/60 border border-gray-800'
                        }`}
                      >
                        <div className="text-[10px] text-gray-500 uppercase font-bold mb-1">
                          {dn} {dayDate.getDate()}
                        </div>
                        <div className="space-y-1">
                          {workoutsToday.map(w => (
                            <WorkoutCard
                              key={w.id}
                              workout={w}
                              isDragging={draggingId === w.id}
                              onClick={() => setSelectedWorkout(w)}
                              onDragStart={e => {
                                setDraggingId(w.id)
                                e.dataTransfer.effectAllowed = 'move'
                                // Algunos navegadores requieren setData para iniciar el drag
                                try { e.dataTransfer.setData('text/plain', String(w.id)) } catch { /* noop */ }
                              }}
                              onDragEnd={() => {
                                setDraggingId(null)
                                setDragOverKey(null)
                              }}
                            />
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
            {(() => {
              const theme = themeOf(selectedWorkout.type)
              const disc = disciplineOf(selectedWorkout.type)
              return (
                <div className={`flex items-start justify-between border-l-4 ${theme.accentBorder} -ml-6 pl-5`}>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{DISCIPLINE_ICONS[disc]}</span>
                      <h3 className="text-lg font-black">{TYPE_LABELS[selectedWorkout.type] || selectedWorkout.type}</h3>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${theme.chipBg}`}>
                        {DISCIPLINE_LABELS[disc]}
                      </span>
                      <span
                        className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                          selectedWorkout.status === 'completed'
                            ? 'bg-green-500/15 text-green-300'
                            : selectedWorkout.status === 'skipped'
                              ? 'bg-gray-500/20 text-gray-400'
                              : 'bg-red-500/15 text-red-300'
                        }`}
                      >
                        {STATUS_LABELS[selectedWorkout.status] || selectedWorkout.status}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1.5 capitalize">
                      {parseLocalDate(selectedWorkout.date).toLocaleDateString('es-ES', {
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
              )
            })()}

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

            {selectedWorkout.instructions && (() => {
              const sets = parseIntervals(selectedWorkout.instructions)
              return (
                <div className="space-y-2">
                  {sets.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 uppercase mb-1.5">Series</p>
                      <div className="space-y-1.5">
                        {sets.map((s, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 bg-black/30 border border-gray-800 rounded-lg px-3 py-2"
                          >
                            <span className="text-red-400 font-black text-sm shrink-0">{s.reps}×</span>
                            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
                              <span className="font-bold text-gray-100">{s.distance}</span>
                              {s.zone && (
                                <span className="text-xs font-semibold text-red-300">@ {s.zone}</span>
                              )}
                              {s.rest && (
                                <span className="text-xs text-gray-500">rec {s.rest}</span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    <p className="text-xs text-gray-500 uppercase mb-1">Instrucciones</p>
                    <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{selectedWorkout.instructions}</p>
                  </div>
                </div>
              )
            })()}

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
                <option value="planned">{STATUS_LABELS.planned}</option>
                <option value="completed">{STATUS_LABELS.completed}</option>
                <option value="skipped">{STATUS_LABELS.skipped}</option>
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
