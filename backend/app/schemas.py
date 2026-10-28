from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

ServerStatus = Literal["ok", "warning", "critical", "offline", "pending"]
RangeKey = Literal["1m", "5m", "1h", "24h"]


def _clean_text(value: str) -> str:
    value = value.strip()
    if _CONTROL_RE.search(value):
        raise ValueError("제어 문자는 사용할 수 없습니다")
    return value


def validate_host(value: str) -> str:
    """IP 주소 또는 호스트명 형식만 허용한다(URL, 경로, 공백, 셸 메타문자 불가)."""
    value = value.strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(value):
        raise ValueError("올바른 IP 주소 또는 호스트명이 아닙니다")
    return value.lower()


# ---------- 인증 ----------
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    created_at: datetime


# ---------- 서버 ----------
class Thresholds(BaseModel):
    cpu_warn: int = Field(80, ge=1, le=100)
    cpu_crit: int = Field(95, ge=1, le=100)
    mem_warn: int = Field(80, ge=1, le=100)
    mem_crit: int = Field(95, ge=1, le=100)
    disk_warn: int = Field(85, ge=1, le=100)
    disk_crit: int = Field(95, ge=1, le=100)

    @model_validator(mode="after")
    def _warn_below_crit(self):
        for m, label in (("cpu", "CPU"), ("mem", "RAM"), ("disk", "디스크")):
            if getattr(self, f"{m}_warn") >= getattr(self, f"{m}_crit"):
                raise ValueError(f"{label} 경고 기준은 장애 기준보다 낮아야 합니다")
        return self


class ServerCreate(Thresholds):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=253)
    os_name: str = Field("", max_length=64)
    description: str = Field("", max_length=255)

    _clean = field_validator("name", "os_name", "description")(_clean_text)
    _host = field_validator("host")(validate_host)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v:
            raise ValueError("서버 이름을 입력하세요")
        return v


class ServerUpdate(ServerCreate):
    pass


class MetricPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ts: datetime
    cpu_percent: float
    mem_percent: float
    mem_used: int
    mem_total: int
    disk_percent: float
    disk_used: int
    disk_total: int
    net_sent_rate: float
    net_recv_rate: float
    net_sent_total: int
    net_recv_total: int
    uptime_seconds: int


class ServerOut(Thresholds):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    host: str
    os_name: str
    description: str
    is_demo: bool
    status: ServerStatus
    last_seen_at: datetime | None
    reported_hostname: str | None
    reported_os: str | None
    agent_version: str | None
    agent_key_prefix: str | None
    open_incident_count: int
    latest: MetricPoint | None  # 연결 끊김 상태라면 "마지막으로 받은 값"이며 현재 값이 아니다
    created_at: datetime

    @model_validator(mode="after")
    def _warn_below_crit(self):  # 출력 모델에서는 검증 생략
        return self


class ServerCreated(BaseModel):
    server: ServerOut
    agent_key: str  # 이 응답에서 단 한 번만 노출


class MetricSeries(BaseModel):
    range: RangeKey
    bucket_seconds: int  # 0 이면 원본 샘플
    start: datetime
    end: datetime
    points: list[MetricPoint]


# ---------- 장애 ----------
class IncidentOut(BaseModel):
    id: int
    server_id: int
    server_name: str
    is_demo: bool
    metric: Literal["cpu", "memory", "disk", "offline"]
    severity: Literal["warning", "critical"]
    started_at: datetime
    resolved_at: datetime | None
    threshold: float | None
    peak_value: float | None
    last_value: float | None
    message: str


# ---------- 대시보드 ----------
class DashboardSummary(BaseModel):
    total: int
    ok: int
    warning: int
    critical: int
    offline: int
    pending: int
    demo: int
    avg_cpu: float | None  # 현재 데이터를 보내는 서버만 평균. 없으면 null
    avg_mem: float | None
    reporting: int
    open_incidents: int
    recent_incidents: list[IncidentOut]


class FleetPoint(BaseModel):
    ts: datetime
    avg_cpu: float
    avg_mem: float
    servers: int


class FleetSeries(BaseModel):
    range: RangeKey
    bucket_seconds: int
    start: datetime
    end: datetime
    points: list[FleetPoint]


# ---------- Agent 수집 ----------
_MAX_BYTES = 2**62


class IngestPayload(BaseModel):
    # 알 수 없는 필드 거부 + 엄격 모드("50" 같은 문자열·불리언을 숫자로 바꿔 받지 않는다)
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    cpu_percent: float = Field(ge=0, le=100)
    mem_percent: float = Field(ge=0, le=100)
    mem_used: int = Field(ge=0, le=_MAX_BYTES)
    mem_total: int = Field(ge=0, le=_MAX_BYTES)
    disk_percent: float = Field(ge=0, le=100)
    disk_used: int = Field(ge=0, le=_MAX_BYTES)
    disk_total: int = Field(ge=0, le=_MAX_BYTES)
    net_sent_rate: float = Field(ge=0, le=1e12)
    net_recv_rate: float = Field(ge=0, le=1e12)
    net_sent_total: int = Field(ge=0, le=_MAX_BYTES)
    net_recv_total: int = Field(ge=0, le=_MAX_BYTES)
    uptime_seconds: int = Field(ge=0, le=10**10)
    hostname: str | None = Field(None, max_length=253)
    os: str | None = Field(None, max_length=128)
    agent_version: str | None = Field(None, max_length=32)

    @field_validator("hostname", "os", "agent_version")
    @classmethod
    def _strip_control(cls, v: str | None) -> str | None:
        return _CONTROL_RE.sub("", v).strip() if v else v

    @model_validator(mode="after")
    def _used_within_total(self):
        if self.mem_used > self.mem_total:
            raise ValueError("mem_used 가 mem_total 보다 클 수 없습니다")
        if self.disk_used > self.disk_total:
            raise ValueError("disk_used 가 disk_total 보다 클 수 없습니다")
        return self


class PublicConfig(BaseModel):
    demo_mode: bool
    allow_registration: bool
    offline_after_seconds: int
