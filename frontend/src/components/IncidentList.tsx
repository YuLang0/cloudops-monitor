import { Link } from 'react-router-dom'
import type { Incident, IncidentMetric } from '../api/types'
import { formatDateTime, formatDuration } from '../lib/format'
import { DemoBadge, SeverityBadge } from './ui'

const METRIC_LABELS: Record<IncidentMetric, string> = { cpu: 'CPU', memory: 'RAM', disk: '디스크', offline: '연결 끊김' }

function duration(incident: Incident, now: number): string {
  const end = incident.resolved_at ? new Date(incident.resolved_at).getTime() : now
  return formatDuration((end - new Date(incident.started_at).getTime()) / 1000)
}

interface Props {
  incidents: Incident[]
  now: number
  showServer?: boolean
  emptyMessage?: string
}

export function IncidentList({ incidents, now, showServer = true, emptyMessage = '기록된 장애가 없습니다' }: Props) {
  if (incidents.length === 0) {
    return <p className="py-8 text-center text-sm text-ink-3">{emptyMessage}</p>
  }
  return (
    <ul className="divide-y divide-line">
      {incidents.map((incident) => {
        const open = incident.resolved_at === null
        return (
          <li key={incident.id} className="animate-fade-in flex flex-col gap-1.5 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
              <SeverityBadge severity={incident.severity} />
              <span className="rounded bg-surface-2 px-1.5 py-0.5 text-xs font-medium text-ink-2">{METRIC_LABELS[incident.metric]}</span>
              {showServer && (
                <Link to={`/servers/${incident.server_id}`} className="truncate text-sm font-semibold text-ink hover:text-accent hover:underline">
                  {incident.server_name}
                </Link>
              )}
              {showServer && incident.is_demo && <DemoBadge />}
              <span className="w-full truncate text-xs text-ink-3 sm:w-auto">{incident.message}</span>
            </div>
            <div className="tabular flex shrink-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-3">
              <span title="시작 시각">{formatDateTime(incident.started_at)}</span>
              <span>
                {open ? (
                  <span className="font-semibold text-crit-ink">진행 중 · {duration(incident, now)}</span>
                ) : (
                  <span title={`해결: ${formatDateTime(incident.resolved_at as string)}`}>해결됨 · {duration(incident, now)} 지속</span>
                )}
              </span>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
