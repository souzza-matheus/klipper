# Landing page do SyncServ

Site estático de vendas (HTML, CSS e JavaScript puro, sem framework e sem build). Objetivo: o dono do negócio começar o teste grátis de 7 dias pelo WhatsApp.

```
landing/
├── index.html         página de vendas (com o CSS crítico embutido no <head>, gerado pelo scripts/build-landing)
├── styles.css         estilos (mobile first)
├── main.js            configuração (número, preços), seletor de nicho, simulador do robô, mockups, calculadora, menu
├── tests/landing_e2e.py  teste no Chromium (Playwright) em 375, 768 e 1440 px
├── privacidade.html   Política de Privacidade (MODELO, revisar com advogado)
├── termos.html        Termos de Uso (MODELO, revisar com advogado)
├── 404.html, 50x.html páginas de erro (o Caddy as devolve com o status de verdade)
├── site.webmanifest, robots.txt, sitemap.xml, favicon.ico
└── assets/            kit de marca (logo, favicons, imagem de compartilhamento, símbolos dos nichos) e fonts/
                       (Plus Jakarta Sans em woff2, licença SIL OFL 1.1 em fonts/OFL.txt)
```

## Antes de publicar: preencha os marcadores

| Marcador | Onde | O que colocar |
| --- | --- | --- |
| `WHATSAPP_NUMBER = "[NUMERO]"` | topo do `main.js` | número que recebe os pedidos de teste, só dígitos com DDI e DDD (ex.: `5531999998888`). Todos os botões de ação usam esse número, com a mensagem pronta e o nicho escolhido |
| `DEMO_NUMBER = ""` | topo do `main.js` | opcional: número do robô de demonstração. Preenchido, aparece o botão "Falar com o robô de verdade" na seção de demonstração |
| `PRICES` (`[PREÇO INDIVIDUAL]`, `[PREÇO EQUIPE]`) | topo do `main.js` | texto do preço de cada plano (ex.: `"R$ 79"`). O HTML tem os mesmos marcadores para quem abre sem JavaScript |
| `[DOMINIO]` | `index.html`, `privacidade.html`, `termos.html`, `robots.txt`, `sitemap.xml` | domínio sem `https://` (ex.: `syncserv.com.br`). Usado no canonical, no Open Graph, no Twitter Card, no JSON-LD e no sitemap |
| `[NUMERO]` | `href` dos botões no `index.html` | o mesmo número (é o link usado se o JavaScript não carregar) |
| `[EMAIL]`, `[CNPJ]`, `[CIDADE/UF]` | rodapé do `index.html` e páginas legais | contato e dados da empresa |
| `[RAZÃO SOCIAL]`, `[DATA]`, `[PRAZO]`, `[PROVEDOR]` etc. | `privacidade.html` e `termos.html` | completar e **revisar com um advogado** antes de publicar (tirar o aviso "MODELO" do topo depois da revisão) |

**Verificação antes de publicar:** `LANDING_ENV=production python3 landing/tests/landing_e2e.py` falha se sobrar
qualquer marcador (`[` + letra maiúscula, ex.: `[DOMINIO]`, `[PREÇO EQUIPE]`) no HTML final das três páginas (depois de
o `main.js` rodar), no `robots.txt`, no `sitemap.xml` ou no `site.webmanifest`. Comentários HTML não contam. Sem
`LANDING_ENV=production` (desenvolvimento), o teste só lista o que falta preencher.

Para trocar tudo de uma vez (Linux/macOS):

```bash
cd landing
grep -rl "\[DOMINIO\]" . | xargs sed -i 's/\[DOMINIO\]/syncserv.com.br/g'
grep -rl "\[NUMERO\]" .  | xargs sed -i 's/\[NUMERO\]/5531999998888/g'
```

Outros pontos deixados prontos:

- **Depoimentos:** a seção está comentada no `index.html` (procure "Depoimentos"). Só descomente com depoimentos reais e autorizados; não use nomes, fotos ou logos inventados.
- **Métricas:** o site não usa cookies nem rastreamento. Há um comentário no `<head>` do `index.html` com o lugar para colar um script de métricas; prefira uma ferramenta sem cookies (Plausible, Umami, Cloudflare Web Analytics). Se usar algo com cookies, peça consentimento antes e cite na Política de Privacidade.
- **Preço no Google:** o JSON-LD (`SoftwareApplication`) não tem `offers` porque os preços ainda não estão definidos. Quando estiverem, dá para acrescentar `"offers": {"@type": "Offer", "price": "79.00", "priceCurrency": "BRL"}`. Não acrescente avaliações (`aggregateRating`) sem avaliações reais.

