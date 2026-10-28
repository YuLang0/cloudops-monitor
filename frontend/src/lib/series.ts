export type ChartRow = { t: number } & Record<string, number | null>

/** 원본 샘플 간격(중앙값)을 추정한다. 표본이 부족하면 fallback 을 쓴다. */
export function medianStepMs(times: number[], fallbackMs = 5000): number {
  if (times.length < 3) return fallbackMs
  const deltas: number[] = []
  for (let i = 1; i < times.length; i += 1) deltas.push(times[i] - times[i - 1])
  deltas.sort((a, b) => a - b)
  return Math.max(1000, deltas[Math.floor(deltas.length / 2)])
}

/**
 * 데이터가 끊긴 구간에 null 행을 끼워 넣는다.
 * 이렇게 하지 않으면 그래프가 끊긴 구간을 직선으로 이어 "계속 수신 중이었던 것처럼" 보인다.
 */
export function withGaps(rows: ChartRow[], stepMs: number, tolerance = 2.5): ChartRow[] {
  if (rows.length === 0) return rows
  const keys = Object.keys(rows[0]).filter((k) => k !== 't')
  const out: ChartRow[] = []
  for (let i = 0; i < rows.length; i += 1) {
    if (i > 0 && rows[i].t - rows[i - 1].t > stepMs * tolerance) {
      const gap: ChartRow = { t: rows[i - 1].t + stepMs }
      for (const k of keys) gap[k] = null
      out.push(gap)
    }
    out.push(rows[i])
  }
  return out
}

/** API 응답 points → 차트 행. bucketSeconds 가 0(원본)이면 간격을 추정한다. */
export function toChartRows<P extends { ts: string }>(
  points: P[],
  pick: (p: P) => Record<string, number>,
  bucketSeconds: number,
): ChartRow[] {
  const rows = points.map((p) => ({ t: new Date(p.ts).getTime(), ...pick(p) }) as ChartRow)
  const step = bucketSeconds > 0 ? bucketSeconds * 1000 : medianStepMs(rows.map((r) => r.t))
  return withGaps(rows, step)
}
