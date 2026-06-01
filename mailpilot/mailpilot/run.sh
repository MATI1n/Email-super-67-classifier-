#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# MailPilot — запуск веб-приложения (бэкенд FastAPI + собранный фронтенд).
#
# Скрипт:
#   * проверяет наличие python3 и каталога с данными;
#   * поднимает виртуальное окружение и ставит зависимости (один раз);
#   * собирает фронтенд, если есть npm и сборки ещё нет;
#   * запускает сервер, перенаправляя логи в backend/server.log.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PORT="${PORT:-8000}"

info()  { printf "\033[1;34m▸ %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
warn()  { printf "\033[1;33m! %s\033[0m\n" "$*"; }
fail()  { printf "\033[1;31m✗ %s\033[0m\n" "$*"; exit 1; }

# --- проверки окружения ---
command -v python3 >/dev/null 2>&1 || fail "python3 не найден. Установите Python 3.10+."

if [ ! -d "$BACKEND/app/data/inbox" ]; then
  fail "Не найден каталог с письмами: backend/app/data/inbox"
fi
MAIL_COUNT=$(find "$BACKEND/app/data/inbox" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
info "Писем в наборе: $MAIL_COUNT"

# --- виртуальное окружение и зависимости ---
cd "$BACKEND"
if [ ! -d ".venv" ]; then
  info "Создаю виртуальное окружение и ставлю зависимости…"
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
  ok "Зависимости установлены"
fi
PY="$BACKEND/.venv/bin/python"

# --- сборка фронтенда (если возможно и ещё не собран) ---
if [ ! -f "$FRONTEND/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    info "Собираю фронтенд (Vite)…"
    ( cd "$FRONTEND" && npm install --silent --no-audit --no-fund && npm run build --silent )
    ok "Фронтенд собран"
  else
    warn "npm не найден — UI не собран. API будет доступен, но без интерфейса."
    warn "Поставьте Node.js 18+ и запустите снова, либо: cd frontend && npm install && npm run build"
  fi
fi

# --- запуск ---
ok "MailPilot запускается на http://localhost:$PORT"
info "Логи: backend/server.log  ·  остановить: Ctrl+C"
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" 2>&1 | tee "$BACKEND/server.log"
