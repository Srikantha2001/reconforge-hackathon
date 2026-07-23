import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { api, setAuthToken } from '../api'
import type { AuthUser } from '../types'

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  role: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const TOKEN_KEY = 'reconos.token'
const USER_KEY = 'reconos.user'

// JWT auth (P4). Token in localStorage, attached to every request by api.ts;
// a 401 clears it and the app falls back to the login screen.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? (JSON.parse(raw) as AuthUser) : null
  })

  if (token) setAuthToken(token)

  const login = async (email: string, password: string) => {
    const resp = await api.login(email, password)
    const authed: AuthUser = { user_id: resp.user_id, email: resp.email, name: resp.name, role: resp.role }
    localStorage.setItem(TOKEN_KEY, resp.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(authed))
    setAuthToken(resp.access_token)
    setToken(resp.access_token)
    setUser(authed)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setAuthToken(null)
    setToken(null)
    setUser(null)
  }

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, role: user?.role ?? null, isAuthenticated: Boolean(token), login, logout }),
    [user, token],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
