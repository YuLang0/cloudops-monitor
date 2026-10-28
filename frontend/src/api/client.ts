import type {
  DashboardSummary,
  FleetSeries,
  Incident,
  MetricSeries,
  PublicConfig,
  RangeKey,
  Server,
  ServerCreated,
  ServerInput,
  User,
} from './types'

const BASE = '/api/v1'
export const AUTH_EXPIRED_EVENT = 'cloudops:auth-expired'
const REQUEST_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

interface ValidationItem {
  msg?: string
  loc?: (string | number)[]
}

function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI 422 검증 오류: [{loc, msg}, ...]
    return (detail as ValidationItem[])
      .map((d) => {
        const field = d.loc?.[d.loc.length - 1]
        const msg = (d.msg ?? '').replace(/^Value error, /, '')
        return typeof field === 'string' && field !== 'body' ? `${field}: ${msg}` : msg
      })
      .join('\n')
  }
  if (status >= 500) return '서버 오류가 발생했습니다. 잠시 후 다시 시도하세요.'
  return `요청을 처리하지 못했습니다 (HTTP ${status})`
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, {
      ...init,
      credentials: 'same-origin', // 세션은 httpOnly 쿠키로만 주고받는다(JS 가 토큰을 만지지 않는다)
      headers: init.body ? { 'Content-Type': 'application/json', ...init.headers } : init.headers,
      // 폴링은 요청을 하나씩만 보내므로, 응답이 영영 오지 않는 요청이 폴링 전체를 멈추지 않게 제한 시간을 둔다
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      throw new ApiError(0, `백엔드가 ${REQUEST_TIMEOUT_MS / 1000}초 안에 응답하지 않았습니다.`)
    }
    throw new ApiError(0, '백엔드에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.')
  }
  if (response.status === 204) return undefined as T
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    }
    throw new ApiError(response.status, errorMessage(response.status, body))
  }
  return body as T
}

const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
})

export const api = {
  config: () => request<PublicConfig>('/config'),

  me: () => request<User>('/auth/me'),
  login: (email: string, password: string) => request<User>('/auth/login', json('POST', { email, password })),
  register: (email: string, password: string) =>
    request<User>('/auth/register', json('POST', { email, password })),
  logout: () => request<void>('/auth/logout', json('POST')),

  servers: () => request<Server[]>('/servers'),
  server: (id: number) => request<Server>(`/servers/${id}`),
  createServer: (input: ServerInput) => request<ServerCreated>('/servers', json('POST', input)),
  updateServer: (id: number, input: ServerInput) => request<Server>(`/servers/${id}`, json('PUT', input)),
  deleteServer: (id: number) => request<void>(`/servers/${id}`, json('DELETE')),
  rotateKey: (id: number) => request<ServerCreated>(`/servers/${id}/rotate-key`, json('POST')),
  metrics: (id: number, range: RangeKey) => request<MetricSeries>(`/servers/${id}/metrics?range=${range}`),
  metricsCsvUrl: (id: number, range: RangeKey) => `${BASE}/servers/${id}/metrics/export?range=${range}`,

  incidents: (params: { state?: 'all' | 'open' | 'resolved'; serverId?: number; limit?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.state) q.set('state', params.state)
    if (params.serverId !== undefined) q.set('server_id', String(params.serverId))
    if (params.limit !== undefined) q.set('limit', String(params.limit))
    return request<Incident[]>(`/incidents?${q}`)
  },
  incidentsCsvUrl: (state: 'all' | 'open' | 'resolved') => `${BASE}/incidents/export?state=${state}`,

  summary: () => request<DashboardSummary>('/dashboard/summary'),
  fleetSeries: (range: RangeKey) => request<FleetSeries>(`/dashboard/timeseries?range=${range}`),

  seedDemo: () => request<Server[]>('/demo/seed', json('POST')),
  removeDemo: () => request<void>('/demo', json('DELETE')),
}
