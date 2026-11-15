import { createContext, useCallback, useContext, useEffect, useState } from 'react'

// ---------------------------------------------------------------- API
const TOKEN_KEY = 'fs_token'
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ } }

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const t = getToken()
  if (t) headers['X-Auth-Token'] = t   // not Authorization: the preview sits behind HTTP basic auth
  const r = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  const data = r.headers.get('content-type')?.includes('json') ? await r.json() : null
  if (!r.ok) {
    let msg = data?.detail
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join('; ')
    throw new Error(msg || `Error ${r.status}`)
  }
  return data
}

export function useApi(path, deps = []) {
  const [state, set] = useState({ data: null, error: null, loading: true, stamp: 0 })
  const load = useCallback(() => {
    if (!path) { set((s) => ({ ...s, data: null, error: null, loading: false })); return }
    set((s) => ({ ...s, loading: true }))
    api(path).then((data) => set((s) => ({ data, error: null, loading: false, stamp: s.stamp + 1 })))
      .catch((error) => set((s) => ({ data: null, error, loading: false, stamp: s.stamp + 1 })))
  }, [path]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(load, [load, ...deps]) // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, reload: load }
}

// ---------------------------------------------------------------- auth
const AuthCtx = createContext(null)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setReady(true); return }
    try { setUser(await api('/me')) } catch { setToken(null); setUser(null) }
    setReady(true)
  }, [])
  useEffect(() => { refresh() }, [refresh])
  const login = async (token) => { setToken(token); await refresh() }
  const logout = () => { setToken(null); setUser(null) }
  return <AuthCtx.Provider value={{ user, ready, login, logout, refresh }}>{children}</AuthCtx.Provider>
}
export const useAuth = () => useContext(AuthCtx)

// ---------------------------------------------------------------- shared data
let _crops, _rayons
export function useCatalog() {
  const [c, setC] = useState({ crops: _crops || [], rayons: _rayons || [] })
  useEffect(() => {
    if (_crops && _rayons) return
    Promise.all([api('/crops'), api('/rayons')]).then(([crops, rayons]) => {
      _crops = crops; _rayons = rayons; setC({ crops, rayons })
    })
  }, [])
  return c
}

// ---------------------------------------------------------------- format
export const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—'
  : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }))
export const fmt0 = (v) => fmt(v, 0)
export const sign = (v, d = 1) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${fmt(v, d)}`)
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
export const doy = (n) => { const d = new Date(2001, 0, n); return `${d.getDate()} ${MONTHS[d.getMonth()]}` }
export const initials = (s = '') => s.split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()
export const ago = (iso) => {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T') + (iso.includes('Z') ? '' : 'Z'))
  const s = (Date.now() - d) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return d.toLocaleDateString('en-GB')
}
