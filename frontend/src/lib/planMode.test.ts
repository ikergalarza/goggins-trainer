import { describe, it, expect } from 'vitest'
import { COMBINED, modeFor, planOptions, generateLabel, type PlanGoal, type PlanInfo } from './planMode'

const bilbao: PlanGoal = { id: 1, description: 'hyrox dobles mixto Bilbao', target_race_date: '2027-02-07' }
const media: PlanGoal = { id: 2, description: 'Media Maraton San Sebastián', target_race_date: '2027-04-04' }
const sinFecha: PlanGoal = { id: 3, description: 'Mejorar fuerza', target_race_date: null }

const combinado: PlanInfo = { kind: 'combined', goals: [bilbao, media] }
const individual: PlanInfo = { kind: 'single', goals: [media] }
const nada: PlanInfo = { kind: 'none', goals: [] }

describe('modeFor (qué plan se va a generar por defecto)', () => {
  it('con un plan combinado en vigor, combinado', () => {
    expect(modeFor(combinado, [bilbao, media])).toBe(COMBINED)
  })
  it('con un plan individual en vigor, ese objetivo', () => {
    expect(modeFor(individual, [bilbao, media])).toBe(2)
  })
  it('sin plan y con 2 carreras con fecha, combinado (lo que se suele querer)', () => {
    expect(modeFor(nada, [bilbao, media])).toBe(COMBINED)
  })
  it('sin plan y con un solo objetivo, ese objetivo', () => {
    expect(modeFor(nada, [bilbao])).toBe(1)
  })
  it('un combinado que ya no se puede combinar (queda 1 carrera con fecha) cae al primer objetivo', () => {
    expect(modeFor(combinado, [bilbao, sinFecha])).toBe(1)
  })
  it('un objetivo del plan que ya no está activo cae al primero activo', () => {
    expect(modeFor({ kind: 'single', goals: [{ id: 99, description: 'viejo' }] }, [bilbao, media])).toBe(COMBINED)
  })
  it('sin objetivos no hay modo', () => {
    expect(modeFor(nada, [])).toBeNull()
  })
})

describe('planOptions (las opciones al elegir plan)', () => {
  it('con 2 carreras: combinado + una opción individual por objetivo', () => {
    const o = planOptions([bilbao, media], combinado)
    expect(o.map(x => x.id)).toEqual([COMBINED, 1, 2])
    expect(o[0].label).toBe('Combinado')
    expect(o[1].label).toBe('Solo hyrox dobles mixto Bilbao')
  })
  it('marca cuál está en vigor', () => {
    expect(planOptions([bilbao, media], combinado).filter(x => x.inForce).map(x => x.id)).toEqual([COMBINED])
    expect(planOptions([bilbao, media], individual).filter(x => x.inForce).map(x => x.id)).toEqual([2])
    expect(planOptions([bilbao, media], nada).filter(x => x.inForce)).toEqual([])
  })
  it('con un solo objetivo no hay nada que elegir', () => {
    expect(planOptions([bilbao], individual)).toEqual([])
  })
  it('solo se puede combinar con 2+ carreras con fecha', () => {
    expect(planOptions([bilbao, sinFecha], nada).map(x => x.id)).toEqual([1, 3])
  })
})

describe('generateLabel (texto del botón)', () => {
  const opts = planOptions([bilbao, media], combinado)
  it('sin plan: generar', () => {
    expect(generateLabel(COMBINED, opts, nada)).toBe('⚡ Generar plan combinado')
  })
  it('mismo plan en vigor: regenerar', () => {
    expect(generateLabel(COMBINED, opts, combinado)).toBe('🔄 Regenerar plan combinado')
  })
  it('otro plan distinto del vigente: cambiar', () => {
    expect(generateLabel(1, opts, combinado)).toBe('🔀 Cambiar a: solo hyrox dobles mixto Bilbao')
  })
  it('un único objetivo', () => {
    expect(generateLabel(1, [], nada)).toBe('⚡ Generar plan')
    expect(generateLabel(1, [], { kind: 'single', goals: [bilbao] })).toBe('🔄 Regenerar plan')
  })
})
