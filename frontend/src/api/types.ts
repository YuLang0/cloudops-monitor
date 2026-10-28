export type ServerStatus = 'ok' | 'warning' | 'critical' | 'offline' | 'pending'
export type RangeKey = '1m' | '5m' | '1h' | '24h'
export type IncidentMetric = 'cpu' | 'memory' | 'disk' | 'offline'
export type Severity = 'warning' | 'critical'

export interface User {
  id: number
  email: string
  created_at: string
}

export interface Thresholds {
  cpu_warn: number
  cpu_crit: number
  mem_warn: number
  mem_crit: number
  disk_warn: number
  disk_crit: number
}

export interface ServerInput extends Thresholds {
  name: string
  host: string
  os_name: string
  description: string
}

export interface MetricPoint {
  ts: string
  cpu_percent: number
  mem_percent: number
  mem_used: number
  mem_total: number
  disk_percent: number
  disk_used: number
  disk_total: number
  net_sent_rate: number
  net_recv_rate: number
  net_sent_total: number
  net_recv_total: number
  uptime_seconds: number
}

export interface Server extends ServerInput {
  id: number
  is_demo: boolean
  status: ServerStatus
  last_seen_at: string | null
  reported_hostname: string | null
  reported_os: string | null
  agent_version: string | null
  agent_key_prefix: string | null
  open_incident_count: number
  /** 연결 끊김 상태에서는 "마지막으로 받은 값"이다. 현재 값이 아니다. */
  latest: MetricPoint | null
  created_at: string
}

export interface ServerCreated {
  server: Server
  agent_key: string
}

export interface MetricSeries {
  range: RangeKey
  bucket_seconds: number
  start: string
  end: string
  points: MetricPoint[]
}

export interface Incident {
  id: number
  server_id: number
  server_name: string
  is_demo: boolean
  metric: IncidentMetric
  severity: Severity
  started_at: string
  resolved_at: string | null
  threshold: number | null
  peak_value: number | null
  last_value: number | null
  message: string
}

export interface DashboardSummary {
  total: number
  ok: number
  warning: number
  critical: number
  offline: number
  pending: number
  demo: number
  avg_cpu: number | null
  avg_mem: number | null
  reporting: number
  open_incidents: number
  recent_incidents: Incident[]
}

export interface FleetPoint {
  ts: string
  avg_cpu: number
  avg_mem: number
  servers: number
}

export interface FleetSeries {
  range: RangeKey
  bucket_seconds: number
  start: string
  end: string
  points: FleetPoint[]
}

export interface PublicConfig {
  demo_mode: boolean
  allow_registration: boolean
  offline_after_seconds: number
}
