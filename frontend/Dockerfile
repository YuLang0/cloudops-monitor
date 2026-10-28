# 빌드 단계는 glibc 기반 이미지를 쓴다. 빌드 도구(rolldown, Tailwind, LightningCSS, TypeScript 7)의
# 네이티브 바이너리가 Linux ARM64(gnu)·AMD64(gnu) 용으로 모두 package-lock.json 에 들어 있다.
# (Alpine=musl 은 TypeScript 7 용 전용 패키지가 없어 ARM 서버에서 실패할 수 있다)
FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.30-alpine
# 신뢰하는 앞단 프록시(CIDR). 기본값은 "없음"과 같다: 127.0.0.1 에서는 연결이 오지 않으므로
# 외부에서 보낸 X-Forwarded-For 를 전혀 믿지 않는다. HTTPS 구성에서만 Caddy 의 IP 로 바꾼다.
ENV CLOUDOPS_TRUSTED_PROXY=127.0.0.1/32
# 템플릿에서 CLOUDOPS_ 로 시작하는 변수만 치환한다
ENV NGINX_ENVSUBST_FILTER=^CLOUDOPS_
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
