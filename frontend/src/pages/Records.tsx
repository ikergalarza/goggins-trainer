import { useEffect, useState } from 'react'
import api from '../api'
import { useAuth } from '../auth/AuthContext'

interface PRecord {
  id: number
  category: string
  value_seconds: number | null
  value_numeric: number | null
  unit: string | null
  date_achieved: string
  notes: string | null
}

const CATEGORIES = [
  { value: '5k', label: '5 km', unit: 'seconds' },
  { value: '10k', label: '10 km', unit: 'seconds' },
  { value: '21k', label: 'Media maratón (21k)', unit: 'seconds' },
  { value: '42k', label: 'Maratón (42k)', unit: 'seconds' },
  { value: '1mile', label: '1 milla', unit: 'seconds' },
  { value: 'vam_test', label: 'Test VAM (5 min)', unit: 'seconds' },
  { value: 'hyrox_full', label: 'Hyrox completo', unit: 'seconds' },
  { value: 'hyrox_run_only', label: 'Hyrox — solo running (8×1k)', unit: 'seconds' },
  { value: 'hyrox_roxzone', label: 'Hyrox — Roxzone', unit: 'seconds' },
  { value: 'squat_1rm', label: 'Sentadilla 1RM', unit: 'kg' },
  { value: 'deadlift_1rm', label: 'Peso muerto 1RM', unit: 'kg' },
  { value: 'bench_1rm', label: 'Press banca 1RM', unit: 'kg' },
  { value: 'wall_balls', label: 'Wall balls (reps/min)', unit: 'reps' },
]

function formatSeconds(total: number): string {
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  return `${m}:${s.toString().padStart(2, '0')}`
}

function parseTimeString(str: string): number | null {
  const parts = str.split(':').map(p => parseInt(p, 10))
  if (parts.some(isNaN)) return null
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 1) return parts[0]
  return null
}

export default function Records() {
  const { effectiveUserId } = useAuth()
  const [records, setRecords] = useState<PRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  // Form state
  const [category, setCategory] = useState(CATEGORIES[0].value)
  const [timeStr, setTimeStr] = useState('')
  const [numericVal, setNumericVal] = useState('')
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  const currentCat = CATEGORIES.find(c => c.value === category)!
  const isTime = currentCat.unit === 'seconds'

  const load = () => {
    if (effectiveUserId == null) return
    setLoading(true)
    api.get(`/api/records/${effectiveUserId}`)
      .then(r => setRecords(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [effectiveUserId])

  const handleSave = async () => {
    if (effectiveUserId == null) return
    setSaving(true)
    try {
      const payload: any = {
        category,
        unit: currentCat.unit,
        date_achieved: date,
        notes: notes || null,
      }
      if (isTime) {
        const seconds = parseTimeString(timeStr)
        if (seconds === null) {
          alert('Formato inválido. Usa mm:ss o hh:mm:ss')
          setSaving(false)
          return
        }
        payload.value_seconds = seconds
      } else {
        payload.value_numeric = parseFloat(numericVal)
      }
      await api.post(`/api/records/${effectiveUserId}`, payload)
      setTimeStr('')
      setNumericVal('')
      setNotes('')
      setShowForm(false)
      load()
    } catch (err: any) {
      alert(`Error: ${err?.response?.data?.detail || err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (effectiveUserId == null) return
    if (!confirm('¿Eliminar marca?')) return
    await api.delete(`/api/records/${effectiveUserId}/${id}`)
    load()
  }

  const renderValue = (r: PRecord) => {
    if (r.value_seconds != null) return formatSeconds(r.value_seconds)
    if (r.value_numeric != null) return `${r.value_numeric} ${r.unit || ''}`
    return '—'
  }

  const renderCategory = (cat: string) => CATEGORIES.find(c => c.value === cat)?.label || cat

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">🏆 Marcas</h1>
          <p className="text-gray-500 text-sm mt-1">{records.length} marcas registradas</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-bold"
        >
          {showForm ? 'Cancelar' : '+ Añadir marca'}
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Categoría</label>
            <select value={category} onChange={e => setCategory(e.target.value)} className={input}>
              {CATEGORIES.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          {isTime ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Tiempo (mm:ss o hh:mm:ss)</label>
              <input type="text" value={timeStr} onChange={e => setTimeStr(e.target.value)} placeholder="1:45:30" className={input} />
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Valor ({currentCat.unit})</label>
              <input type="number" step="0.1" value={numericVal} onChange={e => setNumericVal(e.target.value)} className={input} />
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-400 mb-1">Fecha</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)} className={input} />
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Notas (opcional)</label>
            <input type="text" value={notes} onChange={e => setNotes(e.target.value)} className={input} />
          </div>

          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-bold"
          >
            {saving ? 'Guardando...' : 'Guardar marca'}
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-gray-600 text-sm">Cargando...</p>
      ) : records.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500">Sin marcas registradas. Añade tu primera marca.</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {records.map(r => (
            <div key={r.id} className="flex items-center justify-between px-6 py-4">
              <div>
                <p className="font-semibold text-sm">{renderCategory(r.category)}</p>
                <p className="text-xs text-gray-500">
                  {new Date(r.date_achieved).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })}
                  {r.notes && ` · ${r.notes}`}
                </p>
              </div>
              <div className="flex items-center gap-4">
                <p className="font-black text-red-400 text-lg">{renderValue(r)}</p>
                <button onClick={() => handleDelete(r.id)} className="text-gray-600 hover:text-red-400 text-xs">✕</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const input = "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-red-500"
