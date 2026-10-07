# Roadmap do CRM SyncServ

Plano das funcionalidades de CRM e gestão do SyncServ em 3 fases. Sistemas de mercado foram usados só como
**referência de funcionalidades**; marca, textos, telas e identidade visual são do SyncServ.

Legenda: ✅ pronto · 🟡 pronto no backend, telas na Etapa 2 · 🔜 planejado.

---

## O que já existia antes do CRM

| Área | Situação |
| --- | --- |
| Agenda (timeline, por profissional, mês), agendamento manual, remarcação, cancelamento, bloqueios | ✅ |
| Bot do cliente no WhatsApp (agendar, cancelar, remarcar, Pix, lembrete, pesquisa) e bot do dono | ✅ |
| Pix com chave do estabelecimento, confirmação manual, comprovante pelo WhatsApp | ✅ |
| Comissões e repasses (regras por serviço, vigência, acertos) | ✅ |
| Financeiro (faturamento, gastos, lucro, ticket médio, CSV) e gastos recorrentes | ✅ |
| Avaliações (pesquisa de 1 a 5) e relatórios | ✅ |
| Aprovação manual e bloqueio de clientes; clientes que não podem se encontrar | ✅ |
| Agente de IA (Gemini) com confirmação determinística | ✅ |
| Temas e vocabulário por segmento (barbearia, salão, pet shop, clínica, estúdio) | ✅ |
| Suíte de segurança (isolamento entre lojas, autenticação, entrada, webhook, logs) | ✅ |

---

## Fase 1 (Etapa 1: backend pronto; Etapa 2: telas; Etapa 3: offline)

### 1. Usuários e permissões 🟡

- **Objetivo:** equipe com login próprio, cada um vendo só o que precisa.
- **Regras:**
  - Papéis: **dono** (tudo), **recepção** (agenda, check-in, clientes, comandas, Pix, assinaturas, lista de espera; sem financeiro completo, comissões, cadastros, equipe, WhatsApp e IA; vê produtos sem o custo), **profissional** (só a própria agenda, os clientes que atendeu e as próprias comissões; pode confirmar, concluir, marcar falta e anotar nos próprios atendimentos).
  - Convite com **senha provisória** (12 caracteres, mostrada uma vez). Até trocar a senha, a pessoa só acessa `/me`, `/auth/refresh` e `/auth/change-password`.
  - Mudar papel, profissional vinculado ou desativar derruba as sessões da pessoa na hora. Sempre fica pelo menos um dono ativo. Profissional precisa de um cadastro de profissional (agenda) vinculado.
  - Toda rota declara o papel (`owner_shop`, `staff_shop`, `team_user` em `app/permissions.py`); o padrão é só o dono.
- **Banco:** `users.role`, `barber_id`, `active`, `must_change_password`, `created_at` (migração 0008; quem já existia vira dono).
- **Rotas:** `GET/POST /api/users`, `PUT /api/users/{id}`, `POST /api/users/{id}/reset-password`, `POST /api/auth/change-password`; `/me` e o login devolvem `role`, `barber_id` e `first_login`.
- **Telas (Etapa 2):** Usuários e permissões; menus por papel; troca de senha no primeiro acesso.
- **Bot:** sem mudança (o bot do estabelecimento continua pelo número do dono e dos profissionais).
- **Testes:** `tests/security/test_roles.py` (todas as rotas para recepção e profissional, convite, troca de senha, desativação, último dono, filtro do profissional).

### 2. Comanda 🟡

- **Objetivo:** fechar a conta do atendimento com serviços, produtos, desconto, gorjeta e pagamento dividido.
- **Regras:**
  - Abre ao concluir um agendamento (já entra o serviço agendado e o sinal pago) ou avulsa (encaixe, só produto). Uma comanda por agendamento.
  - Itens: serviço, produto, venda de pacote, desconto (R$ ou % do subtotal no momento) e gorjeta (vai inteira para o profissional, não é faturamento).
  - Serviço pago com saldo: sessão de pacote ou uso da assinatura; o item fica com valor a pagar 0.
  - Pagamento dividido em Pix, dinheiro, débito e crédito. Só fecha com saldo zero.
  - Lançamentos **imutáveis**; estorno é um lançamento negativo que aponta para o original (uma vez só) e devolve estoque, sessão de pacote e uso de assinatura. Em comanda fechada, só o dono estorna.
  - Fechada, alimenta o financeiro (data do fechamento; estorno posterior entra na data do estorno), as comissões e conclui o agendamento.
