import { FlaskConical, Plus, ServerOff } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { RangeKey, Server } from '../api/types'
import { AgentKeyModal } from '../components/AgentKeyModal'
import { IncidentList } from '../components/IncidentList'
import { MetricChart } from '../components/MetricChart'
import { ServerCard } from '../components/ServerCard'
import { ServerFormModal } from '../components/ServerFormModal'
import { ErrorNote, PageHeader, RangeTabs, Spinner, StaleNote } from '../components/ui'
import { useApp } from '../context/AppContext'
import { useNow, usePolling } from '../hooks/usePolling'
import { formatPercent } from '../lib/format'
import { toChartRows } from '../lib/series'

function StatTile({ label, value, sub, tone, wide }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string; wide?: boolean }) {
  return (
    <div className={`card p-4 ${wide ? 'col-span-2 sm:col-span-1' : ''}`}>
      <div className="text-xs font-medium text-ink-3">{label}</div>
      <div className={`tabular mt-1 text-2xl font-bold tracking-tight ${tone ?? 'text-ink'}`}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-ink-3">{sub}</div>}
    </div>
  )
}

export function DashboardPage() {
  const { config } = useApp()
  const now = useNow()
  const [range, setRange] = useState<RangeKey>('5m')
  const summary = usePolling(api.summary, 3000)
  const servers = usePolling(api.servers, 3000)
  const fleet = usePolling(() => api.fleetSeries(range), 5000, [range])

  const [showForm, setShowForm] = useState(false)
  const [newKey, setNewKey] = useState<{ server: Server; key: string } | null>(null)
  const [demoBusy, setDemoBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const refreshAll = () => {
    summary.refresh()
    servers.refresh()
    fleet.refresh()
  }

  const demoAction = async (action: () => Promise<unknown>) => {
    setDemoBusy(true)
    setActionError(null)
    try {
      await action()
      refreshAll()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '요청에 실패했습니다')
    } finally {
      setDemoBusy(false)
    }
  }

  const fleetRows = useMemo(
    () => (fleet.data ? toChartRows(fleet.data.points, (p) => ({ cpu: p.avg_cpu, mem: p.avg_mem }), fleet.data.bucket_seconds) : []),
    [fleet.data],
  )

  const s = summary.data
  const list = servers.data
  if (!s || !list) {
    return summary.error || servers.error ? <ErrorNote message={summary.error ?? servers.error} /> : <Spinner />
  }

  const modals = (
    <>
      {showForm && (
        <ServerFormModal
          onClose={() => setShowForm(false)}
          onSaved={(server, key) => {
            setShowForm(false)
            if (key) setNewKey({ server, key })
            refreshAll()
          }}
        />
      )}
      {newKey && <AgentKeyModal serverName={newKey.server.name} agentKey={newKey.key} onClose={() => setNewKey(null)} />}
    </>
  )

  if (s.total === 0) {
    return (
      <>
        <PageHeader title="대시보드" />
        <div className="card animate-fade-in mx-auto max-w-xl p-8 text-center">
          <ServerOff size={40} className="mx-auto text-ink-3" aria-hidden />
          <h2 className="mt-4 text-lg font-semibold">등록된 서버가 없습니다</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-2">
            실제 서버를 등록하고 Agent 를 연결하거나, 먼저 가상 서버로 화면을 살펴볼 수 있습니다.
            <br />
            가상 서버에는 항상 <strong>데모</strong> 표시가 붙으며 실제 데이터와 섞이지 않습니다.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            {config?.demo_mode && (
              <button type="button" className="btn" disabled={demoBusy} onClick={() => void demoAction(api.seedDemo)}>
                <FlaskConical size={16} aria-hidden /> {demoBusy ? '생성 중…' : '데모 서버 4대 추가'}
              </button>
            )}
            <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
              <Plus size={16} aria-hidden /> 서버 등록
            </button>
          </div>
          <div className="mt-4">
            <ErrorNote message={actionError} />
          </div>
        </div>
        {modals}
      </>
    )
  }

  const domain: [number, number] = fleet.data
    ? [new Date(fleet.data.start).getTime(), new Date(fleet.data.end).getTime()]
    : [now - 300_000, now]

  return (
    <>
      <PageHeader
        title="대시보드"
        subtitle="3초마다 자동 갱신"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            <Plus size={16} aria-hidden /> 서버 등록
          </button>
        }
      />

      <div className="space-y-5">
        <StaleNote error={summary.error ?? servers.error} />
        <ErrorNote message={actionError} />

        {s.demo > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-demo/40 bg-demo/10 px-4 py-2.5 text-sm">
            <span className="flex items-center gap-2 text-ink">
              <FlaskConical size={16} className="shrink-0 text-demo" aria-hidden />
              <span>
                <strong>데모 데이터 포함</strong> — 서버 {s.total}대 중 {s.demo}대는 시뮬레이션된 가상 서버입니다.
                {!config?.demo_mode && ' (데모 모드가 꺼져 있어 가상 서버는 갱신되지 않습니다)'}
              </span>
            </span>
            <button type="button" className="btn px-2.5 py-1 text-xs" disabled={demoBusy} onClick={() => void demoAction(api.removeDemo)}>
              {demoBusy ? '제거 중…' : '데모 서버 제거'}
            </button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
          <StatTile wide label="전체 서버" value={s.total} sub={s.pending > 0 ? `데이터 대기 ${s.pending}대` : `수신 중 ${s.reporting}대`} />
          <StatTile label="정상" value={s.ok} tone={s.ok > 0 ? 'text-ok-ink' : 'text-ink-3'} />
          <StatTile label="경고" value={s.warning} tone={s.warning > 0 ? 'text-warn-ink' : 'text-ink-3'} />
          <StatTile label="장애" value={s.critical} tone={s.critical > 0 ? 'text-crit-ink' : 'text-ink-3'} />
          <StatTile label="연결 끊김" value={s.offline} tone={s.offline > 0 ? 'text-off-ink' : 'text-ink-3'} />
          <StatTile label="평균 CPU" value={formatPercent(s.avg_cpu)} sub={s.reporting > 0 ? `수신 중 ${s.reporting}대 기준` : '수신 중인 서버 없음'} />
          <StatTile label="평균 RAM" value={formatPercent(s.avg_mem)} sub={s.reporting > 0 ? `수신 중 ${s.reporting}대 기준` : '수신 중인 서버 없음'} />
        </div>

        <section className="card p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">전체 평균 사용률</h2>
            <RangeTabs value={range} onChange={setRange} />
          </div>
          <MetricChart
            rows={fleetRows}
            series={[
              { key: 'cpu', label: '평균 CPU', color: 'var(--series-1)' },
              { key: 'mem', label: '평균 RAM', color: 'var(--series-2)' },
            ]}
            domain={domain}
            unit="percent"
            format={(v) => `${v.toFixed(0)}%`}
            height={220}
            emptyMessage={fleet.loading ? '불러오는 중…' : undefined}
          />
        </section>

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">서버 ({list.length})</h2>
            <Link to="/servers" className="text-xs text-accent hover:underline">
              서버 관리 →
            </Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {list.map((server) => (
              <ServerCard key={server.id} server={server} now={now} />
            ))}
          </div>
        </section>

        <section className="card overflow-hidden">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-sm font-semibold">
              최근 장애 {s.open_incidents > 0 && <span className="ml-1 text-crit-ink">· 진행 중 {s.open_incidents}건</span>}
            </h2>
            <Link to="/incidents" className="text-xs text-accent hover:underline">
              전체 이력 →
            </Link>
          </div>
          <IncidentList incidents={s.recent_incidents} now={now} />
        </section>
      </div>
      {modals}
    </>
  )
}
