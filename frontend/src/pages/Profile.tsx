import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../api'
import { useAuth } from '../auth/AuthContext'

// Mensajes del resultado del callback de Strava (?strava=ok|error&reason=...).
const STRAVA_CALLBACK_MSG: Record<string, { text: string; ok: boolean }> = {
  ok: { text: 'Strava conectado correctamente ✅', ok: true },
  cuenta_duplicada: { text: 'Esa cuenta de Strava ya está vinculada a otro usuario de la app.', ok: false },
  state: { text: 'El enlace de conexión caducó. Pulsa "Conectar con Strava" otra vez.', ok: false },
  cancelado: { text: 'Cancelaste la conexión con Strava.', ok: false },
  usuario: { text: 'No se pudo identificar tu usuario. Vuelve a iniciar sesión.', ok: false },
}

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
  adaptive_paces: AdaptivePaces | null
}

// Ritmos adaptativos (VDOT) que el backend recalcula solos con marcas y carreras.
interface AdaptivePaces {
  vdot: number
  paces: Record<string, string>               // easy/marathon/threshold/interval/repetition -> "m:ss"
  ranges: Record<string, { fast: string; slow: string }>
  source: { kind: 'record' | 'activity' | 'vam'; category?: string; name?: string; date?: string | null; time_s?: number; distance_m?: number }
  computed_at: string
}

const PACE_LABELS: { key: string; label: string; hint: string }[] = [
  { key: 'easy', label: 'Rodaje', hint: 'Z2 · fácil' },
  { key: 'marathon', label: 'Maratón', hint: 'Z3 · sostenido' },
  { key: 'threshold', label: 'Umbral', hint: 'Z4 · tempo' },
  { key: 'interval', label: 'Series', hint: 'Z5 · VO2máx' },
  { key: 'repetition', label: 'Repeticiones', hint: 'cortas · velocidad' },
]

