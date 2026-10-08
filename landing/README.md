# Landing page do SyncServ

Site estático de vendas (HTML, CSS e JavaScript puro, sem framework e sem build). Objetivo: o dono do negócio começar o teste grátis de 7 dias pelo WhatsApp.

```
landing/
├── index.html         página de vendas
├── styles.css         estilos (mobile first)
├── main.js            configuração (número, preços), seletor de nicho, simulador do robô, mockups, calculadora, menu
├── tests/landing_e2e.py  teste no Chromium (Playwright) em 375, 768 e 1440 px
├── privacidade.html   Política de Privacidade (MODELO, revisar com advogado)
├── termos.html        Termos de Uso (MODELO, revisar com advogado)
├── site.webmanifest, robots.txt, sitemap.xml, favicon.ico
└── assets/            arquivos do kit de marca (logo, favicons, imagem de compartilhamento, símbolos dos nichos)
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

### Opção 2: Caddy na VPS

Copie a pasta para a VPS (ex.: `rsync -av landing/ usuario@vps:/srv/syncserv-site/`) e acrescente ao `/etc/caddy/Caddyfile`, ao lado do bloco da API:

```
syncserv.com.br, www.syncserv.com.br {
    root * /srv/syncserv-site
    encode zstd gzip
    file_server
    header {
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
    }
    @static path /assets/* /styles.css /main.js
    header @static Cache-Control "public, max-age=604800"
}
```

`sudo systemctl reload caddy`. O certificado HTTPS sai sozinho. Se mudar `styles.css` ou `main.js` com frequência, reduza o `max-age` ou acrescente `?v=2` no `<link>`/`<script>` a cada versão.

## Testar

```bash
python3 landing/tests/landing_e2e.py              # da raiz do repositório
python3 landing/tests/landing_e2e.py /tmp/prints  # também salva capturas de cada largura
```

Precisa do Playwright para Python (`pip install playwright && playwright install chromium`). O teste serve a pasta num
servidor local descartável e bloqueia qualquer pedido para fora (Google Fonts, wa.me). Em 375, 768 e 1440 px confere:
sem rolagem lateral, os 9 cards da gestão, os mockups (comanda no celular e versão web com menu lateral) e a troca de
nicho neles, o comparativo, os planos com os marcadores de preço, as perguntas novas abrindo, o menu do celular, links
internos, imagens, um h1 só, nenhum erro no console, nada de "Pix automático" nem depoimentos, e a política de
privacidade com o banco criptografado do celular.

## Desempenho e acessibilidade

Lighthouse no celular (com `[DOMINIO]` preenchido): 100 em desempenho, acessibilidade, boas práticas e SEO. Com os marcadores ainda no lugar, o SEO cai para 85 porque o canonical e o `robots.txt` apontam para `[DOMINIO]`, que não é uma URL válida.

- A fonte Plus Jakarta Sans (500 e 800) carrega sem bloquear a primeira pintura (`display=swap`).
- Imagens com largura e altura definidas; o logo e os símbolos são SVG do kit; os celulares do hero são HTML/CSS.
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