## Ver no computador

Abrir o `index.html` direto no navegador funciona. Para testar como em produção (caminhos, manifest), sirva a pasta:

```bash
cd landing
python3 -m http.server 8080      # http://localhost:8080
```

## Publicar

### Opção 1: hospedagem estática (Cloudflare Pages, Netlify ou Vercel)

Não há build: publique a pasta `landing/` como está.

- **Cloudflare Pages:** Workers & Pages > Create > Pages > conectar o repositório (ou "Upload assets" com a pasta). Build command: vazio. Build output directory: `landing`.
- **Netlify:** Add new site > Import from Git (ou arraste a pasta `landing` em "Deploy manually"). Build command: vazio. Publish directory: `landing`.
- **Vercel:** Add New > Project > importar o repositório. Framework preset: Other. Root directory: `landing`. Build command e output directory: vazios.

Depois, aponte o domínio no painel do serviço (o HTTPS é automático).

### Opção 2: Caddy na VPS (recomendado; é o que os testes conferem)

Copie a pasta para a VPS (`rsync -a --delete landing/ usuario@vps:/srv/syncserv-site/`) e use o `deploy/Caddyfile`
do repositório (troque `[DOMINIO]`; ver o README da raiz). A parte da landing está em `deploy/caddy/site.caddy`:

- compressão zstd e gzip; HTTP/1.1, HTTP/2 e HTTP/3 (libere a porta 443 em UDP no firewall para o HTTP/3);
- cache: `styles.css` e `main.js` com `?v=` por um ano (imutável), fontes por 30 dias, imagens por 7 dias, HTML,
  manifest, robots e sitemap sempre revalidados;
- endereço que não existe: status 404 com a `404.html`; erro do servidor: status 5xx com a `50x.html`;
- `tests/`, `README.md` e arquivos ocultos não são servidos (o rsync leva a pasta inteira);
- cabeçalhos `X-Content-Type-Options`, `Referrer-Policy` e sem `Server`, também nas páginas de erro.

**Antes de publicar uma mudança** no `styles.css`, no `main.js` ou no topo do `index.html`, rode
`python3 scripts/build-landing` (da raiz): ele refaz o CSS crítico e troca o `?v=` dos arquivos. O teste da landing
falha se você esquecer.

## Testar

```bash
python3 landing/tests/landing_e2e.py              # da raiz do repositório
python3 landing/tests/landing_e2e.py /tmp/prints  # também salva capturas de cada largura
LANDING_ENV=production python3 landing/tests/landing_e2e.py   # antes de publicar: falha com marcador sobrando
```

Precisa do Playwright para Python (`pip install playwright && playwright install chromium`). O teste serve a pasta num
servidor local descartável e bloqueia qualquer pedido para fora (wa.me): a página, as fontes inclusive, tem de
funcionar só com os próprios arquivos. Em 375, 768 e 1440 px confere:
sem rolagem lateral, os 9 cards da gestão, os mockups (comanda no celular e versão web com menu lateral) e a troca de
nicho neles, o comparativo, os planos com os marcadores de preço, as perguntas novas abrindo, o menu do celular, links
internos, imagens, um h1 só, nenhum erro no console, nada de "Pix automático" nem depoimentos, e a política de
privacidade com o banco criptografado do celular. Também: o comparativo sem rolagem lateral no celular (vira pares
"Sem/Com" empilhados), o botão "Falar com o robô de verdade" escondido enquanto não houver número, alvos de 48 px na
calculadora, no simulador e no rodapé, os botões − e + do valor médio e o CTA depois do resultado da calculadora.
Também: a Plus Jakarta Sans carregada do próprio site, a primeira tela só com o CSS crítico idêntica à com o CSS
inteiro e o `scripts/build-landing --check` em dia.

O Caddy (404, 5xx, compressão, cache, HTTP/2) tem teste próprio, com o Caddy de verdade no Docker:
`python3 deploy/tests/caddy_e2e.py` (ver o README da raiz).

## Desempenho e acessibilidade

Lighthouse no celular, servido pelo Caddy com as configurações de produção e o 4G aplicado de verdade: 100 em
desempenho (LCP 0,9 s, CLS 0,018, TBT 40 ms), 100 em acessibilidade e boas práticas. O SEO fica em 85 enquanto o
canonical e o `robots.txt` apontam para `[DOMINIO]`, que não é uma URL válida. Medições de antes e depois em
`audit/AUDITORIA-UX.md` (bloco 2).

