import { ArrowDown, ArrowLeft, ArrowUp, CircleDashed, Download, FlaskConical, KeyRound, Pencil, RefreshCw, Trash2, WifiOff } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { MetricPoint, RangeKey } from '../api/types'
import { AgentInstructions, AgentKeyModal } from '../components/AgentKeyModal'
import { IncidentList } from '../components/IncidentList'
import { MetricChart, type SeriesDef } from '../components/MetricChart'
import { isLive } from '../components/ServerCard'
import { ServerFormModal } from '../components/ServerFormModal'
import { ConfirmDialog, DemoBadge, ErrorNote, RangeTabs, Spinner, StaleNote, StatusBadge } from '../components/ui'
import { useNow, usePolling } from '../hooks/usePolling'
import { formatBytes, formatDuration, formatPercent, formatRate, formatRelative } from '../lib/format'
import { toChartRows } from '../lib/series'

const POLL_MS: Record<RangeKey, number> = { '1m': 2000, '5m': 3000, '1h': 15000, '24h': 60000 }

function ValueTile({ label, value, sub, stale }: { label: string; value: ReactNode; sub?: ReactNode; stale: boolean }) {
  return (
    <div className={`card p-4 ${stale ? 'opacity-60' : ''}`}>
      <div className="text-xs font-medium text-ink-3">{label}</div>
      <div className="tabular mt-1 text-xl font-bold tracking-tight sm:text-2xl">{value}</div>
      {sub && <div className="tabular mt-0.5 truncate text-xs text-ink-3">{sub}</div>}
    </div>
  )
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  )
}

const pct = (v: number) => `${v.toFixed(0)}%`
const single = (key: string, label: string): SeriesDef[] => [{ key, label, color: 'var(--series-1)' }]

