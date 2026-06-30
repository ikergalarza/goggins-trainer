import { describe, it, expect } from 'vitest'
import {
  parseIntervals,
  formatIntervalSet,
  disciplineOf,
} from './workoutMeta'

describe('parseIntervals', () => {
  it('extrae reps, distancia, zona y recuperación de una serie típica', () => {
    const sets = parseIntervals('6x400m @ Z4, rec 90s')
    expect(sets).toHaveLength(1)
    expect(sets[0].reps).toBe(6)
    expect(sets[0].distance).toBe('400m')
    expect(sets[0].zone).toBe('Z4')
    expect(sets[0].rest).toBe('90s')
  })

  it('admite espacios y el símbolo × además de la x', () => {
    const sets = parseIntervals('10 × 1km')
    expect(sets).toHaveLength(1)
    expect(sets[0].reps).toBe(10)
    expect(sets[0].distance).toBe('1km')
  })

  it('separa varias series en varias líneas', () => {
    const sets = parseIntervals('4x800m @ Z3\n6x200m @ Z5')
    expect(sets).toHaveLength(2)
    expect(sets[0].reps).toBe(4)
    expect(sets[1].reps).toBe(6)
    expect(sets[1].zone).toBe('Z5')
  })

  it('no absorbe la zona como parte de la distancia cuando falta unidad', () => {
    // "200 Z5" -> distancia "200", zona "Z5" (no "200Z5").
    const sets = parseIntervals('5x200 Z5')
    expect(sets).toHaveLength(1)
    expect(sets[0].distance).toBe('200')
    expect(sets[0].zone).toBe('Z5')
  })

  it('devuelve [] para texto sin patrón de serie o entrada vacía', () => {
    expect(parseIntervals('Rodaje suave continuo')).toEqual([])
    expect(parseIntervals('')).toEqual([])
    expect(parseIntervals(null)).toEqual([])
    expect(parseIntervals(undefined)).toEqual([])
  })
})

describe('formatIntervalSet', () => {
  it('formatea la serie completa como "6×400m @ Z4 · rec 90s"', () => {
    const [set] = parseIntervals('6x400m @ Z4, rec 90s')
    expect(formatIntervalSet(set)).toBe('6×400m @ Z4 · rec 90s')
  })

  it('omite zona y recuperación cuando no existen', () => {
    const [set] = parseIntervals('10x1km')
    expect(formatIntervalSet(set)).toBe('10×1km')
  })

  it('incluye solo la zona si no hay recuperación', () => {
    const [set] = parseIntervals('4x800m @ Z3')
    expect(formatIntervalSet(set)).toBe('4×800m @ Z3')
  })
})

describe('disciplineOf', () => {
  it('mapea tipos conocidos a su disciplina', () => {
    expect(disciplineOf('swim')).toBe('swim')
    expect(disciplineOf('bike')).toBe('bike')
    expect(disciplineOf('long_run')).toBe('run')
    expect(disciplineOf('strength_full')).toBe('strength')
    expect(disciplineOf('rest')).toBe('rest')
  })

  it('cae a "run" para tipos desconocidos', () => {
    expect(disciplineOf('tipo_inexistente')).toBe('run')
  })
})

import { paceOrSpeed } from './workoutMeta'

describe('paceOrSpeed', () => {
  it('carrera devuelve ritmo min/km', () => {
    expect(paceOrSpeed('easy_run', 10, 50)).toEqual({ label: 'Ritmo', value: '5:00 /km' })
  })
  it('natación devuelve ritmo min/100m', () => {
    // 30 min / (1.5 km * 10 = 15 × 100m) = 2:00 /100m
    expect(paceOrSpeed('swim', 1.5, 30)).toEqual({ label: 'Ritmo', value: '2:00 /100m' })
  })
  it('bici devuelve velocidad km/h', () => {
    expect(paceOrSpeed('bike', 40, 80)).toEqual({ label: 'Velocidad', value: '30.0 km/h' })
  })
  it('sin datos o disciplina sin ritmo devuelve null', () => {
    expect(paceOrSpeed('easy_run', null, 50)).toBeNull()
    expect(paceOrSpeed('mobility', 5, 30)).toBeNull()
    expect(paceOrSpeed('rest', 0, 0)).toBeNull()
  })
})
