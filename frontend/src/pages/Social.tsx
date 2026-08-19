import { useEffect, useState } from 'react'
import api from '../api'

// Ranking del grupo por disciplina + comentario vacilón de Goggins.
// Solo llegan agregados (km/min/sesiones) y nombre de pila: nada personal.

interface Row {
  user_id: number
  name: string
  km: number
  min: number
  sessions: number
  rank: number
  is_me: boolean
}
interface Board {
  weeks: number
  since: string
  until: string
  members: number
  disciplines: Record<string, Row[]>
  roast: { text: string; created_at: string | null; cached: boolean } | null
}

const DISCIPLINES: { key: string; label: string; icon: string; color: string }[] = [
  { key: 'run', label: 'Carrera', icon: '🏃', color: 'text-orange-400' },
  { key: 'bike', label: 'Bici', icon: '🚴', color: 'text-green-400' },
  { key: 'swim', label: 'Natación', icon: '🏊', color: 'text-blue-400' },
  { key: 'strength', label: 'Fuerza', icon: '🏋️', color: 'text-gray-300' },
]

const MEDAL = ['🥇', '🥈', '🥉']

function fmtMin(min: number): string {
  if (min < 60) return `${min}'`
  const h = Math.floor(min / 60), m = min % 60
  return m ? `${h}h ${m}'` : `${h}h`
}

export default function Social() {
  const [weeks, setWeeks] = useState<1 | 4>(1)
  const [disc, setDisc] = useState('run')
  const [board, setBoard] = useState<Board | null>(null)
  const [loading, setLoading] = useState(true)
  const [roasting, setRoasting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = (w: 1 | 4) => {
    setLoading(true)
    setError(null)
    api.get(`/api/social/leaderboard?weeks=${w}`)
      .then(r => setBoard(r.data))
      .catch(() => setError('No se pudo cargar el ranking.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load(weeks) }, [weeks])

  const regenerate = async () => {
    setRoasting(true)
    setError(null)
    try {
      const r = await api.post(`/api/social/roast?weeks=${weeks}`)
      setBoard(b => (b ? { ...b, roast: r.data.roast } : b))
    } catch (e) {
      const err = e as { response?: { status?: number; data?: { detail?: string } } }
      const detail = err?.response?.data?.detail
      // 429 = límite por usuario; 503 = IA no disponible. Ambos traen mensaje.
      setError(typeof detail === 'string' ? detail : 'Goggins no está de humor ahora mismo. Prueba en un rato.')
    } finally {
      setRoasting(false)
    }
  }

  const rows = board?.disciplines?.[disc] ?? []
  const anyActivity = rows.some(r => r.sessions > 0)
  const meta = DISCIPLINES.find(d => d.key === disc)!

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl sm:text-3xl font-black tracking-tight">🏆 Social</h1>
        <p className="text-gray-500 text-sm mt-1">Ranking del grupo. Solo km, tiempo y sesiones: nada más.</p>
      </div>

      {/* Periodo */}
      <div className="flex gap-2">
        {([1, 4] as const).map(w => (
          <button
            key={w}
            onClick={() => setWeeks(w)}
            className={`flex-1 min-h-11 rounded-lg text-sm font-bold transition-colors ${
              weeks === w ? 'bg-red-600 text-white' : 'bg-gray-900 border border-gray-800 text-gray-400 hover:text-white active:bg-gray-800'
            }`}
          >
            {w === 1 ? 'Esta semana' : 'Últimas 4 semanas'}
          </button>
        ))}
      </div>

      {/* Goggins */}
      <div className="bg-gradient-to-br from-gray-900 to-gray-900/60 border border-red-900/40 rounded-xl p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <span className="text-3xl leading-none shrink-0">💀</span>
            <div className="min-w-0">
              <p className="text-xs font-black uppercase tracking-wider text-red-400 mb-1">Goggins opina</p>
              {loading && !board ? (
                <p className="text-sm text-gray-500">Cargando…</p>
              ) : board?.roast?.text ? (
                <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{board.roast.text}</p>
              ) : (
                <p className="text-sm text-gray-500">Goggins no tiene nada que decir ahora mismo (o la IA no está disponible). Prueba «Otro pique» más tarde.</p>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={regenerate}
          disabled={roasting || loading}
          className="mt-3 w-full sm:w-auto min-h-11 bg-gray-800 hover:bg-gray-700 active:bg-gray-600 disabled:opacity-50 text-gray-200 px-4 rounded-lg text-sm font-bold transition-colors"
        >
          {roasting ? '⏳ Pensando…' : '🔥 Otro pique'}
        </button>
      </div>

      {/* Disciplinas */}
      <div className="grid grid-cols-4 gap-2">
        {DISCIPLINES.map(d => (
          <button
            key={d.key}
            onClick={() => setDisc(d.key)}
            aria-pressed={disc === d.key}
            className={`min-h-11 rounded-lg text-xs font-bold flex flex-col items-center justify-center gap-0.5 transition-colors ${
              disc === d.key ? 'bg-gray-800 text-white border border-gray-600' : 'bg-gray-900 border border-gray-800 text-gray-500 hover:text-gray-300 active:bg-gray-800'
            }`}
          >
            <span className="text-base leading-none">{d.icon}</span>
            <span>{d.label}</span>
          </button>
        ))}
      </div>

      {/* Ranking */}
      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && !board ? (
        <p className="text-sm text-gray-600">Cargando ranking…</p>
      ) : !anyActivity ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500 text-sm">Nadie ha hecho {meta.label.toLowerCase()} {weeks === 1 ? 'esta semana' : 'en 4 semanas'}. Sé el primero.</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {rows.map(r => (
            <div
              key={r.user_id}
              className={`flex items-center gap-3 px-4 py-3 ${r.is_me ? 'bg-red-950/30' : ''}`}
            >
              <span className="w-8 text-center text-lg shrink-0">
                {r.sessions > 0 && r.rank <= 3 ? MEDAL[r.rank - 1] : <span className="text-sm font-bold text-gray-600">{r.rank}</span>}
              </span>
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-semibold truncate ${r.is_me ? 'text-red-300' : ''}`}>
                  {r.name}{r.is_me && <span className="text-xs text-gray-500 font-normal"> · tú</span>}
                </p>
                <p className="text-xs text-gray-500">
                  {r.sessions} {r.sessions === 1 ? 'sesión' : 'sesiones'}{r.min > 0 && ` · ${fmtMin(r.min)}`}
                </p>
              </div>
              <p className={`font-black text-lg shrink-0 ${r.sessions > 0 ? meta.color : 'text-gray-700'}`}>
                {disc === 'strength' ? fmtMin(r.min) : `${r.km.toFixed(1)} km`}
              </p>
            </div>
          ))}
        </div>
      )}

      {board && (
        <p className="text-xs text-gray-600">
          {board.members} atletas · del {new Date(board.since).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })} al {new Date(board.until).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })}. Los datos vienen de Strava; sincroniza para actualizar.
        </p>
      )}
    </div>
  )
}
