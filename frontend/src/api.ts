import axios from 'axios'

const TOKEN_KEY = 'gt_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) || ''

const api = axios.create({
  baseURL: API_BASE,
})

// Añade el token Bearer a cada petición.
api.interceptors.request.use((config) => {
  const token = tokenStore.get()
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Si el token caduca o falta, limpia y manda a /login (salvo en el propio login).
api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    if (status === 401 && !url.includes('/api/auth/login')) {
      tokenStore.clear()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

// Cabeceras para peticiones fetch() manuales (streaming SSE).
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = tokenStore.get()
  return token ? { ...extra, Authorization: `Bearer ${token}` } : { ...extra }
}

export default api
