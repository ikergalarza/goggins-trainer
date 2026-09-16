import { EXERCISES, exerciseMeta } from './catalog'
import { Pictogram } from './Pictogram'

// Ficha de un ejercicio: pictograma grande, qué es, cómo se hace y vídeo.
// Hoja desde abajo en móvil; centrada en escritorio. Se abre al tocar
// cualquier ejercicio de un WOD.
export default function ExerciseSheet({ slug, name, onClose }: { slug: string; name?: string | null; onClose: () => void }) {
  const meta = exerciseMeta(slug, name)
  const entry = EXERCISES[slug] || EXERCISES.other
  return (
    <div
      className="fixed inset-0 bg-black/70 z-[60] flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-800 rounded-t-2xl sm:rounded-xl p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] max-w-sm w-full space-y-4 max-h-[85dvh] overflow-y-auto overscroll-contain"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label={`Ficha de ${meta.label}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-lg font-black leading-tight">{meta.label}</h3>
            {entry.desc && <p className="text-sm text-gray-400 mt-1 leading-snug">{entry.desc}</p>}
          </div>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            className="shrink-0 -mt-1 -mr-1 min-h-11 min-w-11 flex items-center justify-center rounded-lg text-gray-500 hover:text-white active:bg-gray-800 text-2xl leading-none transition-colors"
          >
            ×
          </button>
        </div>

        <div className="flex justify-center">
          <div className="w-28 h-28 rounded-xl bg-gray-950 border border-gray-800 text-red-400 p-3">
            <Pictogram slug={slug} className="w-full h-full" />
          </div>
        </div>

        {entry.how && entry.how.length > 0 && (
          <div>
            <p className="text-[10px] font-black uppercase tracking-wider text-gray-500 mb-1.5">Cómo se hace</p>
            <ol className="space-y-1.5">
              {entry.how.map((h, i) => (
                <li key={i} className="text-sm text-gray-300 flex gap-2">
                  <span className="text-red-400 font-black shrink-0">{i + 1}.</span>
                  <span>{h}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        {meta.videoUrl && (
          <a
            href={meta.videoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 min-h-11 w-full bg-red-600 hover:bg-red-700 active:bg-red-800 text-white rounded-lg text-sm font-bold transition-colors"
          >
            ▶ Ver vídeo de técnica
          </a>
        )}
      </div>
    </div>
  )
}