- **Banco:** `comandas`, `comanda_items`, `comanda_payments`.
- **Rotas:** `GET/POST /api/comandas`, `GET /api/comandas/{id}`, `POST .../items`, `POST .../items/{id}/reverse`, `POST .../payments`, `POST .../payments/{id}/reverse`, `POST .../close`, `POST .../cancel`.
- **Financeiro:** `app/services/revenue.py` junta atendimentos sem comanda (como antes), comandas fechadas (desconto rateado entre os itens, valor repartido entre as formas de pagamento), cobranças pagas e sinais retidos. O relatório de comissões ganhou `tips` e `product_commission`.
- **Telas (Etapa 2):** Comanda rápida (teclado numérico, botões grandes), painel lateral no web.
- **Testes:** `tests/test_crm.py` (pagamento dividido, desconto, gorjeta, finanças, comissões, estorno, estorno após fechar).

### 3. Produtos e estoque 🟡

- **Objetivo:** controlar venda e uso interno, com alerta de estoque baixo.
- **Regras:** produto de venda, uso interno ou ambos; custo, preço, estoque mínimo, comissão opcional para quem vende. O saldo é a **soma das movimentações** (entrada, venda, consumo do serviço, uso interno, ajuste, estorno), nunca sobrescrito. Venda na comanda baixa o estoque; serviço lançado baixa o que ele consome (cadastro por serviço). Estoque baixo aparece no app e no resumo diário do dono no WhatsApp. Entrada e ajuste: dono; uso interno: dono e recepção.
- **Banco:** `products`, `stock_movements`, `service_products`.
- **Rotas:** `GET/POST /api/products`, `PUT/DELETE /api/products/{id}`, `GET /api/products/low-stock`, `GET/POST /api/products/{id}/movements`, `GET/PUT /api/services/{id}/consumption`.
- **Telas (Etapa 2):** Produtos e estoque.
- **Testes:** baixa na venda e no serviço, uso interno, histórico sem sobrescrita, alerta no resumo diário.

### 4. Pacotes 🟡

- **Objetivo:** vender N sessões de um serviço com desconto e validade (ex.: 4 cortes por R$ 140).
- **Regras:** saldo = sessões − usos; usado ao agendar (app, bot e IA usam sozinhos quando cobre o serviço) ou na comanda. Cancelamento devolve a sessão; falta não devolve. Vencido não é usado. A comissão da sessão usa o **valor proporcional** (preço ÷ sessões). O pacote entra no faturamento quando é pago (na comanda ou pelo Pix do WhatsApp).
- **Banco:** `package_plans`, `customer_packages`, `package_uses`; `appointments.customer_package_id`.
- **Rotas:** `GET/POST /api/package-plans`, `PUT/DELETE /api/package-plans/{id}`, `GET /api/customers/{id}/balance`, `POST /api/customer-packages/{id}/cancel`; venda pela comanda (`kind: package`).
- **Bot:** opção **8 - Pacotes e assinatura** mostra o saldo e os pacotes à venda; a compra tem resumo com "1 - Confirmar e receber o Pix"; o pacote só vale depois que o Pix é confirmado no app.
- **Telas (Etapa 2):** Pacotes; saldo na ficha do cliente.
- **Testes:** consumo no agendamento, devolução no cancelamento, comanda sem consumo duplo, comissão proporcional, pacote vencido.

### 5. Clube de assinatura 🟡

- **Objetivo:** receita recorrente com planos mensais.
- **Regras:** plano com serviços incluídos, com ou sem limite por período (o ciclo começa no dia do mês em que a assinatura começou). Status **ativa / atrasada / cancelada**. No vencimento, a rotina gera a cobrança e manda o Pix pelo WhatsApp; a confirmação é manual (interface de gateway pronta em `app/services/billing.py` para um Pix automático no futuro). Atrasada há mais de X dias (por plano), os benefícios ficam bloqueados até o pagamento. Relatório de assinantes e MRR (soma das assinaturas não canceladas). Comissão do serviço coberto: preço do serviço.
- **Banco:** `subscription_plans`, `subscription_plan_items`, `subscriptions`, `subscription_uses`, `charges`; `appointments.subscription_id`.
- **Rotas:** `GET/POST /api/subscription-plans`, `PUT/DELETE .../{id}`, `GET/POST /api/subscriptions`, `POST /api/subscriptions/{id}/cancel`, `GET /api/subscriptions/report`, `GET /api/charges`, `POST /api/charges/{id}/confirm|cancel|resend`.
- **Bot:** saldo e status na opção 8; "paguei" marca a cobrança como informada.
- **Telas (Etapa 2):** Assinaturas (planos, assinantes, cobranças, MRR).
- **Testes:** limite por período, estorno devolvendo o uso, atraso bloqueando benefícios, recuperação de vencimentos perdidos, MRR.

