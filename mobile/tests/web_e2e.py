"""Teste ponta a ponta da versão web. Jeito fácil: `npm run test:web` (tests/run_web_e2e.sh sobe um backend
descartável com dados fictícios, gera o export e roda este arquivo). Manual:

    cd mobile && npx expo export --platform web --output-dir /tmp/syncserv-web
    python3 tests/web_e2e.py /tmp/syncserv-web http://localhost:8000      # backend com os dados do seed_mock

Serve o export com o MESMO CSP do deploy/caddy/app-headers.caddy (mais o endereço da API em connect-src, porque aqui a
API fica em outra porta) e as mesmas regras de 404 do deploy/caddy/app.caddy, e confere, no Chromium (Playwright), em
375 e 1440 px:
- login só com e-mail e senha (sem campo de servidor), "E-mail ou senha incorretos" igual para e-mail que existe ou
  não, "Esqueci minha senha"; conta com dois negócios: "Escolha o negócio" e Mais > Trocar de negócio;
- abas por papel e menu lateral no computador;
- o token de acesso não vai para o sessionStorage, nada vai para o localStorage;
- recarregar a aba mantém a sessão (refresh token); aba nova pede login;
- sem internet: aviso e escrita bloqueada, com o erro aparecendo NA FRENTE do sheet (A02);
- tocar num horário vago da agenda abre o agendamento rápido (A01: o clique do mouse não tem locationY);
- nenhum erro no console nem bloqueio do CSP (que não tem 'unsafe-inline'); fontes e ícones carregados, em woff2
  (nenhum TTF baixado);
- endereço desconhecido: status 404 e a tela "Página não encontrada", com o botão que volta ao login;
- a abertura em HTML some quando o app monta; as telas vêm em pedaços separados do JavaScript, e um pedaço que não
  baixa (internet caiu) mostra o erro com "Tentar de novo", que funciona quando a conexão volta.
"""
import functools
import http.server
import io
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

FONTS = tuple(f"PlusJakartaSans_{w}" for w in ("400Regular", "500Medium", "600SemiBold", "700Bold", "800ExtraBold")) + (
    "ionicons",)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MULTI = "duas.empresas@demo.com"  # criada pelo run_web_e2e.sh: dona da Barbearia Demo e da Segunda Loja Demo


def csp(api_origin: str) -> str:
    caddy = open(os.path.join(ROOT, "deploy", "caddy", "app-headers.caddy"), encoding="utf-8").read()
    policy = re.search(r'Content-Security-Policy "([^"]+)"', caddy).group(1)
    # No Caddy, {args[0]} é o domínio (a API em https://api.<domínio>); aqui a API está em outra porta local
    return policy.replace("https://api.{args[0]}", api_origin)


class Handler(http.server.SimpleHTTPRequestHandler):
    policy = ""

    def end_headers(self):
        self.send_header("Content-Security-Policy", self.policy)
        super().end_headers()

    def send_head(self):  # como o deploy/caddy/app.caddy: caminho desconhecido = 404 com o próprio app
        path = self.path.split("?")[0]
        if path != "/" and not os.path.exists(self.translate_path(path)):
            if re.search(r"^/(_expo|assets|fonts|icons)/|\.(js|css|png|svg|ico|woff2|ttf|json)$", path):
                self.send_error(404)
                return None
            body = open(os.path.join(self.directory, "index.html"), "rb").read()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return io.BytesIO(body)
        return super().send_head()

    def log_message(self, *a):
        pass


def serve(directory: str, api: str) -> str:
    Handler.policy = csp(api)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=directory))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def login(pg, web, api, email, password="demo123", wait=True):
    """Só e-mail e senha: o endereço da API veio no build (EXPO_PUBLIC_API_URL do run_web_e2e.sh)."""
    pg.goto(web + "/")
    pg.get_by_label("E-mail").fill(email)
    pg.get_by_label("Senha", exact=True).fill(password)
    pg.get_by_role("button", name="Entrar").click()
    if wait:
        pg.get_by_text("Agenda", exact=True).first.wait_for(timeout=15000)


