"""Teste da landing page no Chromium (Playwright), em 375, 768 e 1440 px.

    python3 landing/tests/landing_e2e.py                 # da raiz do repositório
    python3 landing/tests/landing_e2e.py /tmp/prints     # também salva capturas de tela de cada largura

Serve a pasta landing/ num servidor local descartável e BLOQUEIA qualquer pedido para fora do localhost
(Google Fonts, wa.me): a página tem de funcionar só com os próprios arquivos. Confere:
- nada passa da largura da tela (sem rolagem lateral) e os mockups cabem;
- os 9 cards novos, os mockups (comanda no celular e versão web com menu lateral) e a troca de nicho;
- o comparativo, os planos com [PREÇO INDIVIDUAL]/[PREÇO EQUIPE] e as 4 perguntas novas, que abrem ao tocar;
- menu do celular, links internos (#...) que existem, imagens carregadas, um h1 só, nenhum erro no console;
- nada de "Pix automático", depoimentos ou avaliações inventadas; a política fala do banco criptografado.
"""
import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

LANDING = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIDTHS = (375, 768, 1440)
CARDS = ("Comanda e caixa", "Estoque", "Pacotes", "Clube de assinatura", "Sinal contra faltas", "Lista de espera",
         "Equipe com permissões", "App que funciona sem internet", "Versão web para a recepção")
FAQ = ("Funciona sem internet?", "Posso usar no computador?", "Cada profissional tem seu acesso?",
       "Como funcionam pacotes e assinaturas?")
