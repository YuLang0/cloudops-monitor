import { Activity, Bell, LayoutDashboard, LogOut, Moon, OctagonAlert, Server, Sun } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useApp } from '../context/AppContext'

const NAV = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/servers', label: '서버', icon: Server, end: false },
  { to: '/incidents', label: '장애 이력', icon: Bell, end: false },
]

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-ink shadow-sm">
        <Activity size={18} strokeWidth={2.5} aria-hidden />
      </span>
      <span className="text-base font-bold tracking-tight">
        CloudOps <span className="font-medium text-ink-3">Monitor</span>
      </span>
    </div>
  )
}

export function ThemeToggle() {
  const { theme, toggleTheme } = useApp()
  return (
    <button type="button" className="btn btn-ghost p-2" onClick={toggleTheme}
      aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'} title="테마 전환">
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}

export function Layout() {
  const { user, logout, logoutBusy, logoutError, clearLogoutError } = useApp()
  return (
    <div className="min-h-dvh md:pl-60">
      {/* 데스크톱: 왼쪽 고정 사이드바 */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-line bg-surface/80 backdrop-blur md:flex">
        <div className="px-5 py-5">
          <Logo />
        </div>
        <nav className="flex-1 space-y-1 px-3" aria-label="주 메뉴">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                  isActive ? 'bg-accent/15 text-accent' : 'text-ink-2 hover:bg-surface-2 hover:text-ink'
                }`
              }
            >
              <Icon size={18} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-line p-3">
          <div className="truncate px-2 pb-2 text-xs text-ink-3" title={user?.email}>
            {user?.email}
          </div>
          <div className="flex items-center justify-between">
            <button type="button" className="btn btn-ghost px-2" onClick={() => void logout()} disabled={logoutBusy}>
              <LogOut size={16} aria-hidden /> {logoutBusy ? '로그아웃 중…' : '로그아웃'}
            </button>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* 모바일: 상단 바 */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-2.5 backdrop-blur md:hidden">
        <Logo />
        <div className="flex items-center">
          <ThemeToggle />
          <button type="button" className="btn btn-ghost p-2" onClick={() => void logout()} disabled={logoutBusy} aria-label="로그아웃">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pt-5 pb-24 sm:px-6 md:pb-10">
        {logoutError && (
          // 스크롤 위치와 상관없이 보이도록 화면에 고정한다(사이드바의 로그아웃 버튼은 페이지 맨 아래에서도 누를 수 있다)
          <div
            role="alert"
            className="animate-fade-in fixed inset-x-3 top-3 z-40 mx-auto flex max-w-3xl flex-wrap items-start gap-3 rounded-xl border border-crit/50 bg-surface px-4 py-3 text-sm shadow-xl md:left-64"
          >
            <OctagonAlert size={18} className="mt-0.5 shrink-0 text-crit-ink" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-crit-ink">로그아웃하지 못했습니다. 아직 로그인된 상태입니다.</p>
              <p className="mt-1 text-ink-2">
                서버가 세션을 끝내지 못했습니다 ({logoutError}). 아래 버튼으로 다시 시도하세요. 계속 실패하고 다른 사람과 함께 쓰는 기기라면,
                브라우저 설정에서 이 사이트의 쿠키를 삭제해야 로그아웃됩니다.
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button type="button" className="btn btn-primary px-3 py-1.5" onClick={() => void logout()} disabled={logoutBusy}>
                {logoutBusy ? '시도 중…' : '다시 시도'}
              </button>
              <button type="button" className="btn px-3 py-1.5" onClick={clearLogoutError} disabled={logoutBusy}>
                로그인 유지
              </button>
            </div>
          </div>
        )}
        <Outlet />
      </main>

      {/* 모바일: 하단 탭 */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-3 border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="주 메뉴">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${isActive ? 'text-accent' : 'text-ink-3'}`
            }
          >
            <Icon size={20} aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