def check_login_screen(pg, web, api):
    """Tela de login: sem servidor nem "Configuração avançada"; erro claro abaixo dos campos; "Esqueci minha senha"."""
    pg.goto(web + "/")
    pg.get_by_label("E-mail").wait_for(timeout=15000)
    assert pg.get_by_label("Endereço do servidor").count() == 0
    assert pg.get_by_text("Configuração avançada").count() == 0
    login(pg, web, api, "admin@demo.com", "senha-errada", wait=False)
    pg.get_by_text("E-mail ou senha incorretos").wait_for(timeout=10000)
    login(pg, web, api, "ninguem@exemplo.com", "senha-errada", wait=False)  # mesma frase: não revela o e-mail
    pg.get_by_text("E-mail ou senha incorretos").wait_for(timeout=10000)
    pg.get_by_role("button", name="Esqueci minha senha").click()
    pg.get_by_text("senha provisória", exact=False).first.wait_for(timeout=5000)


def check_two_businesses(pg, web, api):
    """Conta com dois negócios: "Escolha o negócio" no login e Mais > Trocar de negócio, sem sair da conta."""
    login(pg, web, api, MULTI, wait=False)
    pg.get_by_text("Escolha o negócio").wait_for(timeout=15000)
    pg.get_by_role("button", name="Segunda Loja Demo", exact=False).click()
    pg.get_by_text("Agenda", exact=True).first.wait_for(timeout=15000)
    assert pg.get_by_text("Segunda Loja Demo").count() >= 1
    pg.locator('[aria-label="Mais opções"]').first.click()
    pg.get_by_role("button", name="Trocar de negócio").click()
    pg.get_by_role("button", name="Barbearia Demo", exact=False).click()
    pg.get_by_role("button", name="Trocar", exact=True).click()
    pg.get_by_text("Barbearia Demo").first.wait_for(timeout=15000)
    assert pg.evaluate("sessionStorage.getItem('syncserv:shopName')") == "Barbearia Demo"
    # O próximo login (aba nova, mesma conta) abre direto no último negócio escolhido? Na web a lembrança é da aba
    # (sessionStorage); no celular fica no SecureStore.


def open_quick_book(pg) -> bool:
    """Clica em pontos vagos da grade (de hoje em diante) até abrir o agendamento rápido. Antes da correção do A01,
    todo clique respondia "Esse horário não está livre"."""
    pg.get_by_text("Agenda", exact=True).first.click()
    pg.locator('[aria-label^="Horários de"]').first.wait_for(timeout=15000)
    for _ in range(4):  # hoje pode já ter passado (teste à noite): tenta os próximos dias
        pg.wait_for_timeout(600)
        points = pg.evaluate("""() => {
            const out = [];
            for (const col of document.querySelectorAll('[aria-label^="Horários de"]')) {
                const r = col.getBoundingClientRect();
                const x = Math.min(r.left + 12, innerWidth - 2);
                for (let y = Math.max(r.top, 0) + 10; y < Math.min(r.bottom, innerHeight) - 4; y += 19) {
                    const hit = document.elementFromPoint(x, y);
                    if (hit === col) out.push([x, y]);
                }
            }
            return out;
        }""")
        for x, y in points[::2][:40]:
            pg.mouse.click(x, y)
            pg.wait_for_timeout(350)
            if pg.get_by_role("button", name="Agendar", exact=True).count():
                return True
        pg.get_by_role("button", name="Próximo dia").click()
    return False


def toast_on_top(pg) -> bool:
    """O aviso está visível e é o elemento de cima no ponto onde aparece (não escondido atrás de um Modal)."""
    return pg.evaluate("""() => [...document.querySelectorAll('[data-testid="toast"]')].some(t => {
        const r = t.getBoundingClientRect();
        if (!r.width || !r.height) return false;
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return !!hit && t.contains(hit);
    })""")


