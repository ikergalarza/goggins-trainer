// Metadatos de presentación de los entrenos: disciplina, color e iconos.
// El backend NO almacena `discipline` (solo `type`), así que la derivamos aquí
// a partir del `type` para colorear y agrupar de forma consistente.

export type Discipline = 'swim' | 'bike' | 'run' | 'brick' | 'strength' | 'rest'

// Etiquetas legibles por tipo de entreno (es-ES).
export const TYPE_LABELS: Record<string, string> = {
  // Carrera
  easy_run: 'Suave',
  tempo: 'Tempo',
  intervals: 'Series',
  long_run: 'Tirada larga',
  recovery: 'Recuperación',
  fartlek: 'Fartlek',
  hill_repeats: 'Cuestas',
  cross_training: 'Cross-training',
  // Hyrox / fuerza
  hyrox_sim: 'Sim Hyrox',
  hyrox_stations: 'Estaciones',
  strength_upper: 'Fuerza tren sup',
  strength_lower: 'Fuerza tren inf',
  strength_full: 'Fuerza full body',
  // Triatlón / natación / ciclismo
  swim: 'Natación',
  swim_technique: 'Técnica natación',
  open_water: 'Aguas abiertas',
  bike: 'Ciclismo',
  brick: 'Brick',
  transition: 'Transiciones',
  // Otros
  rest: 'Descanso',
}

// Mapa type -> disciplina, para colorear por deporte (no por intensidad).
const TYPE_TO_DISCIPLINE: Record<string, Discipline> = {
  // Natación
  swim: 'swim',
  swim_technique: 'swim',
  open_water: 'swim',
  // Ciclismo
  bike: 'bike',
  // Carrera
  easy_run: 'run',
  tempo: 'run',
  intervals: 'run',
  long_run: 'run',
  recovery: 'run',
  fartlek: 'run',
  hill_repeats: 'run',
  cross_training: 'run',
  // Brick / transiciones (multidisciplina encadenada)
  brick: 'brick',
  transition: 'brick',
  // Fuerza / Hyrox
  strength_upper: 'strength',
  strength_lower: 'strength',
  strength_full: 'strength',
  hyrox_sim: 'strength',
  hyrox_stations: 'strength',
  // Descanso
  rest: 'rest',
}

export function disciplineOf(type: string): Discipline {
  return TYPE_TO_DISCIPLINE[type] || 'run'
}

// Iconos por disciplina.
export const DISCIPLINE_ICONS: Record<Discipline, string> = {
  swim: '🏊',
  bike: '🚴',
  run: '🏃',
  brick: '🔁',
  strength: '🏋️',
  rest: '😴',
}

export const DISCIPLINE_LABELS: Record<Discipline, string> = {
  swim: 'Natación',
  bike: 'Ciclismo',
  run: 'Carrera',
  brick: 'Brick',
  strength: 'Fuerza',
  rest: 'Descanso',
}

// Paleta por disciplina. Mantiene el tema oscuro existente (variantes 900/40)
// pero con un color dominante por deporte:
//   natación=azul · bici=verde · carrera=naranja · brick=morado · fuerza=gris · descanso=neutro
export interface DisciplineTheme {
  // Clases para la tarjeta compacta del calendario (fondo + borde + texto).
  card: string
  // Color del borde izquierdo (acento de la tarjeta).
  accentBorder: string
  // Texto de acento (para iconos / títulos en el modal).
  accentText: string
  // Punto/badge sólido para leyenda.
  dot: string
  // Fondo tenue para chips de la disciplina.
  chipBg: string
}

