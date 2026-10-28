import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatClock, formatDateTime } from '../lib/format'
import type { ChartRow } from '../lib/series'

export interface SeriesDef {
  key: string
  label: string
  color: string // CSS 변수 (예: 'var(--series-1)')
}

interface Props {
  rows: ChartRow[]
  series: SeriesDef[]
  /** x축 범위 [시작, 끝] (ms). 데이터가 없어도 축은 조회 범위 전체를 보여 준다 */
  domain: [number, number]
  /** 'percent' 는 y축을 0~100 으로 고정한다 */
  unit: 'percent' | 'auto'
  format: (value: number) => string
  thresholds?: { warn: number; crit: number }
  height?: number
  emptyMessage?: string
}

interface TooltipEntry {
  dataKey?: string | number
  value?: number | null
}

function ChartTooltip({
  active,
  payload,
  label,
  series,
  format,
}: {
  active?: boolean
  payload?: readonly TooltipEntry[]
  label?: number | string
  series: SeriesDef[]
  format: (value: number) => string
}) {
  const entries = (payload ?? []).filter((p) => typeof p.value === 'number')
  if (!active || entries.length === 0 || typeof label !== 'number') return null
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="tabular mb-1 text-ink-3">{formatDateTime(new Date(label).toISOString())}</div>
      {entries.map((entry) => {
        const def = series.find((s) => s.key === entry.dataKey)
        if (!def) return null
        return (
          <div key={def.key} className="flex items-center gap-2">
            <span className="h-0.5 w-3 rounded-full" style={{ background: def.color }} />
            <span className="text-ink-2">{def.label}</span>
            <span className="tabular ml-auto pl-3 font-semibold text-ink">{format(entry.value as number)}</span>
          </div>
        )
      })}
    </div>
  )
}

export function MetricChart({ rows, series, domain, unit, format, thresholds, height = 200, emptyMessage }: Props) {
  const spanMs = domain[1] - domain[0]
  // 시간 축 눈금은 조회 범위를 4등분한 지점에 고정한다(데이터 유무와 무관하게 일정)
  const xTicks = [0, 1, 2, 3, 4].map((i) => domain[0] + (spanMs * i) / 4)
  const hasData = rows.some((r) => series.some((s) => r[s.key] !== null && r[s.key] !== undefined))

  return (
    <div>
      {series.length > 1 && (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          {series.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={domain}
              ticks={xTicks}
              interval={0}
              allowDataOverflow
              tickFormatter={(t: number) => formatClock(t, spanMs <= 5 * 60_000)}
              tick={{ fill: 'var(--ink-3)', fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--line)' }}
              padding={{ left: 4, right: 20 }}
            />
            <YAxis
              domain={unit === 'percent' ? [0, 100] : [0, 'auto']}
              ticks={unit === 'percent' ? [0, 25, 50, 75, 100] : undefined}
              tickFormatter={(v: number) => format(v).replace(' ', ' ')}
              tick={{ fill: 'var(--ink-3)', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={unit === 'percent' ? 44 : 76}
            />
            <Tooltip
              isAnimationActive={false}
              cursor={{ stroke: 'var(--ink-3)', strokeWidth: 1, strokeDasharray: '3 3' }}
              content={(props) => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload as readonly TooltipEntry[] | undefined}
                  label={props.label as number | string | undefined}
                  series={series}
                  format={format}
                />
              )}
            />
            {thresholds && (
              <>
                <ReferenceLine
                  y={thresholds.warn}
                  stroke="var(--warn)"
                  strokeDasharray="4 4"
                  strokeOpacity={0.8}
                  label={{ value: `경고 ${thresholds.warn}%`, position: 'insideTopRight', fill: 'var(--warn-ink)', fontSize: 10 }}
                />
                <ReferenceLine
                  y={thresholds.crit}
                  stroke="var(--crit)"
                  strokeDasharray="4 4"
                  strokeOpacity={0.8}
                  label={{ value: `장애 ${thresholds.crit}%`, position: 'insideTopRight', fill: 'var(--crit-ink)', fontSize: 10 }}
                />
              </>
            )}
            {series.map((s) => (
              <Line
                key={s.key}
                dataKey={s.key}
                name={s.label}
                type="monotone"
                stroke={s.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--surface)' }}
                connectNulls={false} // 수신이 끊긴 구간은 선을 잇지 않는다
                isAnimationActive={false} // 몇 초마다 갱신되므로 매번 다시 그리는 애니메이션은 끈다
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
        {!hasData && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-ink-3">
            {emptyMessage ?? '이 범위에 수신된 데이터가 없습니다'}
          </div>
        )}
      </div>
    </div>
  )
}
