import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Server } from '../api/types'
import { AgentKeyModal } from '../components/AgentKeyModal'
import { isLive } from '../components/ServerCard'
import { ServerFormModal } from '../components/ServerFormModal'
import { ConfirmDialog, DemoBadge, ErrorNote, PageHeader, Spinner, StaleNote, StatusBadge } from '../components/ui'
import { useNow, usePolling } from '../hooks/usePolling'
import { formatPercent, formatRelative } from '../lib/format'

export function ServersPage() {
  const now = useNow()
  const { data: servers, error, refresh } = usePolling(api.servers, 3000)
  const [editing, setEditing] = useState<Server | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Server | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [newKey, setNewKey] = useState<{ server: Server; key: string } | null>(null)

  const confirmDelete = async () => {
    if (!deleting) return
    setDeleteBusy(true)
    setDeleteError(null)
    try {
      await api.deleteServer(deleting.id)
      setDeleting(null)
      refresh()
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : '삭제하지 못했습니다')
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="서버"
        subtitle="서버를 등록·수정·삭제하고 알림 기준을 설정합니다"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
            <Plus size={16} aria-hidden /> 서버 등록
          </button>
        }
      />
      <div className="space-y-4">
        <StaleNote error={servers ? error : null} />
        {!servers ? (
          error ? <ErrorNote message={error} /> : <Spinner />
        ) : servers.length === 0 ? (
          <div className="card p-10 text-center text-sm text-ink-3">등록된 서버가 없습니다. 오른쪽 위의 “서버 등록”으로 시작하세요.</div>
        ) : (
          <div className="card overflow-hidden">
            <div className="hidden grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_7rem_4rem_4rem_4rem_7rem_5rem] gap-3 border-b border-line bg-surface-2 px-4 py-2 text-xs font-medium text-ink-3 lg:grid">
              <span>이름</span>
              <span>주소 / 운영체제</span>
              <span>상태</span>
              <span className="text-right">CPU</span>
              <span className="text-right">RAM</span>
              <span className="text-right">디스크</span>
              <span>마지막 수신</span>
              <span />
            </div>
            <ul className="divide-y divide-line">
              {servers.map((server) => {
                const live = isLive(server)
                const m = server.latest
                const valueClass = `tabular text-right text-sm ${live ? 'text-ink' : 'text-ink-3'}`
                return (
                  <li
                    key={server.id}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-4 py-3 transition-colors hover:bg-surface-2/60 lg:grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_7rem_4rem_4rem_4rem_7rem_5rem]"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <Link to={`/servers/${server.id}`} className="truncate font-semibold hover:text-accent hover:underline">
                        {server.name}
                      </Link>
                      {server.is_demo && <DemoBadge />}
                    </div>
                    <div className="order-3 col-span-2 min-w-0 truncate text-xs text-ink-3 lg:order-none lg:col-span-1">
                      <span className="font-mono">{server.host}</span>
                      {(server.os_name || server.reported_os) && ` · ${server.os_name || server.reported_os}`}
                    </div>
                    <div className="justify-self-end lg:justify-self-start">
                      <StatusBadge status={server.status} />
                    </div>
                    {/* 모바일에서는 수치 세 개를 한 줄로 */}
                    <div className="order-4 col-span-2 flex gap-4 text-xs text-ink-3 lg:hidden">
                      <span>CPU {formatPercent(m?.cpu_percent, 0)}</span>
                      <span>RAM {formatPercent(m?.mem_percent, 0)}</span>
                      <span>디스크 {formatPercent(m?.disk_percent, 0)}</span>
                      <span className="ml-auto">{formatRelative(server.last_seen_at, now)}</span>
                    </div>
                    <span className={`hidden lg:block ${valueClass}`}>{formatPercent(m?.cpu_percent, 0)}</span>
                    <span className={`hidden lg:block ${valueClass}`}>{formatPercent(m?.mem_percent, 0)}</span>
                    <span className={`hidden lg:block ${valueClass}`}>{formatPercent(m?.disk_percent, 0)}</span>
                    <span className="tabular hidden text-xs text-ink-3 lg:block">{formatRelative(server.last_seen_at, now)}</span>
                    <div className="order-5 col-span-2 flex justify-end gap-1 lg:order-none lg:col-span-1">
                      <button type="button" className="btn btn-ghost p-1.5" onClick={() => setEditing(server)} aria-label={`${server.name} 수정`} title="수정">
                        <Pencil size={15} />
                      </button>
                      <button type="button" className="btn btn-ghost p-1.5 hover:text-crit-ink" onClick={() => setDeleting(server)} aria-label={`${server.name} 삭제`} title="삭제">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </div>

      {editing && (
        <ServerFormModal
          server={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={(server, key) => {
            setEditing(null)
            if (key) setNewKey({ server, key })
            refresh()
          }}
        />
      )}
      {newKey && <AgentKeyModal serverName={newKey.server.name} agentKey={newKey.key} onClose={() => setNewKey(null)} />}
      {deleting && (
        <ConfirmDialog
          title="서버 삭제"
          message={
            <>
              <strong className="text-ink">{deleting.name}</strong> 서버를 삭제합니다. 이 서버의 측정 기록과 장애 이력도 함께 삭제되며 되돌릴 수
              없습니다.
            </>
          }
          confirmLabel="삭제"
          busy={deleteBusy}
          error={deleteError}
          onConfirm={() => void confirmDelete()}
          onClose={() => setDeleting(null)}
        />
      )}
    </>
  )
}
