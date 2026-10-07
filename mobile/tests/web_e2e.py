"""Teste ponta a ponta da versão web. Jeito fácil: `npm run test:web` (tests/run_web_e2e.sh sobe um backend
descartável com dados fictícios, gera o export e roda este arquivo). Manual:

    cd mobile && npx expo export --platform web --output-dir /tmp/syncserv-web
    python3 tests/web_e2e.py /tmp/syncserv-web http://localhost:8000      # backend com os dados do seed_mock

Serve o export com o MESMO CSP do deploy/Caddyfile.app (mais o endereço da API em connect-src, porque aqui a API
fica em outra porta) e confere, no Chromium (Playwright), em 375 e 1440 px:
- login, abas por papel e menu lateral no computador;
- o token de acesso não vai para o sessionStorage, nada vai para o localStorage;
- recarregar a aba mantém a sessão (refresh token); aba nova pede login;
- sem internet: aviso e escrita bloqueada;
- nenhum erro no console nem bloqueio do CSP (que não tem 'unsafe-inline'); fontes e ícones carregados.
"""
import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

FONTS = tuple(f"PlusJakartaSans_{w}" for w in ("400Regular", "500Medium", "600SemiBold", "700Bold", "800ExtraBold")) + (
    "ionicons",)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def csp(api_origin: str) -> str:
    caddy = open(os.path.join(ROOT, "deploy", "Caddyfile.app"), encoding="utf-8").read()
    policy = re.search(r'Content-Security-Policy "([^"]+)"', caddy).group(1)
    return policy.replace("connect-src 'self'", f"connect-src 'self' {api_origin}")


class Handler(http.server.SimpleHTTPRequestHandler):
    policy = ""

    def end_headers(self):
        self.send_header("Content-Security-Policy", self.policy)
        super().end_headers()

    def send_head(self):  # fallback de app de página única, como o try_files do Caddy
        if not os.path.exists(self.translate_path(self.path)):
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *a):
        pass


def serve(directory: str, api: str) -> str:
    Handler.policy = csp(api)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=directory))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def login(pg, web, api, email, password="demo123"):
    pg.goto(web + "/agenda-qualquer")  # rota desconhecida: o fallback devolve o app
    pg.get_by_label("E-mail").fill(email)
    pg.get_by_label("Senha").fill(password)
    if pg.get_by_label("Endereço do servidor").count() == 0:
        pg.get_by_text("Servidor:").click()
    pg.get_by_label("Endereço do servidor").fill(api)
    pg.get_by_role("button", name="Entrar").click()
    pg.get_by_text("Agenda", exact=True).first.wait_for(timeout=15000)


def main(directory: str, api: str) -> None:
    web = serve(directory, api)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width, height in ((1440, 900), (375, 800)):
            ctx = browser.new_context(viewport={"width": width, "height": height})
            pg = ctx.new_page()
            pg.on("console", lambda m: problems.append(f"{width}px console: {m.text}") if m.type == "error" else None)
            pg.on("pageerror", lambda e: problems.append(f"{width}px erro: {e}"))
            pg.add_init_script("window.__csp = []; document.addEventListener('securitypolicyviolation',"
                               " (e) => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI))")
            login(pg, web, api, "admin@demo.com")
            assert pg.title() == "SyncServ"
            # CSP sem 'unsafe-inline' em style-src: nada bloqueado, e fontes e ícones carregados de verdade
            # (sem wait_for_function: ele usa eval, que o próprio CSP bloqueia)
            loaded = "() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/\"/g, ''))"
            for _ in range(30):
                missing = set(FONTS) - set(pg.evaluate(loaded))
                if not missing:
                    break
                pg.wait_for_timeout(500)
            assert not missing, missing
            assert pg.evaluate("window.__csp") == []
            keys = pg.evaluate("Object.keys(sessionStorage)")
            assert "syncserv:refreshToken" in keys and "syncserv:token" not in keys, keys
            assert pg.evaluate("localStorage.length") == 0
            if width >= 900:
                assert pg.get_by_text("Gestão", exact=True).count() == 1, "menu lateral"
            else:
                assert pg.get_by_text("Gestão", exact=True).count() == 0, "celular sem menu lateral"
            pg.reload()
            pg.get_by_text("Agenda", exact=True).first.wait_for(timeout=15000)
            pg.get_by_text("Caixa", exact=True).first.click()
            pg.get_by_role("button", name="Nova comanda").wait_for()
            ctx.set_offline(True)
            pg.get_by_text("Sem conexão. A versão web funciona só com internet", exact=False).wait_for(timeout=5000)
            pg.get_by_role("button", name="Nova comanda").click()
            pg.get_by_role("button", name="Sem cliente (venda avulsa)").click()
            pg.get_by_text("alterações só podem ser feitas com internet", exact=False).first.wait_for(timeout=5000)
            ctx.set_offline(False)
            ctx.close()
        # Papéis: recepção sem Finanças; profissional só Agenda, Clientes e Comissões
        for email, present, absent in (("recepcao@demo.com", ["Caixa"], ["Finanças"]),
                                       ("profissional@demo.com", ["Comissões"], ["Caixa", "Finanças"])):
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            login(pg, web, api, email)
            for t in present:
                assert pg.get_by_text(t, exact=True).count() >= 1, (email, t)
            for t in absent:
                assert pg.get_by_text(t, exact=True).count() == 0, (email, t)
            ctx.close()
        ctx = browser.new_context()
        pg = ctx.new_page()
        pg.goto(web)
        pg.get_by_role("button", name="Entrar").wait_for(timeout=15000)  # aba nova: login de novo
        browser.close()
    assert not problems, "\n".join(problems)
    print("web ok")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].rstrip("/"))
