export interface PollerOptions<T> {
  fetcher: () => Promise<T>
  /** 한 요청이 "끝난 뒤" 다음 요청을 시작하기까지의 대기 시간 */
  intervalMs: number
  onData: (data: T) => void
  onError: (message: string) => void
  /** true 를 돌려주는 동안에는 요청을 보내지 않는다(탭이 숨겨졌을 때 등) */
  isPaused?: () => boolean
}

export interface Poller {
  start: () => void
  /** 지금 바로 다시 가져온다. 요청이 진행 중이면 그 요청이 끝난 직후 한 번 더 가져온다 */
  refresh: () => void
  /** 이후 도착하는 응답은 모두 버린다 */
  stop: () => void
}

/**
 * 요청이 겹치지 않는 폴링.
 *
 * setInterval 로 주기마다 요청을 새로 보내면, 응답이 주기보다 느릴 때 요청이 계속 쌓이고
 * "가장 최근 요청의 응답만 받는다"는 규칙 때문에 어떤 응답도 화면에 반영되지 않는다.
 * 그래서 동시에 진행되는 요청을 1개로 제한하고, 응답을 받은 뒤에 다음 요청을 예약한다.
 * 진행 중인 요청은 항상 가장 최근 요청이므로 응답을 순번으로 걸러낼 필요가 없다.
 */
export function createPoller<T>(options: PollerOptions<T>): Poller {
  const { fetcher, intervalMs, onData, onError, isPaused } = options
  let stopped = false
  let inFlight = false
  let rerunRequested = false
  let timer: ReturnType<typeof setTimeout> | undefined

  const schedule = () => {
    clearTimeout(timer)
    timer = setTimeout(() => {
      if (isPaused?.()) schedule()
      else void run()
    }, intervalMs)
  }

  const run = async () => {
    if (stopped) return
    if (inFlight) {
      rerunRequested = true
      return
    }
    inFlight = true
    clearTimeout(timer)
    try {
      const data = await fetcher()
      if (!stopped) onData(data)
    } catch (e) {
      if (!stopped) onError(e instanceof Error ? e.message : '알 수 없는 오류')
    } finally {
      inFlight = false
      if (!stopped) {
        if (rerunRequested) {
          rerunRequested = false
          void run()
        } else {
          schedule()
        }
      }
    }
  }

  return {
    start: () => void run(),
    refresh: () => void run(),
    stop: () => {
      stopped = true
      clearTimeout(timer)
    },
  }
}
