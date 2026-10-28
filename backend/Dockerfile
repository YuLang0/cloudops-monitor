FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# root 가 아닌 전용 계정으로 실행한다. SQLite 파일은 /app/data (볼륨)에 저장된다.
RUN useradd --system --uid 10001 --no-create-home cloudops \
    && mkdir -p /app/data && chown cloudops:cloudops /app/data
USER cloudops
VOLUME /app/data
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"

# 워커는 1개로 고정한다: 데모 시뮬레이터·연결 끊김 감시·로그인 제한기가 프로세스 안에서 돌기 때문이다.
# --proxy-headers: 신뢰하는 프록시가 넘겨 준 X-Forwarded-For 를 클라이언트 IP 로 사용한다.
# 누구를 신뢰할지는 환경변수 FORWARDED_ALLOW_IPS 로 정한다(compose 가 nginx 컨테이너의 고정 IP 를 넣는다).
# 지정하지 않으면 uvicorn 기본값인 127.0.0.1 만 신뢰하므로, 컨테이너 밖에서 온 헤더는 무시된다.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
