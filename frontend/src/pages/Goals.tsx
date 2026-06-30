import { useEffect, useState } from 'react'
import api from '../api'

const USER_ID = 1

interface Goal {
  id: number
  sport: string | null
  type: string
  description: string
  target_race_distance_km: number | null
  target_race_date: string | null
  target_time_seconds: number | null
  hyrox_division: string | null
  target_weekly_km: number | null
  triathlon_distance: string | null
  notes: string | null
  is_active: boolean
}

const TYPES = [
  { value: 'race', label: 'Carrera (running)' },
  { value: 'triathlon', label: 'Triatlón' },
  { value: 'hyrox', label: 'Hyrox' },
  { value: 'weekly_km', label: 'Volumen semanal' },
  { value: 'fitness', label: 'Forma general' },
  { value: 'custom', label: 'Otro' },
]

const TRIATHLON_DISTANCES = [
  { value: 'sprint', label: 'Sprint' },
  { value: 'olympic', label: 'Olímpico' },
  { value: 'half', label: 'Half (70.3)' },
  { value: 'ironman', label: 'Ironman' },
]

function formatSeconds(total: number | null): string {
  if (!total) return '—'
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  return `${m}:${s.toString().padStart(2, '0')}`
}

function parseTimeString(str: string): number | null {
  if (!str) return null
  const parts = str.split(':').map(p => parseInt(p, 10))
  if (parts.some(isNaN)) return null
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return null
}

