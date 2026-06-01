# syntax=docker/dockerfile:1

# ---------- Stage 1: сборка фронтенда (Vite/React) ----------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: рантайм бэкенда (FastAPI) ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Зависимости Python (ставятся отдельным слоем для кеша)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Код бэкенда (включая датасет app/data/inbox)
COPY backend/app ./app

# Собранный фронтенд из stage 1 → туда, где его ждёт main.py (/app/frontend/dist)
COPY --from=frontend /frontend/dist /app/frontend/dist

# Непривилегированный пользователь + доступ на чтение к скопированным файлам
# (часть файлов датасета имеет права 600 — открываем чтение для appuser)
RUN useradd -m -u 1000 appuser && chmod -R a+rX /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
