// Catálogo de ejercicios: nombre es-ES, búsqueda de vídeo de técnica y
// pictograma animado propio (2 fotogramas SVG, sin GIFs de terceros).
// Mantener slugs en sintonía con backend/app/services/wod_structure.py (EXERCISES).

interface Meta { name: string; pict: string; query: string }

export const EXERCISES: Record<string, Meta> = {
  run: { name: 'Carrera', pict: 'run', query: 'hyrox running pace technique' },
  ski_erg: { name: 'SkiErg', pict: 'ski_erg', query: 'hyrox skierg technique' },
  sled_push: { name: 'Sled Push', pict: 'sled_push', query: 'hyrox sled push technique' },
  sled_pull: { name: 'Sled Pull', pict: 'sled_pull', query: 'hyrox sled pull technique' },
  burpee_broad_jump: { name: 'Burpee Broad Jump', pict: 'burpee_broad_jump', query: 'hyrox burpee broad jump technique' },
  row: { name: 'Remo', pict: 'row', query: 'hyrox rowing 1000m technique' },
  farmers_carry: { name: 'Farmers Carry', pict: 'farmers_carry', query: 'hyrox farmers carry technique' },
  sandbag_lunges: { name: 'Sandbag Lunges', pict: 'sandbag_lunges', query: 'hyrox sandbag lunges technique' },
  wall_balls: { name: 'Wall Balls', pict: 'wall_balls', query: 'hyrox wall balls technique' },
  burpee: { name: 'Burpees', pict: 'burpee', query: 'burpee technique' },
  squat: { name: 'Sentadilla', pict: 'squat', query: 'air squat technique' },
  front_squat: { name: 'Sentadilla frontal', pict: 'squat', query: 'front squat technique' },
  thruster: { name: 'Thruster', pict: 'thruster', query: 'thruster technique' },
  deadlift: { name: 'Peso muerto', pict: 'deadlift', query: 'deadlift technique' },
  kb_swing: { name: 'KB Swing', pict: 'kb_swing', query: 'kettlebell swing technique' },
  box_jump: { name: 'Box Jump', pict: 'box_jump', query: 'box jump technique' },
  press: { name: 'Press hombro', pict: 'press', query: 'overhead press technique' },
  pull_up: { name: 'Dominadas', pict: 'pull_up', query: 'pull up technique' },
  plank: { name: 'Plancha', pict: 'plank', query: 'plank technique' },
  carry: { name: 'Acarreo', pict: 'farmers_carry', query: 'loaded carry technique' },
  bike_erg: { name: 'BikeErg', pict: 'bike_erg', query: 'bike erg technique' },
  mobility: { name: 'Movilidad', pict: 'mobility', query: 'movilidad para hyrox' },
  other: { name: 'Ejercicio', pict: 'other', query: '' },
}

export function exerciseMeta(slug: string, name?: string | null): { label: string; pict: string; videoUrl: string | null } {
  const m = EXERCISES[slug] || EXERCISES.other
  const label = slug === 'other' && name ? name : m.name
  const q = slug === 'other' && name ? `${name} technique` : m.query
  return {
    label,
    pict: m.pict,
    videoUrl: q ? `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` : null,
  }
}

