interface BarChartProps {
  data: { label: string; value: number; sub?: string }[]
  unit?: string
  color?: string
  height?: number
}

export default function BarChart({ data, unit = '', color = 'bg-red-500', height = 160 }: BarChartProps) {
  const maxValue = Math.max(...data.map(d => d.value), 1)

  return (
    <div className="w-full">
      <div className="flex items-end gap-1.5" style={{ height }}>
        {data.map((d, i) => {
          const pct = (d.value / maxValue) * 100
          return (
            <div key={i} className="flex-1 flex flex-col items-center group">
              <div className="text-[10px] text-gray-500 mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {d.value.toFixed(d.value % 1 === 0 ? 0 : 1)}{unit}
              </div>
              <div className="relative w-full flex items-end" style={{ height: height - 32 }}>
                <div
                  className={`${color} w-full rounded-t transition-all hover:opacity-80`}
                  style={{ height: `${pct}%`, minHeight: d.value > 0 ? '2px' : '0' }}
                  title={`${d.label}: ${d.value.toFixed(1)}${unit}`}
                />
              </div>
            </div>
          )
        })}
      </div>
      <div className="flex gap-1.5 mt-2">
        {data.map((d, i) => (
          <div key={i} className="flex-1 text-[10px] text-gray-600 text-center truncate">
            {d.label}
          </div>
        ))}
      </div>
    </div>
  )
}