export const DISCIPLINE_THEME: Record<Discipline, DisciplineTheme> = {
  swim: {
    card: 'bg-blue-950/40 border-blue-800/50 text-blue-200',
    accentBorder: 'border-l-blue-500',
    accentText: 'text-blue-400',
    dot: 'bg-blue-500',
    chipBg: 'bg-blue-500/15 text-blue-300',
  },
  bike: {
    card: 'bg-green-950/40 border-green-800/50 text-green-200',
    accentBorder: 'border-l-green-500',
    accentText: 'text-green-400',
    dot: 'bg-green-500',
    chipBg: 'bg-green-500/15 text-green-300',
  },
  run: {
    card: 'bg-orange-950/40 border-orange-800/50 text-orange-200',
    accentBorder: 'border-l-orange-500',
    accentText: 'text-orange-400',
    dot: 'bg-orange-500',
    chipBg: 'bg-orange-500/15 text-orange-300',
  },
  brick: {
    card: 'bg-purple-950/40 border-purple-800/50 text-purple-200',
    accentBorder: 'border-l-purple-500',
    accentText: 'text-purple-400',
    dot: 'bg-purple-500',
    chipBg: 'bg-purple-500/15 text-purple-300',
  },
  strength: {
    card: 'bg-gray-800/50 border-gray-600/50 text-gray-200',
    accentBorder: 'border-l-gray-400',
    accentText: 'text-gray-300',
    dot: 'bg-gray-400',
    chipBg: 'bg-gray-500/20 text-gray-300',
  },
  rest: {
    card: 'bg-gray-900/50 border-gray-800/60 text-gray-500',
    accentBorder: 'border-l-gray-700',
    accentText: 'text-gray-400',
    dot: 'bg-gray-600',
    chipBg: 'bg-gray-700/30 text-gray-400',
  },
}

export function themeOf(type: string): DisciplineTheme {
  return DISCIPLINE_THEME[disciplineOf(type)]
}

// --- Parser de series / intervalos ---------------------------------------
// Las instrucciones de Claude suelen describir series como texto. Intentamos
// extraer líneas tipo "6x400m @ Z4, rec 90s" o "4 x 800 m" para mostrarlas
// como bloques legibles en lugar de un párrafo apelmazado.

export interface IntervalSet {
  raw: string        // texto original de la serie
  reps?: number      // nº de repeticiones (ej. 6)
  distance?: string  // distancia/duración por rep (ej. "400m")
  zone?: string      // zona/intensidad (ej. "Z4")
  rest?: string      // recuperación (ej. "rec 90s")
}

// Unidad de distancia/duración admitida (más específica primero para no dejar
// "min" reducido a "m"). El orden importa en la alternancia de regex.
const UNIT = "(?:km|metros?|min|seg|m|s|''|')"

// Detecta patrones NxDIST tipo "6x400m", "4 x 800 m", "10×1km".
// La unidad es opcional, pero si falta NO se capturan letras a continuación
// (evita absorber la "Z" de "200 Z5"): tras el número exigimos fin/espacio.
const REP_RE = new RegExp(
  `(\\d+)\\s*[x×]\\s*([\\d.,]+\\s*${UNIT}|[\\d.,]+(?=\\s|$|[,.;]))`,
  'i',
)

// Recuperación: "rec 90s", "r 1'", "descanso 2min", "rec: 2'". El keyword es
// obligatorio y el número debe ir pegado (hasta 4 chars de separación) para no
// capturar números lejanos del resto de la frase.
const REST_RE = new RegExp(
  `\\b(?:recuperaci[oó]n|recup|rec|descanso|r)\\b\\s*[:=]?\\s*([\\d.,]+\\s*${UNIT}?)`,
  'i',
)

export function parseIntervals(instructions: string | null | undefined): IntervalSet[] {
  if (!instructions) return []
  const sets: IntervalSet[] = []
  // Partimos por saltos de línea y por separadores comunes (; y •) para captar
  // varias series en una misma instrucción.
  const fragments = instructions
    .split(/\n|•|·|;|\s\|\s/)
    .map(f => f.trim())
    .filter(Boolean)

  for (const frag of fragments) {
    const m = frag.match(REP_RE)
    if (!m) continue
    const reps = parseInt(m[1], 10)
    const distance = m[2].replace(/\s+/g, '').replace(',', '.')

    // Zona: Z1..Z5.
    const zoneMatch = frag.match(/\bZ\s?([1-5])\b/i)
    const zone = zoneMatch ? `Z${zoneMatch[1]}` : undefined

    const restMatch = frag.match(REST_RE)
    const rest = restMatch ? restMatch[1].replace(/\s+/g, '') : undefined

    sets.push({ raw: frag, reps, distance, zone, rest })
  }
  return sets
}

// Formatea un set como una línea compacta: "6×400m @ Z4 · rec 90s".
export function formatIntervalSet(s: IntervalSet): string {
  let out = `${s.reps}×${s.distance}`
  if (s.zone) out += ` @ ${s.zone}`
  if (s.rest) out += ` · rec ${s.rest}`
  return out
}

export const STATUS_LABELS: Record<string, string> = {
  planned: 'Planificado',
  completed: 'Completado',
  skipped: 'Saltado',
}
