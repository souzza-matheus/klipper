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

**App admin:** agenda por dia e barbeiro, novo agendamento manual, confirmar, concluir, falta, remarcar, cancelar, enviar Pix, clientes com histórico, Pix pendentes, serviços, barbeiros com expediente, bloqueios, avaliações, relatórios, configurações do bot e do Pix, conexão do WhatsApp por QR Code.

**Pix:** gera o "copia e cola" (padrão do Banco Central) com a chave da própria barbearia. O dinheiro vai direto para a conta do dono; a confirmação é manual (app ou WhatsApp).

## Testar em 2 minutos (sem WhatsApp)

```bash
cd backend
pip install -r requirements.txt
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

Testes automatizados: `cd backend && pytest` (Pix, agendamento completo, cancelamento, remarcação, menu do dono, lembrete e pesquisa).

## Colocar no ar (VPS)

1. VPS com Docker (2 vCPU e 4 GB bastam para várias barbearias).
2. `cp .env.example .env` e troque todos os valores.
3. `docker compose up -d --build`
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
