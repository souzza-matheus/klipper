#!/usr/bin/env bash
# Teste ponta a ponta da versão web num comando só (npm run test:web).
# Sobe um backend DESCARTÁVEL (SQLite temporário com os dados fictícios do seed_mock, porta 8010),
# gera o export web e roda tests/web_e2e.py. Não toca no banco de desenvolvimento nem no Docker.
# Precisa: backend/.venv instalado, Playwright para Python (pip install playwright && playwright install chromium) e
# fonttools com brotli (pip install fonttools brotli) para conferir as fontes.
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
  # sem GEMINI_API_KEY: o teste nunca chama o Gemini de verdade (o backend/.env pode ter a chave)
  export GEMINI_API_KEY= DATABASE_URL="sqlite:///$TMP/e2e.db" EVOLUTION_URL= DEV_MODE=true RUN_SCHEDULER=false
  export JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  ./.venv/bin/alembic -x url="$DATABASE_URL" upgrade head >/dev/null
  ./.venv/bin/python -m app.seed_mock >/dev/null
  # Conta com dois negócios (dona da Barbearia Demo e de uma segunda loja), para a escolha e a troca de negócio
  ./.venv/bin/python - <<'PY'
from sqlalchemy import select
from app.auth import hash_password
from app.db import SessionLocal
from app.models import Membership, Shop, User
db = SessionLocal()
first = db.scalar(select(Shop).where(Shop.evolution_instance == "barbearia-demo"))
second = Shop(name="Segunda Loja Demo", evolution_instance="segunda-loja-demo", niche="beauty")
db.add(second)
db.flush()
user = User(name="Conta com dois negócios", email="duas.empresas@demo.com", password_hash=hash_password("demo123"))
user.memberships = [Membership(shop_id=first.id, role="owner"), Membership(shop_id=second.id, role="owner")]
db.add(user)
db.commit()
PY
  exec ./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$TMP/api.log" 2>&1
) &
API_PID=$!
for _ in $(seq 60); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && break; sleep 1; done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || { echo "backend não subiu:"; cat "$TMP/api.log"; exit 1; }

# Fontes web em dia (woff2 e ícones usados no código); falha com "rode scripts/build-fonts" se não
python3 ../scripts/build-fonts --check 2>/dev/null || { echo "Fontes web desatualizadas: rode python3 scripts/build-fonts"; exit 1; }
# O endereço da API entra no build, como nos perfis do eas.json (aqui, o backend descartável)
EXPO_PUBLIC_APP_PROFILE=development EXPO_PUBLIC_API_URL="http://localhost:$PORT" \
  npx expo export --platform web --clear --output-dir "$TMP/web" >/dev/null
python3 tests/web_e2e.py "$TMP/web" "http://localhost:$PORT"
