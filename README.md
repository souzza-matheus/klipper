# BarberBot

Agendamento para barbearias pelo WhatsApp, com bot para o cliente, bot para o dono e app nativo de administração.

```
barberbot/
├── backend/            API em Python (FastAPI), bots, Pix, rotinas automáticas
├── mobile/             App admin em React Native (Expo)
├── docker-compose.yml  Postgres + Redis + Evolution API + backend
└── .env.example
```

## O que está pronto

**Bot do cliente:** agendar (serviço → barbeiro ou "tanto faz" → dia → horário → nome → confirmação), meus agendamentos (cancelar, remarcar, pagar), serviços e preços, barbeiros, horário e endereço, Pix antecipado, falar com atendente (pausa o bot), lembrete com confirmação de presença e pesquisa de satisfação de 1 a 5 com comentário.

**Bot do estabelecimento:** o número do dono (configurações) e os números dos barbeiros abrem um menu próprio: agenda de hoje e amanhã, horários livres de um dia, busca de cliente, Pix pendentes (confirmar), bloqueio rápido de horário, avaliações, resumo do dia e "testar como cliente". Barbeiro vê só a própria agenda.

**Alertas automáticos:** novo agendamento, cancelamento (com o horário que ficou livre), remarcação, "paguei" do cliente, avaliação baixa, pedido de atendente e resumo diário de manhã.

**App admin:** agenda por dia ou por mês e por barbeiro, novo agendamento manual, confirmar, concluir (com forma de pagamento e valor final), falta, remarcar, cancelar, enviar Pix, clientes com histórico, Pix pendentes, financeiro, serviços, barbeiros com expediente e comissões, bloqueios, avaliações, relatórios, configurações do bot e do Pix, conexão do WhatsApp por QR Code.

**Agenda do mês:** na aba Agenda, o seletor **Dia | Mês** mostra o calendário (seg a dom) com o número de atendimentos e uma barra de ocupação em cada dia. Ocupação = atendimentos ÷ capacidade do dia, onde a capacidade é o expediente dos barbeiros (menos os bloqueios) dividido pela duração média dos serviços ativos. Dias sem expediente ficam esmaecidos, dias com bloqueio têm um cadeado e hoje fica destacado. Tocar em um dia abre a visão Dia. Respeita o filtro de barbeiro.

**Forma de pagamento:** ao marcar um atendimento como concluído, o app pergunta como o cliente pagou (Pix, dinheiro, débito ou crédito) e permite ajustar o valor cobrado (desconto ou acréscimo). Se o cliente já pagou o Pix pelo bot, vem "Pix" marcado. O valor final é o que entra no faturamento e nas comissões.

**Gastos:** contas da barbearia por categoria (aluguel, energia, água, internet, produtos, equipamentos, manutenção, marketing, salários, impostos, outros), com vencimento, pagamento, forma de pagamento e barbeiro (opcional). Um gasto marcado como **"Repetir todo mês"** gera automaticamente a conta dos meses seguintes quando o mês é aberto (no app, no resumo ou no aviso diário), sem duplicar. Para parar de repetir, desligue a opção no gasto original. O resumo diário do dono no WhatsApp avisa as contas que vencem hoje ou já venceram.

**Financeiro (aba no app):** faturamento, gastos pagos, lucro e ticket médio do período (este mês, mês passado, 7 dias ou datas escolhidas), com a variação contra o período anterior de mesmo tamanho; gráfico de faturamento x gastos por dia; faturamento por barbeiro, serviço e forma de pagamento; gastos por categoria; exportação em CSV para o Excel (compartilhada pelo celular). Faturamento = atendimentos concluídos; gastos entram no dia em que foram pagos (regime de caixa); lucro = faturamento − gastos pagos.

**Comissões e repasses:** regras de quanto cada barbeiro repassa para a barbearia ou para um barbeiro padrinho (várias ao mesmo tempo, por serviço ou geral, com vigência; a soma não passa de 100%). O cálculo usa o valor cobrado em cada atendimento concluído e a regra vigente no dia dele. Mostra bruto, repasses, líquido, acertado e em aberto por barbeiro, registra acertos e avisa os barbeiros pelo WhatsApp. No app: **Financeiro > Comissões e repasses**; as regras de cada barbeiro também ficam em **Mais > Barbeiros > [barbeiro] > Comissões**.

**Pix:** gera o "copia e cola" (padrão do Banco Central) com a chave da própria barbearia. O dinheiro vai direto para a conta do dono; a confirmação é manual (app ou WhatsApp).

