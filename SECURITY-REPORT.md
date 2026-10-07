# Relatório de segurança: SyncServ

Data: 07/10/2026 · Escopo: código deste repositório (backend FastAPI em `backend/`, app Expo em `mobile/`, `docker-compose.yml`) e ambiente local de desenvolvimento (localhost, banco de teste, dados fictícios). Nenhuma requisição foi feita à VPS de produção nem a serviços de terceiros, exceto as consultas de vulnerabilidades do `pip-audit` (PyPI/OSV) e do `npm audit` (registro do npm). Não havia relatório anterior do Claude Security (`CLAUDE-SECURITY-*`) no repositório.

## Resumo executivo

O que foi testado:

- **Autenticação e sessão:** todas as rotas `/api/*` sem token e com tokens inválidos (malformado, assinatura errada, expirado, `alg: none`, `sub` inexistente, não numérico, ausente ou de outra barbearia), mensagem de erro do login, força bruta, cadastro com `SETUP_TOKEN`, segredos de exemplo em produção e armazenamento de senhas.
- **Isolamento entre barbearias:** com o token da barbearia A, ler, alterar e apagar cada recurso da barbearia B pelo id, em **todas** as 27 rotas com `{id}` (o teste falha se surgir rota nova sem caso), criar recursos apontando para ids da outra barbearia e conferir listas, relatórios, agenda e exportação CSV.
- **Entrada:** atribuição em massa no `PUT /api/shop`, números negativos, zero, gigantes e de tipo errado, datas inválidas, fim antes do início, strings enormes, SQL injection na busca `?q=` e o BR Code do Pix (campos com caracteres especiais e textos longos, estrutura TLV e CRC).
- **Webhook e bots:** secret ausente, errado ou em outro formato; payloads malformados e gigantes; instância de outra barbearia; acesso ao menu do estabelecimento por número estranho (`painel`, `9`...); estado da conversa manipulado com ids de outro cliente; dados de um cliente em mensagens enviadas a outro.
- **Agente de IA:** ferramentas pedindo ids de outros clientes e de outra barbearia, limites por número e por barbearia, manipulação sem confirmação determinística.
- **Comprovantes do Pix:** tamanho, tipo não permitido, conteúdo que finge ser imagem, nome com `../`, download sem token e de outra barbearia.
- **Configuração:** rotas `/dev/*`, `/docs`, `/redoc` e `/openapi.json` em produção, CORS, cabeçalhos de segurança, cabeçalho `server`, limite de tamanho do corpo, erros 500 sem stack trace e segredos nos logs (captura dos logs procurando chave da Evolution, secret do webhook, token de setup, chave do Gemini, JWT e senhas).
- **Fora do pytest:** `pip-audit`, `npm audit`, portas do Docker, segredos no repositório e no histórico do git, e armazenamento do token no app.

Resultado: **26 achados**: 1 crítico, 4 altos, 10 médios e 11 baixos. Todos os críticos e altos foram corrigidos, com testes que comprovam a correção; um alto tem uma ação residual de configuração (migrar o webhook da instância existente). Ficaram pendentes 1 médio (dependências de build do Expo, sem correção compatível) e 6 baixos.

O isolamento entre barbearias, o ponto mais importante, **não teve falhas**: todas as rotas já usavam a checagem de dono (`_own`). Mesmo assim, a suíte agora garante isso de forma sistemática.

| Severidade | Encontrados | Corrigidos | Pendentes |
| --- | --- | --- | --- |
| Crítica | 1 | 1 | 0 |
| Alta | 4 | 4 (1 com ação residual) | 0 |
| Média | 10 | 9 | 1 |
| Baixa | 11 | 5 | 6 |

Suíte: `backend/tests/security/` com **236 testes** (59 de isolamento, 86 de validação de entrada, 43 de webhook e bots, 23 de autenticação, 13 de IA e comprovantes, 12 de configuração e exposição). Suíte completa do backend: **367 testes passando**.

## Achados

