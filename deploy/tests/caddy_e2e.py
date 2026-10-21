"""Teste do Caddy de verdade (imagem oficial no Docker) com as configurações de deploy/caddy/, só na máquina local.

    python3 deploy/tests/caddy_e2e.py                  # gera o export web do app num diretório temporário
    python3 deploy/tests/caddy_e2e.py /tmp/syncserv-web   # usa um export já pronto (npx expo export --platform web)

Precisa de Docker (baixa caddy:2.10.2-alpine na primeira vez) e do Playwright para Python. Nada sai da máquina: o
Caddy roda na rede do host, em portas locais, com certificado interno (tls internal) no teste de HTTP/2.

Confere:
- deploy/Caddyfile de produção válido (caddy validate, com [DOMINIO] trocado por um domínio de exemplo);
- landing: 404 de verdade com a página 404.html (também em caminho fundo, com o CSS carregando), página 50x.html com o
  status 5xx, testes/README/arquivos ocultos não servidos, compressão zstd e gzip, cache por tipo de arquivo;
- app: só "/" abre o app; outro caminho volta 404 com o app, que mostra "Página não encontrada"; JS inexistente é
  404 simples (não HTML); /api/* passa para o backend; backend fora do ar vira 502 com JSON que o app entende;
  CSP e cabeçalhos de segurança também nas respostas de erro;
- HTTP/2 por TLS e anúncio de HTTP/3 (Alt-Svc).
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGE = "caddy:2.10.2-alpine"
NAME = f"syncserv-caddy-teste-{os.getpid()}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


class FakeApi(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def get(url, encoding=None, method="GET"):
    """(status, cabeçalhos, corpo) sem seguir redirecionamento e sem lançar erro em 4xx/5xx."""
    req = urllib.request.Request(url, method=method, headers={"Accept-Encoding": encoding or "identity"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def export_web(dest: str):
    subprocess.run(["npx", "expo", "export", "--platform", "web", "--output-dir", dest], check=True,
                   cwd=os.path.join(ROOT, "mobile"), stdout=subprocess.DEVNULL)


def validate_production():
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(ROOT, "deploy", "caddy"), os.path.join(tmp, "caddy"))
        text = open(os.path.join(ROOT, "deploy", "Caddyfile"), encoding="utf-8").read()
        open(os.path.join(tmp, "Caddyfile"), "w").write(text.replace("[DOMINIO]", "exemplo.com.br"))
        out = subprocess.run(["docker", "run", "--rm", "-v", f"{tmp}:/etc/caddy:ro", IMAGE, "caddy", "validate",
                              "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
                             capture_output=True, text=True)
        check(out.returncode == 0 and "Valid configuration" in out.stdout + out.stderr,
              f"deploy/Caddyfile inválido:\n{out.stdout}\n{out.stderr}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def start_caddy(web: str, site: int, app: int, tls: int, api: int, dead: int) -> str:
    conf = tempfile.mkdtemp()
    # Mesmos snippets da produção; só muda o endereço (porta local) e um caminho que força erro 500 (teste da 50x)
    caddyfile = f"""{{
	admin off
	auto_https disable_redirects
	servers {{
		protocols h1 h2 h3
	}}
}}
http://127.0.0.1:{site} {{
	error /__teste-500 500
	import /deploy/caddy/site.caddy /srv/site
}}
http://127.0.0.1:{app} {{
	handle /__teste-500 {{
		error 500
	}}
	import /deploy/caddy/app.caddy /srv/web 127.0.0.1:{api}
}}
http://127.0.0.1:{dead} {{
	import /deploy/caddy/app.caddy /srv/web 127.0.0.1:9
}}
https://localhost:{tls} {{
	tls internal
	import /deploy/caddy/site.caddy /srv/site
}}
"""
    open(os.path.join(conf, "Caddyfile"), "w").write(caddyfile)
    subprocess.run(["docker", "run", "-d", "--rm", "--name", NAME, "--network", "host",
                    "-v", f"{conf}:/etc/caddy:ro", "-v", f"{os.path.join(ROOT, 'deploy')}:/deploy:ro",
                    "-v", f"{os.path.join(ROOT, 'landing')}:/srv/site:ro", "-v", f"{web}:/srv/web:ro",
                    IMAGE, "caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
                   check=True, stdout=subprocess.DEVNULL)
    for _ in range(50):
        try:
            get(f"http://127.0.0.1:{site}/")
            return conf
        except OSError:
            time.sleep(0.2)
    logs = subprocess.run(["docker", "logs", NAME], capture_output=True, text=True)
    raise AssertionError(f"Caddy não subiu:\n{logs.stdout}\n{logs.stderr}")


def test_site(base: str):
    # Página inicial: comprimida, HTML sempre revalidado, cabeçalhos
    for enc in ("zstd", "gzip"):
        st, h, _ = get(base + "/", enc)
        check(st == 200 and h.get("content-encoding") == enc, f"landing sem {enc}: {st} {h.get('content-encoding')}")
    st, h, body = get(base + "/")
    check(h.get("cache-control") == "no-cache", f"HTML com cache errado: {h.get('cache-control')}")
    check(h.get("x-content-type-options") == "nosniff" and "server" not in h, "cabeçalhos da landing")
    html = body.decode()
    css = html.split('href="styles.css?v=')[1].split('"')[0]
    st, h, _ = get(f"{base}/styles.css?v={css}")
    check(st == 200 and "immutable" in h.get("cache-control", ""), f"CSS versionado sem cache longo: {h}")
    st, h, _ = get(f"{base}/styles.css")
    check(h.get("cache-control") == "no-cache", "CSS sem versão não pode ficar em cache longo")
    st, h, _ = get(f"{base}/assets/fonts/plus-jakarta-sans-800-latin.woff2")
    check(st == 200 and h.get("cache-control") == "public, max-age=2592000", f"fonte: {h.get('cache-control')}")
    check(h.get("content-type") == "font/woff2", f"tipo da fonte: {h.get('content-type')}")
    st, h, _ = get(f"{base}/assets/syncserv-logo.svg", "gzip")
    check(h.get("cache-control") == "public, max-age=604800" and h.get("content-encoding") == "gzip",
          f"SVG: {h.get('cache-control')} {h.get('content-encoding')}")
    # 404 de verdade, com a página amigável
    for path in ("/nao-existe", "/planos/antigos/pagina.html", "/assets/nada.png"):
        st, h, body = get(base + path)
        check(st == 404 and "Página não encontrada" in body.decode(), f"{path}: {st}")
        check(h.get("x-content-type-options") == "nosniff", f"{path}: erro sem os cabeçalhos de segurança")
    # O que o rsync leva mas não deve ser servido
    for path in ("/tests/landing_e2e.py", "/README.md", "/tests/"):
        st, _, body = get(base + path)
        check(st == 404, f"{path} não pode ser servido ({st})")
    # 5xx com a página amigável e o status de erro
    st, h, body = get(base + "/__teste-500")
    check(st == 500 and "O site está com um problema" in body.decode(), f"50x: {st}")


def test_app(base: str, dead: str):
    st, h, body = get(base + "/", "zstd")
    check(st == 200 and h.get("content-encoding") == "zstd", "app sem zstd")
    for header in ("content-security-policy", "strict-transport-security", "x-frame-options", "referrer-policy",
                   "permissions-policy", "cross-origin-opener-policy"):
        check(header in h, f"app sem {header}")
    check(h.get("cache-control") == "no-cache", "index.html do app com cache")
    st, h, body = get(base + "/")
    js = body.decode().split('src="/_expo/static/js/web/')[1].split('"')[0]
    st, h, _ = get(f"{base}/_expo/static/js/web/{js}", "gzip")
    check(st == 200 and "immutable" in h.get("cache-control", "") and h.get("content-encoding") == "gzip",
          f"JS do app: {st} {h.get('cache-control')} {h.get('content-encoding')}")
    st, h, _ = get(f"{base}/fonts/plus-jakarta-sans-400-latin.woff2")
    check(st == 200 and h.get("cache-control") == "public, max-age=2592000", "fonte do app")
    # Rota desconhecida: 404 com o próprio app (o app mostra "Página não encontrada")
    st, h, body = get(base + "/clientes/123")
    check(st == 404 and '<div id="root">' in body.decode(), f"rota desconhecida do app: {st}")
    check("content-security-policy" in h, "404 do app sem CSP")
    # Arquivo de script inexistente: 404 simples, não o index.html (senão o navegador tenta rodar HTML como JS)
    st, h, body = get(f"{base}/_expo/static/js/web/nao-existe.js")
    check(st == 404 and b"<html" not in body.lower(), f"JS inexistente: {st} {body[:80]!r}")
    # API
    st, h, body = get(base + "/api/health")
    check(st == 200 and json.loads(body)["path"] == "/api/health", f"proxy da API: {st} {body[:80]!r}")
    st, h, body = get(dead + "/api/agenda")
    check(st == 502 and h.get("content-type", "").startswith("application/json"), f"API fora do ar: {st} {h}")
    check("fora do ar" in json.loads(body)["detail"], "mensagem da API fora do ar")
    # 5xx do próprio Caddy: página 50x.html do app
    st, h, body = get(base + "/__teste-500")
    check(st == 500 and "O SyncServ está com um problema" in body.decode(), f"50x do app: {st}")


def test_browser(site: str, app: str):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 375, "height": 812})
        errors = []
        page.on("console", lambda m: m.type == "error" and not m.text.startswith("Failed to load resource")
                and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))
        # Landing: 404 em caminho fundo continua com o CSS e a fonte (caminhos absolutos)
        resp = page.goto(site + "/um/caminho/que/nao/existe")
        check(resp.status == 404, f"404 da landing no navegador: {resp.status}")
        check(page.get_by_role("heading", name="Página não encontrada").is_visible(), "título do 404")
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        check(bg == "rgb(15, 23, 42)", f"404 sem o CSS: {bg}")
        check(page.evaluate("document.fonts.check('800 16px \"Plus Jakarta Sans\"')"), "404 sem a fonte")
        page.get_by_role("link", name="Ir para a página inicial").click()
        page.wait_for_url(site + "/")
        check(page.locator("h1").count() == 1, "o link do 404 não voltou à página inicial")
        # App: rota desconhecida mostra a tela "Página não encontrada"; o botão leva ao login
        resp = page.goto(app + "/agenda/antiga")
        check(resp.status == 404, f"404 do app no navegador: {resp.status}")
        page.get_by_text("Página não encontrada").wait_for(timeout=20000)
        page.get_by_role("button", name="Ir para o início").click()
        page.get_by_label("E-mail").wait_for(timeout=20000)
        check(page.url.rstrip("/") == app, f"o botão do 404 não voltou ao início: {page.url}")
        check(not errors, f"erros no console: {errors}")
        browser.close()


def test_http2(tls: int):
    out = subprocess.run(["curl", "-skI", "--http2", f"https://localhost:{tls}/"], capture_output=True, text=True)
    first = out.stdout.splitlines()[0] if out.stdout else out.stderr
    check(first.startswith("HTTP/2 200"), f"sem HTTP/2: {first}")
    check(f'h3=":{tls}"' in out.stdout.lower(), f"sem anúncio de HTTP/3 (alt-svc): {out.stdout}")


def main() -> int:
    if not shutil.which("docker"):
        print("FALHOU: precisa de Docker para rodar o Caddy de teste")
        return 1
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        subprocess.run(["docker", "pull", IMAGE], check=True, stdout=subprocess.DEVNULL)
    validate_production()
    tmp = None
    web = sys.argv[1] if len(sys.argv) > 1 else None
    if not web:
        tmp = tempfile.mkdtemp()
        web = os.path.join(tmp, "web")
        export_web(web)
    api = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", api), FakeApi)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    site, app, tls, dead = free_port(), free_port(), free_port(), free_port()
    conf = start_caddy(os.path.abspath(web), site, app, tls, api, dead)
    try:
        test_site(f"http://127.0.0.1:{site}")
        test_app(f"http://127.0.0.1:{app}", f"http://127.0.0.1:{dead}")
        test_browser(f"http://127.0.0.1:{site}", f"http://127.0.0.1:{app}")
        test_http2(tls)
    finally:
        subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)
        httpd.shutdown()
        shutil.rmtree(conf, ignore_errors=True)
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    print("caddy ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
