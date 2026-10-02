# ---------- 1. Сборка React (dist/) ----------
FROM node:22-alpine AS frontend
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html vite.config.js styles.css admin.css favicon.svg ./
COPY src ./src
COPY public ./public

# vite.config.js не собирает фронт без телефона мастерской
ARG PHONE_E164
RUN test -n "$PHONE_E164" || (echo "PHONE_E164 не передан в сборку (нужен в .env)" && exit 1)
RUN npm run build

# ---------- 2. Python-сервер ----------
FROM python:3.12-slim
WORKDIR /app

# TZ: имена резервных копий и время в логах — по Алматы, а не UTC
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Almaty \
    MEBEL_HOST=0.0.0.0 \
    MEBEL_PORT=8780

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py consultant.py index.html styles.css admin.css favicon.svg ./
COPY core ./core
COPY features ./features
COPY assets ./assets
COPY --from=frontend /app/dist ./dist

RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p data logs assets/products assets/chat \
    && chown -R app:app data logs assets/products assets/chat
USER app

EXPOSE 8780

# Сервер штатно завершается только по Ctrl+C (KeyboardInterrupt); SIGTERM процесс с PID 1 игнорирует
STOPSIGNAL SIGINT

HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8780/', timeout=4)" || exit 1

CMD ["python", "server.py"]