SIDE = ("Hoje", "Agenda", "Caixa", "Clientes", "Produtos e estoque", "Clube de assinatura", "Equipe e permissões")
FORBIDDEN = re.compile(r"pix autom[aá]tico|depoimento|quem usa, recomenda|\d+\s*mil clientes|nota 4[,.]\d|★", re.I)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve() -> str:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=LANDING))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{httpd.server_address[1]}"


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run_width(browser, base, width, shots):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
    blocked = []
    errors = []

    def route(r):
        if r.request.url.startswith(base):
            return r.continue_()
        blocked.append(r.request.url)
        return r.abort()

    ctx.route("**/*", route)
    pg = ctx.new_page()
    pg.on("console", lambda m: m.type == "error" and "net::ERR_FAILED" not in m.text and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(base + "/index.html")
    pg.wait_for_load_state("load")
    tag = f"[{width}px]"

    # sem rolagem lateral, nem com a página inteira renderizada
    over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check(over <= 0, f"{tag} rolagem lateral de {over}px")
    wide = pg.evaluate("""() => [...document.querySelectorAll('main *')].filter(e => {
        const r = e.getBoundingClientRect();
        return r.width && (r.right > innerWidth + 1 || r.left < -1) && !e.closest('.compare, .sr-only, .skip');
    }).map(e => e.className || e.tagName).slice(0, 5)""")
    check(not wide, f"{tag} elementos passando da tela: {wide}")

    check(pg.locator("h1").count() == 1, f"{tag} deve haver um h1 só")

    # cards novos
    for title in CARDS:
        card = pg.locator(".features--crm h3", has_text=re.compile(f"^{re.escape(title)}$"))
        check(card.count() == 1, f"{tag} card ausente: {title}")
        card.scroll_into_view_if_needed()
        check(card.is_visible(), f"{tag} card invisível: {title}")

    # mockup da comanda (celular) e da versão web (menu lateral)
    comanda = pg.locator(".js-mock-comanda")
    comanda.scroll_into_view_if_needed()
    check("Fechar comanda" in comanda.inner_text(), f"{tag} comanda sem o botão de fechar")
    check("Pomada modeladora" in comanda.inner_text(), f"{tag} comanda sem o produto da barbearia")
    check(pg.locator(".m-offline").is_visible(), f"{tag} faixa de sem conexão não aparece")
    check(pg.locator(".js-mock-comanda .m-tag--sync").inner_text() == "A confirmar", f"{tag} selo A confirmar")
    side = pg.locator(".w-side")
    check(side.is_visible(), f"{tag} menu lateral da versão web não aparece")
    side_text = side.inner_text()
    for item in SIDE[:4]:
        check(item in side_text, f"{tag} item do menu lateral ausente: {item}")
    if width >= 768:
        for item in SIDE[4:]:
            check(item in side_text, f"{tag} item de gestão ausente no menu lateral: {item}")
    cols = pg.locator(".js-mock-web .w-col:visible").count()
    check(cols >= 2, f"{tag} a versão web deve mostrar pelo menos 2 profissionais lado a lado (tem {cols})")
    for sel in (".phone--comanda", ".browser", ".phones"):
        box = pg.locator(sel).bounding_box()
        check(box and box["x"] >= 0 and box["x"] + box["width"] <= width + 1, f"{tag} {sel} não cabe na tela: {box}")

    # troca de nicho atualiza os mockups novos
    pg.locator('.niche[data-niche="petshop"]').click()
    check("Shampoo neutro" in comanda.inner_text(), f"{tag} comanda não trocou de nicho")
    check("Dra. Paula" in pg.locator(".js-mock-web").text_content(), f"{tag} versão web não trocou de nicho")
    pg.locator('.niche[data-niche="barbershop"]').click()

    # comparativo e planos
    compare = pg.locator("table").inner_text()
    for t in ("Comanda com serviços", "sincroniza quando a internet volta", "Lista de espera", "Login para cada pessoa"):
        check(t in compare, f"{tag} comparativo sem: {t}")
    check(pg.locator('[data-price="individual"]').inner_text() == "[PREÇO INDIVIDUAL]", f"{tag} preço individual")
    check(pg.locator('[data-price="equipe"]').inner_text() == "[PREÇO EQUIPE]", f"{tag} preço equipe")
    plans = pg.locator("#precos").inner_text()
    for t in ("Comanda e caixa", "Produtos e estoque", "Pacotes e clube de assinatura", "funciona sem internet",
              "permissões por papel"):
        check(t in plans, f"{tag} planos sem: {t}")

    # FAQ novas abrem ao tocar
    for q in FAQ:
        summary = pg.locator("summary", has_text=q)
        check(summary.count() == 1, f"{tag} pergunta ausente: {q}")
        summary.scroll_into_view_if_needed()
        summary.click()
        check(summary.locator("xpath=..").evaluate("d => d.open"), f"{tag} pergunta não abriu: {q}")
    offline = pg.locator("details", has=pg.locator("summary", has_text=FAQ[0])).inner_text()
    check("sempre online" in offline and "sincronizado" in offline, f"{tag} resposta do sem internet incompleta")

    # nada inventado
    text = pg.locator("body").inner_text()
    check(not FORBIDDEN.search(text), f"{tag} texto proibido: {FORBIDDEN.search(text)}")
    check(pg.locator("#depoimentos").count() == 0, f"{tag} seção de depoimentos deve seguir oculta")
    check("aggregateRating" not in pg.content(), f"{tag} JSON-LD não pode ter avaliações")

    # menu: no celular e no tablet abre pelo botão; no computador fica à mostra
    nav = pg.locator("#menu")
    if width < 900:
        pg.evaluate("scrollTo(0, 0)")
        check(not nav.is_visible(), f"{tag} menu deveria começar fechado")
        pg.locator(".menu-btn").click()
        check(nav.is_visible() and pg.locator("#menu a", has_text="Gestão").is_visible(), f"{tag} menu não abriu")
        pg.locator("#menu a", has_text="Gestão").click()
        check(not nav.is_visible(), f"{tag} menu não fechou ao escolher")
    else:
        check(pg.locator("#menu a", has_text="Gestão").is_visible(), f"{tag} link Gestão no menu")

    # links internos e imagens
    missing = pg.evaluate("""() => [...document.querySelectorAll('a[href^="#"], use')]
        .map(a => a.getAttribute('href')).filter(h => h && h.length > 1 && !document.getElementById(h.slice(1)))""")
    check(not missing, f"{tag} âncoras sem destino: {missing}")
    pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pg.wait_for_function("[...document.images].every(i => i.complete)")
    broken = pg.evaluate("[...document.images].filter(i => !i.naturalWidth).map(i => i.src)")
    check(not broken, f"{tag} imagens quebradas: {broken}")

    check(not errors, f"{tag} erros no console: {errors}")
    outside = [u for u in blocked if not u.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com"))]
    check(not outside, f"{tag} pedidos para fora além das fontes: {outside}")

    if shots:
        pg.evaluate("scrollTo(0, 0)")
        pg.screenshot(path=os.path.join(shots, f"landing-{width}.png"), full_page=True)
        pg.locator("#gestao").screenshot(path=os.path.join(shots, f"gestao-{width}.png"))

    # política de privacidade
    pg.goto(base + "/privacidade.html")
    policy = pg.locator("main").inner_text()
    for t in ("criptografado", "apagadas do aparelho", "ao sair da conta", "não guarda dados dos clientes no computador"):
        check(t in policy, f"{tag} política sem: {t}")
    over = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    check(over <= 0, f"{tag} política com rolagem lateral de {over}px")
    ctx.close()


def main():
    shots = sys.argv[1] if len(sys.argv) > 1 else ""
    if shots:
        os.makedirs(shots, exist_ok=True)
    base = serve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for w in WIDTHS:
                run_width(browser, base, w, shots)
                print(f"{w}px ok")
        finally:
            browser.close()
    print("landing ok")


if __name__ == "__main__":
    main()