## Testar em 2 minutos (sem WhatsApp)

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                     # cria/atualiza as tabelas
python -m app.seed                       # cria a "Barbearia Demo"
uvicorn app.main:app --reload
```

Sem `EVOLUTION_URL`, o sistema roda em **modo simulação**: as mensagens aparecem no terminal. Converse com o bot pela documentação interativa em http://localhost:8000/docs, rota `POST /dev/simulate`:

```json
{ "phone": "31977776666", "text": "oi" }
```

- Número de cliente: qualquer um.
- Número do dono da demo: `31999990000`. Barbeiros: `31988880001` (João) e `31988880002` (Pedro).
- `POST /dev/run-jobs` roda na hora os lembretes, pesquisas e expiração de Pix.
- Login do app: `admin@demo.com` / `demo123`.

### Dados de teste (mock)

Para ver a agenda, os relatórios e as avaliações com movimento, popule a demo com dados fictícios:

```bash
cd backend
python -m app.seed_mock            # cria a demo (se preciso) e gera os dados
python -m app.seed_mock --reset    # apaga os dados mock e gera de novo
```

Gera 40 clientes, agendamentos de 30 dias atrás até 7 dias à frente (com concluídos, cancelados e faltas, e forma de pagamento nos concluídos), Pix, avaliações, 3 bloqueios futuros e os gastos de exemplo. O `--reset` apaga só clientes, agendamentos, pagamentos, avaliações, bloqueios, conversas, gastos e acertos da Barbearia Demo e gera tudo de novo; serviços, barbeiros, regras de comissão e o login admin continuam. As datas são relativas ao dia em que o script roda.

O `app.seed` já cria exemplos do financeiro: Pedro (barbeiro novo) repassa 40% para a barbearia e 10% para o João (padrinho), João repassa 30% para a barbearia; contas fixas recorrentes (aluguel, internet, luz, água, contador) e alguns gastos avulsos do mês, um deles vencido e outro vencendo hoje.

Testes automatizados: `cd backend && pytest` (Pix, agendamento completo, cancelamento, remarcação, menu do dono, lembrete, pesquisa, comissões, gastos e recorrência, resumo financeiro, CSV, agenda do mês e migrações).

## Banco de dados e migrações (Alembic)

O esquema do banco é controlado pelo Alembic (`backend/migrations`). A API não cria mais tabelas sozinha.

```bash
cd backend
alembic upgrade head                                   # aplica as migrações pendentes
alembic revision --autogenerate -m "o que mudou"      # depois de alterar app/models.py
```

- `0001` representa o esquema de antes do Alembic e `0002` adiciona a forma de pagamento nos atendimentos e a tabela de gastos.
- Bancos criados pela versão antiga (`create_all`) também funcionam: as migrações só criam as tabelas e colunas que faltam e depois passam a controlar o banco normalmente. Não é preciso apagar nada.
- No Docker, o container do backend roda `alembic upgrade head` antes de subir a API.
- A URL vem da mesma `DATABASE_URL` da API (ou `alembic -x url=sqlite:///outro.db upgrade head`).

Para recriar o banco de desenvolvimento do zero (SQLite):

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

## Colocar no ar (VPS)

1. VPS com Docker (2 vCPU e 4 GB bastam para várias barbearias).
2. `cp .env.example .env` e troque todos os valores.
3. `docker compose up -d --build`
   O backend aplica as migrações do banco (`alembic upgrade head`) toda vez que sobe.
4. Cadastre a barbearia (uma vez por cliente):
   ```bash
   curl -X POST http://SEU_SERVIDOR:8000/api/auth/register -H "Content-Type: application/json" -d '{
     "setup_token": "o SETUP_TOKEN do .env",
     "shop_name": "Barbearia do Zé", "owner_name": "Zé",
     "email": "ze@email.com", "password": "senha-forte", "owner_phone": "31999998888"
   }'
   ```
5. No app: entre com o e-mail e a senha, cadastre serviços e barbeiros, configure o Pix e, em **Mais > Conexão do WhatsApp**, gere o QR Code e leia com o celular da barbearia.

Para produção, coloque um proxy com HTTPS na frente (Caddy ou Nginx) e use o domínio no app. Builds Android de produção bloqueiam `http://` por padrão.

## App admin

```bash
cd mobile
npm install
npx expo start          # abre no celular pelo app Expo Go
```

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
| Resumo diário | 8 h |

## Observações

- **Evolution API é não oficial.** Use o número da barbearia (não o pessoal do dono) e evite disparos em massa. Para migrar para a API oficial da Meta, só `backend/app/services/whatsapp.py` muda.
- O `owner_phone` deve ser o WhatsApp pessoal do dono, diferente do número conectado ao bot.
- Datas são guardadas no horário local da barbearia (`TIMEZONE`).
- Rode o backend com 1 worker: as rotinas automáticas rodam dentro do processo da API.