### 6. Sinal contra faltas 🟡

- **Objetivo:** reduzir falta exigindo um Pix antecipado.
- **Regras:** por estabelecimento e por serviço (desligado, valor fixo ou %). Agendamento do WhatsApp fica **aguardando sinal** (ocupa o horário) e só é confirmado quando o Pix do sinal é confirmado. Sem confirmação em X minutos o horário é liberado (e oferecido à lista de espera). Cancelou com antecedência mínima configurável: sinal **a devolver**; depois disso ou falta: **retido** (entra no faturamento). O sinal pago entra sozinho na comanda. Pago com pacote ou assinatura não pede sinal. No app, o agendamento manual pede sinal só se marcado.
- **Banco:** `shops.deposit_*`, `services.deposit_mode/value`, `appointments.deposit_amount/deposit_status`, `payments.kind`.
- **Rotas:** `PUT /api/shop` (configuração), `POST /api/appointments` (`require_deposit`), `POST /api/payments/{id}/confirm`, `POST /api/appointments/{id}/deposit-refunded`.
- **Bot e IA:** mensagem do sinal com prazo; a IA explica a regra (get_business_info).
- **Telas (Etapa 2):** configuração do sinal; selo "aguardando sinal" na agenda.
- **Testes:** liberação do horário, confirmação, devolução e retenção.

### 7. Lista de espera 🟡

- **Objetivo:** aproveitar horários que abrem.
- **Regras:** quando o dia não tem horário, o bot oferece entrar na lista. Quando um horário abre (cancelamento, sinal vencido, remarcação, bloqueio removido), a primeira pessoa da fila que cabe nele é avisada e a vaga fica **reservada por 10 minutos** (configurável). Sem resposta, passa a vez; recusou, sai da lista.
- **Banco:** `waitlist_entries`; agendamento `held` para a reserva.
- **Rotas:** `GET/POST /api/waitlist`, `DELETE /api/waitlist/{id}`.
- **Bot e IA:** opção no fim da lista de dias; resposta 1/2 à oferta; ferramenta `join_waitlist`.
- **Telas (Etapa 2):** Lista de espera.
- **Testes:** ordem da fila, reserva, expiração, aceite pelo WhatsApp, oferta no bot.

### IA (fase 1) 🟡

Ferramentas novas: `get_my_balance`, `list_packages`, `propose_package_purchase` (resumo com confirmação determinística; nada é cobrado antes do "1") e `join_waitlist`. Regras 10 e 11 no prompt.

### 8. Base da sincronização offline 🟡 (app offline na Etapa 3)

- **Banco:** tabelas do app ganharam `uuid` (id público, pode ser gerado no aparelho), `updated_at` (relógio do servidor), `deleted_at` (exclusão vira tombstone), `version` e `sync_seq` (ordem das mudanças, contador por loja que trava a linha da loja até o commit: o cursor nunca pula mudança em andamento). Consultas normais não enxergam excluídos.
- **`GET /api/sync/pull?cursor=`:** por entidade, o que mudou depois do cursor, paginado (`has_more`), filtrado por papel e por loja; agenda de 30 dias para trás a 60 para frente e comandas dos últimos 30 dias. Profissional recebe só serviços, profissionais, bloqueios, a própria agenda e os clientes que atendeu.
- **`POST /api/sync/push`:** operações em ordem com `operation_id` único (reenvio devolve o mesmo resultado); cada uma em savepoint; resultado `aplicado`, `rejeitado` (motivo) ou `conflito` (com a versão do servidor).
- **Conflitos:** agendamento criado ou remarcado offline é validado como novo (horário ocupado = conflito); lançamentos de comanda, pagamentos e estoque só acrescentam e nunca conflitam; edição de cadastro com versão antiga faz merge campo a campo e só conflita no mesmo campo; WhatsApp só sai depois que a operação foi gravada.
- **Testes:** `tests/security/test_sync.py` (idempotência, conflito de horário, tombstones, filtro por papel, isolamento entre lojas, paginação, merge, operações em ordem com falha isolada, limites de entrada).

### Seeds

`python -m app.seed_mock` e `python -m app.seed_niches` criam produtos (um abaixo do mínimo), pacote, plano com 3 assinantes (um atrasado), comandas fechadas (com produto, desconto, gorjeta e pagamento dividido), lista de espera e logins `recepcao@demo.com` e `profissional@demo.com` (nos outros segmentos, `recepcao.salao@demo.com` etc.), senha `demo123`.

### Decisões e limites da fase 1

