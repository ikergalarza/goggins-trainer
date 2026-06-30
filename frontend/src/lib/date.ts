// Helpers de fecha del plan de entrenamiento.
//
// Extraídos de Plan.tsx para poder testearlos de forma aislada (lógica pura,
// sin React ni DOM). El calendario depende críticamente de que las fechas
// 'YYYY-MM-DD' del backend se interpreten como fecha LOCAL, no UTC.

// CAUSA RAÍZ DEL BUG DE CALENDARIO:
// El backend envía fechas como string 'YYYY-MM-DD'. Al hacer new Date('2026-06-30')
// el motor JS lo interpreta como medianoche UTC, no local. En zonas horarias con
// offset negativo (o en general distintas de UTC) eso "salta" al día anterior/siguiente
// al convertir a hora local, y el workout aparecía en la casilla equivocada.
// Solución: parsear siempre como fecha LOCAL construyendo new Date(y, m-1, d).
export function parseLocalDate(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split('-').map(n => parseInt(n, 10))
  return new Date(y, m - 1, d) // medianoche LOCAL, sin desfase de zona horaria
}

// formatDayKey debe producir la clave 'YYYY-MM-DD' a partir de los componentes
// LOCALES de la fecha. Antes usaba toISOString(), que convierte a UTC y volvía a
// introducir el desfase de día tras arrastrar un entreno.
export function formatDayKey(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// Devuelve el lunes (00:00 local) de la semana a la que pertenece `d`.
export function startOfWeek(d: Date): Date {
  const out = new Date(d)
  const day = (out.getDay() + 6) % 7 // 0 = lunes
  out.setDate(out.getDate() - day)
  out.setHours(0, 0, 0, 0)
  return out
}
