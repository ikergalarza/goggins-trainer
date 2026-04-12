import { useEffect, useState } from 'react'
import api from '../api'

const USER_ID = 1

interface ProfileData {
  id: number
  name: string
  age: number | null
  sex: string | null
  weight_kg: number | null
  height_cm: number | null
  resting_heart_rate: number | null
  max_heart_rate: number | null
  years_training: number | null
  experience_level: string | null
  training_days_per_week: number | null
  vam_ms: number | null
  hr_zones: any
  target_paces: any
}

export default function Profile() {
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [stravaConnected, setStravaConnected] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  useEffect(() => {
    api.get(`/api/profile/${USER_ID}`).then(r => setProfile(r.data)).catch(() => {})
    api.get(`/api/strava/status/${USER_ID}`).then(r => setStravaConnected(r.data.connected)).catch(() => {})
  }, [])

  const handleConnectStrava = () => {
    window.location.href = `/api/strava/auth?user_id=${USER_ID}`
  }

  const update = (field: keyof ProfileData, value: any) => {
    if (!profile) return
    setProfile({ ...profile, [field]: value })
  }

  const handleSave = async () => {
    if (!profile) return
    setSaving(true)
    setMsg(null)
    try {
      const { id, name, hr_zones, target_paces, ...payload } = profile
      await api.put(`/api/profile/${USER_ID}`, payload)
      const r = await api.get(`/api/profile/${USER_ID}`)
      setProfile(r.data)
      setMsg({ text: 'Perfil guardado', ok: true })
    } catch (err: any) {
      setMsg({ text: `Error: ${err?.response?.data?.detail || err.message}`, ok: false })
    } finally {
      setSaving(false)
    }
  }

  if (!profile) return <p className="text-gray-600">Cargando...</p>

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Perfil</h1>
        <p className="text-gray-500 text-sm mt-1">Datos físicos, experiencia y conexiones</p>
      </div>

      {/* Strava */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
        <div>
          <h2 className="font-semibold">Conexión Strava</h2>
          <p className="text-sm text-gray-500 mt-1">
            {stravaConnected
              ? 'Strava conectado ✅'
              : 'Conecta tu cuenta para sincronizar actividades automáticamente.'}
          </p>
        </div>
        <button
          onClick={handleConnectStrava}
          className={`${
            stravaConnected
              ? 'bg-gray-700 hover:bg-gray-600'
              : 'bg-orange-500 hover:bg-orange-600'
          } text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors`}
        >
          {stravaConnected ? 'Reconectar Strava' : 'Conectar con Strava'}
        </button>
      </div>

      {/* Datos físicos */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
        <h2 className="font-semibold">Datos físicos</h2>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Edad">
            <input type="number" value={profile.age ?? ''} onChange={e => update('age', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="Sexo">
            <select value={profile.sex ?? ''} onChange={e => update('sex', e.target.value || null)} className={input}>
              <option value="">—</option>
              <option value="M">Hombre</option>
              <option value="F">Mujer</option>
            </select>
          </Field>
          <Field label="Peso (kg)">
            <input type="number" step="0.1" value={profile.weight_kg ?? ''} onChange={e => update('weight_kg', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="Altura (cm)">
            <input type="number" value={profile.height_cm ?? ''} onChange={e => update('height_cm', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="FC máxima (bpm)">
            <input type="number" value={profile.max_heart_rate ?? ''} onChange={e => update('max_heart_rate', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="FC reposo (bpm)">
            <input type="number" value={profile.resting_heart_rate ?? ''} onChange={e => update('resting_heart_rate', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
        </div>
      </div>

      {/* Experiencia */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
        <h2 className="font-semibold">Experiencia</h2>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Años entrenando">
            <input type="number" value={profile.years_training ?? ''} onChange={e => update('years_training', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="Nivel">
            <select value={profile.experience_level ?? ''} onChange={e => update('experience_level', e.target.value || null)} className={input}>
              <option value="">—</option>
              <option value="beginner">Principiante</option>
              <option value="intermediate">Intermedio</option>
              <option value="advanced">Avanzado</option>
            </select>
          </Field>
          <Field label="Días de entreno / semana">
            <input type="number" min={1} max={7} value={profile.training_days_per_week ?? ''} onChange={e => update('training_days_per_week', e.target.value ? +e.target.value : null)} className={input} />
          </Field>
          <Field label="VAM (m/s) — opcional">
            <input type="number" step="0.1" value={profile.vam_ms ?? ''} onChange={e => update('vam_ms', e.target.value ? +e.target.value : null)} className={input} placeholder="ej. 4.5" />
          </Field>
        </div>
      </div>

      {/* Zonas calculadas */}
      {profile.hr_zones && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
          <h2 className="font-semibold">Zonas cardíacas calculadas</h2>
          <p className="text-xs text-gray-500">Método: {profile.hr_zones.method} · FCmáx {profile.hr_zones.hr_max} · FCrep {profile.hr_zones.hr_rest}</p>
          <div className="space-y-2">
            {Object.entries(profile.hr_zones.zones as Record<string, number[]>).map(([zone, range]) => (
              <div key={zone} className="flex items-center justify-between text-sm">
                <span className="font-bold text-red-400">{zone}</span>
                <span className="text-gray-400">{range[0]}–{range[1]} bpm</span>
                {profile.target_paces?.[zone] && (
                  <span className="text-gray-500 text-xs">
                    {profile.target_paces[zone].pace_fast}–{profile.target_paces[zone].pace_slow} /km
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {msg && (
        <p className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white px-6 py-2.5 rounded-lg text-sm font-bold transition-colors"
      >
        {saving ? 'Guardando...' : '💾 Guardar perfil'}
      </button>
    </div>
  )
}

const input = "w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-red-500"

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      {children}
    </div>
  )
}
