// Qué plan se genera: UNO solo está en vigor (combinado o individual).
//
// El backend dice qué plan hay (`/api/plans/{user}/current`: kind + objetivos).
// Aquí se decide qué opciones ofrecer al generar y cuál va preseleccionada.
// `COMBINED` es el id centinela del plan que encadena todas las carreras.

export const COMBINED = -1

export interface PlanGoal {
  id: number
  description: string
  target_race_date?: string | null
}

export interface PlanInfo {
  kind: 'combined' | 'single' | 'none'
  goals: PlanGoal[]
}

export interface PlanOption {
  id: number
  label: string
  // Fecha de la carrera o nº de carreras (texto secundario del botón).
  sub: string
  // Es el plan que está en vigor ahora mismo.
  inForce: boolean
}

function datedCount(goals: PlanGoal[]): number {
  return goals.filter(g => g.target_race_date).length
}

function shortDate(iso: string): string {
  // 'YYYY-MM-DD' → '07 feb' sin pasar por Date (evita desfases de zona horaria)
  const [, m, d] = iso.split('-').map(Number)
  const meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
  return `${String(d).padStart(2, '0')} ${meses[m - 1]}`
}

// Opciones al elegir qué plan generar. Con un solo objetivo no hay nada que elegir.
export function planOptions(activeGoals: PlanGoal[], plan: PlanInfo | null): PlanOption[] {
  if (activeGoals.length < 2) return []
  const options: PlanOption[] = []
  const dated = datedCount(activeGoals)
  if (dated >= 2) {
    options.push({
      id: COMBINED,
      label: 'Combinado',
      sub: `${dated} carreras`,
      inForce: plan?.kind === 'combined',
    })
  }
  for (const g of activeGoals) {
    options.push({
      id: g.id,
      label: `Solo ${g.description}`,
      sub: g.target_race_date ? shortDate(g.target_race_date) : '',
      inForce: plan?.kind === 'single' && plan.goals[0]?.id === g.id,
    })
  }
  return options
}

// Plan preseleccionado al abrir la pantalla: el que está en vigor; sin plan, el
// combinado si hay 2+ carreras con fecha (lo habitual), si no el primer objetivo.
export function modeFor(plan: PlanInfo | null, activeGoals: PlanGoal[]): number | null {
  if (activeGoals.length === 0) return null
  const canCombine = datedCount(activeGoals) >= 2
  if (plan?.kind === 'combined' && canCombine) return COMBINED
  if (plan?.kind === 'single') {
    const g = activeGoals.find(x => x.id === plan.goals[0]?.id)
    if (g) return g.id
  }
  return canCombine ? COMBINED : activeGoals[0].id
}

// Texto del botón de generar según lo elegido y lo que ya hay.
export function generateLabel(mode: number | null, options: PlanOption[], plan: PlanInfo | null): string {
  const hasPlan = !!plan && plan.kind !== 'none'
  const chosen = options.find(o => o.id === mode)
  if (!chosen) return hasPlan ? '🔄 Regenerar plan' : '⚡ Generar plan'
  const nombre = chosen.id === COMBINED ? 'combinado' : chosen.label.charAt(0).toLowerCase() + chosen.label.slice(1)
  if (!hasPlan) return `⚡ Generar plan ${nombre}`
  if (chosen.inForce) return `🔄 Regenerar plan ${nombre}`
  return `🔀 Cambiar a: ${chosen.id === COMBINED ? 'combinado' : nombre}`
}
