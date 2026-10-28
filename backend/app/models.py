from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    servers: Mapped[list["Server"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    host: Mapped[str] = mapped_column(String(253))  # 표시용 메타데이터. 백엔드는 이 주소로 접속하지 않는다
    os_name: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(String(255), default="")

    # 가상(데모) 서버 여부. 데모 서버는 Agent 키가 없고 실제 수집 API 로 데이터를 받을 수 없다
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Agent 인증키는 평문으로 저장하지 않고 SHA-256 해시만 저장한다
    agent_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    agent_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)

    cpu_warn: Mapped[int] = mapped_column(Integer, default=80)
    cpu_crit: Mapped[int] = mapped_column(Integer, default=95)
    mem_warn: Mapped[int] = mapped_column(Integer, default=80)
    mem_crit: Mapped[int] = mapped_column(Integer, default=95)
    disk_warn: Mapped[int] = mapped_column(Integer, default=85)
    disk_crit: Mapped[int] = mapped_column(Integer, default=95)

    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reported_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    reported_os: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(back_populates="servers")
    metrics: Mapped[list["Metric"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="server", cascade="all, delete-orphan", passive_deletes=True
    )


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_server_ts", "server_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(UTCDateTime)  # 백엔드 수신 시각(Agent 시계를 신뢰하지 않음)

    cpu_percent: Mapped[float] = mapped_column(Float)
    mem_percent: Mapped[float] = mapped_column(Float)
    mem_used: Mapped[int] = mapped_column(BigInteger)
    mem_total: Mapped[int] = mapped_column(BigInteger)
    disk_percent: Mapped[float] = mapped_column(Float)
    disk_used: Mapped[int] = mapped_column(BigInteger)
    disk_total: Mapped[int] = mapped_column(BigInteger)
    net_sent_rate: Mapped[float] = mapped_column(Float)  # bytes/sec
    net_recv_rate: Mapped[float] = mapped_column(Float)  # bytes/sec
    net_sent_total: Mapped[int] = mapped_column(BigInteger)
    net_recv_total: Mapped[int] = mapped_column(BigInteger)
    uptime_seconds: Mapped[int] = mapped_column(BigInteger)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_server_started", "server_id", "started_at"),
        # 같은 서버·같은 항목의 "진행 중" 장애는 DB 수준에서도 1건만 허용 → 중복 알림 방지
        Index(
            "uq_incidents_open",
            "server_id",
            "metric",
            unique=True,
            sqlite_where=text("resolved_at IS NULL"),
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    metric: Mapped[str] = mapped_column(String(16))  # cpu | memory | disk | offline
    severity: Mapped[str] = mapped_column(String(16))  # warning | critical (진행 중 도달한 최고 단계)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    peak_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    clear_streak: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(255), default="")

    server: Mapped[Server] = relationship(back_populates="incidents")
