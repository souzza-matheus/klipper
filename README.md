# SyncServ

Plataforma de agendamento pelo WhatsApp para vários segmentos (barbearia, salão de beleza e estética, pet shop, clínica e consultório, estúdio fitness), com bot para o cliente, bot para o dono e app nativo de administração que aplica o tema e o vocabulário do segmento de cada negócio. O projeto nasceu como BarberBot: a pasta, a instância de demonstração (`barbearia-demo`) e o pacote do app (`br.com.barberbot.admin`) continuam com esse nome.

```
barberbot/
├── backend/            API em Python (FastAPI), bots, Pix, rotinas automáticas
├── mobile/             App admin em React Native (Expo)
├── branding/           kit de logo SyncServ (syncserv-logo-kit) e arquivos da futura landing page (web-publico)
├── landing/            landing page de vendas (site estático com a seção de gestão do CRM; teste: python3 landing/tests/landing_e2e.py)
├── docker-compose.yml  Postgres + Redis + Evolution API + backend
├── scripts/whatsapp.sh atalhos do Docker e do WhatsApp (up, qr, status...)
└── .env.example
```

## O que está pronto

**Bot do cliente:** agendar (serviço → barbeiro ou "tanto faz" → dia → horário → nome → confirmação), meus agendamentos (cancelar, remarcar, pagar), serviços e preços, barbeiros, horário e endereço, Pix antecipado, falar com atendente (pausa o bot), lembrete com confirmação de presença e pesquisa de satisfação de 1 a 5 com comentário.

**Bot do estabelecimento:** o número do dono (configurações) e os números dos barbeiros abrem um menu próprio: agenda de hoje e amanhã, horários livres de um dia, busca de cliente, Pix pendentes (confirmar), bloqueio rápido de horário, avaliações, resumo do dia, "testar como cliente" e, só para o dono, **pedidos para aprovar** (opção 10). Barbeiro vê só a própria agenda.

**Alertas automáticos:** novo agendamento, pedido para aprovar, cancelamento (com o horário que ficou livre), remarcação, "paguei" do cliente, avaliação baixa, pedido de atendente, pedidos que expiraram sem resposta e resumo diário de manhã.

