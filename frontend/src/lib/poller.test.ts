import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPoller } from './poller'

/** latencyMs 뒤에 1, 2, 3 … 을 차례로 돌려주는 가짜 API. 동시에 진행 중인 요청 수도 기록한다 */
function fakeApi(latencyMs: number) {
  const state = { calls: 0, active: 0, maxActive: 0 }
  const fetcher = () => {
    const n = ++state.calls
    state.active += 1
    state.maxActive = Math.max(state.maxActive, state.active)
    return new Promise<number>((resolve) =>
      setTimeout(() => {
        state.active -= 1
        resolve(n)
      }, latencyMs),
    )
  }
  return { state, fetcher }
}

describe('createPoller', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('keeps updating when every response is slower than the interval (3s interval, 4s responses)', async () => {
    const api = fakeApi(4000)
    const received: number[] = []
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: () => {} })

    poller.start()
    await vi.advanceTimersByTimeAsync(30_000)
    poller.stop()

    // 4초 응답 + 3초 대기 = 7초 주기 → 4초, 11초, 18초, 25초에 갱신
    expect(received).toEqual([1, 2, 3, 4])
    expect(api.state.maxActive).toBe(1) // 요청이 겹친 적이 없다
  })

  it('reproduces the old bug for comparison: overlapping setInterval polling never updates', async () => {
    // 수정 전 방식: 주기마다 새 요청을 보내고, 가장 최근 요청의 응답만 받는다
    const api = fakeApi(4000)
    const received: number[] = []
    let seq = 0
    const run = async () => {
      const mine = ++seq
      const data = await api.fetcher()
      if (mine === seq) received.push(data)
    }
    void run()
    const timer = setInterval(() => void run(), 3000)
    await vi.advanceTimersByTimeAsync(30_000)
    clearInterval(timer)

    expect(received).toEqual([]) // 30초 동안 한 번도 갱신되지 않음
    expect(api.state.maxActive).toBeGreaterThan(1)
  })

  it('polls at the normal pace when responses are fast', async () => {
    const api = fakeApi(100)
    const received: number[] = []
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: () => {} })
    poller.start()
    await vi.advanceTimersByTimeAsync(10_000)
    poller.stop()
    expect(received).toEqual([1, 2, 3, 4]) // 0.1초, 3.2초, 6.3초, 9.4초
  })

  it('discards a response that arrives after stop (navigating away)', async () => {
    const api = fakeApi(4000)
    const onData = vi.fn()
    const onError = vi.fn()
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData, onError })
    poller.start()
    await vi.advanceTimersByTimeAsync(1000)
    poller.stop() // 응답이 오기 전에 화면을 떠남
    await vi.advanceTimersByTimeAsync(60_000)

    expect(onData).not.toHaveBeenCalled()
    expect(onError).not.toHaveBeenCalled()
    expect(api.state.calls).toBe(1) // 이후 새 요청도 보내지 않는다
  })

  it('a new poller is not affected by the late response of the stopped one (changing server or range)', async () => {
    const slowOld = fakeApi(5000)
    const fastNew = fakeApi(100)
    const screen: string[] = []
    const oldPoller = createPoller({ fetcher: slowOld.fetcher, intervalMs: 3000, onData: (d) => screen.push(`old-${d}`), onError: () => {} })
    oldPoller.start()
    await vi.advanceTimersByTimeAsync(500)
    oldPoller.stop()
    const newPoller = createPoller({ fetcher: fastNew.fetcher, intervalMs: 3000, onData: (d) => screen.push(`new-${d}`), onError: () => {} })
    newPoller.start()
    await vi.advanceTimersByTimeAsync(6000)
    newPoller.stop()

    expect(screen).toEqual(['new-1', 'new-2'])
  })

  it('refresh during an in-flight request runs exactly one more request right after it', async () => {
    const api = fakeApi(4000)
    const received: number[] = []
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: () => {} })
    poller.start()
    await vi.advanceTimersByTimeAsync(1000)
    poller.refresh()
    poller.refresh()
    poller.refresh()
    await vi.advanceTimersByTimeAsync(7500) // 4초(첫 응답) + 4초(바로 이어진 두 번째 응답)
    poller.stop()

    expect(received).toEqual([1, 2])
    expect(api.state.maxActive).toBe(1)
  })

  it('refresh while idle fetches immediately and restarts the interval', async () => {
    const api = fakeApi(100)
    const received: number[] = []
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: () => {} })
    poller.start()
    await vi.advanceTimersByTimeAsync(1000)
    poller.refresh()
    await vi.advanceTimersByTimeAsync(200)
    expect(received).toEqual([1, 2])
    await vi.advanceTimersByTimeAsync(2500) // 원래 예약됐던 3.1초 시점에는 요청이 나가지 않는다
    expect(received).toEqual([1, 2])
    poller.stop()
  })

  it('reports errors and keeps polling afterwards', async () => {
    let calls = 0
    const fetcher = async () => {
      calls += 1
      if (calls === 2) throw new Error('서버 오류')
      return calls
    }
    const received: number[] = []
    const errors: string[] = []
    const poller = createPoller({ fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: (m) => errors.push(m) })
    poller.start()
    await vi.advanceTimersByTimeAsync(7000)
    poller.stop()

    expect(received).toEqual([1, 3])
    expect(errors).toEqual(['서버 오류'])
  })

  it('sends nothing while paused and resumes afterwards', async () => {
    const api = fakeApi(100)
    let hidden = false
    const received: number[] = []
    const poller = createPoller({ fetcher: api.fetcher, intervalMs: 3000, onData: (d) => received.push(d), onError: () => {}, isPaused: () => hidden })
    poller.start()
    await vi.advanceTimersByTimeAsync(500)
    hidden = true
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api.state.calls).toBe(1)
    hidden = false
    await vi.advanceTimersByTimeAsync(3200)
    poller.stop()
    expect(received).toEqual([1, 2])
  })
})
