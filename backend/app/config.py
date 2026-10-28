"""환경변수 기반 설정. 모든 비밀정보는 코드가 아니라 환경변수(.env)에서 읽는다."""
from __future__ import annotations

import logging
import secrets
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("cloudops")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLOUDOPS_", env_file=".env", extra="ignore")

    environment: str = "development"  # development | production
    secret_key: str = ""  # JWT 서명 키. production 에서는 32자 이상 필수
    database_url: str = "sqlite:///./data/cloudops.db"

    access_token_minutes: int = 720
    cookie_secure: bool = False  # HTTPS 뒤에서 운영할 때 true
    # 쉼표로 구분. 비워두면 CORS 를 허용하지 않고, 쓰기 요청(POST/PUT/DELETE)도 같은 출처에서 온 것만 받는다.
    # 화면과 API 를 같은 도메인으로 서비스하는 기본 구성에서는 비워 둔다.
    cors_origins: str = ""
    allow_registration: bool = True

    demo_mode: bool = True
    demo_interval_seconds: float = 3.0

    offline_after_seconds: int = 30  # 이 시간 동안 수신이 없으면 "연결 끊김"
    ingest_min_interval_seconds: float = 1.0  # Agent 과다 전송 방지
    clear_samples: int = 3  # 연속 N회 정상이어야 장애 해결 처리(플래핑 방지)
    retention_days: int = Field(7, ge=1, le=3650)  # 측정값 보관 기간(일)
    incident_retention_days: int = Field(365, ge=1, le=36500)  # '해결된' 장애 이력 보관 기간(일)
    # 백그라운드 작업(감시·데모·정리)을 한 프로세스만 실행하도록 거는 잠금 파일. 데이터 볼륨 안에 둔다.
    background_lock_file: str = "./data/background.lock"

    login_max_failures: int = 5
    login_window_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if len(settings.secret_key) < 32:
        if settings.is_production:
            raise RuntimeError(
                "CLOUDOPS_SECRET_KEY 는 production 환경에서 32자 이상이어야 합니다. "
                '생성 예: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        logger.warning(
            "CLOUDOPS_SECRET_KEY 가 설정되지 않아 임시 키를 사용합니다. "
            "서버를 재시작하면 로그인 세션이 모두 만료됩니다."
        )
        settings.secret_key = secrets.token_urlsafe(48)
    return settings
