import { disciplineOf, themeOf, TYPE_LABELS, DISCIPLINE_ICONS } from './workoutMeta'

interface WorkoutCardWorkout {
  id: number
  type: string
  status: string
  planned_distance_km: number | null
  planned_duration_min: number | null
  planned_heart_rate_zone: string | null
}

interface WorkoutCardProps {
  workout: WorkoutCardWorkout
  isDragging?: boolean
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
}

// Tarjeta compacta del calendario. Código de color por disciplina, icono,
// y jerarquía clara: título (tipo) arriba, métricas debajo. El estado se
// refleja con un acento de color y un check.
export default function WorkoutCard({
  workout: w,
  isDragging = false,
  onClick,
  onDragStart,
  onDragEnd,
}: WorkoutCardProps) {
  const theme = themeOf(w.type)
  const discipline = disciplineOf(w.type)
  const icon = DISCIPLINE_ICONS[discipline]
  const completed = w.status === 'completed'
  const skipped = w.status === 'skipped'

  // Métrica principal: distancia si existe, si no duración.
  const metric = w.planned_distance_km
    ? `${w.planned_distance_km} km`
    : w.planned_duration_min
      ? `${w.planned_duration_min}'`
      : null

  return (
    <button
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      title={TYPE_LABELS[w.type] || w.type}
      className={[
        'group block w-full text-left rounded-md border border-l-[3px] pl-1.5 pr-1 py-1',
        'cursor-grab active:cursor-grabbing transition-all',
        'hover:brightness-125',
        theme.card,
        theme.accentBorder,
        completed ? 'ring-1 ring-green-500/60' : '',
        skipped ? 'opacity-50 line-through decoration-1' : '',
        isDragging ? 'opacity-40' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-1 min-w-0">
        <span className="text-[11px] leading-none shrink-0">{icon}</span>
        <span className="font-bold text-[10px] leading-tight truncate flex-1">
          {TYPE_LABELS[w.type] || w.type}
        </span>
        {completed && <span className="text-green-400 text-[9px] shrink-0">✓</span>}
      </div>
      {(metric || w.planned_heart_rate_zone) && (
        <div className="flex items-center gap-1 mt-0.5 text-[9px] opacity-80">
          {metric && <span className="font-semibold">{metric}</span>}
          {metric && w.planned_heart_rate_zone && <span className="opacity-50">·</span>}
          {w.planned_heart_rate_zone && (
            <span className="opacity-90">{w.planned_heart_rate_zone}</span>
          )}
        </div>
      )}
    </button>
  )
}