- **Fonte:** Plus Jakarta Sans (500 e 800) servida pelo próprio site, em woff2 só com o recorte latino (15 KB por
  peso), com `preload` e `font-display: swap`. Enquanto ela não chega, o texto usa a "Jakarta Reserva" (Arial,
  Liberation Sans ou Roboto com `size-adjust` e `ascent/descent-override` calculados), que ocupa o mesmo espaço: o
  texto não pula na troca. Os arquivos e os números vêm do `python3 scripts/build-fonts` (a partir do pacote
  `@expo-google-fonts/plus-jakarta-sans` do app; precisa de `pip install fonttools brotli`).
- **CSS crítico:** as regras do cabeçalho e do hero vão no `<style id="css-critico">` do `<head>`; o `styles.css` inteiro
  carrega no fim do `<body>`. Gerado pelo `python3 scripts/build-landing` (não edite o bloco à mão).
- **JavaScript:** um arquivo só (`main.js`, 21 KB), com `defer`.
- **Imagens:** logo e símbolos em SVG otimizados (svgo); imagens abaixo da dobra com `loading="lazy"`; largura e
  altura definidas em todas. Os celulares do hero são HTML/CSS. `python3 scripts/optimize-images` lista as imagens e
  onde são usadas; com `--write` otimiza (svgo, PNG sem perda) e, para fotos colocadas em `assets/img/`, gera AVIF e
  WebP em 480, 960 e 1440 px e imprime o `<picture>` com `srcset` para colar no HTML; `--check` falha se algo ainda
  puder ser otimizado.
- Contraste: contornos de controles (botões secundários, nichos, menu, botões − e +) usam `--control` `#64748B`
  (3:1 contra o fundo); `#334155` (`--border`) fica só nas divisórias.
- Contraste: verde `#22C55E` só nos botões de ação, com texto `#0F172A` (7.9:1). O azul `#0284C7` fica nos títulos de destaque (texto grande, 3:1) e no fundo dos badges; links e textos pequenos em azul usam `#38BDF8` (8.3:1), porque `#0284C7` sobre o fundo escuro dá 4.36:1, abaixo de 4.5:1.
- `prefers-reduced-motion` desliga as animações e encurta o "digitando..." do simulador.

## O que a página promete (e de onde vem)

Os recursos descritos são os que o sistema tem hoje (ver o `README.md` da raiz): agendamento, cancelamento e remarcação 24 horas pelo WhatsApp, Pix pela chave do negócio com confirmação manual no app ou no WhatsApp, lembrete com confirmação de presença, avisos e resumo diário para o dono, pesquisa de satisfação de 1 a 5, app com agenda (dia, profissionais e mês), clientes, equipe, bloqueios, avaliações, relatórios, financeiro com comissões e controle de clientes (aprovação manual, bloqueio). O simulador segue o fluxo real do bot (menu, serviço, profissional, dia, horário, confirmação, oferta de Pix, "paguei", confirmação do Pix e lembrete).

A seção **Gestão** (CRM) cita só o que foi implementado e testado nas etapas do `ROADMAP-CRM.md`: comanda e caixa
(pagamento dividido, desconto, gorjeta, sinal entrando sozinho), estoque (baixa na venda e no serviço, alerta no app e
no resumo diário), pacotes, clube de assinatura (cobrança com o Pix da chave do negócio pelo WhatsApp e **confirmação
manual**; não existe Pix automático), sinal contra faltas, lista de espera, equipe com papéis (dono, recepção,
profissional), app do celular sem internet (SQLCipher, sincronização, "Precisa da sua atenção") e versão web (menu
lateral, agenda por profissional, atalhos N, C e B; só online). Os mockups usam os mesmos rótulos do app ("Chegou",
"Sinal pago", "Aguardando sinal", "Pacote", "A confirmar", "Falta", "Fechar comanda") com nomes e valores fictícios.
Os limites dos planos (1 profissional no Individual, até 6 no Equipe, logins da equipe no Equipe) são decisão
comercial: o sistema ainda não os aplica.

Atenção: as **mensagens do bot** ainda usam "barbeiro" e "barbearia" para todos os segmentos (o vocabulário por segmento hoje só existe no app). O simulador mostra os termos de cada nicho ("profissional", "tutor", "paciente", "aluno"); ajuste o bot antes de vender para os outros segmentos.
