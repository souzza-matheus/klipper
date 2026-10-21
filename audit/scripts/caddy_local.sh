#!/usr/bin/env bash
# Caddy local (Docker) com as mesmas configurações de produção (deploy/caddy/), para medir desempenho com compressão
# e cache de verdade. Uso: caddy_local.sh <pasta da landing> <pasta do export web> [porta landing=8201] [porta app=8202]
# [porta da API=9 (nenhuma)]
# Para parar: docker rm -f syncserv-caddy-medicao
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SITE="$(cd "$1" && pwd)"; WEB="$(cd "$2" && pwd)"; PS="${3:-8201}"; PA="${4:-8202}"; API="${5:-9}"
CONF="$(mktemp -d)"
cat > "$CONF/Caddyfile" <<CADDY
{
	admin off
}
http://127.0.0.1:$PS {
	import /deploy/caddy/site.caddy /srv/site
}
http://127.0.0.1:$PA {
	import /deploy/caddy/app.caddy /srv/web 127.0.0.1:$API
}
CADDY
docker rm -f syncserv-caddy-medicao >/dev/null 2>&1 || true
docker run -d --rm --name syncserv-caddy-medicao --network host -v "$CONF:/etc/caddy:ro" -v "$ROOT/deploy:/deploy:ro" \
  -v "$SITE:/srv/site:ro" -v "$WEB:/srv/web:ro" caddy:2.10.2-alpine >/dev/null
sleep 1
echo "landing: http://127.0.0.1:$PS/   app: http://127.0.0.1:$PA/"
