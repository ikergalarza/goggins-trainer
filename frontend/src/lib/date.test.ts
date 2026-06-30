import { describe, it, expect } from 'vitest'
import { parseLocalDate, formatDayKey, startOfWeek } from './date'

describe('parseLocalDate', () => {
  it('parsea "YYYY-MM-DD" como fecha LOCAL (no UTC)', () => {
    // Regresión del bug de calendario: new Date('2026-06-30') daría medianoche
    // UTC y, según la zona horaria, podría caer en el día 29 al leer componentes
    // locales. parseLocalDate debe devolver siempre el día 30 local.
    const d = parseLocalDate('2026-06-30')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(5) // junio = 5 (0-indexado)
    expect(d.getDate()).toBe(30)
    expect(d.getHours()).toBe(0)
    expect(d.getMinutes()).toBe(0)
  })

  it('ignora la parte de hora si viene un timestamp completo', () => {
    const d = parseLocalDate('2026-01-05T14:30:00Z')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(0) // enero
    expect(d.getDate()).toBe(5)
    expect(d.getHours()).toBe(0) // se descarta la hora, queda medianoche local
  })

  it('es estable round-trip con formatDayKey', () => {
    const key = '2026-12-31'
    expect(formatDayKey(parseLocalDate(key))).toBe(key)
  })
})

describe('formatDayKey', () => {
  it('produce "YYYY-MM-DD" con padding de ceros a partir de componentes locales', () => {
    const d = new Date(2026, 0, 3) // 3 enero 2026, local
    expect(formatDayKey(d)).toBe('2026-01-03')
  })

  it('coincide con la fecha local aunque sea de madrugada', () => {
    const d = new Date(2026, 6, 9, 1, 0, 0) // 9 julio 2026 01:00 local
    expect(formatDayKey(d)).toBe('2026-07-09')
  })
})

describe('startOfWeek', () => {
  // 2026-06-29 es lunes; la semana va del lunes 29 jun al domingo 5 jul.
  const days: Array<[string, string]> = [
    ['2026-06-29', '2026-06-29'], // lunes -> él mismo
    ['2026-06-30', '2026-06-29'], // martes
    ['2026-07-01', '2026-06-29'], // miércoles
    ['2026-07-02', '2026-06-29'], // jueves
    ['2026-07-03', '2026-06-29'], // viernes
    ['2026-07-04', '2026-06-29'], // sábado
    ['2026-07-05', '2026-06-29'], // domingo -> lunes anterior
  ]

  it.each(days)('para %s el inicio de semana (lunes) es %s', (input, expected) => {
    const monday = startOfWeek(parseLocalDate(input))
    expect(formatDayKey(monday)).toBe(expected)
    // Confirmamos que efectivamente es lunes: getDay() === 1
    expect(monday.getDay()).toBe(1)
  })

  it('normaliza la hora a medianoche local', () => {
    const monday = startOfWeek(new Date(2026, 6, 1, 18, 45, 30)) // miércoles tarde
    expect(monday.getHours()).toBe(0)
    expect(monday.getMinutes()).toBe(0)
    expect(monday.getSeconds()).toBe(0)
    expect(monday.getMilliseconds()).toBe(0)
  })

  it('cruza correctamente el límite de mes (domingo -> lunes del mes anterior)', () => {
    // Domingo 1 marzo 2026 pertenece a la semana que empieza el lunes 23 feb.
    const monday = startOfWeek(parseLocalDate('2026-03-01'))
    expect(formatDayKey(monday)).toBe('2026-02-23')
  })
})
