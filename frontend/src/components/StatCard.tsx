interface StatCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  color?: string
}

export default function StatCard({ label, value, unit, sub, color = 'orange' }: StatCardProps) {
  const accent: Record<string, string> = {
    orange: 'text-orange-400',
    blue: 'text-blue-400',
    green: 'text-green-400',
    red: 'text-red-400',
    purple: 'text-purple-400',
  }
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <div className="flex items-baseline gap-1">
        <span className={`text-3xl font-bold ${accent[color] ?? accent.orange}`}>{value}</span>
        {unit && <span className="text-sm text-gray-400">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-gray-600 mt-1">{sub}</p>}
    </div>
  )
}