function describeSource(src: AdaptivePaces['source']): string {
  const when = src.date ? new Date(src.date).toLocaleDateString('es-ES', { day: 'numeric', month: 'short' }) : ''
  if (src.kind === 'record') {
    const cat = src.category || ''
    const secs = src.time_s || 0
    const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), sec = secs % 60
    const t = h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}` : `${m}:${String(sec).padStart(2, '0')}`
    return `tu marca de ${cat.replace('k', ' km')} (${t}${when ? `, ${when}` : ''})`
  }
  if (src.kind === 'activity') {
    const km = src.distance_m ? (src.distance_m / 1000).toFixed(1) : ''
    return `tu carrera «${src.name || 'sin nombre'}»${km ? ` de ${km} km` : ''}${when ? ` (${when})` : ''}`
  }
  return `tu test VAM${when ? ` (${when})` : ''}`
}

// VAM utilities — input en min/km (mm:ss), almacenado en m/s
function msToPace(ms: number | null): string {
  if (!ms || ms <= 0) return ''
  const secondsPerKm = 1000 / ms
  const minutes = Math.floor(secondsPerKm / 60)
  const seconds = Math.round(secondsPerKm - minutes * 60)
  if (seconds === 60) return `${minutes + 1}:00`
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function paceToMs(pace: string): number | null {
  if (!pace) return null
  const match = pace.match(/^(\d+):(\d{1,2})$/)
  if (!match) return null
  const minutes = parseInt(match[1], 10)
  const seconds = parseInt(match[2], 10)
  if (isNaN(minutes) || isNaN(seconds) || seconds >= 60) return null
  const totalSeconds = minutes * 60 + seconds
  if (totalSeconds <= 0) return null
  return 1000 / totalSeconds
}

export default function Profile() {
  const { effectiveUserId, user, viewAs, isMaster, logout } = useAuth()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [vamPace, setVamPace] = useState('')
  const [stravaConnected, setStravaConnected] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [stravaMsg, setStravaMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()

  // Solo puedes conectar TU propia cuenta de Strava, no la del usuario que el
  // maestro esté impersonando.
  const impersonating = viewAs != null

  useEffect(() => {
    if (effectiveUserId == null) return
    api.get(`/api/profile/${effectiveUserId}`).then(r => {
      setProfile(r.data)
      setVamPace(msToPace(r.data.vam_ms))
    }).catch(() => {})
    api.get(`/api/strava/status/${effectiveUserId}`).then(r => setStravaConnected(r.data.connected)).catch(() => {})
  }, [effectiveUserId])

  // Resultado del callback de Strava: ?strava=ok|error&reason=...
  useEffect(() => {
    const status = searchParams.get('strava')
    if (!status) return
    const reason = searchParams.get('reason') || ''
    if (status === 'ok') {
      setStravaMsg(STRAVA_CALLBACK_MSG.ok)
      setStravaConnected(true)
    } else {
      setStravaMsg(STRAVA_CALLBACK_MSG[reason] || { text: 'No se pudo conectar con Strava. Inténtalo de nuevo.', ok: false })
    }
    // Limpia los parámetros para que no reaparezca el mensaje al recargar.
    searchParams.delete('strava')
    searchParams.delete('reason')
    setSearchParams(searchParams, { replace: true })
  }, [searchParams, setSearchParams])

  const handleConnectStrava = async () => {
    if (user == null) return
    setStravaMsg(null)
    try {
      // Siempre sobre la cuenta propia (user.id), nunca la impersonada.
      const r = await api.get(`/api/strava/auth?user_id=${user.id}`)
      window.location.href = r.data.url
    } catch {
      setStravaMsg({ text: 'No se pudo iniciar la conexión con Strava', ok: false })
    }
  }

  const update = (field: keyof ProfileData, value: any) => {
    if (!profile) return
    setProfile({ ...profile, [field]: value })
  }

  const handleSave = async () => {
    if (!profile) return
    // Validar VAM pace si el usuario ha introducido algo
    let vamMs: number | null = null
    if (vamPace.trim()) {
      vamMs = paceToMs(vamPace.trim())
      if (vamMs === null) {
        setMsg({ text: 'VAM: formato inválido. Usa mm:ss (ej. 3:45)', ok: false })
        return
      }
    }
    setSaving(true)
    setMsg(null)
    try {
      // Solo se envían los campos editables; hr_zones/target_paces/adaptive_paces
      // los calcula el backend y son de solo lectura.
      const payload = {
        age: profile.age,
        sex: profile.sex,
        weight_kg: profile.weight_kg,
        height_cm: profile.height_cm,
        resting_heart_rate: profile.resting_heart_rate,
        max_heart_rate: profile.max_heart_rate,
        years_training: profile.years_training,
        experience_level: profile.experience_level,
        training_days_per_week: profile.training_days_per_week,
        vam_ms: vamMs,
      }
      await api.put(`/api/profile/${effectiveUserId}`, payload)
      const r = await api.get(`/api/profile/${effectiveUserId}`)
      setProfile(r.data)
      setVamPace(msToPace(r.data.vam_ms))
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

        {stravaMsg && (
          <p className={`text-sm ${stravaMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{stravaMsg.text}</p>
        )}

        {impersonating ? (
          <p className="text-sm text-yellow-500/90">
            Estás viendo la app como otro usuario. La conexión de Strava solo puede hacerla cada
            usuario desde su propia cuenta.
          </p>
        ) : (
          <button
            onClick={handleConnectStrava}
            className={`${
              stravaConnected
                ? 'bg-gray-700 hover:bg-gray-600 active:bg-gray-500'
                : 'bg-orange-500 hover:bg-orange-600 active:bg-orange-700'
            } w-full sm:w-auto min-h-11 text-white px-5 rounded-lg text-sm font-medium transition-colors`}
          >
            {stravaConnected ? 'Reconectar Strava' : 'Conectar con Strava'}
          </button>
        )}
      </div>

      {/* Accesos: Marcas y Objetivos viven aquí desde que salieron de la nav principal */}
      <div className="grid grid-cols-2 gap-3">
        <Link
          to="/records"
          className="min-h-11 bg-gray-900 border border-gray-800 hover:border-red-900/60 active:bg-gray-800 rounded-xl p-4 transition-colors"
        >
          <p className="text-2xl">🏆</p>
          <p className="font-semibold mt-1">Marcas</p>
          <p className="text-xs text-gray-500 mt-0.5">Tus mejores tiempos por prueba</p>
        </Link>
        <Link
          to="/goals"
          className="min-h-11 bg-gray-900 border border-gray-800 hover:border-red-900/60 active:bg-gray-800 rounded-xl p-4 transition-colors"
        >
          <p className="text-2xl">🎯</p>
          <p className="font-semibold mt-1">Objetivos</p>
          <p className="text-xs text-gray-500 mt-0.5">Las pruebas que estás preparando</p>
        </Link>
        {/* En móvil ya no hay menú con Admin: el maestro entra desde aquí */}
        {isMaster && (
          <Link
            to="/admin"
            className="col-span-2 min-h-11 bg-gray-900 border border-gray-800 hover:border-red-900/60 active:bg-gray-800 rounded-xl p-4 flex items-center gap-3 transition-colors"
          >
            <span className="text-2xl">🛡️</span>
            <span>
              <span className="block font-semibold">Admin</span>
              <span className="block text-xs text-gray-500 mt-0.5">Gestión de usuarios del grupo</span>
            </span>
          </Link>
        )}
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
          <Field label="VAM — ritmo test 5 min (mm:ss /km)">
            <input type="text" value={vamPace} onChange={e => setVamPace(e.target.value)} className={input} placeholder="ej. 3:45" />
          </Field>
        </div>
      </div>

      {/* Ritmos adaptativos: salen solos de marcas y carreras; se actualizan al sincronizar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-3">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-semibold">⚡ Tus ritmos</h2>
          {profile.adaptive_paces && (
            <span className="text-xs font-black text-red-400">VDOT {profile.adaptive_paces.vdot}</span>
          )}
        </div>
        {profile.adaptive_paces ? (
          <>
            <p className="text-xs text-gray-500">
              Calculados de {describeSource(profile.adaptive_paces.source)}. Se recalculan solos cada vez que sincronizas o añades una marca, y Goggins los usa para el plan.
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {PACE_LABELS.map(({ key, label, hint }) => {
                const p = profile.adaptive_paces!.paces[key]
                const r = profile.adaptive_paces!.ranges?.[key]
                if (!p) return null
                return (
                  <div key={key} className="bg-gray-800/60 rounded-lg p-3 min-h-11">
                    <p className="text-[10px] uppercase tracking-wider text-gray-500">{label}</p>
                    <p className="text-lg font-black text-red-400 leading-tight">{p} <span className="text-xs font-normal text-gray-500">/km</span></p>
                    <p className="text-[10px] text-gray-600">{r ? `${r.fast}–${r.slow}` : hint}</p>
                  </div>
                )
              })}
            </div>
          </>
        ) : (
          <p className="text-xs text-gray-500">
            Aún no hay datos suficientes. Añade una marca de carrera reciente en Marcas, o sincroniza Strava con alguna carrera de 3 km o más, y aparecerán aquí.
          </p>
        )}
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

      {/* Cerrar sesión: en móvil ya no existe el menú hamburguesa, así que vive aquí */}
      <div className="border-t border-gray-800 pt-6">
        <button
          onClick={logout}
          className="w-full sm:w-auto min-h-11 bg-gray-900 border border-gray-800 hover:bg-gray-800 active:bg-gray-700 text-gray-400 px-5 rounded-lg text-sm transition-colors"
        >
          ⎋ Cerrar sesión{user?.email ? ` (${user.email})` : ''}
        </button>
      </div>
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
