import { Download } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api/client'
import { IncidentList } from '../components/IncidentList'
import { ErrorNote, PageHeader, Spinner, StaleNote } from '../components/ui'
import { useNow, usePolling } from '../hooks/usePolling'

type State = 'all' | 'open' | 'resolved'
const TABS: { key: State; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'open', label: '진행 중' },
  { key: 'resolved', label: '해결됨' },
]

export function IncidentsPage() {
  const now = useNow()
  const [state, setState] = useState<State>('all')
  const { data, error } = usePolling(() => api.incidents({ state, limit: 200 }), 5000, [state])

  return (
    <>
      <PageHeader
        title="장애 이력"
        subtitle="기준 초과와 연결 끊김의 시작·해결 시각이 기록됩니다. 같은 장애가 이어지는 동안에는 새 기록이 만들어지지 않습니다."
        actions={
          <a className="btn" href={api.incidentsCsvUrl(state)} download>
            <Download size={15} aria-hidden /> CSV 내보내기
          </a>
        }
      />
      <div className="space-y-4">
        <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5" role="group" aria-label="상태 필터">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              aria-pressed={state === tab.key}
              onClick={() => setState(tab.key)}
              className={`cursor-pointer rounded-md px-3 py-1 text-xs font-medium transition-all duration-150 ${
                state === tab.key ? 'bg-accent text-accent-ink shadow-sm' : 'text-ink-2 hover:text-ink'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <StaleNote error={data ? error : null} />
        <div className="card overflow-hidden">
          {data ? (
            <IncidentList incidents={data} now={now} emptyMessage={state === 'open' ? '진행 중인 장애가 없습니다' : '기록된 장애가 없습니다'} />
          ) : error ? (
            <div className="p-4">
              <ErrorNote message={error} />
            </div>
          ) : (
            <Spinner />
          )}
        </div>
        {data && data.length >= 200 && <p className="text-xs text-ink-3">최근 200건만 표시합니다. 전체 기록은 CSV 로 내보내세요.</p>}
      </div>
    </>
  )
}
