const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']

export function formatBytes(bytes: number, digits = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '-'
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < BYTE_UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${unit === 0 ? value.toFixed(0) : value.toFixed(digits)} ${BYTE_UNITS[unit]}`
}

export function formatRate(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '-' : `${value.toFixed(digits)}%`
}

/** 초 단위 기간을 "3일 4시간", "12분 5초"처럼 큰 단위 두 개로 표시 */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds))
  const parts: [number, string][] = [
    [Math.floor(s / 86400), '일'],
    [Math.floor((s % 86400) / 3600), '시간'],
    [Math.floor((s % 3600) / 60), '분'],
    [s % 60, '초'],
  ]
  const first = parts.findIndex(([n]) => n > 0)
  if (first === -1) return '0초'
  return parts
    .slice(first, first + 2)
    .filter(([n]) => n > 0)
    .map(([n, unit]) => `${n}${unit}`)
    .join(' ')
}

export function formatRelative(iso: string | null, now: number = Date.now()): string {
  if (!iso) return '수신 기록 없음'
  const seconds = Math.floor((now - new Date(iso).getTime()) / 1000)
  if (seconds < 2) return '방금 전'
  if (seconds < 60) return `${seconds}초 전`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`
  return `${Math.floor(seconds / 86400)}일 전`
}

const pad = (n: number) => String(n).padStart(2, '0')

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function formatClock(ms: number, withSeconds: boolean): string {
  const d = new Date(ms)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}${withSeconds ? `:${pad(d.getSeconds())}` : ''}`
}
