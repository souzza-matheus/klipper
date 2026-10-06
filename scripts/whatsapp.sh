#!/usr/bin/env bash
# Atalhos para o BarberBot com a Evolution API no Docker.
#
#   scripts/whatsapp.sh up               sobe tudo (build do backend incluso) e espera ficar saudável
#   scripts/whatsapp.sh down             para os containers (os dados ficam nos volumes)
#   scripts/whatsapp.sh logs [serviço]   acompanha os logs (padrão: backend e evolution)
#   scripts/whatsapp.sh qr               gera o QR Code em qrcode.png (na raiz do projeto)
#   scripts/whatsapp.sh status           estado da conexão (open = conectado)
#   scripts/whatsapp.sh reset-instance   desconecta e apaga a instância, para conectar outro número
#
# Login do app usado por qr/status: ADMIN_EMAIL e ADMIN_PASSWORD (padrão: a conta da demo).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
API="${API_URL:-http://localhost:${BACKEND_PORT:-8002}}"
EVOLUTION="${EVOLUTION_LOCAL_URL:-http://localhost:8080}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@demo.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-demo123}"

die() { echo "Erro: $*" >&2; exit 1; }

env_value() {
  # Lê uma variável do .env sem imprimir o valor
  grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2-
}

json_get() {
  # json_get campo < json  (aceita caminho com ponto: instance.state)
  python3 -c '
import json, sys
value = json.load(sys.stdin)
for part in sys.argv[1].split("."):
    value = value.get(part) if isinstance(value, dict) else None
print("" if value is None else value)
' "$1"
}

token() {
  local body
  body=$(python3 -c 'import json, sys; print(json.dumps({"email": sys.argv[1], "password": sys.argv[2]}))' \
    "$ADMIN_EMAIL" "$ADMIN_PASSWORD")
  curl -fsS -X POST "$API/api/auth/login" -H "Content-Type: application/json" -d "$body" | json_get token \
    || die "não consegui fazer login em $API (o backend está no ar? rodou o seed?)"
}

cmd_up() {
  [ -f .env ] || die "crie o .env a partir do .env.example (veja o README)"
  docker compose up -d --build --wait
  docker compose ps
}

cmd_down() {
  docker compose down
}

cmd_logs() {
  if [ $# -gt 0 ]; then docker compose logs -f --tail=100 "$@"; else docker compose logs -f --tail=100 backend evolution; fi
}

cmd_status() {
  curl -fsS "$API/api/whatsapp/status" -H "Authorization: Bearer $(token)"
  echo
}

cmd_qr() {
  local resp out="$ROOT/qrcode.png"
  resp=$(curl -fsS -X POST "$API/api/whatsapp/connect" -H "Authorization: Bearer $(token)") \
    || die "falha ao pedir o QR Code ao backend"
  QR_JSON="$resp" python3 - "$out" <<'PY'
import base64, json, os, sys
data = json.loads(os.environ["QR_JSON"])
qr = data.get("qrcode")
if not qr:
    print(f"Sem QR Code (estado: {data.get('state')}). "
          + (data.get("message") or "Tente de novo em alguns segundos."))
    sys.exit(2)
with open(sys.argv[1], "wb") as f:
    f.write(base64.b64decode(qr.split(",", 1)[-1]))
print(f"QR Code salvo em {sys.argv[1]} (estado: {data.get('state')}).")
print("No WhatsApp do número da barbearia: Aparelhos conectados > Conectar aparelho. O QR expira em ~40 s.")
PY
}

cmd_reset_instance() {
  local key instance
  key=$(env_value EVOLUTION_API_KEY)
  [ -n "$key" ] || die "EVOLUTION_API_KEY não encontrada no .env"
  instance=$(curl -fsS "$API/api/whatsapp/status" -H "Authorization: Bearer $(token)" | json_get instance)
  [ -n "$instance" ] || die "não consegui descobrir o nome da instância"
  echo "Isto desconecta o WhatsApp e APAGA a instância '$instance' na Evolution API (sessão e mensagens guardadas nela)."
  echo "Os dados do BarberBot (clientes, agenda) não são afetados. Depois, rode '$0 qr' para conectar outro número."
  read -r -p "Continuar? [s/N] " ok
  [[ "$ok" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
  curl -sS -o /dev/null -w "logout: HTTP %{http_code}\n" -X DELETE "$EVOLUTION/instance/logout/$instance" -H "apikey: $key" || true
  curl -sS -o /dev/null -w "delete: HTTP %{http_code}\n" -X DELETE "$EVOLUTION/instance/delete/$instance" -H "apikey: $key" || true
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  logs) shift; cmd_logs "$@" ;;
  qr) cmd_qr ;;
  status) cmd_status ;;
  reset-instance) cmd_reset_instance ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
