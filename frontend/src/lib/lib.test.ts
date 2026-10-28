import { describe, expect, it } from 'vitest'
import { formatBytes, formatDuration, formatPercent, formatRate, formatRelative } from './format'
import { medianStepMs, toChartRows, withGaps } from './series'

describe('format', () => {
  it('formats bytes with binary units', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1023)).toBe('1023 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(8 * 1024 ** 3)).toBe('8.0 GB')
    expect(formatBytes(-1)).toBe('-')
    expect(formatRate(1536)).toBe('1.5 KB/s')
  })

  it('formats percent and missing values', () => {
    expect(formatPercent(12.345)).toBe('12.3%')
    expect(formatPercent(null)).toBe('-')
  })

  it('formats durations using the two largest units', () => {
    expect(formatDuration(0)).toBe('0초')
    expect(formatDuration(59)).toBe('59초')
    expect(formatDuration(125)).toBe('2분 5초')
    expect(formatDuration(3600)).toBe('1시간')
    expect(formatDuration(3 * 86400 + 4 * 3600 + 30)).toBe('3일 4시간')
  })

  it('formats relative time', () => {
    const now = Date.parse('2026-01-01T00:10:00Z')
    expect(formatRelative(null, now)).toBe('수신 기록 없음')
    expect(formatRelative('2026-01-01T00:09:59Z', now)).toBe('방금 전')
    expect(formatRelative('2026-01-01T00:09:30Z', now)).toBe('30초 전')
    expect(formatRelative('2026-01-01T00:05:00Z', now)).toBe('5분 전')
    expect(formatRelative('2025-12-30T00:10:00Z', now)).toBe('2일 전')
  })
})

describe('series', () => {
  it('estimates the sampling step from the median delta', () => {
    expect(medianStepMs([0, 5000, 10000, 15000, 80000])).toBe(5000)
    expect(medianStepMs([0, 5000])).toBe(5000) // 표본 부족 → fallback
  })

  it('inserts a null row where data stopped, and nowhere else', () => {
    const rows = [
      { t: 0, cpu: 10 },
      { t: 5000, cpu: 20 },
      { t: 60000, cpu: 30 }, // 55초 공백
      { t: 65000, cpu: 40 },
    ]
    const out = withGaps(rows, 5000)
    expect(out).toHaveLength(5)
    expect(out[2]).toEqual({ t: 10000, cpu: null })
    expect(out.filter((r) => r.cpu === null)).toHaveLength(1)
  })

  it('does not insert gaps for regular jitter', () => {
    const rows = [0, 5200, 9900, 15400].map((t) => ({ t, cpu: 1 }))
    expect(withGaps(rows, 5000)).toHaveLength(4)
  })

  it('converts API points to chart rows using the bucket size', () => {
    const points = [
      { ts: '2026-01-01T00:00:00Z', cpu_percent: 1 },
      { ts: '2026-01-01T00:05:00Z', cpu_percent: 2 },
      { ts: '2026-01-01T00:30:00Z', cpu_percent: 3 },
    ]
    const rows = toChartRows(points, (p) => ({ cpu: p.cpu_percent }), 300)
    expect(rows.map((r) => r.cpu)).toEqual([1, 2, null, 3])
    expect(toChartRows([], () => ({}), 0)).toEqual([])
  })
})
