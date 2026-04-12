import { useEffect, useState } from 'react'
import api from '../api'

const USER_ID = 1

interface Activity {
  id: number
  name: string
  type: string
  distance_km: number
  moving_time_min: number
  elevation_gain_m: number
  average_heartrate: number
  max_heartrate: number
  start_date: string
}

export default function Activities() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/api/strava/activities/${USER_ID}?limit=1000`)
      .then(r => setActivities(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Actividades</h1>
        <p className="text-gray-500 text-sm mt-1">{activities.length} actividades sincronizadas</p>
      </div>

      {loading ? (
        <p className="text-gray-600">Cargando...</p>
      ) : activities.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
          <p className="text-gray-500">No hay actividades. Conecta Strava y sincroniza desde el Dashboard.</p>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-xl divide-y divide-gray-800">
          {activities.map(a => (
            <div key={a.id} className="flex items-center justify-between px-6 py-4">
              <div className="flex-1">
                <p className="font-medium text-sm">{a.name}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {new Date(a.start_date).toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' })}
                  {' · '}{a.type}
                </p>
              </div>
              <div className="flex gap-6 text-right text-sm">
                <div>
                  <p className="font-semibold text-red-400">{a.distance_km?.toFixed(2)} km</p>
                  <p className="text-xs text-gray-500">distancia</p>
                </div>
                <div>
                  <p className="font-semibold">{a.moving_time_min?.toFixed(0)} min</p>
                  <p className="text-xs text-gray-500">tiempo</p>
                </div>
                {a.elevation_gain_m != null && (
                  <div>
                    <p className="font-semibold text-green-400">+{Math.round(a.elevation_gain_m)} m</p>
                    <p className="text-xs text-gray-500">desnivel</p>
                  </div>
                )}
                {a.average_heartrate && (
                  <div>
                    <p className="font-semibold text-red-400">{Math.round(a.average_heartrate)} bpm</p>
                    <p className="text-xs text-gray-500">FC media</p>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