export default function Goals() {
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  // Form
  const [type, setType] = useState('race')
  const [description, setDescription] = useState('')
  const [distance, setDistance] = useState('')
  const [raceDate, setRaceDate] = useState('')
  const [timeStr, setTimeStr] = useState('')
  const [hyroxDivision, setHyroxDivision] = useState('open')
  const [triathlonDistance, setTriathlonDistance] = useState('olympic')
  const [weeklyKm, setWeeklyKm] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true)
    api.get(`/api/goals/${USER_ID}`)
      .then(r => setGoals(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const resetForm = () => {
    setDescription('')
    setDistance('')
    setRaceDate('')
    setTimeStr('')
    setWeeklyKm('')
    setNotes('')
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload: any = {
        type,
        description,
        notes: notes || null,
        is_active: true,
      }
      if (type === 'race') {
        payload.sport = 'running'
        payload.target_race_distance_km = distance ? parseFloat(distance) : null
        payload.target_race_date = raceDate || null
        payload.target_time_seconds = parseTimeString(timeStr)
      } else if (type === 'triathlon') {
        payload.sport = 'triathlon'
        payload.target_race_date = raceDate || null
        payload.triathlon_distance = triathlonDistance
        payload.target_time_seconds = parseTimeString(timeStr)
      } else if (type === 'hyrox') {
        payload.sport = 'hyrox'
        payload.target_race_date = raceDate || null
        payload.hyrox_division = hyroxDivision
        payload.target_time_seconds = parseTimeString(timeStr)
      } else if (type === 'weekly_km') {
        payload.target_weekly_km = weeklyKm ? parseFloat(weeklyKm) : null
      }
      await api.post(`/api/goals/${USER_ID}`, payload)
      resetForm()
      setShowForm(false)
      load()
    } catch (err: any) {
      alert(`Error: ${err?.response?.data?.detail || err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar objetivo?')) return
    await api.delete(`/api/goals/${USER_ID}/${id}`)
    load()
  }

  const renderGoal = (g: Goal) => {
    if (g.type === 'race') {
      return `${g.target_race_distance_km}km en ${formatSeconds(g.target_time_seconds)}`
    }
    if (g.type === 'triathlon') {
      const distLabel = TRIATHLON_DISTANCES.find(d => d.value === g.triathlon_distance)?.label || g.triathlon_distance || 'Olímpico'
      return `Triatlón ${distLabel}${g.target_time_seconds ? ` en ${formatSeconds(g.target_time_seconds)}` : ''}`
    }
    if (g.type === 'hyrox') {
      return `Hyrox ${g.hyrox_division || 'open'}${g.target_time_seconds ? ` en ${formatSeconds(g.target_time_seconds)}` : ''}`
    }
    if (g.type === 'weekly_km') {
      return `${g.target_weekly_km} km/semana`
    }
    return g.description
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">🎯 Objetivos</h1>
          <p className="text-gray-500 text-sm mt-1">{goals.length} objetivos</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-bold"
        >
          {showForm ? 'Cancelar' : '+ Nuevo objetivo'}
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-6 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Tipo</label>
            <select value={type} onChange={e => setType(e.target.value)} className={input}>
              {TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Descripción</label>
            <input type="text" value={description} onChange={e => setDescription(e.target.value)} placeholder="ej. Media maratón de Bilbao" className={input} />
          </div>

          {type === 'race' && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Distancia (km)</label>
                  <input type="number" step="0.1" value={distance} onChange={e => setDistance(e.target.value)} placeholder="21.1" className={input} />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Fecha de la carrera</label>
                  <input type="date" value={raceDate} onChange={e => setRaceDate(e.target.value)} className={input} />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Tiempo objetivo (hh:mm:ss o mm:ss)</label>
                <input type="text" value={timeStr} onChange={e => setTimeStr(e.target.value)} placeholder="1:45:00" className={input} />
              </div>
            </>
          )}

          {type === 'triathlon' && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Distancia</label>
                  <select value={triathlonDistance} onChange={e => setTriathlonDistance(e.target.value)} className={input}>
                    {TRIATHLON_DISTANCES.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Fecha de la carrera</label>
                  <input type="date" value={raceDate} onChange={e => setRaceDate(e.target.value)} className={input} />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Tiempo objetivo (hh:mm:ss o mm:ss)</label>
                <input type="text" value={timeStr} onChange={e => setTimeStr(e.target.value)} placeholder="2:30:00" className={input} />
              </div>
            </>
          )}

          {type === 'hyrox' && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">División</label>
                  <select value={hyroxDivision} onChange={e => setHyroxDivision(e.target.value)} className={input}>
                    <option value="open">Open</option>
                    <option value="pro">Pro</option>
                    <option value="doubles">Doubles</option>
                    <option value="relay">Relay</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Fecha</label>
                  <input type="date" value={raceDate} onChange={e => setRaceDate(e.target.value)} className={input} />
                </div>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Tiempo objetivo</label>
                <input type="text" value={timeStr} onChange={e => setTimeStr(e.target.value)} placeholder="1:10:00" className={input} />
              </div>
            </>
          )}

          {type === 'weekly_km' && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Km por semana</label>
              <input type="number" value={weeklyKm} onChange={e => setWeeklyKm(e.target.value)} className={input} />
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-400 mb-1">Notas (opcional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)} className={input} />
          </div>

          <button
            onClick={handleSave}
            disabled={saving || !description}
            className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-bold"
          >
            {saving ? 'Guardando...' : 'Guardar objetivo'}
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-gray-600 text-sm">Cargando...</p>
      ) : goals.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500">Sin objetivos. Crea tu primer objetivo para empezar a planificar.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {goals.map(g => (
            <div key={g.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4 sm:p-5 flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-xs font-black text-red-400 uppercase">{g.type}</span>
                  {g.sport && <span className="text-xs text-gray-500">· {g.sport}</span>}
                  {g.target_race_date && (
                    <span className="text-xs text-gray-500">
                      · {new Date(g.target_race_date).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </span>
                  )}
                </div>
                <p className="font-semibold mt-1">{g.description}</p>
                <p className="text-sm text-red-400 font-bold mt-0.5">{renderGoal(g)}</p>
                {g.notes && <p className="text-xs text-gray-500 mt-1">{g.notes}</p>}
              </div>
              <button onClick={() => handleDelete(g.id)} className="text-gray-600 hover:text-red-400 text-sm ml-4">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const input = "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-base sm:text-sm text-gray-100 focus:outline-none focus:border-red-500"
