import { useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { Server, ServerInput } from '../api/types'
import { ErrorNote, Modal } from './ui'

const DEFAULTS: ServerInput = {
  name: '',
  host: '',
  os_name: '',
  description: '',
  cpu_warn: 80,
  cpu_crit: 95,
  mem_warn: 80,
  mem_crit: 95,
  disk_warn: 85,
  disk_crit: 95,
}

const THRESHOLD_ROWS = [
  { label: 'CPU', warn: 'cpu_warn', crit: 'cpu_crit' },
  { label: 'RAM', warn: 'mem_warn', crit: 'mem_crit' },
  { label: '디스크', warn: 'disk_warn', crit: 'disk_crit' },
] as const

function toInput(server: Server): ServerInput {
  const { name, host, os_name, description, cpu_warn, cpu_crit, mem_warn, mem_crit, disk_warn, disk_crit } = server
  return { name, host, os_name, description, cpu_warn, cpu_crit, mem_warn, mem_crit, disk_warn, disk_crit }
}

interface Props {
  /** 넘기면 수정, 없으면 신규 등록 */
  server?: Server
  onClose: () => void
  /** 신규 등록이면 agentKey 가 함께 온다(이때 한 번만 볼 수 있다) */
  onSaved: (server: Server, agentKey?: string) => void
}

export function ServerFormModal({ server, onClose, onSaved }: Props) {
  const [form, setForm] = useState<ServerInput>(server ? toInput(server) : DEFAULTS)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = <K extends keyof ServerInput>(key: K, value: ServerInput[K]) => setForm((f) => ({ ...f, [key]: value }))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    // 서버에서도 똑같이 검증하지만, 흔한 실수는 요청 전에 바로 알려 준다
    const bad = THRESHOLD_ROWS.find((r) => form[r.warn] >= form[r.crit])
    if (bad) {
      setError(`${bad.label} 경고 기준은 장애 기준보다 낮아야 합니다`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (server) {
        onSaved(await api.updateServer(server.id, form))
      } else {
        const created = await api.createServer(form)
        onSaved(created.server, created.agent_key)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '저장하지 못했습니다')
      setBusy(false)
    }
  }

  return (
    <Modal title={server ? '서버 수정' : '서버 등록'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="sf-name">
              서버 이름 *
            </label>
            <input id="sf-name" className="input" required maxLength={64} autoFocus value={form.name}
              onChange={(e) => set('name', e.target.value)} placeholder="web-01" />
          </div>
          <div>
            <label className="label" htmlFor="sf-host">
              IP 주소 또는 호스트명 *
            </label>
            <input id="sf-host" className="input font-mono" required maxLength={253} value={form.host}
              onChange={(e) => set('host', e.target.value)} placeholder="192.168.0.10" />
          </div>
          <div>
            <label className="label" htmlFor="sf-os">
              운영체제
            </label>
            <input id="sf-os" className="input" maxLength={64} value={form.os_name}
              onChange={(e) => set('os_name', e.target.value)} placeholder="Ubuntu 24.04 LTS" />
          </div>
          <div>
            <label className="label" htmlFor="sf-desc">
              설명
            </label>
            <input id="sf-desc" className="input" maxLength={255} value={form.description}
              onChange={(e) => set('description', e.target.value)} placeholder="용도, 위치 등" />
          </div>
        </div>
        <p className="-mt-2 text-xs text-ink-3">
          주소는 표시용 정보입니다. 모니터링 서버가 이 주소로 접속하지 않으며, 측정값은 해당 서버에 설치한 Agent 가 보내 줍니다.
        </p>

        <fieldset className="rounded-lg border border-line p-3">
          <legend className="px-1 text-xs font-medium text-ink-2">알림 기준 (사용률 %)</legend>
          <div className="grid grid-cols-[4rem_1fr_1fr] items-center gap-x-3 gap-y-2 text-sm">
            <span />
            <span className="text-xs font-medium text-warn-ink">경고</span>
            <span className="text-xs font-medium text-crit-ink">장애</span>
            {THRESHOLD_ROWS.map((row) => (
              <div key={row.label} className="contents">
                <span className="text-ink-2">{row.label}</span>
                {[row.warn, row.crit].map((key) => (
                  <input
                    key={key}
                    className="input tabular"
                    type="number"
                    min={1}
                    max={100}
                    required
                    aria-label={`${row.label} ${key.endsWith('warn') ? '경고' : '장애'} 기준`}
                    value={form[key]}
                    onChange={(e) => set(key, Number(e.target.value))}
                  />
                ))}
              </div>
            ))}
          </div>
        </fieldset>

        <ErrorNote message={error} />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? '저장 중…' : server ? '저장' : '등록'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
