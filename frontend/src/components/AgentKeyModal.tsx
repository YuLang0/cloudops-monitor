import { Check, Copy, KeyRound, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Modal } from './ui'

function CopyBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* 클립보드 권한이 없으면 직접 선택해 복사하면 된다 */
    }
  }
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="label mb-0">{label}</span>
        <button type="button" className="btn btn-ghost px-2 py-1 text-xs" onClick={copy}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? '복사됨' : '복사'}
        </button>
      </div>
      <pre className="overflow-x-auto rounded-lg border border-line bg-surface-2 p-3 font-mono text-xs leading-relaxed text-ink select-all">
        {text}
      </pre>
    </div>
  )
}

/** Agent 실행 방법. 키를 모를 때는 자리표시자를 보여 준다 */
export function AgentInstructions({ agentKey }: { agentKey?: string }) {
  const url = window.location.origin
  const key = agentKey ?? '<발급받은 Agent 인증키>'
  const linux = `pip install psutil
export CLOUDOPS_URL="${url}"
export CLOUDOPS_AGENT_KEY="${key}"
python agent.py`
  const windows = `pip install psutil
$env:CLOUDOPS_URL = "${url}"
$env:CLOUDOPS_AGENT_KEY = "${key}"
python agent.py`
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-2">
        모니터링할 서버에 <code className="font-mono text-ink">agent/agent.py</code> 를 복사한 뒤 아래 명령을 실행하세요. Agent 는 측정값을
        읽어 보내기만 하며, 원격 명령 실행 기능이 없습니다.
      </p>
      <CopyBlock label="Linux / macOS" text={linux} />
      <CopyBlock label="Windows PowerShell" text={windows} />
      <p className="text-xs text-ink-3">
        본인 소유이거나 모니터링 허가를 받은 서버에서만 실행하세요. localhost 가 아닌 주소로 보낼 때는 https 가 필요합니다.
      </p>
    </div>
  )
}

export function AgentKeyModal({ serverName, agentKey, onClose }: { serverName: string; agentKey: string; onClose: () => void }) {
  return (
    <Modal title={`Agent 인증키 — ${serverName}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-sm text-warn-ink">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>
            이 키는 <strong>지금 한 번만</strong> 표시됩니다. 서버에는 해시만 저장되므로 창을 닫으면 다시 볼 수 없습니다. 잃어버렸다면
            서버 상세 화면에서 재발급하세요.
          </span>
        </div>
        <CopyBlock label="Agent 인증키" text={agentKey} />
        <div className="flex items-center gap-2 pt-1 text-sm font-semibold">
          <KeyRound size={15} aria-hidden /> Agent 실행 방법
        </div>
        <AgentInstructions agentKey={agentKey} />
        <div className="flex justify-end">
          <button type="button" className="btn btn-primary" onClick={onClose}>
            키를 저장했습니다
          </button>
        </div>
      </div>
    </Modal>
  )
}
