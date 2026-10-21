#!/usr/bin/env bash
set -e
E=${AUDIT_ENV:-/tmp/syncserv-audit}
mkdir -p $E && cp "$(dirname "$0")/clock.py" $E/clock.py
D=$E/$1
mkdir -p $D/receipts
cd /home/souzza-matheus/barberbot/backend
# GEMINI_API_KEY vazia: o backend descartável nunca chama o Gemini de verdade (o .env do backend tem a chave)
export GEMINI_API_KEY= DATABASE_URL="sqlite:///$D/e2e.db" EVOLUTION_URL= DEV_MODE=true RUN_SCHEDULER=false SETUP_TOKEN=audit-token RECEIPTS_DIR=$D/receipts PYTHONPATH=.
export JWT_SECRET=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
if [ ! -f $D/e2e.db ]; then
  ./.venv/bin/alembic -x url="$DATABASE_URL" upgrade head >/dev/null
  ./.venv/bin/python $E/clock.py seed > $D/seed.log
fi
exec ./.venv/bin/python $E/clock.py serve $2 > $D/api.log 2>&1
