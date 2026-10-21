#!/usr/bin/env bash
# Lighthouse no perfil de celular (Moto G Power simulado, 4G lento). Uso: lighthouse.sh <url> <nome> [vezes=3]
# LH_ARGS="--preset=desktop" mede no perfil de computador. Roda N vezes e guarda o JSON da mediana de desempenho em audit/data/lighthouse-<nome>.json.
set -euo pipefail
URL="$1"; NAME="$2"; N="${3:-3}"
DIR="$(cd "$(dirname "$0")/.." && pwd)/data"
TMP="$(mktemp -d)"
export CHROME_PATH="${CHROME_PATH:-$HOME/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome}"
for i in $(seq 1 "$N"); do
  npx --yes lighthouse@12.6.0 "$URL" --quiet --output=json --output-path="$TMP/$i.json" \
    --chrome-flags="--headless=new --no-sandbox ${LH_FLAGS:-}" ${LH_ARGS:-} >/dev/null 2>&1 || true
done
python3 - "$TMP" "$DIR/lighthouse-$NAME.json" <<'PY'
import glob, json, shutil, sys
runs = []
for f in glob.glob(sys.argv[1] + '/*.json'):
    d = json.load(open(f))
    if d['categories']['performance']['score'] is not None: runs.append((d['audits']['largest-contentful-paint']['numericValue'], f, d))
runs.sort(key=lambda r: r[0])
lcp, f, d = runs[len(runs) // 2]
shutil.copy(f, sys.argv[2])
a = d['audits']
print(json.dumps({'arquivo': sys.argv[2].split('/')[-1], 'execucoes': len(runs),
  'notas': {k: round(v['score'] * 100) for k, v in d['categories'].items()},
  'FCP': a['first-contentful-paint']['displayValue'], 'LCP': a['largest-contentful-paint']['displayValue'],
  'CLS': a['cumulative-layout-shift']['displayValue'], 'TBT': a['total-blocking-time']['displayValue'],
  'SI': a['speed-index']['displayValue'], 'bytes': a['total-byte-weight']['displayValue'],
  'bloqueio': [i['url'].split('/')[-1] for i in a['render-blocking-resources']['details'].get('items', [])]},
  ensure_ascii=False))
PY
rm -rf "$TMP"