Linhas referem-se ao código atual (depois das correções).

| Id | Severidade | Onde | Como explorar | Status | Recomendação |
| --- | --- | --- | --- | --- | --- |
| C-01 | Crítica | `backend/app/config.py:11-22`, `backend/app/security.py` (`production_problems`), `backend/app/main.py` (`create_app`) | Com `JWT_SECRET` no valor de exemplo publicado no código (`troque-este-segredo`), qualquer pessoa assina um token com o `sub` de qualquer usuário e acessa qualquer barbearia. O mesmo valia para `WEBHOOK_SECRET` (forjar mensagens) e `SETUP_TOKEN` (criar barbearias). | Corrigido: com `DEV_MODE=false` a API não sobe com segredos de exemplo ou curtos (`JWT_SECRET` com 32+ caracteres, os outros com 16+). Testes: `test_auth.py::test_production_refuses_example_secrets`, `test_production_app_does_not_start_with_defaults`. | Gerar os segredos com `openssl rand -hex 24` (README) e nunca reaproveitar entre ambientes. |
| A-01 | Alta | `backend/app/api/admin.py:65` (`login`), `:83` (`register`), `backend/app/security.py` (`LoginLimiter`) | Tentar senhas sem limite no `POST /api/auth/login` (e chutar o `SETUP_TOKEN` no cadastro). | Corrigido: bloqueio temporário de 15 min após 5 falhas por e-mail ou 20 por IP, com `429` e `Retry-After`; o login certo zera as falhas do e-mail. Testes: `test_brute_force_by_email_is_blocked`, `test_brute_force_by_ip_is_blocked`, `test_register_requires_setup_token`. | Com mais de um worker, mover o limitador para o Redis (ver B-09). |
| A-02 | Alta | `backend/app/config.py:27` | Subir a API sem definir `DEV_MODE` deixava o modo de desenvolvimento ligado: `/dev/simulate` permite mandar mensagens "do número do dono" e usar o menu do estabelecimento (agenda com telefones, confirmar Pix, bloquear horários), e `/dev/run-jobs` dispara as rotinas. | Corrigido: o padrão agora é `DEV_MODE=false` (seguro por padrão); desenvolvimento liga explicitamente (`.env`, README). Testes: `test_dev_mode_is_off_by_default`, `test_dev_routes_are_404_in_production`. | Manter `DEV_MODE=false` no servidor (já fixado no `docker-compose.prod.yml`). |
| A-03 | Alta | `backend/app/api/webhook.py:24`, `backend/app/services/whatsapp.py:144`, `backend/app/security.py:146` (`RedactSecretsFilter`) | O secret do webhook ia na URL (`?secret=`) e aparecia no log de acesso do uvicorn (confirmado nos logs do backend), nos logs da Evolution e de proxies. Quem lê esses logs forja mensagens de qualquer número, inclusive do dono. | Corrigido: o webhook aceita o secret no cabeçalho `X-Webhook-Secret`, instâncias novas são criadas com o cabeçalho (sem secret na URL) e o filtro de logs apaga `secret=`/`token=`/`apikey=` das linhas de log (inclusive em objetos como a URL do `httpx`). Testes: `test_secrets_never_reach_the_logs`, `test_webhook_accepts_secret_in_header_or_query`, `test_whatsapp_connect.py::test_instancia_inexistente_e_criada_com_webhook`. **Ação residual:** a instância existente (`barbearia-demo`) ainda usa `?secret=`. | Com a Evolution ligada, atualizar o webhook da instância para `url=http://backend:8000/webhook/evolution` e `headers={"x-webhook-secret": ...}` (`POST /webhook/set/{instância}`) e trocar o `WEBHOOK_SECRET`. Depois, remover o suporte ao `?secret=`. |
| A-04 | Alta | `backend/requirements.txt` | Vulnerabilidades conhecidas: `pyjwt` 2.10.1 (16 avisos, ex.: cabeçalho `crit` não validado, assinatura com caracteres fora do Base64URL aceita), `starlette` 0.41.3 (7, ex.: `Host` sem validação na reconstrução da URL, DoS em formulários e `Range`), `pytest` 8.3.4 (1, local). A maioria não se aplica ao uso atual (só HS256, sem JWK, formulários ou arquivos estáticos), mas a correção é simples. | Corrigido: `fastapi` 0.115.6 → 0.142.2, `starlette` → 1.7.0, `pyjwt` → 2.15.0, `pytest` → 9.0.3. Suíte completa passando com as versões novas; `pip-audit` sem pendências no backend. | Rodar `pip-audit -r backend/requirements.txt` a cada release. |
| M-01 | Média | `backend/app/auth.py:48` (`current_user`) | Token assinado sem `sub`, ou com `sub` não numérico, gerava erro 500 em vez de 401. | Corrigido: qualquer token inválido dá 401; exige `exp` e `sub` e confere a barbearia do token. Teste: `test_invalid_tokens_get_401` (11 casos). | — |
| M-02 | Média | `backend/app/api/webhook.py:24` | JSON inválido ou com tipos inesperados no webhook derrubava a requisição com 500. | Corrigido: payload inválido é ignorado (200). Teste: `test_malformed_payloads_never_crash` (12 formatos). | — |
| M-03 | Média | `backend/app/schemas.py` (tipos `Id`, `QId`, `Money`, `Text`), `backend/app/api/admin.py:44` (`_own`), `:463` | Strings maiores que a coluna, preços e ids gigantes, `sort_order` enorme e `offset` negativo davam erro do banco (500 no Postgres; overflow no SQLite). | Corrigido: limites em todos os schemas de entrada e em ids de caminho e query; erro de banco residual vira 422 sem detalhes. Testes: `test_invalid_input_is_rejected_without_500` (32), `test_invalid_query_and_path_values_never_500` (17), `test_out_of_range_query_ids_never_500` (9). | — |
| M-04 | Média | `backend/app/services/pix.py:12` (`_field`), `:73`; `backend/app/api/admin.py:121` (`update_shop`) | A chave Pix entrava no BR Code sem validação: uma chave com mais de 99 caracteres ou não ASCII gerava "copia e cola" quebrado para o cliente. | Corrigido: chave validada por tipo (CPF, CNPJ, celular, e-mail até 77, aleatória UUID) no `PUT /api/shop`; o Pix só é oferecido com chave válida; campo EMV fora do padrão é recusado. Nome, cidade e descrição já eram limpos. Testes: `test_brcode_fields_cannot_break_or_inject`, `test_pix_key_validation`, `test_invalid_pix_key_is_refused_by_api`. | — |
| M-05 | Média | `backend/app/services/reports.py:169` (`export_csv`) | Um cliente com nome de WhatsApp começando com `=` (ex.: `=HYPERLINK(...)`) vira fórmula ao abrir o CSV no Excel/Sheets. | Corrigido: células que começam com `= + - @` ganham apóstrofo. | — |
| M-06 | Média | `backend/app/services/payments.py:91` (`save_receipt`), `backend/app/api/admin.py:556` (`payment_receipt`) | O tipo do comprovante vinha do que o remetente declarou: um SVG ou HTML com tipo `image/png` era aceito e servido pela API. | Corrigido: o tipo é detectado pelos bytes (JPEG, PNG, WebP, GIF, PDF); o resto é recusado. O download vai com `nosniff`, `Content-Disposition` com nome fixo e CSP `sandbox`. Testes: `test_bad_receipts_are_refused` (6), `test_good_receipt_is_stored_with_real_type_and_safe_name`, `test_receipt_download_needs_token_and_owner`. | — |
| M-07 | Média | `backend/app/main.py` (`create_app`), `backend/app/security.py` (`SecurityHeadersMiddleware`), `backend/Dockerfile` | CORS `*` sempre; `/docs`, `/redoc` e `/openapi.json` públicos em produção (mapa completo da API); sem cabeçalhos de segurança; `server: uvicorn` exposto. | Corrigido: CORS vem de `CORS_ORIGINS` (`*` impede subir em produção); documentação só com `DEV_MODE=true`; `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy: frame-ancestors 'none'`, `Referrer-Policy`, `Permissions-Policy` e `Cache-Control: no-store` nas rotas da API; uvicorn com `--no-server-header`. Testes: `test_docs_and_openapi_are_off_in_production`, `test_cors_in_production_only_allows_configured_origins`, `test_security_headers_on_every_response`. | — |
| M-08 | Média | `backend/app/bot/customer.py:368` (`st_book_pay`), `:556` (`st_pay_pick`), `:626` (`st_survey_rating`), `:425` (`_my_appt`) | Se o estado da conversa tivesse o id de um agendamento de outro cliente, o bot mandava o Pix dele, deixava avaliar o atendimento dele ou (em `_my_appt`) usava agendamento de outra barbearia com o mesmo telefone. Os ids vêm do servidor, então é defesa em profundidade. | Corrigido: toda ação confere cliente e barbearia. Teste: `test_conversation_state_with_other_customer_ids_does_nothing` (9 estados; 3 deles falhavam antes da correção). | — |
| M-09 | Média | `docker-compose.yml:82` | O backend fica publicado em `0.0.0.0:8002` (todas as interfaces), acessível sem HTTPS se o firewall falhar. Postgres (`127.0.0.1:5434`), Evolution (`127.0.0.1:8080`) e Redis (sem porta) já estavam restritos. | Corrigido para produção: `docker-compose.prod.yml` publica só o backend em `127.0.0.1` (atrás do Caddy) e tira as portas do Postgres e da Evolution. O compose de desenvolvimento continua com `0.0.0.0` para o celular acessar na rede local. Teste: `test_production_compose_publishes_only_the_backend_on_localhost`. | Em produção: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`. |
| M-10 | Média | `mobile/package-lock.json` | `npm audit`: 24 avisos (15 altos, 9 moderados), todos transitivos das ferramentas de build e do servidor de desenvolvimento do Expo/Metro: `braces` e `micromatch` (DoS por padrão aninhado), `node-forge` (verificação de assinatura RSA, usado na assinatura de código do CLI) e `uuid` (via `xcode`). As "correções" sugeridas pelo npm são rebaixar para Expo 44 / React Native 0.72. | Pendente: sem correção compatível com o Expo SDK 57. Esses pacotes rodam no build e no `expo start`, não no app instalado. | `npx expo install --check` a cada patch do SDK; não expor o servidor do Expo fora da rede local; avaliar `overrides` quando houver versão corrigida. A landing não tem dependências npm. |
| B-01 | Baixa | `backend/app/auth.py` (`check_password_or_dummy`) | O login respondia mais rápido para e-mail inexistente (sem bcrypt), revelando quais e-mails têm conta. | Corrigido: confere contra um hash falso quando o e-mail não existe; mesma mensagem e status. Teste: `test_login_error_does_not_reveal_which_emails_exist`. | — |
| B-02 | Baixa | `backend/app/api/webhook.py:24`, `backend/app/api/admin.py:83`, `backend/app/security.py` (`same_secret`) | Secret do webhook e token de setup comparados com `!=` (vazamento por tempo). | Corrigido: `hmac.compare_digest`. Teste: `test_secret_comparison_is_constant_time`. | — |
| B-03 | Baixa | `backend/app/schemas.py` (`RegisterIn`, `LoginIn`), `backend/app/auth.py` | Senha mínima de 6 caracteres e sem máximo (uma senha com mais de 72 bytes derrubava o cadastro no bcrypt). | Corrigido: 8 a 128 caracteres; o bcrypt usa os primeiros 72 bytes de forma consistente. Senhas continuam só com hash bcrypt (`$2b$`) e nunca são devolvidas. Testes: `test_register_password_policy`, `test_passwords_are_bcrypt_and_never_returned`. | — |
| B-04 | Baixa | `backend/app/security.py` (`BodySizeLimitMiddleware`) | Requisições de qualquer tamanho eram lidas inteiras (consumo de memória). | Corrigido: acima de `MAX_BODY_BYTES` (2 MB), 413 antes de ler. Testes: `test_body_size_limit`, `test_giant_payload_is_refused_before_reading`. | — |
| B-05 | Baixa | `backend/app/security.py` (`RedactSecretsFilter`) | Encontrado pela suíte: a primeira versão do filtro de logs só limpava argumentos de texto, e a URL do `httpx` (objeto) passava com o secret. | Corrigido: o filtro limpa qualquer argumento não numérico. Teste: `test_secrets_never_reach_the_logs`. | — |
| B-06 | Baixa | git (`backend/.venv/`, 3.647 arquivos) | O ambiente virtual do Python está versionado desde o primeiro commit (aumenta o repositório e arrisca versionar algo sensível instalado ali). Nenhum segredo real foi encontrado no histórico (`git log -p`: os valores do `.env` não aparecem; os demais acertos são exemplos dentro das bibliotecas). | Pendente (exige commit): `.gitignore` atualizado. | `git rm -r --cached backend/.venv && git commit`. |
| B-07 | Baixa | `backend/app/config.py:12` | Token JWT vale 30 dias e não há como revogar (sair do app só apaga no celular). Um token vazado dá acesso até expirar. | Pendente. | Reduzir para 7 dias com renovação, ou guardar uma versão de token por usuário para invalidar na troca de senha/logout. |
| B-08 | Baixa | `backend/app/security.py` (`LoginLimiter`), `backend/Dockerfile` | O limitador é em memória (vale para 1 worker, que é o caso) e o IP real depende de o proxy ser confiável (`--forwarded-allow-ips`); sem isso, todos os logins parecem vir do IP do Caddy. O limite por e-mail funciona de qualquer forma. | Pendente/documentado: Dockerfile e `docker-compose.prod.yml` já passam `FORWARDED_ALLOW_IPS`. | Conferir o IP real nos logs depois do deploy; usar Redis se aumentar o número de workers. |
| B-09 | Baixa | `backend/app/api/webhook.py`, `backend/app/bot/*`, `backend/app/services/*` | Alguns logs têm telefone completo de clientes (ex.: "Erro ao processar mensagem de ..."), dado pessoal em log. | Pendente. | Mascarar o telefone nos logs (só os 4 últimos dígitos, como já feito na IA e nos comprovantes). |
| B-10 | Baixa | `backend/app/api/webhook.py` (`/dev/simulate`) | Em desenvolvimento, quem alcança a porta do backend simula mensagens de qualquer número, inclusive do dono. | Aceito em desenvolvimento (A-02 desliga em produção). | Não expor a porta de desenvolvimento fora da rede local. |
| B-11 | Baixa | `backend/app/config.py` (`WEBHOOK_SECRET`) | Um único secret para todas as instâncias: se vazar, vale para todas as barbearias. | Pendente. | Secret por instância (guardado na barbearia) quando houver várias barbearias em produção. |

### Verificado sem achados

- **Isolamento entre barbearias:** as 27 rotas com `{id}` devolvem 404 para recursos de outra barbearia, sem vazar dados e sem alterar nada (conferido no banco depois de cada tentativa). Criar recursos com ids da outra barbearia é recusado (18 combinações). Listas, relatórios, agenda do dia e CSV só têm dados da própria barbearia.
- **Atribuição em massa:** `PUT /api/shop` ignora `id`, `evolution_instance`, `ai_allow_free_tier`, `ai_monthly_limit` e `ai_enabled`; `PUT /api/ai/settings` só muda os dois liga/desliga.
- **SQL injection:** a busca `?q=` usa parâmetros; 11 cargas maliciosas testadas.
- **Bots:** número que não é do dono nem de profissional nunca chega ao menu do estabelecimento (`painel`, `9`, `10`...); mensagem para instância de outra barbearia só afeta aquela; "paguei" não confirma pagamento; nenhuma mensagem enviada a um cliente cita nome ou telefone de outro (varredura da tabela `outbox`).
- **Agente de IA:** pedindo explicitamente ids de agendamentos de outro cliente ou de outra barbearia, as 9 tentativas (cancelar, remarcar, Pix) são recusadas como "não encontrado"; não há ferramenta que grave sem o "1" determinístico; limites por número e por barbearia respeitados.
- **App mobile:** o token fica no `expo-secure-store` (não em AsyncStorage) e não há chave de API no código.
- **Segredos no repositório:** `.env`, `qrcode.png` e as pastas `CLAUDE-SECURITY-*` estão no `.gitignore`; `.env.example` só tem valores de exemplo.

## Dependências

Backend (`pip-audit -r backend/requirements.txt`), antes da correção:

| Pacote | Versão | Avisos | Versão corrigida | Aplicação no SyncServ |
| --- | --- | --- | --- | --- |
| pyjwt | 2.10.1 | 16 | 2.15.0 | Baixa: só HS256, sem JWK nem `crit` |
| starlette | 0.41.3 | 7 | 1.3.1 (instalada 1.7.0, com fastapi 0.142.2) | Média: reconstrução de URL pelo `Host`; o resto (formulários, `FileResponse`, `StaticFiles`) não é usado |
| pytest | 8.3.4 | 1 | 9.0.3 | Só na máquina de quem roda os testes |

Depois da atualização: sem pendências no backend. Mobile: ver M-10.

## Checklist de produção

- [ ] **Segredos trocados:** `POSTGRES_PASSWORD`, `EVOLUTION_API_KEY`, `JWT_SECRET` (32+), `WEBHOOK_SECRET` e `SETUP_TOKEN` gerados com `openssl rand -hex 24`, diferentes dos de desenvolvimento. A API recusa subir com valores de exemplo.
- [ ] **`DEV_MODE=false`** (o padrão; o `docker-compose.prod.yml` fixa). Conferir que `/docs`, `/dev/simulate` e `/openapi.json` dão 404.
- [ ] **HTTPS:** Caddy na frente do backend com certificado automático; o app de produção só aceita `https://`.
- [ ] **CORS:** `CORS_ORIGINS` vazio (o app nativo não precisa) ou só os domínios do painel web, nunca `*`.
- [ ] **Portas fechadas:** subir com `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`; firewall só com 22, 80 e 443; Postgres, Redis e Evolution sem porta publicada.
- [ ] **Proxy confiável:** `FORWARDED_ALLOW_IPS` com a rede do Caddy, para o limite de login ver o IP real.
- [ ] **Webhook:** instâncias com o secret no cabeçalho (A-03); trocar o `WEBHOOK_SECRET` depois da migração.
- [ ] **Backups do banco:** `pg_dump` diário do volume `pgdata`, cópia fora da VPS e teste de restauração.
- [ ] **Dependências atualizadas:** `pip-audit -r backend/requirements.txt` e `npm audit` (mobile) a cada release; atualizar a imagem da Evolution dentro da v2 estável.
- [ ] **IA:** `AI_TIER=paid` com faturamento ativo e limite de gasto antes de usar dados reais.
- [ ] **Logs:** retenção curta e acesso restrito (contêm telefones, B-09).
- [ ] **Repositório:** remover o `backend/.venv` do git (B-06).

## Como rodar a suíte

```bash
cd backend
pytest tests/security -v      # só segurança (236 testes)
pytest                        # tudo (367 testes)
```

Os testes usam SQLite de teste e dados fictícios, sem rede (a Evolution e o Gemini são simulados). Para rodar a verificação de dependências:

```bash
python -m venv /tmp/pa && /tmp/pa/bin/pip install pip-audit && /tmp/pa/bin/pip-audit -r backend/requirements.txt
cd mobile && npm audit
```
