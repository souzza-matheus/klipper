# Auditoria de UI/UX: app SyncServ (celular e web) e landing page

Data: 20/10/2026 (andamento das correções: ver "Andamento das correções"). Escopo: `mobile/` (export web do Expo, em 375, 768 e 1440 px, temas barbearia/escuro e salão de beleza/claro) e `landing/` (375, 768 e 1440 px). **Nenhum arquivo do app ou da landing foi alterado.** Tudo o que foi gerado está em `audit/`.

## Resumo

### As 5 melhorias de maior impacto no app

1. **Consertar o toque em horário vago na versão web** (A01). No navegador, tocar num horário livre da agenda sempre responde "Esse horário não está livre": o `onPress` da web recebe um `MouseEvent`, sem `locationY`, e o minuto vira `NaN` (`mobile/src/components/DayGrid.js:135`). O agendamento rápido, o caminho mais curto para agendar, não existe hoje no computador da recepção.
2. **Fazer os avisos aparecerem por cima dos bottom sheets** (A02). O toast fica atrás do `Modal` do sheet: erro ao agendar, "sem conexão" na venda avulsa e qualquer falha dentro de um sheet não aparecem para quem está usando. A pessoa toca, nada acontece e ela não sabe por quê.
3. **Colocar o próximo atendimento no topo da tela Hoje, grande e com ações** (A16), e enxugar o cabeçalho da Agenda (A17, A18). Hoje o "Próximo cliente" é um card pequeno, o terceiro bloco da tela. A agenda gasta cerca de 45% da tela do celular em controles e, na visão por profissional, os nomes das colunas somem ao rolar.
4. **Separar a cor do segmento das cores de status na barbearia** (A19, A08). O âmbar da marca (#F59E0B) e o laranja do Pix pendente (#F97316) ficam a 1,31:1 um do outro: botão principal, alerta de Pix, pedido para aprovar e bloco "agendado" da agenda parecem a mesma coisa. Para quem olha de longe, isso apaga o sinal mais importante da tela.
5. **Encurtar o fechamento da comanda** (A20) e mostrar as ações rápidas sem depender de "tocar e segurar" (A05). Fechar uma comanda paga no Pix leva 4 toques, uma rolagem até abaixo do teclado numérico e começa por um gesto escondido.

### As 5 melhorias de maior impacto na landing

1. **Mostrar a coluna "Com SyncServ" do comparativo no celular** (L01). Em 375 px a tabela corta exatamente a coluna dos benefícios, e nada indica que dá para rolar para o lado.
2. **Explicar a IA e a franquia nos planos** (L03). O app tem atendimento com IA, leitura de comprovante por IA e um limite de 3.000 respostas por mês (`backend/app/models.py:192`), mas a landing não fala de IA, de limite nem do que acontece quando ele acaba. Os preços ainda são marcadores. Junto vai o item L04: trocar `[DOMINIO]`, `[NUMERO]` etc. (os CTAs apontam para `wa.me/[NUMERO]`, e o SEO do Lighthouse cai para 85).
3. **Esconder o botão "Falar com o robô de verdade" enquanto não houver número** (L02). Ele aparece, mas leva para `#` e não faz nada: o `display: inline-flex` do `.btn` anula o atributo `hidden`.
4. **Enxugar a primeira dobra no celular** (L05) e dar um CTA fixo no topo (L06). O subtítulo ocupa 6 linhas e não há nenhuma imagem do produto nos primeiros 812 px. Depois do hero, o próximo CTA só aparece no fim do simulador ou nos preços, numa página de 15.800 px.
5. **Dar retorno visível ao seletor de nicho e ao simulador no toque** (L07, L08). No celular o seletor muda só os mockups, que estão abaixo da dobra. O simulador diz "conversa ao lado" (no celular ela está embaixo) e começa como uma caixa preta de 460 px com um botão "Oi".

## Como foi feito

- **App web:** `npx expo export --platform web`, servido localmente com o fallback de página única. Backend descartável (SQLite temporário com os dados fictícios do `seed_mock`, sem tocar no banco de desenvolvimento), um para a "Barbearia Demo" (escuro) e uma cópia com `niche=beauty` ("Studio Bella Demo", claro). O relógio do backend de teste foi fixado em **10h40 de hoje** (`audit/scripts/clock.py`), porque às 22h30 a agenda do dia inteiro já teria passado. Um comprovante de Pix fictício foi enviado pelo endpoint de desenvolvimento `/dev/simulate-receipt` (resultado "divergente").
- **Ajuste só no navegador de teste:** por causa do bug A01, as capturas do agendamento rápido usam um script injetado que completa o `locationY` do clique. A evidência do bug sem o ajuste está em `barbearia-375-41-bug-toque-em-horario-vago-web.png`.
- **Playwright** com o Chromium já baixado em `~/.cache/ms-playwright/chromium-1223`. O caminho `/opt/pw-browsers` não existe nesta máquina e `playwright install` não foi rodado. O `@axe-core/playwright` já estava em `devDependencies` (por isso `mobile/package.json` e `package-lock.json` aparecem modificados no git; nada mais foi instalado no projeto). O Lighthouse 12.6.0 rodou via `npx`, só no cache do npx.
- **Roteiros** em `audit/scripts/`: `landing.mjs`, `app.mjs`, `extra.mjs`, `contrast.mjs`, `summary.py` e os auxiliares do backend. Eles usam caminhos absolutos desta máquina. **Dados brutos** em `audit/data/` (axe, medições, contraste, Lighthouse em HTML e JSON). O campo `measure` dos arquivos `app-*.json` foi medido antes de descontar as telas escondidas da pilha e não deve ser usado; os números válidos de alvos e textos estão em `medidas-*.json`.
- **Capturas** em `audit/screenshots/landing/` (85) e `audit/screenshots/app/` (nome = `tema-largura-número-tela`, com versões `-inteira` das telas longas).
- **Limites:** o modo offline completo e a tela "Precisa da sua atenção" existem só no app nativo, então não foram fotografados (a web mostra o aviso de "sem conexão", que foi capturado). Leitor de tela, teclado nativo e gestos foram avaliados pelo código, não num aparelho.

## Avaliação do app

### Hierarquia

- **Hoje** (`barbearia-375-03-hoje.png`): o alerta de Pix pendente é a primeira coisa que se vê (bom). Logo abaixo vêm "pedido para aprovar" e quatro cards de número do mesmo tamanho. O próximo cliente aparece como "14:00 Renan" em 20 px dentro de um desses cards. Os atendimentos em andamento (10h30–11h, com o relógio em 10h50) aparecem na lista "Próximos" sem nenhuma marca de "agora", e o card "Próximo cliente" pula para 14h. Quem olha de longe não sabe quem está na cadeira nem quem é o próximo.
- **Agenda** (`barbearia-375-06-agenda-timeline.png`): banner de aprovação, seletor Timeline/Barbeiros/Mês, navegação do dia, chips de profissional e uma frase de ajuda ocupam cerca de 370 px de 812 px. Sobram cerca de 5 horas visíveis de grade. Na visão por profissional (`barbearia-375-09`, `-768-09` e `-1440-09`), os nomes das colunas ficam dentro da área que rola e somem quando a grade abre no horário atual.
- **Pix** (`barbearia-375-16-pix-pendentes-inteira.png`): os pedidos em que o cliente disse que pagou têm contorno laranja e vêm primeiro (bom). Cada card tem cerca de 300 px, então 8 pendentes viram 2.600 px. "Confirmar" e "Recusar" têm o mesmo tamanho, lado a lado.

### Velocidade (toques contados nas capturas e no código)

| tarefa | caminho atual | toques | onde cortar |
|---|---|---|---|
| Agendar (celular) | Agenda → toque no horário vago → digitar 2 letras → escolher o cliente → serviço → Agendar | 5 + digitação | já é curto; no "+" da Hoje o formulário começa pelo telefone, sem busca por nome (A22) |
| Agendar (web) | o toque no horário vago não funciona (A01); só pelo "+"/atalho N: telefone, nome, serviço, profissional, horário, Agendar | 6 + digitação | consertar A01; usar a busca de cliente do agendamento rápido no formulário |
| Fechar comanda paga no Pix | Hoje → **segurar** o card → Abrir comanda → rolar → Lançar Pix → Fechar comanda | 4 + rolagem + gesto oculto | botão fixo "Receber R$ 40,00 no Pix e fechar" quando um só meio cobre o total (A20) |
| Confirmar Pix | Hoje → "Confirmar Pix" no card → "Recebi" | 2 | bom. Pelo banner: 3 toques. Na tela cheia do comprovante não há como confirmar (A29) |

### Legibilidade a distância, densidade e cores de status

- Os horários dos cards (24 px, extrabold) leem bem de longe. Na grade da agenda, nome e horário dos blocos têm 14 px e o serviço tem 12 px; blocos de 30 min mostram uma linha só.
- Os selos são bem usados (cor e ícone), mas os cards da Hoje somam até 3 selos ("Agendado", "Pix expirado", "WhatsApp"), e o de origem "WhatsApp" é ruído para quem atende. O nome é cortado pelo preço ("Wellington Men…").
- No tema da barbearia, âmbar da marca e laranja de alerta se confundem (A19). No salão, o rosa da marca e o laranja do Pix se separam bem (`salao-375-03-hoje.png`).
- O bloco "agendado" da agenda usa a cor do segmento, mas o selo "Agendado" é azul (A08).

### Estados

- **Carregando** (`barbearia-375-36-carregando.png`): esqueleto no lugar da lista (bom).
- **Erro** (`barbearia-375-37-erro.png`): ícone, "Sem conexão com o servidor. Confira o endereço e a internet." e "Tentar de novo" (bom).
- **Vazio** (`salao-375-21-clientes-busca-vazia.png`): símbolo e frase curta, mas sem ação ("Cadastrar 'zzzzqq'"). O vazio da Hoje tem a ação "Agendar" (bom).
- **Offline na web** (`barbearia-375-38-offline.png`): faixa laranja no topo de todas as telas (boa). Mas, ao tentar uma ação dentro de um sheet, o aviso de bloqueio fica escondido atrás dele (`barbearia-375-39-offline-acao-bloqueada.png`, A02).
- **Conflito** (`barbearia-375-11-agendamento-rapido-conflito.png`): o aviso "Não agendar junto" com o motivo e a distância mínima é claro e fica antes da escolha do serviço (bom).

### Formulários

- Máscaras de telefone e dinheiro, teclados certos (`phone-pad`, `number-pad`, `email-address`) e botão principal fixo no rodapé, que sobe com o teclado (bom).
- Datas ("dd/mm/aaaa") e horas ("HH:MM") são texto livre, sem máscara (`Finance.js:131`, `Catalog.js:172`). O valor do gasto usa `decimal-pad` em vez da máscara de dinheiro (`Finance.js:301`).
- O `Field` tem a prop `error`, mas nenhuma tela a usa: os erros só chegam por toast depois que a API recusa, e o toast pode ficar atrás do sheet (A02). No login, o toast cobre o botão Entrar (`barbearia-375-02-login-erro.png`).
- Configurações (`barbearia-375-33-configuracoes-inteira.png`) é uma tela de cerca de 4.500 px. A IA e a Aparência salvam ao tocar, o resto só pelo botão "Salvar configurações" (A21).

### Versão web (computador)

- Menu lateral com Gestão e atalhos N/C/B (bom). A comanda usa duas colunas em 1440 px (`salao-1440-14-comanda.png`), mas o botão "Fechar comanda" fica cortado no rodapé de uma janela de 900 px.
- Hoje, listas e formulários usam uma coluna só esticada até 1.120 px, com o preço a 1.000 px do nome (`barbearia-1440-03-hoje.png`, `-1440-12-novo-agendamento-inteira.png`).
- A agenda do computador mostra só o nome nos blocos, sem serviço nem status. Os textos dizem "Toque" e "Toque e segure", e as ações rápidas só abrem segurando o mouse (A24).

## Avaliação da landing

- **5 segundos:** em 375 px aparecem a promessa ("Sua agenda cheia e seu WhatsApp no automático."), um subtítulo de 6 linhas e o CTA verde em y = 512 px (visível sem rolar). Não aparece para quem é (o seletor de nicho está em y ≈ 690) nem como o produto é (os celulares começam em y = 954). No computador, o hero com os dois celulares resolve as duas coisas (`landing-1440-primeira-dobra.png`).
- **CTA:** os botões abrem o WhatsApp com a mensagem pronta e o nicho escolhido, coerente com "Testar 7 dias grátis no WhatsApp". Mas nada diz o que acontece depois do toque (quem responde, em quanto tempo, se precisa de cartão) (L10). No celular não há CTA no topo: ele fica dentro do menu (L06).
- **Planos:** são claros em profissionais (1 e até 6) e em "sem adesão, sem fidelidade". Não falam de IA, da franquia de respostas da IA nem do excedente, e o preço ainda é `[PREÇO INDIVIDUAL]` (L03).
- **Confiança e objeções:** o FAQ responde bem número de WhatsApp, Pix, cancelamento, offline, equipe e LGPD, e o site não usa depoimentos nem números inventados (há um comentário no HTML proibindo isso). Faltam no FAQ "o que a IA faz e quanto custa" e "o que acontece depois dos 7 dias".
- **Ritmo:** em 375 px a página tem cerca de 15.800 px. Recursos (8 cards), Gestão (9 cards, 3.955 px), comparativo (10 linhas), planos (12 itens) e FAQ repetem a mesma lista de funções (L11).
- **Mockups no celular:** texto de 10 a 12 px, nomes quebrando em 2 linhas (L12). No computador ficam bons.
- **Textos:** português claro, sem promessa que o sistema não cumpre; a calculadora deixa claro que é estimativa. Pequenos ajustes: "Bem-vindo" com nomes femininos (Mariana, Fernanda, Helena) e "conversa ao lado" no celular.

## Andamento das correções

Cada achado tem a coluna **status** na tabela abaixo. As capturas e os dados de antes de cada rodada ficam em
`audit/antes/` (mesmos nomes de arquivo); `audit/screenshots/` e `audit/data/` têm sempre o estado atual.

### Bloco 1 (21/10/2026): defeitos e ganhos rápidos

Corrigidos: A01, A02, A03, A04, A08, A09, A10, A11, A14, A25, A26, A27, A28, A29, A30, L01, L02, L09, L14, L15, L16 e
L17. L04: criada a verificação (`LANDING_ENV=production python3 landing/tests/landing_e2e.py` falha se sobrar marcador
no HTML final, no `robots.txt`, no `sitemap.xml` ou no manifest; em desenvolvimento só lista); os marcadores continuam
para você preencher. L03 e L10 aguardam a definição de preços; L13 fica para o bloco 2.

| id | o que mudou | onde | como conferir |
|---|---|---|---|
| A01 | A posição do toque vem de `locationY` no celular e de `clientY` menos o topo da coluna na web (`tapY`); toque sem posição é ignorado em vez de virar "não está livre" | `mobile/src/components/DayGrid.js` | `tests/web_e2e.py` clica em horários vagos em 375 e 1440 px e exige o sheet com "Agendar"; `app/barbearia-375-07-agendamento-rapido.png` foi tirada sem o ajuste antigo do navegador (`SHIM`) |
| A02 | Pilha de hosts de aviso: cada bottom sheet aberto (e o diálogo e a tela cheia do comprovante) tem o próprio host, no topo da tela para não cobrir o botão; ao fechar, o aviso passa para o host de baixo | `mobile/src/ui.js` (`toast`, `ToastHost`, `BottomSheet`, `DialogHost`), `ReceiptReview.js` | `tests/web_e2e.py` confere que o aviso é o elemento de cima no ponto onde aparece; `app/barbearia-375-39-offline-acao-bloqueada.png` |
| A03 | Helper `a11yState` manda `aria-checked`/`aria-selected`/`aria-disabled`/`aria-busy`/`aria-expanded` junto do `accessibilityState` (o react-native-web 0.21 ignora este); chips em `radiogroup`; menu lateral com `aria-current`; botões grandes com `aria-pressed`; o interruptor na web é só desenho (sem `<input>` dentro do controle) e no celular o `Switch` fica fora da acessibilidade | `ui.js`, `Layout.js`, `Settings.js` | axe: `aria-required-attr`, `label`, `nested-interactive` e `target-size` zerados |
| A04 | `StatValue`: na web a fonte diminui pelo tamanho do texto e quebra em 2 linhas em vez de cortar; cards de número com largura mínima, 3 cards viram 2 + 1 no celular | `ui.js`, `ThemeProvider.js`, `Finance.js`, `Insights.js`, `Customers.js` | `app/barbearia-375-25-assinaturas.png` ("R$ 240,00" inteiro) |
| A08 | O bloco da agenda usa o tom de `status.js` (fonte única): "agendado" em azul, como o selo | `DayGrid.js` | `app/barbearia-375-06-agenda-timeline.png` |
| A09 | `border` dos temas escuros mais claro (barbearia `#747474`, fitness `#8B8B92`, escuro derivado `#6F727A`, marca `#707F94`) | `mobile/src/theme.js` | `tests/contrast.test.mjs` agora mede a borda também sobre `surfaceElevated` |
| A10 | Faixa cheia de erro com `dangerFill` `#B91C1C` e `onDanger` branco (6,47:1) | `theme.js`, `Sync.js` | teste "faixa cheia de erro" no `contrast.test.mjs` |
| A11 | Nenhum texto abaixo de 13 px no app (abas, agenda, calendário, Financeiro, menu lateral, eixos do gráfico); as abas recuperam o respiro lateral para "Finanças" caber em 375 px | `App.js`, `DayGrid.js`, `Agenda.js`, `Finance.js`, `Layout.js`, `chart.js` | medição: textos de 12 px de 214 nós para 0 (sobra só o ícone de cadeado do calendário, que é ícone) |
| A14 | Erro do login em texto vermelho abaixo da senha (`role="alert"`), servidor em "Configuração avançada" (na web é o próprio site), `autoComplete="current-password"` | `Login.js`, `ui.js` (`Field`) | `app/barbearia-375-02-login-erro.png` |
| A25 | Cards da Hoje sem o selo de origem "WhatsApp" e sem "Pix expirado"; no celular o valor vai para a linha do serviço e o nome tem 2 linhas | `AppointmentCard.js` | `app/barbearia-375-03-hoje-inteira.png` |
| A26 | Barras de ocupação com o tom de texto de status (5,6 a 7,4:1 sobre a trilha); dia fechado em `textMuted`, sem opacidade | `Agenda.js` | teste "barras de ocupação" no `contrast.test.mjs`; `app/salao-375-10-agenda-mes.png` |
| A27 | Busca de cliente sem resultado oferece "Cadastrar "X" e agendar" (o cadastro acontece no agendamento); estoque abaixo de zero mostra "Estoque negativo: confira a contagem" | `Customers.js`, `Stock.js` | `app/salao-375-21-clientes-busca-vazia.png` |
| A28 | `main` na área de conteúdo, `navigation` nas abas e no menu lateral, `h1` na Hoje e no login, sheets e diálogos com nome, barra de uso da IA com nome, `inert` automático em tudo que está com `aria-hidden` (telas de baixo da pilha) na web, rótulos que começam pelo texto visível (calendário e blocos da agenda), cards sem botão dentro de botão | `App.js`, `Layout.js`, `Home.js`, `Login.js`, `src/webA11y.web.js`, `ui.js` (`Card actions`), `DayGrid.js`, `Agenda.js`, `Settings.js` | axe: `region`, `landmark-one-main`, `page-has-heading-one`, `aria-hidden-focus`, `aria-dialog-name`, `aria-progressbar-name`, `label-content-name-mismatch` e `aria-prohibited-attr` zerados |
| A29 | Tela cheia do comprovante com Confirmar e Recusar (as mesmas ações do card, inclusive nas cobranças do clube); textos com a fonte do app | `ReceiptReview.js`, `Payments.js`, `Plans.js` | `app/barbearia-375-18-pix-comprovante-aberto.png` |
| A30 | Botões `compact`, chips, abas segmentadas, pílulas de incompatível e "Ver dados lidos" com 48 px; "Voltar" do cabeçalho na web vira botão de 48 px | `ui.js`, `App.js`, `Customers.js`, `ReceiptReview.js` | medição de alvos abaixo |
| L01 + L17 | Abaixo de 600 px o comparativo vira pares empilhados ("Sem SyncServ" riscado em cima, "Com SyncServ" embaixo), sem rolagem lateral; "Gestão" do mockup em `#94A3B8` e 11 px | `landing/index.html`, `styles.css` | `landing_e2e.py` confere a coluna "Com" inteira na tela; `landing/landing-375-07-comparativo.png` |
| L02 | `[hidden] { display: none !important; }` | `styles.css` | `landing_e2e.py` confere que o botão não aparece |
| L09 | `--control: #64748B` nos contornos de controles; `#334155` só em divisórias | `styles.css` | `audit/data/contraste.json` (landing) |
| L14 | Selo "Para equipes" do tamanho do texto; CTA do hero sem quebrar linha no computador | `styles.css` | `landing/landing-1440-primeira-dobra.png`, `landing-375-09-precos.png` |
| L15 | Sliders, recomeçar e respostas do simulador, links do rodapé, menu e "Pular para o conteúdo" com 48 px; botões − e + ao lado do valor médio | `index.html`, `styles.css`, `main.js` | `landing_e2e.py` (alvos e botões − e +) |
| L16 | "Boas-vindas" no simulador e no mockup; resultado da calculadora em laranja claro; CTA "Testar 7 dias grátis" logo abaixo do resultado (a seção não tinha CTA) | `main.js`, `index.html`, `styles.css` | `landing_e2e.py`; `landing/landing-375-08-calculadora.png` |

**axe (app, ocorrências em número de telas, antes → depois):**

| regra (impacto) | Barbearia 375 | Barbearia 768 | Barbearia 1440 | Salão 375 | Salão 1440 |
|---|---|---|---|---|---|
| `aria-required-attr` (critical) | 52 em 10 → 0 | 52 em 10 → 0 | 47 em 9 → 0 | 52 em 10 → 0 | 29 em 4 → 0 |
| `label` (critical) | 10 em 5 → 0 | 10 em 5 → 0 | 9 em 4 → 0 | 10 em 5 → 0 | 7 em 2 → 0 |
| `aria-dialog-name` (serious) | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 |
| `aria-hidden-focus` (serious) | 0 → 0 | 0 → 0 | 65 em 20 → 0 | 0 → 0 | 19 em 8 → 0 |
| `aria-progressbar-name` (serious) | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 |
| `aria-prohibited-attr` (serious) | 7 em 3 → 0 | 8 em 4 → 0 | 8 em 4 → 0 | 8 em 4 → 0 | 8 em 4 → 0 |
| `autocomplete-valid` (serious) | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 1 em 1 → 0 | 0 → 0 |
| `color-contrast` (serious) | 4 em 2 → 0 | 5 em 3 → 0 | 4 em 2 → 0 | 5 em 2 → 0 | 6 em 3 → 0 |
| `label-content-name-mismatch` (serious) | 38 em 6 → 0 | 51 em 6 → 0 | 49 em 6 → 0 | 38 em 6 → 0 | 48 em 5 → 0 |
| `nested-interactive` (serious) | 10 em 6 → 0 | 10 em 6 → 0 | 9 em 5 → 0 | 10 em 6 → 0 | 7 em 3 → 0 |
| `target-size` (serious) | 4 em 4 → 0 | 4 em 4 → 0 | 3 em 3 → 0 | 4 em 4 → 0 | 1 em 1 → 0 |
| `landmark-one-main` (moderate) | 1 em 1 → 0 | 1 em 1 → 0 | 23 em 23 → 0 | 1 em 1 → 0 | 10 em 10 → 0 |
| `page-has-heading-one` (moderate) | 1 em 1 → 0 | 1 em 1 → 0 | 2 em 2 → 0 | 1 em 1 → 0 | 1 em 1 → 0 |
| `region` (moderate) | 191 em 26 → 0 | 191 em 26 → 0 | 671 em 24 → 0 | 194 em 26 → 0 | 346 em 11 → 0 |

Telas analisadas depois: 27, 27, 26, 27 e 13 (antes: 26, 26, 24, 26 e 11; o roteiro agora também passa pelas telas
que antes falhavam no meio do caminho).

**Landing (axe):** 1 violação por largura (`scrollable-region-focusable` em 375 px, `color-contrast` em 768 e 1440) → 0
em todas as larguras e no simulador.

**Alvos de toque menores que 48 px (barbearia, 375 px, 27 telas):** 171 → 77 ocorrências. As 77 que sobram: 36 campos
de texto (falso positivo: o contorno do `Field` tem 48 px), 31 dias do calendário (43 x 64 px, limitados pela grade de 7
colunas) e 8 blocos de 30 minutos da agenda (36 px de altura; ficam para o A13/A17). "Ver dados lidos" e as pílulas de
incompatível foram para 48 px depois da medição (conferido no teste ponta a ponta, não na medição). **Landing:** 12 → 1
alvo (o link inline da política no FAQ, isento por estar no meio do texto).

**Textos menores que 13 px (barbearia, 375 px):** 221 nós (214 de 12 px) → 4 (o ícone de cadeado do calendário, que é
um glifo de ícone).

**Contraste** (`audit/data/contraste.json`, 274 combinações): 86 abaixo do mínimo → 48. As que sobram são da hachura de
bloqueio e do fundo fora do expediente (A13), da cor do segmento x laranja de alerta e do "pedido para aprovar" nos
temas claros de pet shop e fitness (A19), das divisórias decorativas dos cards (não são o único sinal) e de duas
combinações do tema da marca-base que só aparece no login (a agenda nunca usa esse tema).

**Lighthouse da landing (celular, servidor local):** 97 / 100 / 100 / 85, igual ao de antes (FCP 0,9 s, LCP 1,5 s,
TBT 0 ms, CLS 0,106). O SEO 85 é o L04 (canonical e `robots.txt` com `[DOMINIO]`) e o CLS é o L13 (bloco 2).
`audit/data/lighthouse-landing-celular-bloco1.json`.

**Roteiros:** `audit/scripts/start_api.sh` agora usa `AUDIT_ENV` (padrão `/tmp/syncserv-audit`) e sobe o backend sem
`GEMINI_API_KEY`; `app.mjs` e `extra.mjs` não usam mais o ajuste do `locationY` (só com `SHIM=1`), entram pelo
"Configuração avançada" do login, clicam nas abas dentro da navegação e só no "Voltar" que está por cima.

## Tabela de achados

Ordem: impacto ÷ esforço (alta = 3, média = 2, baixa = 1; pequeno = 1, médio = 2, grande = 3). Os ganhos rápidos vêm primeiro e, no empate, o de maior impacto.
Capturas: `app/` = `audit/screenshots/app/`, `landing/` = `audit/screenshots/landing/`.

| id | onde (tela · arquivo · captura) | problema | por que importa | sev. | esforço | recomendação | status |
|---|---|---|---|---|---|---|---|
| A01 | Agenda (web) · `mobile/src/components/DayGrid.js:135` · `app/barbearia-375-41-bug-toque-em-horario-vago-web.png` | Na web, tocar num horário vago sempre responde "Esse horário não está livre": `e.nativeEvent.locationY` não existe no `MouseEvent` e o minuto vira `NaN`. | O agendamento rápido, o caminho mais curto para agendar, não funciona na recepção. O aviso ainda diz algo falso. | alta | pequeno | Calcular a posição com `locationY ?? offsetY` (ou `pageY` menos o topo medido no `onLayout`). Incluir no `tests/web_e2e.py` um toque num horário livre que abra o sheet. | corrigido (bloco 1) |
| A02 | Todos os bottom sheets · `mobile/src/ui.js:126` (`ToastHost`) e `:610` (`BottomSheet` em `Modal`) · `app/barbearia-375-39-offline-acao-bloqueada.png` | O toast é desenhado na raiz, atrás do `Modal` do sheet: erros e avisos de ações feitas dentro de um sheet não aparecem. Medido: o toast "Sem conexão. Na versão web as alterações só podem ser feitas com internet." existe em y = 641 px, mas não é o elemento visível naquele ponto. | Quem agenda, lança produto ou abre comanda num sheet não recebe retorno quando algo falha e repete o toque ou desiste. Como o `Modal` nativo também fica por cima da raiz, o mesmo deve ocorrer no celular. | alta | pequeno | Renderizar um `ToastHost` dentro do `BottomSheet` (e do `DialogHost`), ou mostrar o erro como `Banner` dentro do próprio sheet, perto do botão. | corrigido (bloco 1) |
| L01 | Comparativo · `landing/styles.css` (`.compare table { min-width: 520px }`) · `landing/landing-375-07-comparativo.png` | Em 375 px aparece só a coluna "Sem SyncServ"; a coluna "Com SyncServ" fica cortada, atrás de uma rolagem lateral sem nenhuma indicação. | É a seção de argumento de venda, e o celular mostra só o lado negativo. | alta | pequeno | Abaixo de 600 px, trocar a tabela por pares empilhados (o "sem" riscado em cima, o "com" embaixo) ou por uma lista com as duas frases em cada item. | corrigido (bloco 1) |
| L02 | Demonstração · `landing/index.html:185`, `styles.css` (`.btn { display: inline-flex }`) · `landing/landing-375-03-demo.png` | O botão "Falar com o robô de verdade" aparece com `DEMO_NUMBER` vazio e leva para `#`: o `display` do `.btn` anula o atributo `hidden`. | Um botão que não faz nada, logo na seção de demonstração, passa a impressão de site quebrado. | alta | pequeno | `[hidden] { display: none !important; }` no CSS (vale para qualquer `hidden` futuro). | corrigido (bloco 1) |
| A03 | Chips, abas segmentadas, interruptores, cards de nicho · `mobile/src/ui.js:383-459`, `screens/Settings.js:100` · axe em todas as telas | Na web, o estado de seleção não chega ao DOM. Medido: `role="tab"` sem `aria-selected`, `role="radio"`/`role="switch"` sem `aria-checked` (axe `aria-required-attr`, crítico: 52 ocorrências em 10 telas, mais `label` crítico no `<input>` do Switch e `nested-interactive`). As abas do rodapé, do React Navigation, têm `aria-selected` corretamente. | Leitor de tela e navegação por teclado não dizem qual serviço, profissional ou modo está escolhido; o interruptor é anunciado duas vezes e sem nome. | alta | pequeno | Nos componentes de `ui.js`, passar também `aria-checked`/`aria-selected` (ou `role` + `aria-*` do RN-web 0.21) e, no `Toggle`, esconder o `Switch` interno da acessibilidade (`importantForAccessibility="no-hide-descendants"`/`aria-hidden`). | corrigido (bloco 1) |
| L03 | Preços · `landing/index.html:477-521`, `main.js:9` · `landing/landing-375-09-precos.png` | Os planos não falam do atendimento com IA, do limite de 3.000 respostas da IA por mês (`backend/app/models.py:192`) nem do que acontece no limite (o bot volta ao menu); o preço ainda é marcador. | É a primeira pergunta de quem vê "robô": entende o que eu escrevo? Tem limite? Pago a mais? Sem resposta, o dono desconfia ou se surpreende depois. | alta | pequeno | Uma linha por plano: "Atendimento com IA: até N respostas por mês. Passou disso, o robô continua pelo menu numerado, sem custo extra" (ou o excedente real, se houver). Mais uma pergunta no FAQ sobre IA e comprovante. | aguarda a definição de preços |
| L04 | Página inteira · `landing/index.html`, `robots.txt:4`, `main.js:5` · `audit/data/lighthouse-landing-celular.html` | Marcadores `[DOMINIO]`, `[NUMERO]`, `[PREÇO …]`, `[EMAIL]`, `[CNPJ]`, `[CIDADE/UF]` visíveis ou em links: os CTAs apontam para `wa.me/[NUMERO]`, o canonical é inválido e o sitemap do robots.txt também (SEO 85). | Publicar assim quebra todos os CTAs e mostra "[EMAIL]" no rodapé. | alta | pequeno | Preencher pelo roteiro do `landing/README.md` e acrescentar ao `landing_e2e.py` uma verificação que falha se sobrar `[` + letra maiúscula no HTML final. | parcial (bloco 1): verificação de produção criada; marcadores aguardam o preenchimento |
| L05 | Hero (celular) · `landing/index.html:122-176` · `landing/landing-375-primeira-dobra.png` | O subtítulo ocupa 6 linhas (lista agenda, comanda, caixa, estoque, offline e web); não há nenhum visual do produto nos primeiros 812 px; "para quem é" (o seletor de nicho) fica abaixo do CTA. | O dono que abre o link no celular decide em segundos; uma parede de texto cinza não mostra o produto. | alta | pequeno | Subtítulo de 1 ou 2 linhas ("O robô agenda, lembra e cobra o Pix pelo seu WhatsApp. Você acompanha tudo no app."). Mover o resto para Gestão. No celular, mostrar o celular da conversa logo abaixo do CTA, ou a fileira de nichos acima do título. | pendente (bloco 10) |
| A04 | Cards de número · `mobile/src/ui.js:270` (`Stat`), `screens/Finance.js:45` · `app/barbearia-375-25-assinaturas-inteira.png` | O `adjustsFontSizeToFit` não funciona no react-native-web: o valor é cortado ("R$ 24…" em Receita recorrente). | Dinheiro cortado é o número que o dono mais quer ver. | média | pequeno | Na web, reduzir a fonte pelo comprimento do texto ou permitir 2 linhas; nos grids de 3 cards, usar 2 colunas no celular. | corrigido (bloco 1) |
| A05 | Hoje e Agenda · `components/AppointmentCard.js:592`, `DayGrid.js:72` · `app/barbearia-375-05-acoes-rapidas.png` | As ações rápidas (Cliente chegou, Abrir comanda, Faltou) só abrem com "tocar e segurar"; na Hoje não há nenhuma dica, e no computador é preciso segurar o mouse. | O atalho mais útil do dia é invisível; quem não descobre faz 2 ou 3 toques a mais em cada atendimento. | média | pequeno | Botão "⋯" (48 px) no card e no bloco; no card do atendimento atual, mostrar "Chegou" e "Abrir comanda" direto. No computador, abrir com clique direito também. | pendente (bloco 10) |
| A06 | Pix com comprovante · `components/ReceiptReview.js`, `screens/Payments.js:115-121` · `app/barbearia-375-17-pix-com-comprovante.png` | Com "Comprovante divergente", "Confirmar" continua como botão principal cheio e "Recusar" tem o mesmo tamanho, lado a lado; os avisos laranja somem perto do botão âmbar no tema da barbearia. | Incentiva confirmar sem olhar o extrato e torna fácil recusar por engano. | média | pequeno | Quando divergente: o principal vira "Conferi no extrato, confirmar" (secundário) e "Recusar" vai para um botão discreto ou um menu; quando confere: mantém o "Confirmar" cheio. | pendente (bloco 10) |
| A07 | Lista de Pix · `screens/Payments.js:95-130` · `app/barbearia-375-16-pix-pendentes-inteira.png` | Cada pendente ocupa cerca de 300 px (2 fileiras de botões, 3 linhas de selos); 8 pendentes = 2.600 px. | Entre um atendimento e outro, a pessoa quer passar o olho e confirmar vários. | média | pequeno | Card compacto (nome, valor, "disse que pagou há 34 h" e um botão "Confirmar"); copiar código, ver agendamento e recusar num menu "⋯". | pendente (bloco 10) |
| A08 | Agenda · `components/DayGrid.js:68-70` (`TONE_OF`) x `src/status.js:4` · `app/barbearia-375-09-agenda-profissionais.png` | O bloco "agendado" usa a cor do segmento (`accent`), mas o selo "Agendado" é azul (`info`). | A mesma informação muda de cor entre telas; na barbearia, "agendado" fica da cor do alerta. | média | pequeno | `TONE_OF.scheduled = 'info'`, usando o `STATUS` de `status.js` como fonte única. | corrigido (bloco 1) |
| A09 | Bottom sheets (temas escuros) · `mobile/src/theme.js` (`border`) x `surfaceElevated` · `app/barbearia-375-07-agendamento-rapido.png` | Contorno de chips e campos dentro do sheet: 2,16 a 2,89:1 (mínimo 3:1). O teste de contraste confere a borda só contra `background` e `surface`. | Os serviços não escolhidos no agendamento rápido quase somem. | média | pequeno | Clarear o `border` dos temas escuros ou criar `borderElevated`; acrescentar `surfaceElevated` ao `tests/contrast.test.mjs`. | corrigido (bloco 1) |
| A10 | Faixa de sincronização (app) · `mobile/src/components/Sync.js:50` | Texto `#FFFFFF` sobre `status.danger` (#EF4444): 3,76:1 em todos os temas (mínimo 4,5:1 para 15 px). | Justamente o aviso de erro de envio fica difícil de ler. | média | pequeno | Usar `#7F1D1D`/`onWarning` sobre o vermelho, ou o vermelho mais escuro (#B91C1C) como fundo; incluir no teste de contraste. | corrigido (bloco 1) |
| A11 | Rodapé de abas, agenda, calendário, Financeiro, menu lateral · `App.js:195`, `DayGrid.js:95,100,144`, `Agenda.js:152`, `Finance.js:46`, `Layout.js:63,76,82`, `chart.js:78` | Texto de 12 px fora da escala tipográfica (o menor token é 13). | De longe, rótulo das abas, serviço do bloco e "+87,6% vs. anterior" não se leem. | média | pequeno | Usar `type.caption` (13) como piso e acrescentar 12 a uma lista de valores proibidos no lint. | corrigido (bloco 1) |
| A12 | Ficha do cliente, comanda, abas · `screens/Customers.js`, `ui.js:268,347,451` · `app/barbearia-375-20-ficha-cliente-inteira.png`, `-14-comanda-inteira.png`, `salao-375-06-agenda-timeline.png` | A ficha não tem "Agendar" para o cliente (só WhatsApp e Nova comanda). Palavras quebradas no meio: "Atendiment os", "Atendiment o", "Pomada modelado ra"; "Profission…" cortado no seletor do salão. | Agendar o retorno de quem está na cadeira é a ação mais comum na ficha. Palavra quebrada parece defeito. | média | pequeno | Botão "Agendar" na ficha (abre o Novo agendamento com o cliente preenchido). Rótulos mais curtos ("Visitas"), `numberOfLines` com `adjustsFontSizeToFit` só onde funciona, e "Equipe" no seletor quando não couber. | pendente (bloco 10) |
| A13 | Grade da agenda · `DayGrid.js:57-66,121-128` · `app/salao-375-06-agenda-timeline.png` | Bloqueio hachurado em `divider`: 1,15 a 1,38:1 contra o fundo; fora do expediente x expediente: 1,15:1 nos temas claros. | Fica difícil ver de longe que um horário está bloqueado ou fora do expediente, e o toque ali só responde "não está livre". | média | pequeno | Hachura em `border` (3:1) e fundo fora do expediente com mais diferença; rótulo "Almoço" ou "Fechado" na faixa. | pendente (bloco 10) |
| A14 | Login · `screens/Login.js:44-54` · `app/barbearia-375-02-login-erro.png` | O erro aparece num toast que cobre o botão Entrar; o campo "Endereço do servidor" aparece para o usuário final; `autoComplete="password"` é inválido na web (axe `autocomplete-valid`). | É a primeira tela de toda pessoa da equipe. | média | pequeno | Erro em texto vermelho abaixo da senha; servidor escondido atrás de "Configuração avançada"; `autoComplete="current-password"`. | corrigido (bloco 1) |
| A15 | Clientes (computador) · `screens/Customers.js:36-46` · `app/barbearia-1440-19-clientes.png` | Dois campos de busca seguidos ("Buscar por nome ou telefone" e "Filtrar resultados") e o selo "Normal" repetido em todas as linhas da tabela. | Não fica claro qual campo usar; o selo repetido esconde os poucos clientes "Bloqueado" ou "Aprovação". | média | pequeno | Um campo só (busca no servidor, com filtro local enquanto digita); coluna Acesso vazia para "normal" e selo só nas exceções. | pendente (bloco 11) |
| L06 | Topo (celular) e página inteira · `landing/styles.css:91-110` · `landing/landing-375-pagina-inteira.png` | No celular o CTA do topo fica dentro do menu; depois do hero, o próximo CTA está no fim do simulador ou nos preços, numa página de 15.800 px. | Quem se convenceu no meio da página precisa procurar o botão. | média | pequeno | CTA compacto "Testar grátis" fixo no topo também no celular (ao lado do menu) ou uma barra inferior que aparece depois do hero. | pendente (bloco 10) |
| L07 | Seletor de nicho · `landing/main.js:398-415` · `landing/landing-375-nicho-beauty-hero.png` | No celular, tocar num nicho muda só os mockups, que estão abaixo da dobra; na tela, só a borda do chip muda. | Parece que o toque não fez nada. | média | pequeno | No celular, rolar suavemente até os celulares depois do toque, ou trocar também o título ("Sua agenda do salão cheia…") e o selo do topo. | pendente (bloco 10) |
| L08 | Simulador · `landing/index.html:183`, `main.js:375` · `landing/landing-375-03-demo.png` | "Toque nas opções da conversa ao lado" (no celular, ela está embaixo); caixa de 460 px vazia com um botão "Oi" sozinho no canto. | O primeiro contato com a demonstração parece vazio. | média | pequeno | "Toque nas respostas abaixo" no celular; começar já com a mensagem de boas-vindas do robô e 2 ou 3 respostas grandes; altura menor antes do primeiro toque. | pendente (bloco 10) |
| L09 | Botões de nicho, "Ver como funciona", menu · `landing/styles.css` (`--border: #334155`) | Contorno dos controles: 1,72:1 contra o fundo (mínimo 3:1 para componentes). | Os botões secundários quase não se distinguem do fundo, principalmente no sol. | média | pequeno | Usar `#64748B` (o mesmo `border` do app na marca-base, 3:1) para controles e deixar `#334155` só para divisórias. | corrigido (bloco 1) |
| L10 | Todos os CTAs · `landing/main.js:71-76` · `landing/landing-375-09-precos.png` | O botão abre o WhatsApp, mas nada diz o que acontece depois (quem responde, em quanto tempo, se precisa de cartão). | Reduz a hesitação no toque mais importante da página. | média | pequeno | Microtexto sob o CTA principal: "Você fala com a gente no WhatsApp e começa no mesmo dia. Sem cartão." (só o que for verdade). | aguarda a definição de preços |
| A16 | Hoje · `mobile/src/screens/Home.js:88-107` · `app/barbearia-375-03-hoje.png` | O próximo cliente é um card de número pequeno (20 px), o terceiro bloco da tela; os atendimentos em andamento não têm marca de "agora", e o card "Próximo" pula para 14h com dois clientes ainda na cadeira. | É a informação que o profissional busca de longe entre um atendimento e outro. | alta | médio | Card de destaque no topo: "Agora" (em andamento) e "Próximo", com horário em 32–40 px, nome, serviço e as ações "Chegou" e "Abrir comanda". Os quatro números viram uma linha compacta abaixo. | pendente (bloco 10) |
| A17 | Agenda (celular) · `screens/Agenda.js:256-270` · `app/barbearia-375-06-agenda-timeline.png` | Banner, seletor de modo, navegação do dia, chips e frase de ajuda ocupam cerca de 370 px de 812; a grade mostra cerca de 5 horas. | A agenda é a tela mais aberta do dia e mostra pouco do dia. | alta | médio | Aprovações como contador no ícone do topo; chips de profissional na mesma linha da data; frase de ajuda só na primeira vez; cabeçalho que encolhe ao rolar. | pendente (bloco 10) |
| A18 | Agenda por profissional · `components/DayGrid.js:190-205` · `app/barbearia-768-09-agenda-profissionais.png`, `-1440-09` | O cabeçalho com o nome de cada coluna fica dentro da área que rola na vertical; como a grade abre no horário atual, os nomes nunca aparecem. | Não dá para saber qual coluna é de qual profissional. | alta | médio | Cabeçalho fixo fora do `ScrollView` vertical, sincronizado com a rolagem horizontal; repetir o nome no bloco quando a coluna for estreita. | pendente (bloco 10) |
| A19 | Tema barbearia · `mobile/src/theme.js:21,31` · `app/barbearia-375-03-hoje.png` | Âmbar da marca (#F59E0B) x laranja de Pix pendente (#F97316): 1,31:1 entre si. Botão principal, alerta de Pix, "pedido para aprovar" e bloco "agendado" ficam quase da mesma cor. | Em todas as telas, o alerta mais importante (dinheiro a confirmar) perde destaque. | alta | médio | Na barbearia, reservar o laranja só para alertas e dar a eles forma própria (faixa cheia com ícone e contador); o "pedido para aprovar" usa `info`; os blocos "agendado" usam `info` (A08). Avaliar também com simulação de daltonismo. | pendente (bloco 10) |
| A20 | Comanda · `screens/Comandas.js:292-360` · `app/barbearia-375-14-comanda-inteira.png` | Com o Pix pré-escolhido e o valor certo, ainda é preciso "Lançar Pix" e depois "Fechar comanda", que fica abaixo do teclado numérico (cerca de 1.300 px em 375; cortado em 1440 x 900). O teclado fica sempre aberto. "Estornar" aparece em cada lançamento com o mesmo peso dos valores. | Fechar a conta é o momento de maior fila no balcão. | alta | médio | Rodapé fixo com "Receber R$ X no Pix e fechar" quando um só meio cobre o total; teclado só ao tocar em "Outro valor" ou "Dividir"; "Estornar" num menu do lançamento. | pendente (bloco 10) |
| A21 | Configurações · `screens/Settings.js:129-330` · `app/barbearia-375-33-configuracoes-inteira.png` | Uma tela de cerca de 4.500 px com IA, aparência, dados do negócio, Pix, sinal e cerca de 15 regras do bot; IA e Aparência salvam ao tocar, o resto só pelo botão. | Dá para achar que salvou e não ter salvado (ou o contrário). | média | médio | Lista de seções (Aparência, Pix e sinal, Atendimento com IA, Regras do bot), cada uma numa tela com o mesmo jeito de salvar. | pendente (bloco 10) |
| A22 | Novo agendamento · `screens/Agenda.js:379-400` · `app/barbearia-375-12-novo-agendamento.png` | O formulário começa pelo WhatsApp do cliente; não busca por nome (o agendamento rápido busca). | Para cliente já cadastrado, é preciso saber ou digitar o número. | média | médio | Reutilizar a busca do `QuickBookSheet` ("Nome ou telefone") com "Cadastrar novo" embaixo. | pendente (bloco 10) |
| A23 | Formulários · `ui.js:353` (`Field.error` sem uso), `Finance.js:131,301`, `Catalog.js:172` | Nenhum campo mostra erro no próprio campo; datas e horas são texto livre; o valor do gasto não usa a máscara de dinheiro. | Erros aparecem tarde (depois do envio) e longe do campo. | média | médio | Validar ao sair do campo com `Field error`; máscaras `date` e `time` no `MASKS` do `ui.js`; `mask="money"` em todo valor. | pendente (bloco 10) |
| A24 | Agenda (computador) · `DayGrid.js:72-110`, `Agenda.js:278` · `app/barbearia-1440-09-agenda-profissionais.png` | Blocos de 560 px de largura mostram só "10:30 Nome"; não mostram serviço nem status, não há passar o mouse ou clique direito, e os textos dizem "Toque" e "Toque e segure". | O computador da recepção tem espaço para mostrar muito mais e é usado com mouse. | média | médio | Mostrar serviço, status e valor quando houver espaço; menu de clique direito com as ações rápidas; textos "Clique" na web. | pendente (bloco 11) |
| L11 | Recursos, Gestão, comparativo, planos e FAQ · `landing/index.html:231-381` · `landing/landing-375-06-gestao.png` | As mesmas funções aparecem em 5 seções; só Gestão tem 9 cards e 3.955 px no celular. | O dono rola muito, cansa e não chega aos preços. | média | médio | Recursos em grade de ícones com 1 linha cada; Gestão com abas (Comanda, Estoque, Pacotes, Equipe, Offline) mostrando um mockup por vez; tirar dos planos o que já está em "Tudo do Individual". | pendente (bloco 10) |
| L12 | Mockups (celular) · `landing/styles.css:145-215` · `landing/landing-375-02-hero.png` | Os dois celulares lado a lado em 375 px usam texto de 10–12 px (mais de 80 nós abaixo de 13 px) e os nomes quebram em 2 linhas. | O mockup é a prova visual do produto; ilegível, não convence. | média | médio | No celular, um celular por vez (abas "Cliente" e "Você") em largura maior, com fonte mínima de 13 px. | pendente (bloco 10) |
| A25 | Cards da Hoje · `components/AppointmentCard.js:604-618` · `app/barbearia-375-03-hoje-inteira.png` | Selos "WhatsApp" (origem) e "Pix expirado" em quase todos os cards; nome cortado pelo preço. | Ruído visual que dilui os selos que importam. | baixa | pequeno | Esconder o selo de origem na Hoje; "Pix expirado" só na ficha ou na lista de Pix; preço numa linha abaixo no celular. | corrigido (bloco 1) |
| A26 | Calendário do mês (temas claros) · `screens/Agenda.js:112,156` · `app/salao-375-10-agenda-mes.png` | Barras de ocupação verde e laranja sobre a trilha: 1,98 e 2,43:1. Dias fechados com opacidade 0,4: número a 3,56:1 (escuro) e 2,5:1 (claro), apontado pelo axe. | O dono não vê os dias cheios de relance. | baixa | pequeno | Tons mais escuros nos temas claros (`statusText`) para as barras; dia fechado com `textMuted` em vez de opacidade. | corrigido (bloco 1) |
| A27 | Estados vazios e estoque · `screens/Customers.js`, `screens/Stock.js` · `app/salao-375-21-clientes-busca-vazia.png`, `app/barbearia-375-22-produtos-estoque.png` | Busca sem resultado não oferece "Cadastrar"; estoque negativo aparece como "-2 un" sem explicação. | Um toque a menos e menos dúvida. | baixa | pequeno | Ação "Cadastrar '{busca}'" no vazio; "Estoque negativo: confira a contagem" no selo. | corrigido (bloco 1) |
| A28 | Estrutura da web · `App.js` · axe (`region` 191 em 26 telas, `landmark-one-main`, `page-has-heading-one`, `aria-hidden-focus` em 1440) | Sem `main` nem `h1`; telas que ficam por baixo na pilha continuam focáveis dentro de `aria-hidden` (67 ocorrências em 1440 px); o sheet não tem nome (`aria-dialog-name`), a barra de uso da IA não tem nome (`aria-progressbar-name`) e os dias do calendário têm um rótulo que não contém o número visível (`label-content-name-mismatch`). | Quem navega por teclado ou leitor de tela cai em telas escondidas. | baixa | pequeno | `role="main"` no conteúdo, título da tela como `h1`, `inert` nas telas inativas da pilha na web. | corrigido (bloco 1) |
| A29 | Comprovante em tela cheia e fontes · `components/ReceiptReview.js:38-50`, `Finance.js:46`, `DayGrid.js:144` · `app/barbearia-375-18-pix-comprovante-aberto.png` | A tela cheia do comprovante não tem Confirmar nem Recusar; alguns textos não definem `fontFamily` e saem na fonte do sistema. | Obriga a fechar e procurar o botão; quebra a identidade visual. | baixa | pequeno | Rodapé com Confirmar e Recusar na tela cheia; usar `T`/`s.caption` em vez de `Text` cru. | corrigido (bloco 1) |
| A30 | Botões compactos e Voltar · `ui.js:296` (`compact` 40 px), cabeçalho do React Navigation · medição de alvos | "Abrir comanda", "Ficha", "Estornar", "Trocar" e "Cadastrar novo cliente" têm 40–41 px de altura; o "Voltar" do cabeçalho na web tem 30 x 30 px; chips e segmentos têm 44 px. | Abaixo dos 48 px pedidos para uso rápido, às vezes com a mão ocupada. | baixa | pequeno | `compact` com `minHeight: TOUCH` (mantendo o visual menor com `hitSlop`); `headerBackTitleVisible` com área de 48 px; chips com 48 px. | corrigido (bloco 1) |
| L13 | Fonte da landing · `landing/index.html:38` · Lighthouse | CLS de 0,106 (limite bom: 0,1) causado pela troca da Plus Jakarta Sans. | Pequeno salto do texto ao carregar no 4G. | baixa | pequeno | `@font-face` local com `size-adjust` na fonte reserva, ou `font-display: optional`; pré-carregar o `woff2` do peso 800. | pendente (bloco 2) |
| L14 | Planos e hero · `landing/styles.css` (`.badge`, `.actions .btn`) · `landing/landing-375-09-precos.png`, `landing-1440-primeira-dobra.png` | O selo "Para equipes" estica na largura do card; o CTA do hero quebra em 2 linhas no 1440. | Acabamento. | baixa | pequeno | `.plan .badge { align-self: flex-start }`; `flex: 0 1 auto` no CTA principal. | corrigido (bloco 1) |
| L15 | Calculadora e simulador · `landing/styles.css` (`.range input` 32 px, `.sim__reset` e `.opt` 44 px, links do rodapé 44 px) | Alvos menores que 48 px; o slider de valor (10 a 500, passo 5) é difícil de acertar no dedo. | Toque impreciso no celular. | baixa | pequeno | Área de toque de 48 px (padding ou `min-height`); botões − e + ao lado do slider de valor. | corrigido (bloco 1) |
| L16 | Textos · `landing/main.js` (`welcome`), `#calc-total` | "Bem-vindo" com Mariana, Fernanda e Helena; o resultado da calculadora (uma perda) aparece em verde e não tem CTA depois. | Concordância e semântica de cor; perde o momento de conversão. | baixa | pequeno | "Boas-vindas ao Seu Salão"; resultado em laranja ou branco; CTA "Testar 7 dias grátis" logo abaixo do resultado. | corrigido (bloco 1) |
| L17 | Comparativo e mockup web · `.compare`, `.w-group` | Região rolável sem foco de teclado (axe `scrollable-region-focusable`, sério) e "Gestão" em 9 px com 3,75:1 (axe `color-contrast`). | Acessibilidade de teclado; texto ilegível. | baixa | pequeno | Resolvido junto com L01; `.w-group` com `#94A3B8` e 11 px ou mais. | corrigido (bloco 1) |
| A31 | Hoje, listas e formulários (computador) · `ui.js:192` (`Screen maxWidth 1200`) · `app/barbearia-1440-03-hoje.png` | Uma coluna esticada até 1.120 px; preço a 1.000 px do nome; formulário com campos de 1.100 px. | Desperdiça o espaço do computador e obriga a olhar de um canto ao outro. | média | grande | Hoje em duas colunas (lista do dia + painel com Pix e aprovações); formulários com largura máxima de cerca de 640 px; listas grandes como `DataTable`. | pendente (bloco 11) |
| A32 | Código do app (consistência) · ver "Consistência de design" abaixo | Tamanhos de fonte, raios e espaçamentos fixos fora dos tokens; `DeltaStat` e as pílulas de incompatível duplicam `Stat` e `Chips`; títulos do menu lateral duplicam `s.section` com 12 px. | Cada valor fixo é uma divergência futura entre temas e telas. | baixa | médio | Trocar pelos tokens (`TYPE`, `RADIUS`, `SPACE`), acrescentar `RADIUS.small: 8`, e uma regra de lint que acuse `fontSize`/`borderRadius` numéricos fora de `theme.js`. | pendente (bloco 11) |

## Medições automáticas

### Acessibilidade (axe-core 4.x, regras WCAG 2.0/2.1/2.2 A e AA + boas práticas)

**Landing** (página inteira em cada largura, mais o simulador já no fim da conversa): 53 regras passam em cada largura.

| largura | violações |
|---|---|
| 375 px | `scrollable-region-focusable` (sério, 1): a tabela do comparativo rola na horizontal e não recebe foco de teclado (L01, L17) |
| 768 e 1440 px | `color-contrast` (sério, 1): "Gestão" no mockup da versão web, 9 px, #64748B sobre #0F172A = 3,75:1 (L17) |
| simulador (3 larguras) | nenhuma |

**App** (ocorrências "em" número de telas; cada tela analisada depois de carregar):

| regra (impacto) | Barbearia 375 px (27 telas) | Barbearia 768 px (27 telas) | Barbearia 1440 px (27 telas) | Salão 375 px (27 telas) | Salão 1440 px (11 telas) |
|---|---|---|---|---|---|
| `aria-required-attr` (crítico) | 52 em 10 | 52 em 10 | 51 em 10 | 52 em 10 | 29 em 4 |
| `label` (crítico) | 10 em 5 | 10 em 5 | 9 em 4 | 10 em 5 | 7 em 2 |
| `aria-hidden-focus` (sério) | 0 | 0 | 67 em 23 | 0 | 19 em 8 |
| `label-content-name-mismatch` (sério) | 38 em 6 | 51 em 6 | 49 em 6 | 38 em 6 | 48 em 5 |
| `nested-interactive` (sério) | 10 em 6 | 10 em 6 | 9 em 5 | 10 em 6 | 7 em 3 |
| `aria-prohibited-attr` (sério) | 8 em 4 | 9 em 5 | 9 em 5 | 9 em 5 | 8 em 4 |
| `color-contrast` (sério) | 4 em 2 | 5 em 3 | 4 em 2 | 5 em 2 | 6 em 3 |
| `target-size` (sério) | 4 em 4 | 4 em 4 | 3 em 3 | 4 em 4 | 1 em 1 |
| `aria-dialog-name` (sério) | 1 em 1 | 1 em 1 | 1 em 1 | 1 em 1 | 1 em 1 |
| `aria-progressbar-name` (sério) | 1 em 1 | 1 em 1 | 1 em 1 | 1 em 1 | 1 em 1 |
| `autocomplete-valid` (sério) | 1 em 1 | 1 em 1 | 1 em 1 | 1 em 1 | 0 |
| `region` (moderado) | 211 em 27 | 211 em 27 | 775 em 27 | 214 em 27 | 346 em 11 |
| `landmark-one-main` (moderado) | 1 em 1 | 1 em 1 | 26 em 26 | 1 em 1 | 10 em 10 |
| `page-has-heading-one` (moderado) | 1 em 1 | 1 em 1 | 2 em 2 | 1 em 1 | 1 em 1 |

O que está por trás:
- `aria-required-attr`, `label` e `nested-interactive`: os interruptores (`Toggle`), chips (`Chips`) e cards de nicho saem sem `aria-checked`, e o `<input>` do Switch fica sem nome e dentro de outro controle (A03). Conferido no DOM: `<div role="tab" aria-label="Timeline">` sem `aria-selected` e `<div role="radio">` sem `aria-checked`; as abas do rodapé (React Navigation) têm `aria-selected` corretamente.
- `aria-hidden-focus` (só no computador): as telas que ficam por baixo na pilha estão em `aria-hidden`, mas continuam com botões focáveis (A28).
- `color-contrast`: textos de interruptor desligado (opacidade 0,5, de 2,15 a 3,29:1; o WCAG isenta controle desativado, mas a dica explica o que ele faz) e dias fechados do calendário (opacidade 0,4, de 2,5 a 3,56:1) (A26).
- `target-size`: o `<input>` do Switch na web tem 40 x 20 px.
- `region` e `landmark-one-main`: o react-native-web não marca `main` (A28).
- Dados completos: `audit/data/app-*.json` e `audit/data/landing.json`.

### Contraste (WCAG: 4,5:1 texto, 3:1 ícones, bordas e componentes)

Calculado pelos tokens de `mobile/src/theme.js` (as mesmas funções do teste) para as 11 combinações de tema, mais as cores da landing: 263 combinações, 86 abaixo do mínimo, sendo 33 delas checagens de semântica de cor e decoração, não do WCAG. Lista completa em `audit/data/contraste.json`.

| combinação | resultado | mínimo | achado |
|---|---|---|---|
| Borda de chips e campos (`border`) sobre o fundo do sheet (`surfaceElevated`) | 2,16 (fitness) a 2,89:1 em todos os temas escuros e na marca-base | 3:1 | A09 |
| Texto branco sobre `status.danger` (faixa de sincronização com erro) | 3,76:1 em todos os temas | 4,5:1 | A10 |
| Barra do bloco "atendido" (`border`) sobre `neutralBg` | 2,23 a 2,44:1 nos temas escuros | 3:1 | A13 |
| Hachura de bloqueio (`divider`) sobre o fundo | 1,15 a 1,72:1 | 3:1 | A13 |
| Fora do expediente x expediente (temas claros) | 1,15:1 | (diferença visível) | A13 |
| Barras de ocupação do mês (verde e laranja, temas claros) | 1,98 e 2,43:1 | 3:1 | A26 |
| Contorno do toast de sucesso (temas claros) | 2,28:1 | 3:1 | junto com A09 (o ícone e o texto do toast passam) |
| Contorno do toast de informação (fitness escuro) | 2,55:1 | 3:1 | junto com A09 |
| `accent` puro como ícone e indicador (barbearia, pet shop e fitness claros) | 1,98 a 2,43:1 | 3:1 (o logo é isento) | A19 |
| "Pedido para aprovar" (`accentText` sobre `accentSoft` no fundo) | 4,49 (pet shop claro) e 4,26:1 (fitness claro) | 4,5:1 | A19 |
| Âmbar da marca x laranja de alerta (barbearia) | 1,31:1 entre as duas cores; 1,15 a 1,46 nos outros segmentos | (precisam se distinguir) | A19 |
| Landing: contorno dos botões de nicho, "Ver como funciona" e menu (#334155) | 1,72:1 | 3:1 | L09 |
| Landing: "Gestão" no mockup web (#64748B, 9 px) | 3,75:1 | 4,5:1 | L17 |

O que passa e deve continuar assim: texto, texto secundário e `accentText` sobre todos os fundos; texto sobre botão principal (`onAccent`); selos de status (texto sobre a cor a 15%); faixa laranja de Pix pendente (#1C1917 sobre #F97316); na landing, CTA verde (#0F172A sobre #22C55E = 7,9:1), texto secundário, bolhas do simulador e selos dos mockups.

### Alvos de toque menores que 48 px e textos menores que 13 px (telas de celular, 375 px)

Medido em 27 telas de cada tema, considerando só o que está de fato na frente (as telas de baixo da pilha continuam no DOM e foram descontadas); a tela foi esticada na altura para medir o conteúdo inteiro. Dados em `audit/data/medidas-barber-375.json` e `medidas-beauty-375.json` (os dois temas dão os mesmos números).

| alvo | tamanho | ocorrências | observação |
|---|---|---|---|
| Dias do calendário do mês | 43 x 64 px | 31 | largura limitada pela grade de 7 colunas; aceitável, mas sem folga entre os dias |
| Chips e segmentos (Timeline/Barbeiros/Mês, profissionais, serviços) | altura 44 px | 47 | `Chips` e `SegmentedControl` usam `minHeight: 44` (A30) |
| "Voltar" do cabeçalho (web) | 30 x 30 px | 17 telas | A30 |
| Blocos de 30 min na agenda | altura 36 px | 10 | o toque no bloco fica pequeno; o "segurar" também |
| Botões `compact` ("Abrir comanda", "Ficha", "Estornar", "Trocar", "Cadastrar novo cliente") | altura 40–41 px | em quase todas as telas | A30 |
| Campos de texto | 46 px internos | 37 | falso positivo: o contorno do `Field` tem 48 px |

| texto | ocorrências (27 telas) | onde |
|---|---|---|
| 12 px | 214 | rótulos das abas do rodapé (6 em toda tela), blocos da agenda (horário e serviço), números do calendário, "+87,6% vs. anterior" no Financeiro |
| 10–11 px | 7 | eixo do gráfico do Financeiro ("0", "1k", "2k") e ícone de cadeado do calendário |
| telas com mais texto pequeno | | Agenda Mês (37), Timeline (24), Profissionais (20), Financeiro (14) |

**Landing em 375 px:** 12 alvos abaixo de 48 px: os 4 sliders da calculadora (32 px de altura), o botão de recomeçar do simulador (44 x 44), as respostas do simulador (44–47 px), os links do rodapé (44 px) e um link inline. Textos abaixo de 13 px: 80 nós (50 de 11 px, 19 de 12 px, 11 de 10 px), quase todos nos mockups (L12) e na nota do simulador (12 px). Sem rolagem lateral em 375, 768 e 1440 px.

### Lighthouse da landing (celular, Lighthouse 12.6.0, servidor local)

| categoria | nota |
|---|---|
| Desempenho | **97** (FCP 0,9 s · LCP 1,4 s · TBT 50 ms · CLS 0,106 · Speed Index 0,9 s) |
| Acessibilidade | **100** |
| Boas práticas | **100** |
| SEO | **85**: `canonical` inválido (`https://[DOMINIO]/`) e `robots.txt` com `Sitemap: https://[DOMINIO]/sitemap.xml` (L04) |

O CLS de 0,106 vem da troca da fonte (`fonts.gstatic.com/.../plusjakartasans`, 0,087 do total) (L13). Relatório completo: `audit/data/lighthouse-landing-celular.html`. Servidor local não tem a compressão nem o cache de produção, então o desempenho real depende do servidor do domínio.

### Consistência de design (código do app)

| o que | quantidade | detalhes |
|---|---|---|
| `fontSize` numérico fora dos tokens | 43 (contra 11 `type.*` e 226 usos dos estilos base `s.*`) | valores fora da escala 32/24/20/17/15/13: 12 (8x), 14, 16 (4x), 22, 26, 34, 40. Ex.: `App.js:195`, `DayGrid.js:95,100,144`, `Layout.js:29,63,76,82`, `Finance.js:46`, `chart.js:78`, `Settings.js:496` (40), `Team.js:36` (26), `Comandas.js:319` (22) |
| `borderRadius` numérico | 30 (contra 11 `radius.*`) | 2, 3, 4, 5, 6, 8, 10, 12, 13, 14, 17 e 999; `14` e `999` já existem como `RADIUS.card` e `RADIUS.pill`. Ex.: `ui.js:156,485,524` (14), `DayGrid.js:86` (8), `Settings.js:358` (13), `Finance.js:162` (12) |
| espaçamento numérico (padding, margin e gap sem `SPACE`) | 60 (contra 328 `SPACE()`) | `marginTop: 2` (6x), `marginRight: 6` (4x), `gap: 8`, `marginTop: 10`; concentrado em `Finance.js:56,128,145,223,254,416,444` e `chart.js:69` |
| cores fixas fora de `theme.js` | 4 | `Sync.js:50` (`#FFFFFF` sobre vermelho, A10) e `ReceiptReview.js:42,46,48` (visualizador preto, aceitável) |
| texto sem `fontFamily` (sai na fonte do sistema na web) | vários | `Finance.js:46`, `DayGrid.js:144`, `ReceiptReview.js:48` |
| componentes duplicados que deveriam usar `ui.js` | 4 | `DeltaStat` (`Finance.js:38`) refaz o `Stat`; pílulas de "Incompatível com" (`Customers.js:236-258`) refazem `Chips` e `Badge`; os títulos "Gestão" e "Atalhos" do menu lateral (`Layout.js:63,76`) refazem `s.section` com 12 px em vez de 13; o calendário (`Agenda.js:140`) e os cards de nicho (`Settings.js:100`) têm botões próprios sem os estados de acessibilidade do `ui.js` |

## O que já está bom e deve ser mantido

- **Design system com contraste testado:** `theme.js` documenta cada token e o `tests/contrast.test.mjs` cobre texto, botões, selos e banners em 11 combinações de tema. Os achados de contraste acima são combinações que o teste ainda não inclui (borda em `surfaceElevated`, branco sobre vermelho).
- **Cor nunca sozinha:** todo status tem rótulo e ícone (`status.js`); a ocupação do mês tem legenda.
- **Alvo de 48 px nos componentes base:** `IconButton`, `Button` (52 px), campos e linhas de lista (60 px) respeitam o `TOUCH`. Os alvos menores estão em chips e segmentos (44 px), no Switch e no "Voltar" do cabeçalho (30 px).
- **Pix pendente como primeiro alerta** na Hoje e no Caixa, com contador, e "Confirmar Pix" direto no card (2 toques).
- **Conflito entre clientes** explicado no momento de agendar, com o motivo e a distância mínima.
- **Estados de carregamento e erro** padronizados (`Loading`, `SkeletonList`, `Empty`) com "Tentar de novo".
- **Faixa offline** clara na web, e o texto honesto de que a web só funciona com internet.
- **Botão principal fixo no rodapé** dos formulários e dos sheets, subindo com o teclado; máscaras de telefone e dinheiro.
- **Versão web com menu lateral, atalhos N/C/B visíveis e comanda em duas colunas.**
- **Temas por segmento:** o salão (claro) separa bem o rosa da marca do laranja de alerta e é agradável de ler.
- **Landing honesta:** sem depoimentos nem números inventados (com regra no HTML e no teste), calculadora com a fórmula explicada e "não é uma promessa de resultado", FAQ completo sobre offline, Pix e LGPD.
- **Landing rápida e acessível:** Lighthouse no celular com desempenho 97, acessibilidade 100 e boas práticas 100; sem rolagem lateral em nenhuma largura; menu do celular com `aria-expanded`; FAQ com `details`; um só `h1`.
- **Simulador fiel ao robô real** (mesmas etapas e textos) e roda só no navegador, sem enviar nada.
