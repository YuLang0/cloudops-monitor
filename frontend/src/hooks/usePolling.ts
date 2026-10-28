import { useCallback, useEffect, useRef, useState } from 'react'
import { createPoller, type Poller } from '../lib/poller'

export interface PollState<T> {
  data: T | null
  error: string | null
  loading: boolean
  refresh: () => void
}

/**
 * 일정 주기로 API 를 다시 호출한다. 실제 동작은 lib/poller.ts 에 있다.
 * - 요청은 한 번에 하나만 진행한다. 응답이 주기보다 느려도 화면은 계속 갱신된다.
 * - 탭이 보이지 않을 때는 쉬고, 다시 보이면 즉시 갱신한다.
 * - 화면을 떠나거나 deps(서버 ID, 조회 범위 등)가 바뀌면 이전 요청의 응답은 버린다.
 * - 실패해도 직전 데이터는 유지하되 error 를 채워, 화면이 "오래된 값"임을 알릴 수 있게 한다.
 */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[] = []): PollState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const pollerRef = useRef<Poller | null>(null)

  useEffect(() => {
    setLoading(true)
    setData(null)
    const poller = createPoller<T>({
      fetcher: () => fetcherRef.current(),
      intervalMs,
      onData: (result) => {
        setData(result)
        setError(null)
        setLoading(false)
      },
      onError: (message) => {
        setError(message)
        setLoading(false)
      },
      isPaused: () => document.hidden,
    })
    pollerRef.current = poller
    poller.start()
    const onVisible = () => {
      if (!document.hidden) poller.refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      poller.stop() // 진행 중인 요청의 결과를 버린다
      document.removeEventListener('visibilitychange', onVisible)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, ...deps])

  const refresh = useCallback(() => pollerRef.current?.refresh(), [])
  return { data, error, loading, refresh }
}

/** 상대 시간("5초 전") 표시를 매초 갱신하기 위한 현재 시각 훅 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}