**App admin:** aba **Hoje** (resumo do dia, banners de Pix pendente e de pedidos para aprovar, próximos atendimentos), agenda em **Timeline**, **Profissionais** lado a lado ou **Mês**, agendamento rápido tocando num horário vago, ações rápidas ao segurar um atendimento (confirmar presença, concluir, faltou, WhatsApp), confirmar Pix direto no card, novo agendamento manual, remarcar, cancelar, enviar Pix, Pix pendentes com comprovante, clientes com histórico, aprovação manual, bloqueio e clientes incompatíveis, financeiro, serviços, profissionais com expediente e comissões, bloqueios, avaliações, relatórios, configurações do bot, do Pix e da aparência, conexão do WhatsApp por QR Code ou código de pareamento. Detalhes em [App admin](#app-admin).

**Agenda:** na aba Agenda, o seletor **Timeline | Profissionais | Mês** troca a visão. A Timeline tem um eixo vertical de horas, blocos com altura proporcional à duração (lado a lado quando se sobrepõem), o expediente em destaque, bloqueios hachurados e a linha do "agora" (atualiza a cada minuto); filtra por profissional. Profissionais mostra uma coluna por profissional no mesmo eixo de horas (rola na horizontal se não couber). Mês mostra o calendário (seg a dom) com o número de atendimentos e uma barra de ocupação em cada dia. Ocupação = atendimentos ÷ capacidade do dia, onde a capacidade é o expediente dos profissionais (menos os bloqueios) dividido pela duração média dos serviços ativos. Tocar em um dia abre a Timeline.

**Forma de pagamento:** ao marcar um atendimento como concluído, o app pergunta como o cliente pagou (Pix, dinheiro, débito ou crédito) e permite ajustar o valor cobrado (desconto ou acréscimo). Se o cliente já pagou o Pix pelo bot, vem "Pix" marcado. O valor final é o que entra no faturamento e nas comissões.

**Gastos:** contas da barbearia por categoria (aluguel, energia, água, internet, produtos, equipamentos, manutenção, marketing, salários, impostos, outros), com vencimento, pagamento, forma de pagamento e barbeiro (opcional). Um gasto marcado como **"Repetir todo mês"** gera automaticamente a conta dos meses seguintes quando o mês é aberto (no app, no resumo ou no aviso diário), sem duplicar. Para parar de repetir, desligue a opção no gasto original. O resumo diário do dono no WhatsApp avisa as contas que vencem hoje ou já venceram.

**Financeiro (aba no app):** faturamento, gastos pagos, lucro e ticket médio do período (este mês, mês passado, 7 dias ou datas escolhidas), com a variação contra o período anterior de mesmo tamanho; gráfico de faturamento x gastos por dia; faturamento por barbeiro, serviço e forma de pagamento; gastos por categoria; exportação em CSV para o Excel (compartilhada pelo celular). Faturamento = atendimentos concluídos; gastos entram no dia em que foram pagos (regime de caixa); lucro = faturamento − gastos pagos.

**Comissões e repasses:** regras de quanto cada barbeiro repassa para a barbearia ou para um barbeiro padrinho (várias ao mesmo tempo, por serviço ou geral, com vigência; a soma não passa de 100%). O cálculo usa o valor cobrado em cada atendimento concluído e a regra vigente no dia dele. Mostra bruto, repasses, líquido, acertado e em aberto por barbeiro, registra acertos e avisa os barbeiros pelo WhatsApp. No app: **Financeiro > Comissões e repasses**; as regras de cada barbeiro também ficam em **Mais > Barbeiros > [barbeiro] > Comissões**.

**Acesso ao agendamento ("demitir" cliente):** na ficha do cliente, em **Acesso ao agendamento**, o dono escolhe entre:

- **Normal:** agenda pelo WhatsApp como sempre.
- **Precisa de aprovação:** o fluxo do bot é o mesmo, mas no fim o agendamento fica como **Aguardando aprovação** (`pending_approval`) e o cliente recebe "Recebemos seu pedido! A barbearia vai confirmar e te avisamos por aqui." O horário fica reservado enquanto aguarda. O dono recebe um alerta no WhatsApp e aprova ou recusa pelo bot (menu, opção 10: escolhe o pedido e responde 1 para aprovar ou 2 para recusar) ou pelo app (faixa "N pedidos para aprovar" no topo da Agenda). Aprovado, vira agendado, o cliente recebe o resumo e, com o Pix ativo, a oferta de pagamento (o Pix antecipado só é oferecido depois da aprovação). Recusado, é cancelado e o cliente recebe uma mensagem neutra. O pedido expira sozinho depois de **X horas sem resposta** (configuração "Pedido para aprovar expira em", padrão 12 h) ou quando faltar menos de 1 h para o horário, o que vier primeiro: o horário é liberado e o cliente e o dono são avisados. Para dar tempo de o dono responder, pelo bot esse cliente só vê horários com pelo menos 2 h de antecedência. Remarcar pelo bot também gera um novo pedido para aprovar.
- **Bloqueado:** ao tentar agendar ou remarcar, o bot responde "No momento não conseguimos agendar por aqui. Por favor, fale com a barbearia." Serviços, barbeiros, horários e endereço continuam funcionando. Os agendamentos futuros não são cancelados automaticamente: ao bloquear, o app pergunta se quer cancelá-los (avisando ou não o cliente) e, se forem mantidos, a ficha mostra um aviso.

O motivo é interno (só o dono vê, no app e na busca de cliente do bot). Nenhuma mensagem ao cliente diz que ele foi bloqueado ou que precisa de aprovação. A lista de clientes mostra um selo para quem está em aprovação ou bloqueado e tem filtro por acesso. O dono pode agendar manualmente pelo app um cliente bloqueado ou em aprovação: o app avisa antes de confirmar e o agendamento já entra como agendado.

**Clientes que não podem se encontrar:** na ficha do cliente, em **Incompatível com**, o dono adiciona outro cliente (busca por nome ou telefone num painel que sobe de baixo), a distância mínima (padrão do negócio, 1 h, 2 h, 4 h, 8 h ou "dia inteiro"), o que fazer quando o horário ficar perto demais (`conflict_action`: **Bloquear o horário**, o padrão, ou **Exigir minha aprovação**) e o motivo interno. A distância vale entre o fim de um atendimento e o início do outro, nos dois sentidos e **com qualquer barbeiro**, contando agendamentos agendados, confirmados e aguardando aprovação. "Dia inteiro" impede os dois no mesmo dia. Sem distância própria, vale a configuração "Distância padrão entre clientes que não podem se encontrar" (padrão 240 min = 4 h).

- Com **Exigir minha aprovação**, o bot mostra o horário normalmente, mas o agendamento fica **Aguardando aprovação** (mesmo fluxo do cliente "precisa de aprovação", com o alerta ao dono). Se houver ao mesmo tempo um conflito "bloquear" e um "exigir aprovação", vale o bloqueio.
- No bot, com **Bloquear o horário**, os horários proibidos simplesmente não aparecem; se o dia inteiro ficar sem horário, o bot diz só que não há horários livres no dia. Ao confirmar, a regra é conferida de novo (dois clientes agendando ao mesmo tempo): se não puder, o bot diz que o horário acabou de ser ocupado.
- No app, o novo agendamento mostra um aviso discreto quando o cliente tem conflito com alguém agendado no dia e esconde os horários próximos (com a opção "Mostrar todos"). Se o horário violar a regra, o app mostra o nome e o horário do outro cliente e a distância exigida, e permite **Agendar mesmo assim**. O mesmo vale ao remarcar.
- Nenhuma mensagem para cliente menciona o outro cliente ou a existência do conflito.

**CRM (fase 1).** No app (e na versão web): aba **Caixa** (comandas), e em Mais / menu lateral: Produtos e estoque,
Pacotes, Clube de assinatura, Lista de espera e Equipe e permissões; menus e botões conforme o papel de quem entrou. Plano completo e decisões em [ROADMAP-CRM.md](ROADMAP-CRM.md).

- **Equipe e permissões:** dono, recepção e profissional, com convite por senha provisória (trocada no primeiro acesso). A recepção agenda, faz check-in, fecha comandas e confirma Pix, sem o financeiro completo; o profissional vê só a própria agenda, os clientes que atendeu e as próprias comissões. Toda rota da API checa o papel.
- **Comanda:** serviços, produtos, venda de pacote, desconto em R$ ou %, gorjeta para o profissional e pagamento dividido (Pix, dinheiro, débito, crédito), com saldo de pacote ou assinatura. Lançamentos imutáveis: corrigir é estornar (lançamento negativo). Fechada, entra no financeiro e nas comissões e conclui o atendimento.
- **Produtos e estoque:** venda e uso interno, custo, preço, mínimo e comissão opcional. O saldo é a soma das movimentações (nunca sobrescrito); a venda e o consumo do serviço baixam o estoque; estoque baixo aparece no app e no resumo diário.
- **Pacotes:** N sessões de um serviço com validade; usados ao agendar ou na comanda; cancelamento devolve a sessão; comissão pelo valor proporcional da sessão. O cliente compra pelo WhatsApp (opção 8) e o pacote vale depois que o Pix é confirmado.
- **Clube de assinatura:** planos mensais com serviços e limites por período, cobrança por Pix no WhatsApp no vencimento (confirmação manual; gateway plugável), status ativa/atrasada/cancelada, benefícios bloqueados depois de X dias de atraso e relatório com MRR.
- **Sinal contra faltas:** por estabelecimento e por serviço (desligado, fixo ou %). O horário fica "aguardando sinal" e é liberado se o Pix não for confirmado a tempo; regra de devolução configurável.
- **Lista de espera:** o bot oferece quando o dia está cheio; quando um horário abre, a primeira pessoa da fila é avisada e a vaga fica reservada por 10 minutos.
- **Sincronização offline:** ids públicos (UUID), versão e exclusões como tombstone; `GET /api/sync/pull` e `POST /api/sync/push` com idempotência e regras de conflito.
- **App offline (celular):** banco local criptografado (SQLCipher) com a agenda, clientes, catálogo, estoque, saldos e comandas; agenda, comanda, estoque e lista de espera funcionam sem internet e sincronizam sozinhos (ver "Modo offline do app").

**Pix:** gera o "copia e cola" (padrão do Banco Central) com a chave do próprio negócio. O dinheiro vai direto para a conta do dono; a confirmação é manual (app ou WhatsApp). Se o cliente manda a imagem ou o PDF do comprovante no WhatsApp, a IA lê os dados e o sistema faz uma **pré-conferência** (valor, recebedor, data, comprovante já usado) para o dono confirmar com um toque; ver [Comprovante de Pix](#comprovante-de-pix-pré-conferência-com-ia). **Recusar** um Pix (o dinheiro não caiu) marca como expirado e avisa o cliente com uma mensagem neutra; o horário continua marcado.

## Testar em 2 minutos (sem WhatsApp)

```bash
cd backend
pip install -r requirements.txt
echo "DEV_MODE=true" >> .env             # desenvolvimento (sem isso a API roda como produção)
alembic upgrade head                     # cria/atualiza as tabelas
python -m app.seed                       # cria a "Barbearia Demo"
uvicorn app.main:app --reload
```

Sem `EVOLUTION_URL`, o sistema roda em **modo simulação**: as mensagens aparecem no terminal. Converse com o bot pela documentação interativa em http://localhost:8000/docs, rota `POST /dev/simulate` (as rotas `/dev/*` exigem o cabeçalho `X-Setup-Token` com o `SETUP_TOKEN` do `.env`; no `/docs` ele aparece como campo da rota):

```json
{ "phone": "31977776666", "text": "oi" }
```

- Número de cliente: qualquer um.
- Número do dono da demo: `31999990000`. Barbeiros: `31988880001` (João) e `31988880002` (Pedro).
- `POST /dev/run-jobs` roda na hora os lembretes, pesquisas e expiração de Pix (também com `X-Setup-Token`).
- Pelo terminal: `curl -X POST localhost:8000/dev/simulate -H "X-Setup-Token: $SETUP_TOKEN" -H "Content-Type: application/json" -d '{"phone":"31977776666","text":"oi"}'`.
- Login do app: `admin@demo.com` / `demo123`.

### Dados de teste (mock)

Para ver a agenda, os relatórios e as avaliações com movimento, popule a demo com dados fictícios:

```bash
cd backend
python -m app.seed_mock            # cria a demo (se preciso) e gera os dados
python -m app.seed_mock --reset    # apaga os dados mock e gera de novo
```

Gera 40 clientes com celulares fictícios de DDD 00, que não existe, para nenhuma mensagem chegar a uma pessoa real (mais os 4 de exemplo do controle de clientes, abaixo), agendamentos de 30 dias atrás até 7 dias à frente (com concluídos, cancelados e faltas, e forma de pagamento nos concluídos), Pix, avaliações, 3 bloqueios futuros e os gastos de exemplo. Também marca horários futuros para os clientes de exemplo: o bloqueado (para ver o aviso na ficha), um pedido aguardando aprovação e um horário para um dos clientes em conflito. O `--reset` apaga só clientes, conflitos entre clientes, agendamentos, pagamentos, avaliações, bloqueios, conversas, gastos e acertos da Barbearia Demo e gera tudo de novo; serviços, barbeiros, regras de comissão e o login admin continuam. As datas são relativas ao dia em que o script roda.

O `app.seed` já cria exemplos do controle de clientes: **Marcos Teixeira** (`5500955550001`, bloqueado), **Paulo Duarte** (`5500955550002`, precisa de aprovação) e o par **Renato Vasconcelos** (`5500955550003`) e **Alexandre Pinto** (`5500955550004`), que não podem se encontrar (distância padrão da barbearia). Para testar, mande mensagens com esses números no `/dev/simulate`.

O `app.seed` também cria exemplos do financeiro: Pedro (barbeiro novo) repassa 40% para a barbearia e 10% para o João (padrinho), João repassa 30% para a barbearia; contas fixas recorrentes (aluguel, internet, luz, água, contador) e alguns gastos avulsos do mês, um deles vencido e outro vencendo hoje.

### Uma empresa de demonstração por segmento

```bash
cd backend
python -m app.seed_niches            # cria as que faltam e gera os dados de cada uma
python -m app.seed_niches --reset    # apaga os dados mock delas e gera de novo
```

Cria quatro empresas, além da Barbearia Demo, cada uma com serviços, profissionais e expediente do segmento e o mesmo tipo de dados do `seed_mock` (40 clientes, agenda de 30 dias para trás e 7 para frente, Pix, avaliações, bloqueios, gastos, um cliente bloqueado, um em aprovação com pedido pendente e um par incompatível). Senha de todas: `demo123`.

| Segmento | Empresa | Login |
| --- | --- | --- |
| barbershop | Barbearia Demo | `admin@demo.com` |
| beauty | Studio Bella Beleza & Estética | `salao@demo.com` |
| petshop | Pet Feliz Banho e Tosa | `pet@demo.com` |
| clinic | Clínica Vida Plena | `clinica@demo.com` |
| fitness | Estúdio Movimento Pilates & Funcional | `estudio@demo.com` |

Cada empresa também tem os dados do CRM: produtos (um abaixo do mínimo), um pacote, o "Clube Mensal" com 3 assinantes (um atrasado), comandas fechadas e um cliente na lista de espera. Equipe de exemplo (senha `demo123`): `recepcao@demo.com` e `profissional@demo.com` na Barbearia Demo; nas outras, `recepcao.<login>@demo.com` e `profissional.<login>@demo.com` (ex.: `recepcao.salao@demo.com`). O `seed_mock` faz o mesmo na Barbearia Demo.

Essas quatro não têm WhatsApp do dono nem dos profissionais, e a instância delas (`salao-demo`, `petshop-demo`, `clinica-demo`, `estudio-demo`) não existe na Evolution: nenhuma mensagem sai delas.

Testes automatizados: `cd backend && pytest` (Pix, agendamento completo, cancelamento, remarcação, menu do dono, lembrete, pesquisa, comissões, gastos e recorrência, resumo financeiro, CSV, agenda do mês, cliente bloqueado e em aprovação, conflitos entre clientes, migrações, comanda, estoque, pacotes, assinatura, sinal, lista de espera, papéis, sincronização e comprovantes de Pix com IA falsa). Rode um `pytest` por vez: os testes usam o mesmo arquivo SQLite.

## Banco de dados e migrações (Alembic)

O esquema do banco é controlado pelo Alembic (`backend/migrations`). A API não cria mais tabelas sozinha.

```bash
cd backend
alembic upgrade head                                   # aplica as migrações pendentes
alembic revision --autogenerate -m "o que mudou"      # depois de alterar app/models.py
```

- `0009` (comprovantes) cria `payment_receipts` (arquivo, dados lidos, conferências, resultado e decisão; `e2e_id` único) e as configurações `shops.receipt_auto_confirm` e `receipt_auto_confirm_max`.
- `0008` (CRM fase 1) adiciona os papéis dos usuários (quem já existia vira dono), as colunas da sincronização (`uuid`, `updated_at`, `deleted_at`, `version`, `sync_seq`, preenchidas para as linhas existentes) e as tabelas de comanda, estoque, pacotes, assinaturas, cobranças, lista de espera e operações do sync.
- `0004` adiciona o segmento e o modo do tema do negócio (`shops.niche`, padrão `barbershop`, e `shops.theme_mode`, padrão `auto`), a ação de conflito (`customer_conflicts.conflict_action`, padrão `block`) e o comprovante do Pix (`payments.receipt_mime`, `receipt_data`, `receipt_at`).
- `0001` representa o esquema de antes do Alembic, `0002` adiciona a forma de pagamento nos atendimentos e a tabela de gastos e `0003` adiciona o acesso do cliente (`access_status`, `access_reason`, `access_changed_at`), o início do pedido para aprovar nos agendamentos (`approval_requested_at`), as configurações `approval_expire_hours` e `conflict_default_gap_minutes` e a tabela `customer_conflicts`. Clientes que já existiam ficam com acesso "normal".
- Bancos criados pela versão antiga (`create_all`) também funcionam: as migrações só criam as tabelas e colunas que faltam e depois passam a controlar o banco normalmente. Não é preciso apagar nada.
- No Docker, o container do backend roda `alembic upgrade head` antes de subir a API.
- A URL vem da mesma `DATABASE_URL` da API (ou `alembic -x url=sqlite:///outro.db upgrade head`).

**Banco de desenvolvimento: Postgres.** O Postgres do Docker fica exposto só no localhost, na porta `POSTGRES_HOST_PORT` do `.env` (padrão 5434, porque a 5432 costuma estar ocupada). O backend local (`uvicorn` na 8000) usa esse mesmo banco pelo `backend/.env`, então a porta 8000 e a 8002 (backend do Docker) enxergam os mesmos dados:

```bash
# backend/.env
DATABASE_URL=postgresql+psycopg://barberbot:SENHA_DO_POSTGRES@localhost:5434/barberbot
RUN_SCHEDULER=false   # as rotinas automáticas já rodam no backend do Docker; aqui seriam duplicadas
```

Os testes continuam em SQLite (o `tests/conftest.py` define o próprio `DATABASE_URL`). Sem `DATABASE_URL`, a API usa `sqlite:///./barberbot.db`, útil para testar sem Docker.

Para recriar um banco SQLite de desenvolvimento do zero:

```bash
cd backend
rm -f barberbot.db
alembic upgrade head
python -m app.seed_mock
```

## API do financeiro

Todas as rotas exigem login e enxergam só a barbearia do usuário. Valores em reais como texto decimal (`"1234.50"`), datas no horário local sem fuso.

| Rota | O que faz |
| --- | --- |
| `PATCH /api/appointments/{id}` | além de `status`, aceita `payment_method` (`pix`, `dinheiro`, `debito`, `credito`) e `price` (valor final) |
| `GET /api/appointments/month?year&month&barber_id` | por dia: total, cancelados, faturamento previsto, capacidade, ocupação (0 a 1), se tem expediente e se tem bloqueio |
| `GET/POST /api/expenses`, `GET/PUT/DELETE /api/expenses/{id}` | gastos; filtros `month=AAAA-MM`, `category`, `status=paid\|open\|overdue`, `barber_id` |
| `POST /api/expenses/{id}/pay` | marca como pago (corpo opcional: `paid_at`, `payment_method`) |
| `GET /api/finance/summary?date_from&date_to` | faturamento, gastos pagos e em aberto, lucro, ticket médio, atendimentos, quebras por barbeiro, serviço, forma de pagamento e categoria, período anterior e variação em % |
| `GET /api/finance/daily?date_from&date_to` | série diária de faturamento e gastos |
| `GET /api/finance/export.csv?date_from&date_to` | atendimentos concluídos e gastos em CSV (`;`, vírgula decimal, UTF-8 com BOM) |
| `/api/commission-rules`, `/api/finance/commissions`, `/api/finance/settlements` | regras de comissão, repasses do período e acertos |

## API do controle de clientes

| Rota | O que faz |
| --- | --- |
| `GET /api/customers?access_status=` | filtra por acesso (`normal`, `approval`, `blocked`); clientes trazem `access_status`, `access_reason` e `access_changed_at` |
| `PUT /api/customers/{id}/access` | `access_status`, `access_reason`; ao bloquear, `cancel_future=true` cancela os agendamentos futuros e `notify_customer=true` avisa o cliente (mensagem neutra) |
| `GET /api/approvals` | pedidos aguardando aprovação, com `approval_deadline` |
| `POST /api/appointments/{id}/approve`, `.../refuse` | aprova ou recusa (409 se já foi respondido ou expirou) |
| `GET/POST /api/customer-conflicts`, `GET/PUT/DELETE /api/customer-conflicts/{id}` | pares que não podem se encontrar; `?customer_id=` lista os de um cliente (com `other_customer_*`). Corpo: `customer_id`, `other_customer_id`, `min_gap_minutes` (nulo = padrão), `same_day_block`, `conflict_action` (`block` ou `approval`), `notes` |
| `GET /api/customer-conflicts/day?day&customer_id\|customer_phone` | clientes em conflito com horário no dia (aviso da tela de agendamento) |
| `GET /api/availability?...&customer_id=` | horários livres já sem os que violam conflitos do cliente |
| `POST /api/appointments`, `POST /api/appointments/{id}/reschedule` | aceitam `force=true`. Sem ele, um conflito entre clientes devolve 409 com `detail = {code: "customer_conflict", message, conflict: {other_customer_name, start, end, barber_name, gap_minutes, same_day_block}}` |

## API da agenda, do Pix e da aparência

| Rota | O que faz |
| --- | --- |
| `GET /api/agenda/day?day=AAAA-MM-DD` | tudo da agenda do dia numa resposta: para cada profissional ativo (ou com agendamento no dia), `working` (expediente), `blocks` (com `whole_shop`), `appointments` (sem os cancelados) e `free` (expediente menos bloqueios e agendamentos, a partir de agora; dia passado não tem livre). Também `now` e `slot_step_minutes` |
| `GET /api/payments?status=pending` | pendentes: primeiro os com comprovante que **confere**, depois os que o cliente disse que pagou, depois pelo horário do atendimento; trazem serviço, profissional, `kind` (`full` ou `deposit`), `has_receipt` e `receipt` (o último comprovante: dados lidos, `checks`, `result`, `decision`, `auto_confirmed`, `has_file`) |
| `POST /api/payments/{id}/reject` | o Pix não caiu: marca como expirado e avisa o cliente com mensagem neutra (409 se não estiver pendente) |
| `GET /api/payments/{id}/receipt` | o último comprovante (imagem ou PDF) com o `Content-Type` original; exige login de dono ou recepção |
| `GET /api/receipts/{id}`, `GET /api/receipts/{id}/file` | dados e arquivo de um comprovante (dono e recepção da própria loja; 404 depois do prazo de retenção) |
| `POST /api/receipts/{id}/confirm`, `.../reject` | confirma (fluxo de sempre) ou recusa (mensagem neutra) o pagamento do comprovante; 409 se não estiver mais pendente |
| `POST /api/receipts/{id}/undo` | só o dono: desfaz uma confirmação automática (o pagamento volta para pendente e o cliente é avisado) |
| `GET /api/charges?status=pending` | as cobranças também trazem `receipt`, com as que conferem no topo |
| `GET/PUT /api/shop`, `POST /api/auth/login`, `GET /api/me` | incluem `niche` (`barbershop`, `beauty`, `petshop`, `clinic`, `fitness`) e `theme_mode` (`auto`, `dark`, `light`) |

Os agendamentos (`AppointmentOut`) trazem `payment_id` e `customer_reported_paid`, para o app confirmar o Pix direto do card.

## API do CRM (fase 1)

Papéis: **D** = dono, **R** = recepção, **P** = profissional. Sem papel permitido, a rota responde 403.

| Rota | Quem | O que faz |
| --- | --- | --- |
| `GET/POST /api/users`, `PUT /api/users/{id}`, `POST /api/users/{id}/reset-password` | D | equipe; o convite devolve `provisional_password` (uma vez) |
| `POST /api/auth/change-password` | todos | troca a senha (obrigatória no primeiro acesso) e devolve um token novo |
| `POST /api/appointments/{id}/check-in` | D R P (P: só os próprios) | cliente chegou |
| `POST /api/appointments/{id}/deposit-refunded` | D | sinal devolvido |
| `GET/POST /api/comandas`, `GET /api/comandas/{id}`, `POST .../items`, `.../payments`, `.../close`, `.../cancel` | D R | comanda; item: `kind` = `service`, `product`, `package`, `discount` (`value` ou `percent`), `tip` (`value` + `barber_id`); `cover` = `none`, `package`, `subscription` |
| `POST /api/comandas/{id}/items/{item}/reverse`, `.../payments/{pag}/reverse` | D R (comanda fechada: D) | estorno |
| `GET/POST /api/products`, `PUT/DELETE /api/products/{id}`, `GET /api/products/low-stock` | leitura D R (custo só D); cadastro D | produtos com `stock` e `low_stock` |
| `GET/POST /api/products/{id}/movements` | D (R: só `internal`) | movimentação: `purchase`, `internal`, `adjust` |
| `GET/PUT /api/services/{id}/consumption` | leitura D R; alteração D | o que cada serviço consome |
| `GET/POST /api/package-plans`, `PUT/DELETE .../{id}` | leitura D R; cadastro D | pacotes à venda |
| `GET /api/customers/{id}/balance` | D R | saldo de pacotes e assinaturas |
| `GET/POST /api/subscription-plans`, `PUT/DELETE .../{id}` | leitura D R; cadastro D | planos do clube |
| `GET/POST /api/subscriptions`, `POST /api/subscriptions/{id}/cancel` | D R | assinantes |
| `GET /api/subscriptions/report` | D | ativas, atrasadas, canceladas e MRR |
| `GET /api/charges`, `POST /api/charges/{id}/confirm`, `.../resend` (D R), `.../cancel` (D) | | cobranças de mensalidade e de pacote |
| `GET/POST /api/waitlist`, `DELETE /api/waitlist/{id}` | D R | lista de espera |
| `GET /api/sync/pull?cursor=&limit=`, `POST /api/sync/push` | todos (filtrado por papel) | sincronização do app offline |
| `PUT /api/shop` | D | `deposit_mode`, `deposit_value`, `deposit_expire_minutes`, `deposit_refund_hours`, `waitlist_hold_minutes` |

Mudam também: `GET /api/finance/commissions` (D e P, este só com a própria linha; ganhou `tips` e `product_commission`), `GET /api/finance/summary` e o CSV (incluem comandas, pacotes, mensalidades e sinais retidos; gorjeta não é faturamento) e `POST /api/appointments` (`use_balance`, `require_deposit`).

## WhatsApp de verdade no seu PC (Docker + Evolution API)

Roda tudo localmente (Postgres, Redis, Evolution API v2.3.7 e backend) para testar com um WhatsApp real. Use um **número de teste** (chip da barbearia ou um chip só para isso), nunca o seu número pessoal.

Precisa de Docker com o plugin `docker compose` v2 e o usuário no grupo `docker`.

1. Crie o `.env` com segredos aleatórios (o `.env` está no `.gitignore` e nunca vai para o GitHub):
   ```bash
   cp .env.example .env
   for v in POSTGRES_PASSWORD EVOLUTION_API_KEY JWT_SECRET WEBHOOK_SECRET SETUP_TOKEN; do
     sed -i "s|^$v=.*|$v=$(openssl rand -hex 24)|" .env
   done
   sed -i 's|^EVOLUTION_PUBLIC_URL=.*|EVOLUTION_PUBLIC_URL=http://localhost:8080|; s|^DEV_MODE=.*|DEV_MODE=true|' .env
   chmod 600 .env
   ```
2. Suba tudo. O backend do Docker fica em http://localhost:8002 (`BACKEND_PORT` no `.env`), então não briga com um `uvicorn` local na 8000:
   ```bash
   scripts/whatsapp.sh up        # docker compose up -d --build --wait
   docker compose exec backend python -m app.seed
   ```
   O backend só sobe depois que o Postgres e a Evolution estão saudáveis (healthchecks) e aplica as migrações sozinho.
3. Gere o QR Code e leia com o celular do número de teste (**Aparelhos conectados > Conectar aparelho**):
   ```bash
   scripts/whatsapp.sh qr        # salva qrcode.png na raiz do projeto (expira em ~40 s; rode de novo se precisar)
   scripts/whatsapp.sh status    # espere "state": "open"
   ```
   Ou pelo app: **Mais > Conexão do WhatsApp** (detalhes em [Conectar o WhatsApp pelo app](#conectar-o-whatsapp-pelo-app)).
4. No app (Configurações) ou em `PUT /api/shop`, coloque em `owner_phone` o WhatsApp do dono, **diferente** do número conectado.
5. De outro celular, mande "oi" para o número conectado e acompanhe com `scripts/whatsapp.sh logs`.

Como as peças se falam (rede interna do Docker):

- Backend → Evolution: `http://evolution:8080` (header `apikey` = `EVOLUTION_API_KEY`).
- Evolution → backend: webhook `http://backend:8000/webhook/evolution` com o cabeçalho `X-Webhook-Secret`, evento `MESSAGES_UPSERT`, registrado automaticamente quando a instância é criada pelo `qr`. Cada barbearia tem o próprio secret (`shops.webhook_secret`, gerado no cadastro); o `WEBHOOK_SECRET` do `.env` só vale para barbearias sem secret próprio. O secret nunca vai na URL (que aparece em logs).
- No seu PC o backend fica em `localhost:${BACKEND_PORT}` (padrão 8002); dentro do Docker ele continua em `backend:8000`. No app, use `http://IP_DO_PC:8002` no login.
- A porta 8080 da Evolution só fica aberta em `127.0.0.1` (manager em http://localhost:8080/manager, com a `EVOLUTION_API_KEY`).

### Conectar o WhatsApp pelo app

Em **Mais > Conexão do WhatsApp** (o app precisa estar logado em `http://IP_DO_PC:8002`, o backend do Docker; um `uvicorn` local na 8000 sem `EVOLUTION_URL` fica em **modo simulação** e não gera QR Code):

O status atualiza a cada 3 s enquanto a tela está aberta. A tela tem duas abas:

- **QR Code:** toque em **Gerar QR Code** e, no celular do número da barbearia, abra **WhatsApp > Aparelhos conectados > Conectar aparelho** e leia o código. Ele vale cerca de 40 s; quando vencer, toque em **Gerar novo QR Code**. O app consulta o status a cada 3 s e mostra **Conectado** sozinho.
- **Código de pareamento** (sem outro aparelho para ler o QR Code): digite o número do bot com DDD e toque em **Gerar código**. O código aparece grande, com o botão **Copiar código** e o passo a passo. No celular do bot: **WhatsApp > Aparelhos conectados > Conectar aparelho > Conectar com número de telefone** e digite o código de 8 caracteres.
- **Desconectar WhatsApp** aparece quando está conectado (pede confirmação). O bot para de responder até conectar de novo.

Se não der para gerar, o app mostra o motivo (já conectado, modo simulação ou o erro da Evolution).

Rotas usadas (todas com login):

| Rota | O que faz |
|---|---|
| `GET /api/whatsapp/status` | `{instance, state}`: `open`, `connecting`, `close`, `nao_criada`, `simulacao` ou `erro` |
| `POST /api/whatsapp/connect` | Cria a instância (com o webhook) se não existir; se estiver travada ou com o QR Code vencido, reinicia a sessão. Devolve `{state, qrcode, pairing_code, message}`; `qrcode` vem como `data:image/png;base64,...` ou `null`, e `message` explica quando não há QR Code |
| `POST /api/whatsapp/pairing-code` | Corpo `{"number": "31999998888"}`. Mesmo formato, com `pairing_code` preenchido |
| `POST /api/whatsapp/disconnect` | Faz logout da instância na Evolution |

Falhas da Evolution (fora do ar, `apikey` errada, erro interno) voltam como HTTP 502 com a mensagem em português; o detalhe técnico fica em `docker compose logs backend`.

Comandos do `scripts/whatsapp.sh`: `up`, `down`, `logs [serviço]`, `qr`, `status` e `reset-instance` (desconecta e apaga a instância na Evolution para conectar outro número; pede confirmação e não mexe nos dados do BarberBot). `qr` e `status` usam o login da demo; para outra conta, defina `ADMIN_EMAIL` e `ADMIN_PASSWORD`.

Se a mensagem não chegar:

- `docker compose logs evolution | grep -i webhook`: erros de envio do webhook.
- `curl -s localhost:8080/webhook/find/barbearia-demo -H "apikey: $EVOLUTION_API_KEY"`: confira URL, `enabled: true` e o evento `MESSAGES_UPSERT`.
- `403 secret inválido` nos logs do backend: o `WEBHOOK_SECRET` mudou depois de a instância ser criada. Rode `reset-instance` e `qr` de novo.
- Contatos com privacidade de número (LID): a Evolution entrega o número real em `remoteJidAlt`. Se vier só o `@lid`, o backend ignora a mensagem e registra um aviso no log.

## Atendimento com IA (Google Gemini)

Com a IA ligada, o cliente escreve do jeito dele ("quero cortar cabelo e barba amanhã depois das 17h com o João", "vcs abrem sábado?", "preciso desmarcar") e o bot entende, consulta o sistema e responde. **A IA só interpreta e conversa:** horários livres, preços e regras (expediente, bloqueios, antecedência, prazo de cancelamento, cliente bloqueado ou em aprovação, conflitos entre clientes) vêm do código que já existe, e nada é gravado sem o cliente confirmar.

Código em `backend/app/ai/`: `provider.py` (interface), `gemini.py` (SDK oficial `google-genai`, function calling manual), `fake.py` (provedor roteirizado dos testes), `tools.py` (ferramentas), `agent.py` (loop), `prompts.py` (instruções) e `usage.py` (limites e uso). Trocar de provedor = novo adaptador + `AI_PROVIDER` no `.env`.

**Modo híbrido.** O menu numerado continua igual:

- `menu`, `0`, `voltar` → menu clássico; `atendente` → chama a equipe e pausa o bot.
- Números, respostas de confirmação (`1`, `sim`, `2`, `3`, `não`), lembrete, pesquisa de satisfação e o nome no fim do agendamento → fluxo atual, sem gastar IA. Atendimento humano pausado → bot em silêncio.
- Qualquer outro texto, com a IA ligada para a barbearia → agente de IA.
- Se a IA falhar (erro, cota 429 nos dois modelos, tempo esgotado, resposta inválida) → menu clássico, e o erro vai para o log. O cliente nunca fica sem resposta.
- O bot do dono e dos barbeiros continua só com menu.

**Ferramentas do agente:** `get_business_info`, `list_services`, `list_professionals`, `find_free_slots` (no máximo 8 horários, com filtro de dia e período), `get_my_appointments`, `propose_booking`, `propose_cancel`, `propose_reschedule`, `set_customer_name`, `send_pix` e `talk_to_human`. As `propose_*` não gravam: o sistema envia o resumo padrão ("1 - Confirmar / 2 - Escolher outro / 3 - Desistir") e o `1` passa pelo mesmo caminho do menu (`_do_book`), com os mesmos avisos. Todas agem só sobre o cliente do número da conversa; cliente bloqueado recebe a mesma resposta neutra de hoje; horários proibidos por conflito não aparecem.

**Histórico:** `conversation_messages` guarda as mensagens (da IA e do menu) que entram como contexto (`AI_HISTORY_MESSAGES`, padrão 12) e é apagada depois de 30 dias pela rotina de minuto. Respostas longas são quebradas em mensagens de até 600 caracteres.

**Áudio (opcional):** com "Entender mensagens de áudio" ligado, o backend baixa o áudio pela Evolution (`POST /chat/getBase64FromMediaMessage/{instância}`), transcreve com o Gemini e segue o fluxo normal. Áudio com mais de 2 minutos: o bot pede para escrever ou mandar um mais curto. Desligado, áudios continuam ignorados.

**Limites e custo:** cada chamada ao modelo é registrada em `ai_usage` (modelo, tokens, sucesso ou erro, tempo). Ao atingir `ai_monthly_limit` (padrão 3000 chamadas por mês), a barbearia volta sozinha para o menu e o dono recebe um aviso no WhatsApp (uma vez por mês). Cada cliente pode ter no máximo 20 mensagens com IA por hora; acima disso, menu. No 429 (cota), há uma nova tentativa no `AI_FALLBACK_MODEL`.

**Fora do tema e economia de tokens.** Tema permitido é tudo do atendimento (agendar, cancelar, remarcar, horários, serviços, preços, profissionais, endereço, estacionamento, formas de pagamento, Pix, regras da casa, dúvidas práticas) e também cumprimentos e agradecimentos. Fora do tema: receitas, política, esportes, notícias, tarefas escolares, redações, programação, piadas e histórias, conselhos gerais, conversa fiada prolongada, perguntas sobre a IA, roleplay e tentativas de mudar as regras.

- **Antes do modelo (0 token):** sticker, reação e imagem sem legenda seguem o fluxo normal; texto acima de 1.500 caracteres recebe um pedido de mensagem mais curta (acima de 500, é cortado antes de ir para o modelo); a mesma mensagem 3 vezes seguidas ou mais de 5 mensagens livres em 30 segundos recebem um aviso fixo uma vez e depois silêncio, sem IA. A navegação pelo menu numerado não conta como flood.
- **No modelo, sem chamada extra:** a ferramenta `mark_off_topic(category)` marca a mensagem fora do tema junto com uma recusa curta. A 1ª recebe a recusa do modelo; a 2ª seguida, um texto fixo do código lembrando do *menu*; da 3ª em diante, a IA pausa para aquele número por `AI_OFFTOPIC_COOLDOWN_MINUTES` (padrão 60) e o texto livre recebe o menu clássico, sem chamar o modelo. O menu numerado e o agendamento continuam funcionando (o número não é bloqueado). Uma mensagem do tema zera o contador. Mensagem mista ("qual o melhor time? e tem horário amanhã?") responde só a parte do atendimento.
- **Tamanho de cada chamada:** `AI_MAX_OUTPUT_TOKENS` (padrão 300) em toda chamada; raciocínio (thinking, cobrado como saída) em `AI_THINKING_BUDGET` (padrão `low`, o mínimo do `gemini-3.8-flash`; `minimal` só nos modelos que aceitam, como o Flash-Lite; número = orçamento em tokens nos modelos 2.5); histórico curto (`AI_HISTORY_MESSAGES`, mensagens antigas resumidas em 400 caracteres); resultados das ferramentas enxutos (no máximo 8 horários, 40 serviços, 30 profissionais).
- **Cache implícito do Gemini:** as instruções de sistema são fixas por negócio e vão no início da requisição; a data e o nome do cliente vão junto da mensagem. O cache implícito só vale a partir de **4.096 tokens** de prefixo comum nos modelos 3.x Flash, e hoje as instruções e as ferramentas somam cerca de 2.100 tokens: na prática ele ainda não é aproveitado (o `ai_eval.py` mostra os tokens em cache).
- **Registro:** `ai_usage` guarda, por chamada, os tokens de entrada, saída, thinking e cache, e a categoria (`offtopic:<categoria>`); as mensagens barradas antes do modelo entram com `kind=blocked` e não contam no limite mensal. O app mostra quantas mensagens fora do tema foram barradas no mês e uma estimativa de tokens economizados (barradas x média de tokens por chamada).

**No app:** Mais > Configurações > **Atendimento com IA**: ligar ou desligar, transcrição de áudio, uso do mês e o aviso de modo de teste. API: `GET/PUT /api/ai/settings` (`ai_enabled`, `ai_audio_enabled`) e `GET /api/ai/usage?month=AAAA-MM`. O `/dev/simulate` usa a IA quando ela está ligada para a barbearia.

### Configurar (desenvolvimento, plano gratuito)

1. Gere a chave em [Google AI Studio](https://aistudio.google.com/apikey) (botão "Create API key").
2. Coloque em `GEMINI_API_KEY=` no `.env` da raiz (backend do Docker) e no `backend/.env` (backend local e scripts). Os dois estão no `.gitignore`; nunca coloque a chave em código, log ou arquivo versionado.
3. `AI_TIER=free`: a IA só funciona para barbearias com `ai_allow_free_tier=true`, ligado pelo `python -m app.seed` apenas na Barbearia Demo. **No plano gratuito o Google pode usar o conteúdo das conversas para melhorar os produtos dele:** use só dados fictícios. O backend registra um aviso no log ao iniciar nesse modo.
4. Ligue a IA no app (Mais > Configurações > Atendimento com IA) e converse pelo `/dev/simulate` ou pelo WhatsApp de teste.
5. Avaliação com o Gemini de verdade (não envia nada pelo WhatsApp e desfaz tudo no banco):
   ```bash
   cd backend
   python scripts/ai_eval.py              # ~30 mensagens: pedidos completos e incompletos, gírias, datas relativas,
                                          # preços, cancelamento, remarcação, fora do assunto e tentativas de manipulação
   python scripts/ai_eval.py --only 1 19  # só alguns cenários
   python scripts/ai_eval.py --sleep 8    # mais pausa entre mensagens se bater no limite por minuto do plano gratuito
   python scripts/ai_eval.py --groups     # só os grupos FORA DO TEMA, DENTRO DO TEMA e MISTO, com acertos por grupo,
                                          # tokens (entrada, saída, thinking, cache) e custo estimado por mil mensagens
   ```
   O custo usa os preços do `gemini-3.8-flash` no plano pago até 31/12/2026 (US$ 0,75 entrada e US$ 3,75 saída por 1 milhão de tokens; ajuste com `--price-in`, `--price-out` e `--price-cached`).

Modelos padrão (confira os nomes atuais em https://ai.google.dev/gemini-api/docs/models): `AI_MODEL=gemini-3.8-flash` e `AI_FALLBACK_MODEL=gemini-3.5-flash-lite`.

### Produção (plano pago)

1. No [Google AI Studio](https://aistudio.google.com) ou no Google Cloud Console, **ative o faturamento** no projeto da chave (no plano pago o Google não usa o conteúdo para treinar os modelos).
2. Defina um **limite de gasto** (orçamento e alertas no Cloud Billing) para o projeto.
3. No `.env` do servidor: `AI_TIER=paid` e a chave do projeto com faturamento. Reinicie o backend (`docker compose up -d --build backend`).
4. Ligue a IA por barbearia no app. Ajuste o limite mensal de cada uma direto no banco (`shops.ai_monthly_limit`) se precisar.
5. Atualize a política de privacidade (provedor de IA e uso dos dados; ver `landing/privacidade.html`, que já descreve o banco criptografado do celular e o apagamento ao sair).

## Comprovante de Pix (pré-conferência com IA)

Comprovante **não prova** que o dinheiro caiu (pode ser editado ou reaproveitado). O sistema lê e confere para poupar trabalho do dono, mas quem confirma é ele, olhando o extrato. A única exceção é a confirmação automática opcional, desligada por padrão.

1. **Recebimento.** O cliente manda imagem (JPG, PNG, WEBP) ou PDF numa conversa com pagamento pendente: Pix de agendamento ou de sinal, pacote ou mensalidade (comanda não gera Pix pelo WhatsApp, é paga no balcão). O backend baixa a mídia pela Evolution API: se o webhook já trouxer o arquivo (`base64`), usa direto; senão chama `POST /chat/getBase64FromMediaMessage/{instância}` com a mensagem inteira (no modo QR Code, `key` + `message`; no modo oficial/Cloud API, também `messageType`, que a Evolution usa para baixar a mídia da Graph API). Limites: até 5 MB, tipo conferido pelos bytes (não pela extensão), PDF de até 2 páginas. Fora disso, o bot pede uma foto do comprovante. Sem pagamento pendente, a IA não é chamada: o bot diz que não há pagamento em aberto e mostra o menu. O cliente recebe na hora "Recebi seu comprovante! A barbearia vai conferir e te aviso assim que confirmar." Com mais de um pendente, o valor lido escolhe; se ainda houver dúvida, o bot pergunta a qual pagamento ele se refere (lista numerada).
2. **Leitura.** `app/services/receipt_reader.py` manda o arquivo ao Gemini (mesma chave, mesmo limite mensal e registro em `ai_usage` com a categoria `comprovante`) pedindo saída estruturada (`response_mime_type=application/json` + `response_json_schema`). Campos: valor, data e hora, recebedor (nome, chave, banco), pagador (nome, banco), ID da transação (E2E: `E` + ISPB + data e hora + 11 caracteres, 32 no total), tipo (comprovante, Pix agendado ou outro) e confiança. O texto da imagem é tratado como dado, nunca como instrução, e o JSON é validado no código. Falhou = "ilegível", e vai para a conferência manual. Limite de 5 comprovantes por cliente por dia. A leitura não depende do atendimento com IA estar ligado, só da chave e do limite.
3. **Conferências (no código).** Valor igual ao cobrado (tolerância zero); recebedor (nome parecido com o do Pix cadastrado, sem acentos e maiúsculas, ou chave compatível, inclusive mascarada como `***.456.789-**`); data depois da geração do Pix e no máximo 48 h antes do envio; ID da transação nunca usado em outro pagamento da plataforma (índice único); tipo (Pix agendado gera alerta próprio); o mesmo arquivo reenviado é reconhecido pelo hash, sem nova leitura. Resultado: **confere**, **divergente** (com a lista do que falhou) ou **ilegível**.
4. **Para o dono.** Alerta no WhatsApp ("Comprovante confere: R$ 65,00 para Barbearia Demo às 14:32 (ID final ...A1B2). Confira no extrato e responda 1 para confirmar." ou "Atenção no comprovante de Carlos: valor R$ 30,00, cobrado R$ 65,00."). Responder **1** confirma (o fluxo de sempre: cliente avisado, horário pago, sinal, pacote ou mensalidade liberados) e **2** recusa (o cliente recebe uma mensagem neutra pedindo para conferir o pagamento ou falar com a barbearia). No app, em Pagamentos Pix e em Clube de assinatura > Cobranças: miniatura (tela cheia ao tocar), selo verde/laranja/cinza, dados lidos, a lista de conferências e Confirmar/Recusar; os que conferem ficam no topo.
5. **Confirmação automática (opcional).** Configurações > Pix: "Confirmar automaticamente comprovantes que conferem até R$ X" (desligada; teto de R$ 100). Só confirma se o resultado for "confere", a confiança for de pelo menos 0,9, o valor estiver dentro do limite, o cliente nunca tiver tido comprovante divergente, recusado ou desfeito e tiver no máximo 3 confirmações automáticas no mês. Cada uma fica marcada como "automática pelo comprovante", vai para o resumo diário do dono e pode ser desfeita (app ou "2" no WhatsApp).
6. **Armazenamento e LGPD.** Arquivo em `RECEIPTS_DIR` (padrão `backend/data/receipts`, no Docker o volume `receipts`), fora de pastas públicas, com nome aleatório, permissão só do dono do processo e download só autenticado para dono e recepção da própria loja. Depois de `RECEIPT_RETENTION_DAYS` (90) o arquivo é apagado pela rotina automática; ficam os dados lidos, o resultado e o ID da transação. Os dados do comprovante não vão para o log. Comprovantes antigos (guardados no banco antes desta versão) continuam abrindo e também são apagados no prazo.
7. **Confirmação pelo banco (futuro).** `app/services/verifiers.py` tem a interface `PaymentVerifier` (`ReceiptVerifier` hoje; `BankPixVerifier` e gateway depois). O que falta está no [ROADMAP-CRM.md](ROADMAP-CRM.md#confirmação-real-do-pix-pelo-banco-próximo-passo-só-a-interface).

Testar sem WhatsApp: `POST /dev/simulate-receipt` (com `X-Setup-Token`) recebe `{"phone": "...", "base64": "<arquivo>", "mimetype": "image/png"}` e devolve as mensagens enviadas e o resultado. Comprovantes **fictícios** para teste em `backend/tests/fixtures/receipts/` (gerados com Pillow por `generate.py`; nunca use comprovantes reais). Avaliação com o Gemini de verdade:

```bash
cd backend
python scripts/receipt_eval.py           # gera as imagens com o horário atual e imprime campos, conferências e custo
python scripts/receipt_eval.py --only correto injecao --sleep 6
```

Ele usa um SQLite temporário (não mexe no banco de desenvolvimento) e não envia nada pelo WhatsApp.

## Colocar no ar (VPS)

1. VPS com Docker (2 vCPU e 4 GB bastam para várias barbearias) e um domínio apontando para ela (ex.: `api.suabarbearia.com.br`).
2. Crie o `.env` como no passo 1 acima, com `DEV_MODE=false` e `EVOLUTION_PUBLIC_URL=https://api.suabarbearia.com.br` (o domínio, não `localhost`). Com `DEV_MODE=false` a API **não sobe** com segredos de exemplo: `JWT_SECRET` com 32+ caracteres e `WEBHOOK_SECRET` e `SETUP_TOKEN` com 16+ (o `openssl rand -hex 24` do passo 1 gera 48).
3. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait`. O arquivo de produção publica só o backend, em `127.0.0.1` (o Caddy faz o HTTPS na frente), tira as portas do Postgres e da Evolution, fixa `DEV_MODE=false` e liga o Redis no limite de tentativas de login (`REDIS_URL`). O backend aplica as migrações (`alembic upgrade head`) toda vez que sobe. Ver também o checklist de produção em `SECURITY-REPORT.md`.
4. HTTPS com o Caddy na frente do backend, na porta `BACKEND_PORT` (padrão 8002; certificado automático). `/etc/caddy/Caddyfile`:
   ```
   api.suabarbearia.com.br {
       reverse_proxy localhost:8002
   }
   ```
   No firewall, libere só 22, 80 e 443. Com o `docker-compose.prod.yml`, a Evolution fica sem porta publicada: para usar o manager, suba temporariamente só com o `docker-compose.yml` (porta em `127.0.0.1:8080`) e faça um túnel (`ssh -L 8080:localhost:8080 usuario@vps`).

**Sessões:** o token do app vale 7 dias e é renovado sozinho a cada abertura (`POST /api/auth/refresh`). Em Mais > **Sair de todos os aparelhos** (`POST /api/auth/logout-all`) o dono invalida todos os tokens emitidos (celular perdido, senha vista por alguém). Depois de 5 senhas erradas no mesmo e-mail (ou 20 no mesmo IP), o login fica bloqueado por 15 minutos.
5. Cadastre a barbearia (uma vez por cliente):
   ```bash
   curl -X POST https://api.suabarbearia.com.br/api/auth/register -H "Content-Type: application/json" -d '{
     "setup_token": "o SETUP_TOKEN do .env",
     "shop_name": "Barbearia do Zé", "owner_name": "Zé",
     "email": "ze@email.com", "password": "senha-forte", "owner_phone": "31999998888"
   }'
   ```
6. No app (apontando para `https://api.suabarbearia.com.br`): entre com o e-mail e a senha, cadastre serviços e barbeiros, configure o Pix e, em **Mais > Conexão do WhatsApp**, gere o QR Code e leia com o celular da barbearia.

Builds Android de produção bloqueiam `http://`, por isso o domínio com HTTPS é obrigatório para o app.

## Versão web do app (app.[DOMINIO])

O app admin roda também no navegador, com o **mesmo código** (react-native-web). No computador (tela a partir de
900 px) ganha menu lateral fixo com o logo, conteúdo mais largo, agenda com uma coluna por profissional, tabelas com
busca e ordenação (produtos, clientes, assinantes, equipe), a comanda com o painel de pagamento ao lado e atalhos de
teclado: **N** novo agendamento, **C** abrir comanda, **B** buscar cliente (fora de campos de texto). No celular,
abas embaixo, como no app.

**Gerar e publicar:**

```bash
cd mobile
npx expo export --platform web            # gera mobile/dist (index.html, manifest, ícones, JS)
rsync -a --delete dist/ usuario@vps:/srv/syncserv-web/
```

No servidor, use o bloco de `deploy/Caddyfile.app` (troque `[DOMINIO]`): o Caddy serve o app em `app.[DOMINIO]`,
devolve o `index.html` para qualquer rota (app de página única), encaminha `/api/*` para o backend
(`127.0.0.1:8002`) e aplica o CSP e os cabeçalhos de segurança (HSTS, `nosniff`, `X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy`). Com o app e a API no mesmo endereço não é preciso CORS. O título da aba é "SyncServ" e o
`manifest.webmanifest` permite instalar como app (PWA) com os ícones do kit da marca.

**Segurança da sessão no navegador:** o login web recebe um token de acesso de **15 minutos**, guardado só em
memória, e um **refresh token** de 12 horas, guardado no `sessionStorage` da aba (nunca no `localStorage`). O app
renova o token sozinho (`POST /api/auth/token`); fechar a aba encerra a sessão; "Sair de todos os aparelhos",
trocar a senha ou desativar a pessoa invalidam o refresh token. O `/api/auth/refresh` mantém o token web curto.

**Só online:** sem internet, a versão web mostra o aviso "Sem conexão" e bloqueia as alterações. Nada de dados de
clientes fica no navegador (o modo offline é só do app do celular).

**CSP:** o Caddyfile não libera `'unsafe-inline'`. Os estilos do react-native-web e as fontes entram pelo CSSOM
(`src/webFonts.web.js`), e o estilo base fica em `public/web.css`. Não coloque `<style>` nem `<script>` inline no
`public/index.html`: o navegador bloqueia (e o teste de segurança acusa).

Teste ponta a ponta: `cd mobile && npm run test:web`. Precisa do Playwright para Python:
`pip install playwright && playwright install chromium`. O comando sobe um backend descartável (SQLite temporário com
os dados fictícios do `seed_mock`, porta 8010), gera o export e o serve com o mesmo CSP do Caddyfile. Confere login,
papéis, armazenamento, sessão, modo sem internet, fontes e ausência de erros de console ou bloqueios do CSP, em 375
e 1440 px.

## Modo offline do app (celular)

O app do celular funciona sem internet e sincroniza sozinho. A versão web continua só online.

**Onde ficam os dados:** num SQLite do aparelho criptografado com **SQLCipher**: o plugin `expo-sqlite` vem com
`useSQLCipher: true` no `app.json`. A chave é aleatória (256 bits), gerada no aparelho e guardada no SecureStore
(Keychain/Keystore, `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`). O arquivo e a chave são apagados quando:
- a pessoa sai da conta;
- outra pessoa (ou outro papel) entra no aparelho;
- o servidor recusa o token (inclusive "Sair de todos os aparelhos").

**O que vai para o aparelho:** a janela que o servidor manda, já filtrada por papel:
- agenda de 30 dias para trás a 60 para frente;
- clientes, serviços, profissionais e bloqueios;
- produtos e o estoque (movimentos);
- pacotes, assinaturas e os saldos;
- comandas dos últimos 30 dias.

O profissional recebe só a própria agenda e os clientes que atendeu. Uma vez por dia o pull recomeça do zero, porque
a janela anda com o calendário.

**O que funciona offline:**
- agendar, remarcar, check-in, concluir, falta e cancelar;
- editar nome e observações do cliente;
- comanda inteira: abrir, lançar, desconto, gorjeta, receber, estornar, fechar e cancelar;
- movimentar o estoque;
- lista de espera;
- bloqueios.

Relatórios, financeiro, Pix, configurações, equipe e cadastros (serviços, produtos, planos) continuam precisando de
internet. O app avisa e não deixa a ação sair sem conexão.

**Como sincroniza:** cada alteração é gravada no aparelho junto com a operação da fila (outbox), na mesma
transação, com um `operation_id` (UUID).
- **Quando:** ao abrir o app, ao voltar para ele, quando a internet volta, a cada 2 minutos e logo depois de cada
  alteração. Também em segundo plano (`expo-background-task`, a cada ~15 min, quando o sistema deixar).
- **Falha de rede:** a próxima tentativa espera 5 s, 10 s, 20 s, e assim por diante até 5 min.
- **Envio e resposta:** a fila sai na ordem em que foi feita. O reenvio usa o mesmo `operation_id`, e o servidor
  devolve a resposta já gravada (nada se aplica duas vezes).
- **Com internet:** o app espera a resposta por alguns segundos. Conflito ou recusa aparecem na hora, na própria tela.

**Na tela:**
- **Avisos no topo:** a faixa "Sem conexão: suas alterações serão sincronizadas" mostra o número de pendências.
  Cada item ainda não confirmado tem o selo **A confirmar**.
- **Sincronização:** em *Mais › Sincronização e modo offline* ficam a última sincronização, a lista do que está
  pendente e o botão **Sincronizar agora**.
- **Atenção:** o que o servidor não aceitou, como horário ocupado enquanto o aparelho estava offline, é desfeito no
  aparelho e vai para **Precisa da sua atenção**, com "Agendar em outro horário".
- **WhatsApp:** agendamento feito offline fica "a confirmar". O cliente só recebe a mensagem depois que o servidor
  aceitar.

**Logs:** a sincronização registra só eventos e contagens, nunca nome, telefone ou outros dados de clientes.

**Build:** o Expo Go não traz o SQLCipher. Nele o modo offline fica desligado e o app funciona online, como a web.
- **Para testar o offline de verdade:** gere o APK com `npx eas-cli build -p android --profile apk`, ou rode
  `npx expo run:android`.
- **Só para mexer na interface:** `EXPO_PUBLIC_OFFLINE_PLAINTEXT=1 npx expo start` liga o modo offline no Expo Go
  sem criptografia, apenas em desenvolvimento e com dados fictícios.

**Código:**
- `mobile/src/offline/`:
  - `store.js`: banco e outbox;
  - `engine.js`: push, pull, conflitos e espera entre tentativas;
  - `shapes.js`: os formatos da API montados no aparelho;
  - `db.js`: SQLCipher;
  - `manager.js`: gatilhos.
- `mobile/src/repo.js`: o repositório. As telas usam sempre a mesma interface: `repo.local.js` no celular,
  `repo.remote.js` (API) na web.

**Testes:**
- `cd mobile && npm test` roda o Jest com o SQLite do Node, o mesmo SQL do aparelho. Cobre:
  - motor de sincronização: ordem, reenvio sem duplicar, conflito indo para a atenção, tombstones, apagar ao trocar
    de usuário, transação, espera entre tentativas, pull diário e nada de dados de clientes no log;
  - repositório de ponta a ponta: agenda e caixa offline sincronizando sem duplicar.
- Roteiro manual com modo avião: `mobile/tests/OFFLINE-TESTE-MANUAL.md`.

## Marca e temas (SyncServ)

**Logo:** só os arquivos de `branding/syncserv-logo-kit` (ver o `LEIA-ME.md` do kit), sem redesenhar.

- Ícone do app (`mobile/assets/icon.png`), ícone adaptativo do Android (`adaptive-icon.png` sobre `#0F172A`), splash (`splash-icon.png` sobre `#0F172A`, pelo plugin `expo-splash-screen`) e favicon do Expo web vêm de `png/app` e `png/web`. Não há ícone monocromático do Android (não foi gerado a partir do SVG branco).
- Dentro do app o logo é vetorial: `mobile/src/brand/logoData.js` é gerado a partir dos SVG do kit (mesmos paths e cores) e `mobile/src/brand/Logo.js` exporta `Symbol` (sem `color`, o degradê azul → verde; com `color`, o símbolo inteiro naquela cor), `Wordmark` (horizontal) e `LogoVertical`. Dentro do app importe como `{ Symbol as BrandSymbol }`, para não esconder o `Symbol` do JavaScript.
- Onde aparece: login e splash interna (logo vertical), header da aba Hoje e menu Mais (símbolo na cor do segmento + nome do negócio), estados vazios e tela Sobre (símbolo em cor neutra).
- `branding/web-publico` guarda a imagem de prévia (`og-image-1200x630.png`) e os favicons para a futura landing page; o app não usa.

**Segmento do negócio:** cada negócio tem `niche` e `theme_mode`, escolhidos em **Mais > Configurações > Aparência** (cards com o símbolo na cor de cada segmento). A troca vale na hora. `theme_mode` "Automático" usa o modo do segmento; "Escuro" ou "Claro" forçam o modo e derivam as superfícies, mantendo a cor do segmento.

| Segmento | Modo | Fundo | Destaque (accent) | Termos |
| --- | --- | --- | --- | --- |
| Barbearia (`barbershop`) | escuro | `#121212` | âmbar `#F59E0B` | barbeiro, cliente, atendimento |
| Salão de beleza e estética (`beauty`) | claro | `#FAF5F5` | rosa `#EC4899` | profissional, cliente, atendimento |
| Pet shop (`petshop`) | claro | `#F8FAFC` | turquesa `#06B6D4` | tosador, tutor, atendimento |
| Clínica e consultório (`clinic`) | claro | `#F0FDFA` | azul `#0284C7` | profissional, paciente, consulta |
| Estúdio fitness (`fitness`) | escuro | `#18181B` | verde-limão `#84CC16` | professor, aluno, aula |

A marca-base SyncServ (login) usa fundo `#0F172A`, superfícies `#1E293B` e `#273449`, texto `#F8FAFC` e `#94A3B8`, primária `#0284C7` e secundária `#22C55E`.

**Design system (`mobile/src/theme.js`):** tokens por tema (`background`, `surface`, `surfaceElevated`, `border`, `divider`, `text`, `textMuted`, `accent`, `accentPressed`, `accentFill`, `onAccent`, `accentText`), cores de status iguais em todos os temas (Pix confirmado `#22C55E`, Pix pendente `#F97316`, erro e cancelado `#EF4444`, informação `#0284C7`; badges com fundo a 15% e texto num tom da mesma família que passe no contraste), fonte Plus Jakarta Sans (escala 32/24/20/17/15/13), espaçamento em múltiplos de 4, raios 10/14/20 e alvo de toque de 48 px. O `ThemeProvider` (`src/ThemeProvider.js`) lê o segmento e o modo do negócio logado e expõe `useTheme()` com os tokens, os estilos e o vocabulário (`src/vocab.js`); nenhuma tela usa cor fixa.

Contraste (WCAG AA): `cd mobile && npm test` confere 4.5:1 para textos e 3:1 para bordas e ícones em todos os temas. Ajustes que o teste exigiu:

- O azul `#0284C7` não chega a 4.5:1 com texto branco nem escuro, então os botões principais da clínica e da marca-base usam `accentFill` `#0369A1`; o `#0284C7` continua no símbolo, nas barras e na seleção.
- Nos temas claros, o accent como texto ou ícone usa `accentText` mais escuro (rosa `#BE185D`, turquesa `#0E7490`, azul `#0369A1`, âmbar `#92400E`, limão `#4D7C0F`); botões rosa, turquesa, âmbar e limão usam texto escuro.
- A "borda" `#334155` da marca é o `divider` (separadores); contornos de campos e botões usam `border`, que passa em 3:1.

## App admin

```bash
cd mobile
npm install
npx expo start          # abre no celular pelo app Expo Go (sem o modo offline: ver "Modo offline do app")
npm test                # testes do app (temas, papéis, teclado, sincronização offline)
```

Telas:

- **Hoje:** símbolo na cor do segmento e nome do negócio; banner laranja quando há Pix aguardando confirmação (abre a lista) e banner de pedidos para aprovar; cards de resumo (atendimentos, faturamento previsto, próximo cliente, horários livres); próximos atendimentos. Puxar para atualizar e atualização automática a cada 60 s.
- **Agenda:** Timeline, Profissionais e Mês (ver "Agenda" acima). Tocar num horário vago abre o **agendamento rápido** (painel que sobe de baixo) com horário e profissional preenchidos: busca ou cadastro rápido do cliente, serviço com duração e preço (só os que o profissional faz), aviso quando o serviço não cabe no espaço livre, avisos de acesso restrito e de clientes incompatíveis no dia, e **Agendar mesmo assim** quando a API recusa por conflito. Segurar um atendimento abre as ações rápidas.
- **Cards de atendimento:** horário grande, nome em negrito, serviço, profissional, valor, status, Pix (e "disse que pagou") e o botão **Confirmar Pix** quando o Pix está pendente.
- **Pix:** pendentes primeiro os que o cliente disse que pagou, com valor em destaque, há quanto tempo está pendente, comprovante (imagem ampliável ou PDF) e botões **Confirmar** e **Recusar**.
- **Ficha do cliente:** **Aprovação manual obrigatória** e **Bloqueado** (com motivo interno) e os chips **Incompatível com**.
- **Configurações:** seção **Aparência** (segmento e modo), dados do negócio, Pix e regras do bot, com o botão de salvar fixo no rodapé.
- **Login:** logo vertical, tema da marca-base; lembra o endereço do servidor e o e-mail.

Experiência: esqueletos enquanto carrega, estados vazios com ícone e ação, avisos curtos (toast) para sucesso e erro, alerta só para confirmar ações destrutivas, vibração nas ações importantes, máscaras de telefone e dinheiro, teclado certo em cada campo, rótulos de acessibilidade em botões só com ícone e textos que respeitam o tamanho de fonte do sistema.

APK para instalar direto no Android: `npx eas-cli build -p android --profile apk` (precisa de conta gratuita na Expo). Publicar na Play Store: perfil `production`.

## Configurações importantes (app > Configurações)

| Configuração | Padrão |
| --- | --- |
| Lembrete antes do horário | 120 min |
| Cliente pode cancelar até | 2 h antes |
| Pesquisa após o atendimento | 30 min |
| Intervalo entre horários | 30 min |
| Agenda aberta | 7 dias |
| Pix pendente expira | 12 h |
| Pedido para aprovar expira | 12 h (ou 1 h antes do horário) |
| Distância padrão entre clientes que não podem se encontrar | 240 min |
| Resumo diário | 8 h |
| Confirmar automaticamente comprovantes que conferem | desligado (teto de R$ 100) |

## Observações

- **Evolution API é não oficial.** Use o número da barbearia (não o pessoal do dono) e evite disparos em massa. Para migrar para a API oficial da Meta, só `backend/app/services/whatsapp.py` muda.
- O `owner_phone` deve ser o WhatsApp pessoal do dono, diferente do número conectado ao bot.
- Datas são guardadas no horário local da barbearia (`TIMEZONE`).
- Rode o backend com 1 worker: as rotinas automáticas rodam dentro do processo da API.
