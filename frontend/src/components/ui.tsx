import {
  CircleCheck,
  CircleDashed,
  FlaskConical,
  LoaderCircle,
  OctagonAlert,
  TriangleAlert,
  WifiOff,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import type { RangeKey, ServerStatus, Severity } from '../api/types'

// 상태는 색만으로 구분하지 않고 항상 아이콘 + 글자를 함께 쓴다(색각 이상·흑백 화면 대응)
export const STATUS_META: Record<ServerStatus, { label: string; icon: LucideIcon; text: string; dot: string; tint: string }> = {
  ok: { label: '정상', icon: CircleCheck, text: 'text-ok-ink', dot: 'bg-ok', tint: 'bg-ok/10 border-ok/30' },
  warning: { label: '경고', icon: TriangleAlert, text: 'text-warn-ink', dot: 'bg-warn', tint: 'bg-warn/10 border-warn/30' },
  critical: { label: '장애', icon: OctagonAlert, text: 'text-crit-ink', dot: 'bg-crit', tint: 'bg-crit/10 border-crit/30' },
  offline: { label: '연결 끊김', icon: WifiOff, text: 'text-off-ink', dot: 'bg-off', tint: 'bg-off/10 border-off/30' },
  pending: { label: '데이터 대기', icon: CircleDashed, text: 'text-off-ink', dot: 'bg-off', tint: 'bg-off/10 border-off/30' },
}

export function StatusBadge({ status, size = 'md' }: { status: ServerStatus; size?: 'md' | 'lg' }) {
  const meta = STATUS_META[status]
  const Icon = meta.icon
  const sizing = size === 'lg' ? 'px-3 py-1.5 text-sm' : 'px-2 py-0.5 text-xs'
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border font-semibold whitespace-nowrap ${sizing} ${meta.text} ${meta.tint}`}
    >
      <Icon size={size === 'lg' ? 16 : 13} strokeWidth={2.25} aria-hidden />
      {meta.label}
    </span>
  )
}

export function StatusDot({ status }: { status: ServerStatus }) {
  const live = status === 'ok' || status === 'warning' || status === 'critical'
  return (
    <span className="relative inline-flex h-2.5 w-2.5 shrink-0" aria-hidden>
      {live && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-40 ${STATUS_META[status].dot}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${STATUS_META[status].dot}`} />
    </span>
  )
}

export function DemoBadge() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-demo/40 bg-demo/10 px-2 py-0.5 text-xs font-semibold whitespace-nowrap text-demo"
      title="실제 서버가 아닌 시뮬레이션 데이터입니다"
    >
      <FlaskConical size={12} aria-hidden />
      데모
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const critical = severity === 'critical'
  const Icon = critical ? OctagonAlert : TriangleAlert
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${
        critical ? 'border-crit/30 bg-crit/10 text-crit-ink' : 'border-warn/30 bg-warn/10 text-warn-ink'
      }`}
    >
      <Icon size={13} aria-hidden />
      {critical ? '장애' : '경고'}
    </span>
  )
}

export function Spinner({ label = '불러오는 중…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-3" role="status">
      <LoaderCircle size={18} className="animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-crit/30 bg-crit/10 px-3 py-2 text-sm whitespace-pre-line text-crit-ink">
      <OctagonAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  )
}

/** 폴링이 실패하고 있을 때: 화면의 값이 오래됐을 수 있음을 알린다 */
export function StaleNote({ error }: { error: string | null }) {
  if (!error) return null
  return <ErrorNote message={`최신 데이터를 가져오지 못했습니다. 화면의 값이 오래됐을 수 있습니다.\n(${error})`} />
}

const RANGE_LABELS: Record<RangeKey, string> = { '1m': '1분', '5m': '5분', '1h': '1시간', '24h': '24시간' }

export function RangeTabs({ value, onChange }: { value: RangeKey; onChange: (r: RangeKey) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5" role="group" aria-label="조회 범위">
      {(Object.keys(RANGE_LABELS) as RangeKey[]).map((key) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={`cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-all duration-150 ${
            value === key ? 'bg-accent text-accent-ink shadow-sm' : 'text-ink-2 hover:text-ink'
          }`}
        >
          {RANGE_LABELS[key]}
        </button>
      ))}
    </div>
  )
}

/** 사용률 막대. 기준(warn/crit)을 넘으면 색이 바뀌고, stale 이면 회색으로 흐려진다 */
export function UsageBar({
  label,
  value,
  warn,
  crit,
  stale,
}: {
  label: string
  value: number | null
  warn: number
  crit: number
  stale: boolean
}) {
  const color = value === null || stale ? 'bg-off' : value >= crit ? 'bg-crit' : value >= warn ? 'bg-warn' : 'bg-accent'
  return (
    <div className={stale ? 'opacity-60' : ''}>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-ink-3">{label}</span>
        <span className="tabular font-semibold text-ink">{value === null ? '-' : `${value.toFixed(0)}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
        <div
          className={`h-full rounded-full transition-[width,background-color] duration-700 ease-out ${color}`}
          style={{ width: `${Math.min(100, Math.max(0, value ?? 0))}%` }}
        />
      </div>
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-4" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
        className={`card animate-pop-in max-h-[92vh] w-full overflow-y-auto rounded-b-none sm:rounded-b-xl ${wide ? 'sm:max-w-2xl' : 'sm:max-w-lg'}`}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button type="button" className="btn btn-ghost -mr-2 p-1.5" onClick={onClose} aria-label="닫기">
            <X size={18} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  title: string
  message: ReactNode
  confirmLabel: string
  busy: boolean
  error: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <Modal title={title} onClose={onClose}>
      <div className="space-y-4">
        <div className="text-sm leading-relaxed text-ink-2">{message}</div>
        <ErrorNote message={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? '처리 중…' : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight sm:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