export function ServerDetailPage() {
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const now = useNow()
  const [range, setRange] = useState<RangeKey>('5m')

  const serverPoll = usePolling(() => api.server(id), 3000, [id])
  const metricsPoll = usePolling(() => api.metrics(id, range), POLL_MS[range], [id, range])
  const incidentsPoll = usePolling(() => api.incidents({ serverId: id, limit: 20 }), 5000, [id])

  const [editing, setEditing] = useState(false)
  const [confirm, setConfirm] = useState<'delete' | 'rotate' | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [newKey, setNewKey] = useState<string | null>(null)

  const series = metricsPoll.data
  const rows = useMemo(() => {
    const build = (pick: (p: MetricPoint) => Record<string, number>) =>
      series ? toChartRows(series.points, pick, series.bucket_seconds) : []
    return {
      cpu: build((p) => ({ cpu: p.cpu_percent })),
      mem: build((p) => ({ mem: p.mem_percent })),
      disk: build((p) => ({ disk: p.disk_percent })),
      net: build((p) => ({ sent: p.net_sent_rate, recv: p.net_recv_rate })),
    }
  }, [series])

  const server = serverPoll.data
  if (!server) {
    return (
      <div className="space-y-4">
        <Link to="/servers" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
          <ArrowLeft size={16} /> 서버 목록
        </Link>
        {serverPoll.error ? <ErrorNote message={serverPoll.error} /> : <Spinner />}
      </div>
    )
  }

  const live = isLive(server)
  const m = server.latest
  const domain: [number, number] = series ? [new Date(series.start).getTime(), new Date(series.end).getTime()] : [now - 300_000, now]
  const emptyMessage = metricsPoll.loading ? '불러오는 중…' : undefined

  const runAction = async () => {
    setBusy(true)
    setActionError(null)
    try {
      if (confirm === 'delete') {
        await api.deleteServer(server.id)
        navigate('/servers', { replace: true })
        return
      }
      const result = await api.rotateKey(server.id)
      setNewKey(result.agent_key)
      setConfirm(null)
      serverPoll.refresh()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '요청에 실패했습니다')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <Link to="/servers" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft size={16} aria-hidden /> 서버 목록
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl">{server.name}</h1>
            <StatusBadge status={server.status} size="lg" />
            {server.is_demo && <DemoBadge />}
          </div>
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-3">
            <div className="flex gap-1.5">
              <dt>주소</dt>
              <dd className="font-mono text-ink-2">{server.host}</dd>
            </div>
            {(server.os_name || server.reported_os) && (
              <div className="flex gap-1.5">
                <dt>운영체제</dt>
                <dd className="text-ink-2">
                  {server.os_name || server.reported_os}
                  {server.os_name && server.reported_os && server.reported_os !== server.os_name && ` (Agent 보고: ${server.reported_os})`}
                </dd>
              </div>
            )}
            <div className="flex gap-1.5">
              <dt>마지막 수신</dt>
              <dd className="tabular text-ink-2">{formatRelative(server.last_seen_at, now)}</dd>
            </div>
            {m && (
              <div className="flex gap-1.5">
                <dt>가동 시간</dt>
                <dd className="tabular text-ink-2">
                  {formatDuration(m.uptime_seconds)}
                  {!live && ' (마지막 보고 기준)'}
                </dd>
              </div>
            )}
          </dl>
          {server.description && <p className="mt-2 text-sm text-ink-2">{server.description}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <a className="btn" href={api.metricsCsvUrl(server.id, range)} download>
            <Download size={15} aria-hidden /> CSV
          </a>
          <button type="button" className="btn" onClick={() => setEditing(true)}>
            <Pencil size={15} aria-hidden /> 수정
          </button>
          <button type="button" className="btn hover:text-crit-ink" onClick={() => setConfirm('delete')}>
            <Trash2 size={15} aria-hidden /> 삭제
          </button>
        </div>
      </header>

      <StaleNote error={serverPoll.error ?? metricsPoll.error} />

      {server.is_demo && (
        <div className="flex items-center gap-2 rounded-xl border border-demo/40 bg-demo/10 px-4 py-2.5 text-sm">
          <FlaskConical size={16} className="shrink-0 text-demo" aria-hidden />
          이 서버는 가상 서버입니다. 아래 수치는 실제 측정값이 아니라 시뮬레이터가 만든 데모 데이터입니다.
        </div>
      )}
      {server.status === 'offline' && (
        <div className="flex items-start gap-2 rounded-xl border border-off/40 bg-off/10 px-4 py-2.5 text-sm" role="status">
          <WifiOff size={16} className="mt-0.5 shrink-0 text-off-ink" aria-hidden />
          <span>
            <strong>연결 끊김</strong> — {formatRelative(server.last_seen_at, now)} 이후 데이터가 들어오지 않습니다. 아래 수치는 현재 값이 아니라{' '}
            <strong>마지막으로 받은 값</strong>입니다.
          </span>
        </div>
      )}
      {server.status === 'pending' && (
        <div className="card animate-fade-in space-y-3 p-5">
          <div className="flex items-center gap-2 font-semibold">
            <CircleDashed size={18} className="text-off-ink" aria-hidden /> 아직 데이터를 받은 적이 없습니다
          </div>
          <AgentInstructions />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <ValueTile stale={!live} label="CPU" value={formatPercent(m?.cpu_percent)} sub={`기준 ${server.cpu_warn}% / ${server.cpu_crit}%`} />
        <ValueTile stale={!live} label="RAM" value={formatPercent(m?.mem_percent)}
          sub={m ? `${formatBytes(m.mem_used)} / ${formatBytes(m.mem_total)}` : `기준 ${server.mem_warn}% / ${server.mem_crit}%`} />
        <ValueTile stale={!live} label="디스크" value={formatPercent(m?.disk_percent)}
          sub={m ? `${formatBytes(m.disk_used)} / ${formatBytes(m.disk_total)}` : `기준 ${server.disk_warn}% / ${server.disk_crit}%`} />
        <ValueTile
          stale={!live}
          label="네트워크"
          value={
            m ? (
              <span className="flex flex-col text-base leading-snug sm:text-lg">
                <span className="inline-flex items-center gap-1">
                  <ArrowUp size={15} className="text-ink-3" aria-label="송신" /> {formatRate(m.net_sent_rate)}
                </span>
                <span className="inline-flex items-center gap-1">
                  <ArrowDown size={15} className="text-ink-3" aria-label="수신" /> {formatRate(m.net_recv_rate)}
                </span>
              </span>
            ) : (
              '-'
            )
          }
          sub={m ? `누적 ↑${formatBytes(m.net_sent_total)} ↓${formatBytes(m.net_recv_total)}` : undefined}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">
          사용량 추이
          {series && series.bucket_seconds > 0 && (
            <span className="ml-2 font-normal text-ink-3">({formatDuration(series.bucket_seconds)} 평균)</span>
          )}
        </h2>
        <RangeTabs value={range} onChange={setRange} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="CPU 사용률">
          <MetricChart rows={rows.cpu} series={single('cpu', 'CPU')} domain={domain} unit="percent" format={pct}
            thresholds={{ warn: server.cpu_warn, crit: server.cpu_crit }} emptyMessage={emptyMessage} />
        </ChartCard>
        <ChartCard title="RAM 사용률">
          <MetricChart rows={rows.mem} series={single('mem', 'RAM')} domain={domain} unit="percent" format={pct}
            thresholds={{ warn: server.mem_warn, crit: server.mem_crit }} emptyMessage={emptyMessage} />
        </ChartCard>
        <ChartCard title="디스크 사용률">
          <MetricChart rows={rows.disk} series={single('disk', '디스크')} domain={domain} unit="percent" format={pct}
            thresholds={{ warn: server.disk_warn, crit: server.disk_crit }} emptyMessage={emptyMessage} />
        </ChartCard>
        <ChartCard title="네트워크 송수신량">
          <MetricChart
            rows={rows.net}
            series={[
              { key: 'sent', label: '송신', color: 'var(--series-1)' },
              { key: 'recv', label: '수신', color: 'var(--series-2)' },
            ]}
            domain={domain}
            unit="auto"
            format={formatRate}
            emptyMessage={emptyMessage}
          />
        </ChartCard>
      </div>

      <section className="card overflow-hidden">
        <h2 className="border-b border-line px-4 py-3 text-sm font-semibold">이 서버의 장애 이력</h2>
        {incidentsPoll.data ? (
          <IncidentList incidents={incidentsPoll.data} now={now} showServer={false} />
        ) : incidentsPoll.error ? (
          <div className="p-4">
            <ErrorNote message={incidentsPoll.error} />
          </div>
        ) : (
          <Spinner />
        )}
      </section>

      {!server.is_demo && (
        <section className="card space-y-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <KeyRound size={16} aria-hidden /> Agent 연결
            </h2>
            <button type="button" className="btn px-2.5 py-1.5 text-xs" onClick={() => setConfirm('rotate')}>
              <RefreshCw size={13} aria-hidden /> 인증키 재발급
            </button>
          </div>
          <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
            <div className="flex gap-1.5">
              <dt className="text-ink-3">인증키</dt>
              <dd className="font-mono text-ink-2">{server.agent_key_prefix}…</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-ink-3">Agent 호스트명</dt>
              <dd className="font-mono text-ink-2">{server.reported_hostname ?? '-'}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-ink-3">Agent 버전</dt>
              <dd className="font-mono text-ink-2">{server.agent_version ?? '-'}</dd>
            </div>
          </dl>
          {server.status !== 'pending' && (
            <details className="text-sm">
              <summary className="cursor-pointer text-ink-2 hover:text-ink">Agent 실행 방법 보기</summary>
              <div className="mt-3">
                <AgentInstructions />
              </div>
            </details>
          )}
        </section>
      )}

      {editing && (
        <ServerFormModal
          server={server}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            serverPoll.refresh()
          }}
        />
      )}
      {newKey && <AgentKeyModal serverName={server.name} agentKey={newKey} onClose={() => setNewKey(null)} />}
      {confirm && (
        <ConfirmDialog
          title={confirm === 'delete' ? '서버 삭제' : 'Agent 인증키 재발급'}
          message={
            confirm === 'delete' ? (
              <>
                <strong className="text-ink">{server.name}</strong> 서버를 삭제합니다. 측정 기록과 장애 이력도 함께 삭제되며 되돌릴 수 없습니다.
              </>
            ) : (
              <>
                새 키를 발급하면 <strong className="text-ink">기존 키는 즉시 무효</strong>가 됩니다. 실행 중인 Agent 는 새 키로 다시 시작하기 전까지
                데이터를 보낼 수 없습니다.
              </>
            )
          }
          confirmLabel={confirm === 'delete' ? '삭제' : '재발급'}
          busy={busy}
          error={actionError}
          onConfirm={() => void runAction()}
          onClose={() => {
            setConfirm(null)
            setActionError(null)
          }}
        />
      )}
    </div>
  )
}
