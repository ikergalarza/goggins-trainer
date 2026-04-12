import { useState } from 'react'
import api from '../api'

const USER_ID = 1

export default function Profile() {
  const [accessToken, setAccessToken] = useState('')
  const [refreshToken, setRefreshToken] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)

  const handleSave = async () => {
    if (!accessToken || !refreshToken) {
      setMsg({ text: 'Rellena los dos tokens.', ok: false })
      return
    }
    setSaving(true)
    setMsg(null)
    try {
      await api.post(`/api/strava/tokens/${USER_ID}`, {
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_at: 0,
      })
      const r_data = r.data
      const text = r_data.warning
        ? `${r_data.message} (${r_data.warning})`
        : r_data.message
      setMsg({ text, ok: !r_data.warning })
      setAccessToken('')
      setRefreshToken('')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Error desconocido'
      setMsg({ text: `Error: ${detail}`, ok: false })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Perfil</h1>
        <p className="text-gray-500 text-sm mt-1">Configura tu cuenta y conexiones</p>
      </div>

      {/* Conectar Strava con tokens */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
        <div>
          <h2 className="font-semibold">Conectar Strava</h2>
          <p className="text-sm text-gray-500 mt-1">
            Obtén tus tokens en{' '}
            <a
              href="https://www.strava.com/settings/api"
              target="_blank"
              rel="noreferrer"
              className="text-orange-400 hover:underline"
            >
              strava.com/settings/api
            </a>
            {' '}→ sección <strong className="text-gray-300">"Your Access Token"</strong>.
          </p>
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Access Token</label>
            <input
              type="password"
              value={accessToken}
              onChange={e => setAccessToken(e.target.value)}
              placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-orange-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Refresh Token</label>
            <input
              type="password"
              value={refreshToken}
              onChange={e => setRefreshToken(e.target.value)}
              placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-orange-500"
            />
          </div>
        </div>

        {msg && (
          <p className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</p>
        )}

        <button
          onClick={handleSave}
          disabled={saving}
          className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          {saving ? 'Guardando...' : 'Guardar tokens'}
        </button>
      </div>

      {/* Placeholder datos físicos */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <h2 className="font-semibold mb-2">Datos físicos</h2>
        <p className="text-sm text-gray-500">Próximamente — edad, peso, FC máxima y zonas cardíacas.</p>
      </div>
    </div>
  )
}