- Falta (no-show) não devolve a sessão do pacote nem o uso da assinatura.
- Desconto da comanda é rateado proporcionalmente entre serviços, produtos e pacotes.
- A janela da agenda no pull é calculada no dia do pull; o app deve refazer o pull completo (cursor 0) uma vez por dia (Etapa 3).
- O MRR soma as assinaturas não canceladas pelo valor contratado.
- Cobrança automática (gateway com webhook) fica para quando houver contrato com um provedor: só a interface está pronta.

---

## Fase 2 🔜

| Funcionalidade | Objetivo | Regras de negócio | Banco | Rotas | Telas | Bot | Testes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ficha 360 do cliente | Tudo do cliente numa tela | Histórico de atendimentos, comandas, produtos comprados, saldo, avaliações, preferências e observações; profissional vê só o que atendeu | (usa as tabelas existentes) + `customer_notes` com autor e data | `GET /api/customers/{id}/360` | Ficha com abas | — | isolamento e papel |
| Segmentação | Achar grupos de clientes | Filtros combináveis: sumidos há X dias, ticket, frequência, serviço, profissional, aniversariantes, assinantes, saldo de pacote | `segments` (filtro salvo em JSON) | `GET/POST /api/segments`, `GET /api/segments/{id}/customers` | Construtor de filtros | — | cada filtro, isolamento |
| Convite de retorno | Trazer de volta quem sumiu | Intervalo médio por cliente; convite automático com opt-in, no máximo 1 por mês | `return_invites` | `GET/PUT /api/settings/return` | Configuração e relatório | mensagem com "1 - Agendar" | frequência, opt-out |
| Aniversário | Relacionamento | Mensagem no dia (com cupom opcional), só com opt-in | `customers.birthdate` | ficha do cliente | campo e configuração | mensagem | data, opt-in |
| Fidelidade | Recompensar frequência | Pontos por real gasto em comanda fechada; resgate como desconto; estorno remove pontos | `loyalty_ledger` (só acrescenta) | `GET /api/customers/{id}/points`, resgate na comanda | saldo e resgate | saldo na opção 8 | estorno, resgate |
| Cupons | Promoções | Código, % ou R$, validade, limite de uso, por serviço | `coupons`, `coupon_uses` | `/api/coupons` | cadastro; uso na comanda | código no agendamento | limite, validade |
| Campanhas com opt-in | Marketing responsável | Só para quem aceitou; "SAIR" remove; limite de envio por dia (evita bloqueio do WhatsApp) | `customers.marketing_opt_in`, `campaigns`, `campaign_sends` | `/api/campaigns` | criar, agendar, resultado | opt-in e "SAIR" | opt-out, limite |
| NPS | Medir satisfação | Pesquisa 0–10 periódica (além da nota do atendimento) | `nps_answers` | `GET /api/reports/nps` | painel | pergunta e resposta | cálculo |
| Anamnese | Ficha de saúde (clínica, estética, pet) | Formulário por serviço, assinatura do cliente, só dono e profissional que atende veem; LGPD (dado sensível) | `anamnesis_forms`, `anamnesis_answers` | `/api/anamnesis` | formulário e histórico | link para preencher | acesso por papel |

## Fase 3 🔜

| Funcionalidade | Objetivo | Regras de negócio | Banco | Rotas | Telas | Bot | Testes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Página pública `/agendar/nome` | Agendar sem WhatsApp | Mesmas regras do bot (antecedência, conflitos, sinal); confirmação por código no WhatsApp; anti-robô | `shops.public_slug` | `GET /p/{slug}`, `POST /p/{slug}/book` (sem login, com limite) | página web | confirmação | abuso, isolamento |
| Rodízio e fila com painel | Ordem justa de atendimento sem hora marcada | Fila de chegada; próximo profissional livre pela vez; painel em tablet | `walk_in_queue` | `/api/queue` | painel tablet (web) | "entrar na fila" | ordem, concorrência |
| Mapa de calor | Ver ocupação por dia e hora | Ocupação média por faixa | (consulta) | `GET /api/reports/heatmap` | gráfico | — | cálculo |
| Relatórios avançados | Decisão com dados | Retenção, LTV, cancelamento por profissional, curva ABC de produtos, comparativos | (consultas) | `/api/reports/*` | relatórios | — | cálculos |
| Multiunidade | Redes com mais de uma loja | Dono vê consolidado; equipe por unidade; estoque e caixa por unidade | `organizations`, `shops.organization_id`, permissões por unidade | `/api/org/*` | troca de unidade | um número por unidade | isolamento entre unidades |
| NFS-e plugável | Emitir nota de serviço | Interface de provedor (como o gateway de pagamento); emissão no fechamento da comanda | `invoices` | `/api/invoices` | status da nota | — | provedor falso nos testes |
