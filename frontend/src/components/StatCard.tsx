interface StatCardProps {
  label: string
  value: string | number
  unit?: string
  sub?: string
  color?: string
}

export default function StatCard({ label, value, unit, sub, color = 'red' }: StatCardProps) {
  const accent: Record<string, string> = {
    red: 'text-red-400',
    blue: 'text-blue-400',
    green: 'text-green-400',
    yellow: 'text-yellow-400',
    purple: 'text-purple-400',
  }
  return (
    <div className="bg-gray-900 border border-gray-800 hover:border-red-900/60 rounded-xl p-5 transition-colors">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">{label}</p>
      <div className="flex items-baseline gap-1">
        <span className={`text-3xl font-black ${accent[color] ?? accent.red}`}>{value}</span>
        {unit && <span className="text-sm text-gray-500">{unit}</span>}
      </div>
      {sub && <p className="text-xs text-gray-600 mt-1">{sub}</p>}
    </div>
  )
}
