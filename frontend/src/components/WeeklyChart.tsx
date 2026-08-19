import { useEffect, useState } from 'react'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts'

// Detecta pantallas estrechas para ajustar la densidad del gráfico en móvil.
function useIsNarrow(breakpoint = 640) {
  const [narrow, setNarrow] = useState(
    typeof window !== 'undefined' ? window.innerWidth < breakpoint : false
  )
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < breakpoint)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [breakpoint])
  return narrow
}

interface WeekPoint {
  label: string
  value: number
  date: string
  /** Desglose del total por serie (p.ej. km por disciplina) para apilar. */
  parts?: Record<string, number>
}

/** Serie de una barra apilada: clave en `parts`, etiqueta de leyenda y color. */
interface SeriesDef {
  key: string
  label: string
  color: string
}

interface Props {
  data: WeekPoint[]
  unit?: string
  barColor?: string
  lineColor?: string
  averageLabel?: string
  movingAverageWindow?: number
  height?: number
  title?: string
  /**
   * Si se pasa (no vacío), cada barra se apila por estas series leyendo
   * `parts` de cada punto. La media móvil y la línea de media siguen
   * calculándose sobre el TOTAL (`value`). Sin `series`, el gráfico se
   * comporta exactamente como antes (una sola barra por semana).
   */
  series?: SeriesDef[]
}

function computeMovingAverage(values: number[], window: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < values.length; i++) {
    if (i < window - 1) {
      result.push(null)
      continue
    }
    let sum = 0
    for (let j = i - window + 1; j <= i; j++) sum += values[j]
    result.push(+(sum / window).toFixed(1))
  }
  return result
}

export default function WeeklyChart({
  data,
  unit = '',
  barColor = '#ef4444',
  lineColor = '#38bdf8',
  averageLabel = 'Media',
  movingAverageWindow = 4,
  height = 320,
  title,
  series,
}: Props) {
  const isNarrow = useIsNarrow()

  if (data.length === 0) {
    return <p className="text-sm text-gray-600">Sin datos.</p>
  }

  // Modo apilado solo si hay series; con array vacío caemos al modo clásico.
  const stackSeries = series && series.length > 0 ? series : null

  // En móvil reducimos altura y aligeramos las etiquetas del eje X para que sea legible.
  const effectiveHeight = isNarrow ? Math.min(height, 220) : height
  const xTickInterval = isNarrow
    ? Math.max(0, Math.ceil(data.length / 6) - 1)
    : 'preserveStartEnd'

  const values = data.map(d => d.value)
  const total = values.reduce((a, b) => a + b, 0)
  const avg = total / values.length
  const ma = computeMovingAverage(values, movingAverageWindow)

  const chartData = data.map((d, i) => ({
    label: d.label,
    date: d.date,
    value: d.value,
    ma: ma[i],
    // Las claves de disciplina (run/bike/...) no chocan con las fijas.
    ...(stackSeries ? d.parts ?? {} : {}),
  }))

  // Etiqueta legible para cada dataKey (series apiladas, total y media móvil).
  const nameFor = (name: string) => {
    if (name === 'value') return 'Semanal'
    if (name === 'ma') return `MA(${movingAverageWindow})`
    return stackSeries?.find(s => s.key === name)?.label ?? name
  }

  return (
    <div className="w-full">
      {title && <h3 className="font-bold text-sm text-gray-300 mb-3">{title}</h3>}
      {/* Leyenda propia para el modo apilado: la de recharts v3 ignora el orden
          de las series (ordena alfabéticamente) y aquí queremos el del apilado,
          compacta y legible a 375px. */}
      {stackSeries && (
        <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 mb-2 text-[10px] sm:text-[11px] text-gray-400">
          {stackSeries.map(s => (
            <span key={s.key} className="inline-flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-3 h-0.5 rounded" style={{ background: lineColor }} />
            MA({movingAverageWindow})
          </span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={effectiveHeight}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 5 }}>
          {!stackSeries && (
            <defs>
              <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={barColor} stopOpacity={0.9} />
                <stop offset="100%" stopColor={barColor} stopOpacity={0.3} />
              </linearGradient>
            </defs>
          )}
          <CartesianGrid stroke="#1f2937" vertical={false} />
          <XAxis
            dataKey="label"
            stroke="#6b7280"
            fontSize={isNarrow ? 10 : 11}
            tickLine={false}
            axisLine={{ stroke: '#1f2937' }}
            interval={xTickInterval}
            minTickGap={isNarrow ? 12 : 5}
          />
          <YAxis
            stroke="#6b7280"
            fontSize={11}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `${v}${unit ? unit.trim() : ''}`}
          />
          <Tooltip
            contentStyle={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: '#94a3b8', fontWeight: 'bold', marginBottom: 4 }}
            formatter={(value: any, name: any) => {
              const label = nameFor(String(name ?? ''))
              if (value == null) return ['—', label]
              return [`${value}${unit}`, label]
            }}
          />
          {!stackSeries && (
            <Legend
              verticalAlign="top"
              align="right"
              iconType="line"
              wrapperStyle={{ fontSize: 11, color: '#9ca3af', paddingBottom: 8 }}
              formatter={v => nameFor(String(v))}
            />
          )}
          <ReferenceLine
            y={avg}
            stroke="#f97316"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: `${averageLabel}: ${avg.toFixed(1)}`,
              position: 'insideTopRight',
              fill: '#f97316',
              fontSize: 11,
            }}
          />
          {stackSeries ? (
            stackSeries.map(s => (
              <Bar
                key={s.key}
                dataKey={s.key}
                stackId="disciplinas"
                fill={s.color}
                fillOpacity={0.85}
                maxBarSize={40}
              />
            ))
          ) : (
            <Bar dataKey="value" fill="url(#barGradient)" radius={[4, 4, 0, 0]} maxBarSize={40} />
          )}
          <Line
            type="monotone"
            dataKey="ma"
            stroke={lineColor}
            strokeWidth={2.5}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
