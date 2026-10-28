import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, AUTH_EXPIRED_EVENT } from '../api/client'
import type { PublicConfig, User } from '../api/types'

type Theme = 'dark' | 'light'

interface AppState {
  /** undefined = 세션 확인 중, null = 로그아웃 상태 */
  user: User | null | undefined
  config: PublicConfig | null
  theme: Theme
  toggleTheme: () => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  /** 서버 로그아웃이 성공했을 때만 user 가 null 이 된다. 실패하면 logoutError 가 채워진다 */
  logout: () => Promise<void>
  logoutBusy: boolean
  logoutError: string | null
  clearLogoutError: () => void
}

const AppContext = createContext<AppState | null>(null)
const THEME_KEY = 'cloudops-theme'

function initialTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined)
  const [config, setConfig] = useState<PublicConfig | null>(null)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [logoutState, setLogoutState] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null })

  useEffect(() => {
    api.me().then(setUser, () => setUser(null))
    api.config().then(setConfig, () => setConfig(null))
    const onExpired = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* 사생활 보호 모드 등에서는 저장하지 못해도 동작에는 문제없다 */
    }
  }, [theme])

  useEffect(() => {
    // 세션 만료 등으로 로그아웃 상태가 되면 지난 로그아웃 오류는 의미가 없다
    if (user === null) setLogoutState({ busy: false, error: null })
  }, [user])

  const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  const login = useCallback(async (email: string, password: string) => setUser(await api.login(email, password)), [])
  const register = useCallback(
    async (email: string, password: string) => setUser(await api.register(email, password)),
    [],
  )
  const logout = useCallback(async () => {
    // 세션 쿠키는 httpOnly 라서 서버만 지울 수 있다. 서버 로그아웃이 실패했는데 로그인 화면을 보여 주면
    // 사용자는 로그아웃됐다고 믿지만 쿠키는 남아 있게 된다. 실패하면 로그인 상태를 그대로 두고 알린다.
    setLogoutState({ busy: true, error: null })
    try {
      await api.logout()
      setLogoutState({ busy: false, error: null })
      setUser(null)
    } catch (e) {
      setLogoutState({ busy: false, error: e instanceof Error ? e.message : '알 수 없는 오류' })
    }
  }, [])
  const clearLogoutError = useCallback(() => setLogoutState((s) => ({ ...s, error: null })), [])

  const value = useMemo(
    () => ({
      user, config, theme, toggleTheme, login, register, logout,
      logoutBusy: logoutState.busy, logoutError: logoutState.error, clearLogoutError,
    }),
    [user, config, theme, toggleTheme, login, register, logout, logoutState, clearLogoutError],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppState {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('AppProvider 안에서만 사용할 수 있습니다')
  return ctx
}
