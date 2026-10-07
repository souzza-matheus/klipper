#!/usr/bin/env bash
# Teste ponta a ponta da versão web num comando só (npm run test:web).
# Sobe um backend DESCARTÁVEL (SQLite temporário com os dados fictícios do seed_mock, porta 8010),
# gera o export web e roda tests/web_e2e.py. Não toca no banco de desenvolvimento nem no Docker.
# Precisa: backend/.venv instalado e Playwright para Python (pip install playwright && playwright install chromium).
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
PORT=${E2E_API_PORT:-8010}
API_PID=""
cleanup() { [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null; rm -rf "$TMP"; }
trap cleanup EXIT

python3 -c "import playwright" 2>/dev/null || { echo "Instale: pip install playwright && playwright install chromium"; exit 1; }
(
  cd ../backend
  export DATABASE_URL="sqlite:///$TMP/e2e.db" EVOLUTION_URL= DEV_MODE=true RUN_SCHEDULER=false
  export JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  ./.venv/bin/alembic -x url="$DATABASE_URL" upgrade head >/dev/null
  ./.venv/bin/python -m app.seed_mock >/dev/null
  exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$TMP/api.log" 2>&1
) &
API_PID=$!
for _ in $(seq 60); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 1; done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { echo "backend não subiu:"; cat "$TMP/api.log"; exit 1; }

npx expo export --platform web --output-dir "$TMP/web" >/dev/null
python3 tests/web_e2e.py "$TMP/web" "http://localhost:$PORT"
