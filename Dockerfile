FROM node:22-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend

COPY --from=ui /app/frontend/build ./frontend/build

ENV OSINTLAB_DATA_DIR=/data \
    OSINTLAB_UI_DIR=/app/frontend/build \
    OSINTLAB_USER_AGENT="osint-lab/0.1 (educational; contact: change-me@example.org)"

VOLUME ["/data"]
EXPOSE 8000

CMD ["osintlab", "serve", "--host", "0.0.0.0", "--port", "8000"]
