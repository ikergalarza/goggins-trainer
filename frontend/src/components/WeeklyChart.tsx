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
}: Props) {
  const isNarrow = useIsNarrow()

  if (data.length === 0) {
    return <p className="text-sm text-gray-600">Sin datos.</p>
  }

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
  }))

  return (
    <div className="w-full">
      {title && <h3 className="font-bold text-sm text-gray-300 mb-3">{title}</h3>}
      <ResponsiveContainer width="100%" height={effectiveHeight}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: -10, bottom: 5 }}>
          <defs>
            <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={barColor} stopOpacity={0.9} />
              <stop offset="100%" stopColor={barColor} stopOpacity={0.3} />
            </linearGradient>
          </defs>
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
              const label = name === 'value' ? 'Valor' : name === 'ma' ? `MA(${movingAverageWindow})` : String(name ?? '')
              if (value == null) return ['—', label]
              return [`${value}${unit}`, label]
            }}
          />
          <Legend
            verticalAlign="top"
            align="right"
            iconType="line"
            wrapperStyle={{ fontSize: 11, color: '#9ca3af', paddingBottom: 8 }}
            formatter={v => {
              if (v === 'value') return 'Semanal'
              if (v === 'ma') return `MA(${movingAverageWindow})`
              return v
            }}
          />
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
          <Bar dataKey="value" fill="url(#barGradient)" radius={[4, 4, 0, 0]} maxBarSize={40} />
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
