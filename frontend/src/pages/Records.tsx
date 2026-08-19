import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth/AuthContext'
import DeleteButton from '../components/DeleteButton'

interface PRecord {
  id: number
  category: string
  value_seconds: number | null
  value_numeric: number | null
  unit: string | null
  date_achieved: string
  notes: string | null
}

// Mantener en sintonía con CATEGORY_LABELS en backend/app/services/record_labels.py,
// que es lo que lee la IA para saber de qué prueba habla cada marca.
// `label` se usa en el desplegable, donde conviene ver las distancias para
// elegir bien. `short` es lo que se lista, acompañado de `group`, para que en
// una pantalla estrecha quepa en una línea sin perder la disciplina.
const CATEGORIES = [
  { value: '5k', label: '5 km', short: '5 km', unit: 'seconds', group: 'Carrera' },
  { value: '10k', label: '10 km', short: '10 km', unit: 'seconds', group: 'Carrera' },
  { value: '21k', label: 'Media maratón (21k)', short: 'Media maratón', unit: 'seconds', group: 'Carrera' },
  { value: '42k', label: 'Maratón (42k)', short: 'Maratón', unit: 'seconds', group: 'Carrera' },
  { value: '1mile', label: '1 milla', short: '1 milla', unit: 'seconds', group: 'Carrera' },
  { value: 'vam_test', label: 'Test VAM (5 min)', short: 'Test VAM', unit: 'seconds', group: 'Carrera' },
  { value: 'tri_sprint', label: 'Sprint (750m · 20k · 5k)', short: 'Sprint', unit: 'seconds', group: 'Triatlón' },
  { value: 'tri_olympic', label: 'Olímpico (1.5k · 40k · 10k)', short: 'Olímpico', unit: 'seconds', group: 'Triatlón' },
  { value: 'tri_half', label: 'Medio · 70.3 (1.9k · 90k · 21k)', short: 'Medio · 70.3', unit: 'seconds', group: 'Triatlón' },
  { value: 'tri_ironman', label: 'Completo · Ironman (3.8k · 180k · 42k)', short: 'Ironman', unit: 'seconds', group: 'Triatlón' },
  { value: 'swim_400m', label: '400 m', short: '400 m', unit: 'seconds', group: 'Natación' },
  { value: 'swim_1500m', label: '1500 m', short: '1500 m', unit: 'seconds', group: 'Natación' },
  { value: 'bike_40k_tt', label: '40 km contrarreloj', short: '40 km CRI', unit: 'seconds', group: 'Ciclismo' },
  { value: 'bike_ftp', label: 'FTP', short: 'FTP', unit: 'watts', group: 'Ciclismo' },
  { value: 'hyrox_full', label: 'Hyrox completo', short: 'Completo', unit: 'seconds', group: 'Hyrox' },
  { value: 'hyrox_run_only', label: 'Solo running (8×1k)', short: 'Solo running', unit: 'seconds', group: 'Hyrox' },
  { value: 'hyrox_roxzone', label: 'Roxzone', short: 'Roxzone', unit: 'seconds', group: 'Hyrox' },
  { value: 'squat_1rm', label: 'Sentadilla 1RM', short: 'Sentadilla 1RM', unit: 'kg', group: 'Fuerza' },
  { value: 'deadlift_1rm', label: 'Peso muerto 1RM', short: 'Peso muerto 1RM', unit: 'kg', group: 'Fuerza' },
  { value: 'bench_1rm', label: 'Press banca 1RM', short: 'Press banca 1RM', unit: 'kg', group: 'Fuerza' },
  { value: 'wall_balls', label: 'Wall balls (reps/min)', short: 'Wall balls', unit: 'reps', group: 'Fuerza' },
]

// Con 21 categorías el desplegable plano se hace incómodo en móvil; agrupadas,
// el selector nativo de iOS y Android muestra los encabezados y se navega mucho mejor.
const GROUPS = [...new Set(CATEGORIES.map(c => c.group))]

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
  const findCat = (cat: string) => CATEGORIES.find(c => c.value === cat)

  return (
    <div className="space-y-6">
      {/* Vuelta a Perfil, que es desde donde se llega a esta página */}
      <Link
        to="/profile"
        className="inline-flex items-center min-h-11 text-sm text-gray-400 hover:text-white active:text-white transition-colors"
      >
        ← Perfil
      </Link>

      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold">🏆 Marcas</h1>
          <p className="text-gray-500 text-sm mt-1">{records.length} marcas registradas</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="shrink-0 min-h-11 bg-red-600 hover:bg-red-700 active:bg-red-800 text-white px-4 rounded-lg text-sm font-bold transition-colors"
        >
          {showForm ? 'Cancelar' : '+ Añadir'}
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Categoría</label>
            <select value={category} onChange={e => setCategory(e.target.value)} className={input}>
              {GROUPS.map(g => (
                <optgroup key={g} label={g}>
                  {CATEGORIES.filter(c => c.group === g).map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </optgroup>
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
            className="w-full sm:w-auto min-h-11 bg-red-600 hover:bg-red-700 active:bg-red-800 disabled:opacity-50 text-white px-5 rounded-lg text-sm font-bold transition-colors"
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
            <div key={r.id} className="flex items-center justify-between gap-3 px-4 sm:px-6 py-3 sm:py-4">
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-black uppercase tracking-wider text-red-400/70">
                  {findCat(r.category)?.group || 'Otros'}
                </p>
                <p className="font-semibold text-sm leading-tight">
                  {findCat(r.category)?.short || r.category}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {new Date(r.date_achieved).toLocaleDateString('es-ES', { day: 'numeric', month: 'short', year: 'numeric' })}
                  {r.notes && ` · ${r.notes}`}
                </p>
              </div>
              <div className="flex items-center gap-2 sm:gap-3 shrink-0">
                <p className="font-black text-red-400 text-lg">{renderValue(r)}</p>
                <DeleteButton
                  onDelete={() => handleDelete(r.id)}
                  label={`Eliminar marca de ${renderCategory(r.category)}`}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// text-base en móvil (16px): por debajo de eso iOS Safari hace zoom a la página
// al enfocar el campo. min-h-11 mantiene el objetivo táctil en 44px.
const input = "w-full min-h-11 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-base sm:text-sm text-gray-100 focus:outline-none focus:border-red-500"