def main(directory: str, api: str) -> None:
    web = serve(directory, api)
    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        pg.on("console", lambda m: problems.append(f"login console: {m.text}") if m.type == "error"
              and "401" not in m.text else None)  # o 401 da senha errada aparece no console do navegador
        check_login_screen(pg, web, api)
        ctx.close()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        check_two_businesses(pg, web, api)
        ctx.close()
        # Endereço desconhecido: 404 de verdade e a tela do app "Página não encontrada"
        ctx = browser.new_context(viewport={"width": 375, "height": 800})
        pg = ctx.new_page()
        resp = pg.goto(web + "/agenda/antiga")
        assert resp.status == 404, resp.status
        pg.get_by_role("heading", name="Página não encontrada").wait_for(timeout=15000)
        pg.get_by_role("button", name="Ir para o início").click()
        pg.get_by_label("E-mail").wait_for(timeout=15000)
        assert pg.url.rstrip("/") == web, pg.url
        ctx.close()
        for width, height in ((1440, 900), (375, 800)):
            ctx = browser.new_context(viewport={"width": width, "height": height})
            pg = ctx.new_page()
            fonts = []
            pg.on("request", lambda r: fonts.append(r.url) if re.search(r"\.(ttf|woff2?)(\?|$)", r.url) else None)
            quiet = []  # passos que provocam erro de rede de propósito
            pg.on("console", lambda m: problems.append(f"{width}px console: {m.text}")
                  if m.type == "error" and not quiet else None)
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
            assert not [u for u in fonts if u.endswith(".ttf") or ".ttf?" in u], fonts  # web: só woff2
            assert pg.locator(".abertura").count() == 0, "a abertura em HTML continua na tela"
            assert pg.evaluate("window.__csp") == []
            keys = pg.evaluate("Object.keys(sessionStorage)")
            assert "syncserv:refreshToken" in keys and "syncserv:token" not in keys, keys
            assert pg.evaluate("localStorage.length") == 0
            if width >= 900:
                assert pg.get_by_text("Gestão", exact=True).count() == 1, "menu lateral"
                # Tela sob demanda sem internet: erro com "Tentar de novo"; com a conexão de volta, abre
                quiet.append(1)
                pg.route("**/_expo/static/js/web/Stock-*.js", lambda r: r.abort())
                pg.locator('[aria-label="Produtos e estoque"]').first.click()
                pg.get_by_text("Não foi possível abrir esta tela", exact=False).wait_for(timeout=10000)
                pg.unroute("**/_expo/static/js/web/Stock-*.js")
                pg.get_by_role("button", name="Tentar de novo").click()
                pg.get_by_label("Novo produto").first.wait_for(timeout=10000)
                quiet.clear()
            else:
                assert pg.get_by_text("Gestão", exact=True).count() == 0, "celular sem menu lateral"
            pg.reload()
            pg.get_by_text("Agenda", exact=True).first.wait_for(timeout=15000)
            # A01: clique num horário vago abre o agendamento rápido (sheet com o botão Agendar)
            assert open_quick_book(pg), f"{width}px: clique em horário vago não abriu o agendamento rápido"
            pg.keyboard.press("Escape")
            pg.get_by_role("button", name="Agendar", exact=True).wait_for(state="detached", timeout=5000)
            pg.get_by_text("Caixa", exact=True).first.click()
            pg.get_by_role("button", name="Nova comanda").wait_for()
            ctx.set_offline(True)
            pg.get_by_text("Sem conexão. A versão web funciona só com internet", exact=False).wait_for(timeout=5000)
            pg.get_by_role("button", name="Nova comanda").click()
            pg.get_by_role("button", name="Sem cliente (venda avulsa)").click()
            pg.get_by_text("alterações só podem ser feitas com internet", exact=False).first.wait_for(timeout=5000)
            # A02: o erro de uma ação feita dentro do sheet aparece na frente dele, não escondido atrás do Modal
            assert toast_on_top(pg), f"{width}px: aviso de erro escondido atrás do sheet"
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
