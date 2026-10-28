import { Link } from 'react-router-dom'
import type { Server } from '../api/types'
import { formatRelative } from '../lib/format'
import { DemoBadge, StatusBadge, StatusDot, UsageBar } from './ui'

export const isLive = (server: Server) => server.status === 'ok' || server.status === 'warning' || server.status === 'critical'

export function ServerCard({ server, now }: { server: Server; now: number }) {
  const live = isLive(server)
  const m = server.latest
  return (
    <Link
      to={`/servers/${server.id}`}
      className="card group animate-fade-in block p-4 hover:-translate-y-0.5 hover:border-accent/60 hover:shadow-md"
      style={{ transitionProperty: 'transform, border-color, box-shadow, background-color' }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <StatusDot status={server.status} />
            <span className="truncate font-semibold group-hover:text-accent">{server.name}</span>
          </div>
          <div className="mt-0.5 truncate font-mono text-xs text-ink-3">
            {server.host}
            {(server.os_name || server.reported_os) && ` · ${server.os_name || server.reported_os}`}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <StatusBadge status={server.status} />
          {server.is_demo && <DemoBadge />}
        </div>
      </div>

      <div className="mt-4 space-y-2.5">
        <UsageBar label="CPU" value={m?.cpu_percent ?? null} warn={server.cpu_warn} crit={server.cpu_crit} stale={!live} />
        <UsageBar label="RAM" value={m?.mem_percent ?? null} warn={server.mem_warn} crit={server.mem_crit} stale={!live} />
        <UsageBar label="디스크" value={m?.disk_percent ?? null} warn={server.disk_warn} crit={server.disk_crit} stale={!live} />
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-ink-3">
        <span>
          {server.status === 'pending'
            ? 'Agent 연결을 기다리는 중'
            : `${live ? '마지막 수신' : '마지막 수신(이후 끊김)'} · ${formatRelative(server.last_seen_at, now)}`}
        </span>
        {server.open_incident_count > 0 && (
          <span className="font-semibold text-crit-ink">진행 중 장애 {server.open_incident_count}건</span>
        )}
      </div>
    </Link>
  )
}
