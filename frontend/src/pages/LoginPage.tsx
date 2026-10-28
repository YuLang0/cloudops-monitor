import { ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Logo, ThemeToggle } from '../components/Layout'
import { ErrorNote } from '../components/ui'
import { useApp } from '../context/AppContext'

export function LoginPage() {
  const { login, register, config } = useApp()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canRegister = config?.allow_registration !== false

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await (mode === 'login' ? login(email, password) : register(email, password))
    } catch (err) {
      setError(err instanceof Error ? err.message : '요청에 실패했습니다')
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <div className="absolute top-3 right-3">
        <ThemeToggle />
      </div>
      <div className="animate-fade-in w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <Logo />
        </div>
        <div className="card p-6">
          {canRegister && (
            <div className="mb-5 grid grid-cols-2 rounded-lg border border-line bg-surface-2 p-0.5 text-sm font-medium">
              {(['login', 'register'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setMode(m)
                    setError(null)
                  }}
                  className={`cursor-pointer rounded-md py-1.5 transition-all ${mode === m ? 'bg-accent text-accent-ink shadow-sm' : 'text-ink-2 hover:text-ink'}`}
                >
                  {m === 'login' ? '로그인' : '회원가입'}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label" htmlFor="email">
                이메일
              </label>
              <input id="email" className="input" type="email" required autoComplete="email" autoFocus value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <label className="label" htmlFor="password">
                비밀번호 {mode === 'register' && <span className="text-ink-3">(8자 이상)</span>}
              </label>
              <input id="password" className="input" type="password" required minLength={8} maxLength={128}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password}
                onChange={(e) => setPassword(e.target.value)} />
            </div>
            <ErrorNote message={error} />
            <button type="submit" className="btn btn-primary w-full py-2.5" disabled={busy}>
              {busy ? '처리 중…' : mode === 'login' ? '로그인' : '계정 만들기'}
            </button>
          </form>
        </div>
        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-ink-3">
          <ShieldCheck size={14} aria-hidden />
          비밀번호는 Argon2id 해시로만 저장되고, 세션은 httpOnly 쿠키로 관리됩니다
        </p>
      </div>
    </div>
  )
}
