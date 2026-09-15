import { exerciseMeta } from './exercises/catalog'
import { Pictogram } from './exercises/Pictogram'

// Vista visual de un WOD estructurado (Workout.structure): objetivo,
// calentamiento paso a paso, bloques con pictograma + dosis + pesos,
// transiciones, enfriamiento y notas. El backend sanea el JSON
// (wod_structure.sanitize), así que aquí se pinta defensivo pero simple.

export interface WodItem {
  exercise: string
  name?: string
  reps?: number
  distance_m?: number
  duration_s?: number
  weight_kg?: number
  pace?: string
  target_m?: number
  notes?: string
}
export interface WodBlock {
  title?: string
  format?: string
  rounds?: number
  rest_s?: number
  duration_min?: number
  interval_s?: number
  items: WodItem[]
}
export interface WodStructure {
  objective?: string
  warmup?: { duration_min?: number; steps?: string[] }
  blocks?: WodBlock[]
  cooldown?: string[]
  notes?: string
}

function fmtSecs(s: number): string {
  if (s < 60) return `${s}''`
  const m = Math.floor(s / 60)
  const r = s % 60
  return r ? `${m}'${r}''` : `${m}'`
}

function fmtDist(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(m % 1000 === 0 ? 0 : 1)} km` : `${m} m`
}

function blockBadge(b: WodBlock): string {
  const f = b.format || 'rounds'
  if (f === 'rounds') return b.rounds ? `${b.rounds} RONDAS` : 'RONDAS'
  if (f === 'amrap') return `AMRAP ${b.duration_min ? `${b.duration_min}'` : ''}`.trim()
  if (f === 'emom') return `EMOM${b.interval_s ? ` ${fmtSecs(b.interval_s)}` : ''}${b.duration_min ? ` × ${b.duration_min}'` : ''}`
  if (f === 'fortime') return 'FOR TIME'
  if (f === 'sets') return 'SERIES'
  return 'CIRCUITO'
}

function doseChips(it: WodItem): string[] {
  const chips: string[] = []
  if (it.reps != null) chips.push(`${it.reps} reps`)
  if (it.distance_m != null) chips.push(fmtDist(it.distance_m))
  if (it.duration_s != null) chips.push(fmtSecs(it.duration_s))
  if (it.pace) chips.push(it.pace)
  if (it.target_m != null) chips.push(`diana ${it.target_m} m`)
  return chips
}

export default function WodView({ structure }: { structure: WodStructure }) {
  const blocks = structure.blocks || []
  return (
    <div className="space-y-4">
      {structure.objective && (
        <div className="bg-red-900/20 border border-red-900/40 rounded-lg p-3">
          <p className="text-[10px] font-black uppercase tracking-wider text-red-400 mb-0.5">🎯 Objetivo de hoy</p>
          <p className="text-sm text-gray-200 leading-snug">{structure.objective}</p>
        </div>
      )}

      {structure.warmup && (structure.warmup.steps?.length || structure.warmup.duration_min) && (
        <div className="bg-gray-800/40 border border-gray-800 rounded-lg p-3">
          <p className="text-[10px] font-black uppercase tracking-wider text-yellow-500/90 mb-1.5">
            🔥 Calentamiento{structure.warmup.duration_min ? ` · ${structure.warmup.duration_min}'` : ''}
          </p>
          <ul className="space-y-1">
            {(structure.warmup.steps || []).map((s, i) => (
              <li key={i} className="text-sm text-gray-300 flex gap-2">
                <span className="text-gray-600 shrink-0">{i + 1}.</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {blocks.map((b, bi) => (
        <div key={bi} className="bg-gray-800/40 border border-gray-700/60 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between gap-2 px-3 py-2 bg-gray-800/70">
            <p className="text-sm font-bold text-gray-200 truncate">{b.title || `Bloque ${bi + 1}`}</p>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="text-[10px] font-black tracking-wider bg-red-600/90 text-white px-2 py-0.5 rounded">
                {blockBadge(b)}
              </span>
              {b.rest_s != null && b.rest_s > 0 && (
                <span className="text-[10px] font-bold text-gray-400 bg-gray-700/70 px-2 py-0.5 rounded">
                  rec {fmtSecs(b.rest_s)}
                </span>
              )}
            </div>
          </div>
          <div className="px-3 py-1">
            {b.items.map((it, ii) => {
              const meta = exerciseMeta(it.exercise, it.name)
              const chips = doseChips(it)
              return (
                <div key={ii}>
                  {ii > 0 && (
                    <div className="flex items-center gap-2 pl-5 py-0.5" aria-hidden="true">
                      <span className="text-gray-700 text-xs leading-none">↓</span>
                      <span className="text-[9px] uppercase tracking-wider text-gray-700">sin pausa</span>
                    </div>
                  )}
                  <div className="flex items-center gap-3 py-1.5">
                    <div className="shrink-0 w-11 h-11 rounded-lg bg-gray-900 border border-gray-800 text-red-400 p-1">
                      <Pictogram slug={it.exercise} className="w-full h-full" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-gray-100 leading-tight">
                        {meta.label}
                        {it.weight_kg != null && (
                          <span className="ml-1.5 text-xs font-black text-orange-400">{it.weight_kg} kg</span>
                        )}
                      </p>
                      <p className="text-xs text-gray-500">
                        {chips.join(' · ')}
                        {it.notes && <span className="text-gray-600"> · {it.notes}</span>}
                      </p>
                    </div>
                    {meta.videoUrl && (
                      <a
                        href={meta.videoUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Ver técnica de ${meta.label} en vídeo`}
                        className="shrink-0 w-11 h-11 flex items-center justify-center rounded-lg text-gray-600 hover:text-red-400 active:text-red-300 transition-colors"
                      >
                        <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor" aria-hidden="true">
                          <path d="M8 5.14v13.72L19 12 8 5.14z" />
                        </svg>
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}

      {structure.cooldown && structure.cooldown.length > 0 && (
        <div className="bg-gray-800/40 border border-gray-800 rounded-lg p-3">
          <p className="text-[10px] font-black uppercase tracking-wider text-teal-400/90 mb-1.5">🧊 Vuelta a la calma</p>
          <ul className="space-y-1">
            {structure.cooldown.map((s, i) => (
              <li key={i} className="text-sm text-gray-300 flex gap-2">
                <span className="text-gray-600 shrink-0">·</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {structure.notes && (
        <p className="text-xs text-gray-400 bg-gray-800/30 border border-gray-800/60 rounded-lg p-3">
          💡 {structure.notes}
        </p>
      )}
    </div>
  )
}
