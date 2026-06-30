import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import api, { tokenStore } from '../api'

export interface AuthUser {
  id: number
  name: string
  email: string
  is_master: boolean
  strava_connected?: boolean
}

interface AuthState {
  user: AuthUser | null
  loading: boolean
  isMaster: boolean
  // Impersonación del maestro: usuario al que está "viendo como" (null = él mismo).
  viewAs: AuthUser | null
  // ID efectivo cuyos datos se muestran (el propio, o el impersonado).
  effectiveUserId: number | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  setViewAs: (u: AuthUser | null) => void
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [viewAs, setViewAs] = useState<AuthUser | null>(null)

  // Al cargar, si hay token, recupera el usuario.
  useEffect(() => {
    const token = tokenStore.get()
    if (!token) {
      setLoading(false)
      return
    }
    api.get('/api/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => {
        tokenStore.clear()
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const r = await api.post('/api/auth/login', { email, password })
    tokenStore.set(r.data.access_token)
    setUser(r.data.user)
    setViewAs(null)
  }

  const logout = () => {
    tokenStore.clear()
    setUser(null)
    setViewAs(null)
    window.location.href = '/login'
  }

  const value: AuthState = {
    user,
    loading,
    isMaster: !!user?.is_master,
    viewAs,
    effectiveUserId: viewAs?.id ?? user?.id ?? null,
    login,
    logout,
    setViewAs,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>')
  return ctx
}
