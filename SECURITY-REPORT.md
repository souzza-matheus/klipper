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

Resultado: **26 achados**: 1 crítico, 4 altos, 10 médios e 11 baixos. **25 corrigidos**, com testes que comprovam a correção. Fica pendente só parte do M-10: duas dependências de build do Expo (`braces` e `node-forge`) cuja versão mais recente publicada ainda é a vulnerável.

Atualização (segunda rodada, mesma data): as pendências da primeira rodada foram corrigidas: secret do webhook por barbearia e só no cabeçalho (instância existente migrada e secret global trocado), tokens de 7 dias com renovação e revogação, limitador de login no Redis, telefones mascarados nos logs, `/dev/*` com `SETUP_TOKEN`, `uuid` corrigido no app e `backend/.venv` fora do git.

O isolamento entre barbearias, o ponto mais importante, **não teve falhas**: todas as rotas já usavam a checagem de dono (`_own`). Mesmo assim, a suíte agora garante isso de forma sistemática.

| Severidade | Encontrados | Corrigidos | Pendentes |
| --- | --- | --- | --- |
| Crítica | 1 | 1 | 0 |
| Alta | 4 | 4 | 0 |
| Média | 10 | 9 (M-10 em parte) | 1 (parte do M-10) |
| Baixa | 11 | 11 | 0 |

Suíte: `backend/tests/security/` com **243 testes** (59 de isolamento, 86 de validação de entrada, 44 de webhook e bots, 27 de autenticação, 14 de configuração e exposição, 13 de IA e comprovantes). Suíte completa do backend: **374 testes passando**.

## Achados

Linhas referem-se ao código atual (depois das correções).

| Id | Severidade | Onde | Como explorar | Status | Recomendação |
| --- | --- | --- | --- | --- | --- |
| C-01 | Crítica | `backend/app/config.py:11-22`, `backend/app/security.py` (`production_problems`), `backend/app/main.py` (`create_app`) | Com `JWT_SECRET` no valor de exemplo publicado no código (`troque-este-segredo`), qualquer pessoa assina um token com o `sub` de qualquer usuário e acessa qualquer barbearia. O mesmo valia para `WEBHOOK_SECRET` (forjar mensagens) e `SETUP_TOKEN` (criar barbearias). | Corrigido: com `DEV_MODE=false` a API não sobe com segredos de exemplo ou curtos (`JWT_SECRET` com 32+ caracteres, os outros com 16+). Testes: `test_auth.py::test_production_refuses_example_secrets`, `test_production_app_does_not_start_with_defaults`. | Gerar os segredos com `openssl rand -hex 24` (README) e nunca reaproveitar entre ambientes. |
| A-01 | Alta | `backend/app/api/admin.py:65` (`login`), `:83` (`register`), `backend/app/security.py` (`LoginLimiter`) | Tentar senhas sem limite no `POST /api/auth/login` (e chutar o `SETUP_TOKEN` no cadastro). | Corrigido: bloqueio temporário de 15 min após 5 falhas por e-mail ou 20 por IP, com `429` e `Retry-After`; o login certo zera as falhas do e-mail. Testes: `test_brute_force_by_email_is_blocked`, `test_brute_force_by_ip_is_blocked`, `test_register_requires_setup_token`. | Com mais de um worker, mover o limitador para o Redis (ver B-09). |
| A-02 | Alta | `backend/app/config.py:27` | Subir a API sem definir `DEV_MODE` deixava o modo de desenvolvimento ligado: `/dev/simulate` permite mandar mensagens "do número do dono" e usar o menu do estabelecimento (agenda com telefones, confirmar Pix, bloquear horários), e `/dev/run-jobs` dispara as rotinas. | Corrigido: o padrão agora é `DEV_MODE=false` (seguro por padrão); desenvolvimento liga explicitamente (`.env`, README). Testes: `test_dev_mode_is_off_by_default`, `test_dev_routes_are_404_in_production`. | Manter `DEV_MODE=false` no servidor (já fixado no `docker-compose.prod.yml`). |
| A-03 | Alta | `backend/app/api/webhook.py` (`evolution_webhook`), `backend/app/services/whatsapp.py` (`create_instance`), `backend/app/security.py` (`RedactSecretsFilter`), migração `0007` | O secret do webhook ia na URL (`?secret=`) e aparecia no log de acesso do uvicorn (confirmado nos logs do backend), nos logs da Evolution e de proxies. Quem lê esses logs forja mensagens de qualquer número, inclusive do dono. | Corrigido: o secret só é aceito no cabeçalho `X-Webhook-Secret` (o `?secret=` não vale mais); cada barbearia tem o próprio secret (`shops.webhook_secret`, 32+ caracteres, ver B-11); a instância `barbearia-demo` foi migrada no banco da Evolution (URL sem secret, cabeçalho com o secret da barbearia) e o `WEBHOOK_SECRET` global, que tinha vazado nos logs, foi trocado nos dois `.env`; o filtro de logs apaga `secret=`/`token=`/`apikey=`. Testes: `test_webhook_rejects_missing_or_wrong_secret` (8 casos, inclusive o secret certo na URL), `test_webhook_accepts_only_the_shop_secret_in_the_header`, `test_secrets_never_reach_the_logs`. | Recriar o backend do Docker para valer no ambiente local (ver "Para aplicar"). |
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
| M-10 | Média | `mobile/package.json` (`overrides`), `mobile/package-lock.json` | `npm audit`: 24 avisos (15 altos, 9 moderados), todos transitivos das ferramentas de build e do servidor de desenvolvimento do Expo/Metro: `braces` e `micromatch` (DoS por padrão aninhado), `node-forge` (verificação de assinatura RSA, usado na assinatura de código do CLI) e `uuid` (via `xcode`). As "correções" sugeridas pelo npm são rebaixar para Expo 44 / React Native 0.72. | Parcial: `uuid` 7.0.3 → 11.1.1 por `overrides` (o `xcode` continua gerando ids; `expo export` e `expo config --type prebuild` ok): os 9 moderados zeraram. **Pendente:** 15 altos via `braces` 3.0.3 e `node-forge` 1.4.0, que já são as últimas versões publicadas (não há correção ainda); `npx expo install --check` sem atualizações. Esses pacotes rodam no build e no `expo start`, não no app instalado. | Repetir `npm audit` e `npx expo install --check` a cada patch; quando sair versão corrigida, acrescentar em `overrides`. Não expor o servidor do Expo fora da rede local. |
| B-01 | Baixa | `backend/app/auth.py` (`check_password_or_dummy`) | O login respondia mais rápido para e-mail inexistente (sem bcrypt), revelando quais e-mails têm conta. | Corrigido: confere contra um hash falso quando o e-mail não existe; mesma mensagem e status. Teste: `test_login_error_does_not_reveal_which_emails_exist`. | — |
| B-02 | Baixa | `backend/app/api/webhook.py:24`, `backend/app/api/admin.py:83`, `backend/app/security.py` (`same_secret`) | Secret do webhook e token de setup comparados com `!=` (vazamento por tempo). | Corrigido: `hmac.compare_digest`. Teste: `test_secret_comparison_is_constant_time`. | — |
| B-03 | Baixa | `backend/app/schemas.py` (`RegisterIn`, `LoginIn`), `backend/app/auth.py` | Senha mínima de 6 caracteres e sem máximo (uma senha com mais de 72 bytes derrubava o cadastro no bcrypt). | Corrigido: 8 a 128 caracteres; o bcrypt usa os primeiros 72 bytes de forma consistente. Senhas continuam só com hash bcrypt (`$2b$`) e nunca são devolvidas. Testes: `test_register_password_policy`, `test_passwords_are_bcrypt_and_never_returned`. | — |
| B-04 | Baixa | `backend/app/security.py` (`BodySizeLimitMiddleware`) | Requisições de qualquer tamanho eram lidas inteiras (consumo de memória). | Corrigido: acima de `MAX_BODY_BYTES` (2 MB), 413 antes de ler. Testes: `test_body_size_limit`, `test_giant_payload_is_refused_before_reading`. | — |
| B-05 | Baixa | `backend/app/security.py` (`RedactSecretsFilter`) | Encontrado pela suíte: a primeira versão do filtro de logs só limpava argumentos de texto, e a URL do `httpx` (objeto) passava com o secret. | Corrigido: o filtro limpa qualquer argumento não numérico. Teste: `test_secrets_never_reach_the_logs`. | — |
| B-06 | Baixa | git (`backend/.venv/`, 3.647 arquivos) | O ambiente virtual do Python estava versionado desde o primeiro commit. Nenhum segredo real foi encontrado no histórico (`git log -p`: os valores do `.env` não aparecem; os demais acertos são exemplos dentro das bibliotecas). | Corrigido: removido do git (commit "security fix") e coberto pelo `.gitignore`. | — |
| B-07 | Baixa | `backend/app/config.py` (`jwt_expire_hours`), `backend/app/auth.py`, `backend/app/api/admin.py` (`refresh`, `logout_all`), `mobile/App.js`, `mobile/src/screens/Settings.js` | Token JWT valia 30 dias e não havia como revogar (sair do app só apagava no celular). | Corrigido: token de 7 dias renovado pelo app a cada abertura (`POST /api/auth/refresh`); `users.token_version` no token e "Sair de todos os aparelhos" (`POST /api/auth/logout-all`) invalida todos os tokens emitidos. Testes: `test_token_lifetime_is_short`, `test_refresh_gives_a_new_valid_token`, `test_logout_all_revokes_every_issued_token`. | Ao criar troca de senha, subir o `token_version` também. |
| B-08 | Baixa | `backend/app/security.py` (`LoginLimiter`, `_RedisStore`), `docker-compose.prod.yml`, `backend/Dockerfile` | O limitador era só em memória (1 worker) e o IP real dependia de o proxy ser confiável. | Corrigido: com `REDIS_URL` os contadores ficam no Redis (vários workers, sobrevivem a reinícios), com volta automática para memória se o Redis cair; o `docker-compose.prod.yml` liga o Redis e passa `FORWARDED_ALLOW_IPS` (uvicorn 0.34 aceita CIDR). Teste: `test_login_limiter_works_with_redis_and_survives_redis_outage`. | Conferir o IP real nos logs depois do deploy. |
| B-09 | Baixa | `backend/app/services/whatsapp.py` (`mask_phone`), `backend/app/api/webhook.py`, `backend/app/services/payments.py` | Alguns logs tinham o telefone completo de clientes (dado pessoal em log). | Corrigido: logs mostram só os 4 últimos dígitos (`...4321`). Teste: `test_full_customer_phone_never_reaches_the_logs`. | — |
| B-10 | Baixa | `backend/app/api/webhook.py` (`dev_only`) | Em desenvolvimento, quem alcançava a porta do backend simulava mensagens de qualquer número, inclusive do dono. | Corrigido: `/dev/simulate` e `/dev/run-jobs` exigem o cabeçalho `X-Setup-Token` com o `SETUP_TOKEN` (e continuam 404 em produção). Teste: `test_dev_routes_need_setup_token_even_in_development`. | — |
| B-11 | Baixa | `backend/app/models.py` (`Shop.webhook_secret`), migração `0007`, `backend/app/api/webhook.py` | Um único secret para todas as instâncias: se vazasse, valia para todas as barbearias. | Corrigido: secret próprio por barbearia (gerado no cadastro e pela migração para as existentes); o `WEBHOOK_SECRET` global só vale para barbearia sem secret. Testes: `test_each_shop_has_its_own_strong_secret`, caso "secret da outra barbearia". | — |

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
- [ ] **Webhook:** cada instância com o secret da própria barbearia no cabeçalho (criadas assim pelo `connect`; instâncias antigas: atualizar URL e `headers` como em A-03).
- [ ] **Redis** ligado no limite de login (`REDIS_URL`, já no `docker-compose.prod.yml`).
- [ ] **Backups do banco:** `pg_dump` diário do volume `pgdata`, cópia fora da VPS e teste de restauração.
- [ ] **Dependências atualizadas:** `pip-audit -r backend/requirements.txt` e `npm audit` (mobile) a cada release; atualizar a imagem da Evolution dentro da v2 estável.
- [ ] **IA:** `AI_TIER=paid` com faturamento ativo e limite de gasto antes de usar dados reais.
- [ ] **Logs:** retenção curta e acesso restrito.

## Atualização: CRM fase 1 (Etapa 1)

As rotas novas (equipe, comanda, estoque, pacotes, assinatura, cobranças, lista de espera e sincronização) entraram na
suíte com as mesmas garantias das antigas:

- **Papéis:** `tests/security/test_roles.py` varre TODAS as rotas do OpenAPI com login de recepção e de profissional
  e confere 403 fora do papel e acesso dentro dele. Rota nova sem papel declarado cai no padrão "só o dono"
  (`shop_of = owner_shop`). Convidado com senha provisória só acessa `/me`, `/auth/refresh` e `/auth/change-password`
  até trocar a senha; desativar ou mudar o papel derruba as sessões na hora; o login desativado responde igual a senha
  errada.
- **Isolamento:** os 28 casos novos com `{id}` estão em `ROUTE_CASES` (o teste de cobertura falha se faltar algum),
  mais criação cruzada (comanda, item, pagamento, pacote, assinatura, consumo, usuário, lista de espera com ids de
  outra loja) e listas/relatórios novos sem vazamento.
- **Sincronização:** `tests/security/test_sync.py` cobre idempotência por loja, pull filtrado por papel e por loja,
  referências a registros de outra loja (rejeitadas sem vazar dados), limites de entrada e custo do produto escondido
  de quem não é dono.
- **Entrada:** 25 corpos e 10 consultas inválidas novos (valores negativos, porcentagens fora da faixa, quantidades
  enormes, métodos de pagamento inexistentes, cursor inválido) respondem 4xx, nunca 500.
- **WhatsApp no push:** mensagens geradas por uma operação do sync ficam numa fila e só saem depois do commit; operação
  rejeitada ou em conflito não manda nada.

## Atualização: versão web (Etapa 2)

- Login web (`client: "web"`) recebe token de acesso de 15 min e refresh token de 12 h (`typ=refresh`, não abre a
  API); `/auth/refresh` e a troca de senha mantêm o token web curto; "sair de todos os aparelhos" invalida o refresh.
- No navegador o token fica só em memória e o refresh token no `sessionStorage` da aba; o teste
  `test_mobile_keeps_token_in_secure_store_and_has_no_api_keys` falha se o código usar `localStorage` ou cookies.
- `deploy/Caddyfile.app`: CSP `default-src 'self'` sem `unsafe-eval` nem script inline, `frame-ancestors 'none'`,
  HSTS, `nosniff`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, sem cabeçalho `Server`
  (`test_web_app_is_served_with_csp_and_security_headers`).
- **CSP sem `'unsafe-inline'`:** `style-src 'self'` mais um único hash, o da string vazia. O react-native-web cria
  um `<style>` vazio e o preenche pelo CSSOM (`insertRule`), que o CSP não bloqueia. As fontes (`src/webFonts.web.js`)
  entram do mesmo jeito, em vez do texto que o expo-font injetaria. O estilo base saiu do `index.html` para
  `public/web.css`. O teste de segurança exige que a política não tenha `unsafe-inline`, tenha só esse hash e que o
  `index.html` não tenha `<style>`, script inline nem atributo `style`.
- `npm run test:web` (`mobile/tests/run_web_e2e.sh`) sobe um backend descartável com dados fictícios e roda
  `mobile/tests/web_e2e.py` com esse CSP. O teste falha em qualquer violação de CSP ou erro de console, e confere que
  as fontes e os ícones carregaram. Contraprova: sem o hash, o app nem desenha a tela de login e o teste falha.
- `npm audit` (15 altos, M-10) conferido de novo: `braces` 3.0.3 e `node-forge` 1.4.0 continuam sendo as últimas
  versões publicadas. Nenhum dos dois entra no bundle web nem no Android (só o Expo CLI e o Metro, no build, os
  usam), e a dependência nova (`expo-asset`) não acrescentou aviso.

## Atualização: modo offline do app (Etapa 3)

- **Dados no aparelho criptografados:** SQLite com SQLCipher (`expo-sqlite` com `useSQLCipher: true`). A chave é
  aleatória, de 256 bits, gerada com `expo-crypto` e guardada no SecureStore (`AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`:
  não vai para backup nem para outro aparelho). Se o build não tiver SQLCipher (Expo Go), o modo offline não liga e
  nenhum dado de cliente é gravado no aparelho. A exceção é desenvolvimento com `EXPO_PUBLIC_OFFLINE_PLAINTEXT=1`
  (`__DEV__`), que nunca vale num build de produção.
- **Transações na mesma conexão:** não usamos o `withExclusiveTransactionAsync` do expo-sqlite, porque ele abre outra
  conexão, que não receberia a chave. Isso foi achado na revisão: no aparelho, as gravações falhariam.
- **Apagar (LGPD):** o arquivo e a chave são apagados quando:
  - a pessoa sai da conta;
  - outra pessoa ou outro papel entra no aparelho (`user_id` e `shop_id` agora vêm no login);
  - o servidor recusa o token, inclusive durante a sincronização em segundo plano.

  Ao sair com alterações pendentes, o aviso diz que elas serão perdidas.
- **Sem dados de clientes em logs:** a sincronização registra só eventos e contagens. O teste
  `sync.jest.js › o log não recebe dados de clientes` roda um conflito com nome e telefone e confere o log.
- **Ações sem internet:** no celular sem conexão, as chamadas diretas à API que não têm versão offline (Pix,
  financeiro, equipe, configurações) são bloqueadas com aviso, como na web.
- **Push:** continua com a mesma validação de papel e de loja de antes. Os campos novos foram testados em
  `test_sync.py`:
  - check-in e conclusão: o profissional não altera valor nem forma de pagamento;
  - lista de espera com telefone inválido é rejeitada.
- **Teste estático novo:** `test_mobile_offline_db_is_encrypted_and_wiped` cobre:
  - o plugin SQLCipher, o `PRAGMA key` e a chave no SecureStore;
  - apagar ao sair e com token recusado;
  - nenhum dado no log;
  - nada de banco local na web.
- **Dependências novas** (todas na versão do SDK 57): `expo-sqlite`, `expo-crypto`, `expo-task-manager`,
  `expo-background-task`, e `jest` e `jest-expo` só para desenvolvimento. Elas não trouxeram aviso novo no app. O
  `npm audit` agora também lista ferramentas de teste do Jest, que o React Native 0.86 puxa (`@react-native/jest-preset`):
  `micromatch`/`braces` e `sprintf-js`, sem versão corrigida publicada. Nada disso entra no bundle.

## Como rodar a suíte

```bash
cd backend
pytest tests/security -v      # só segurança (368 testes)
pytest                        # tudo (513 testes)
```

Os testes usam SQLite de teste e dados fictícios, sem rede (a Evolution e o Gemini são simulados). Para rodar a verificação de dependências:

```bash
python -m venv /tmp/pa && /tmp/pa/bin/pip install pip-audit && /tmp/pa/bin/pip-audit -r backend/requirements.txt
cd mobile && npm audit
```

## Para aplicar no ambiente local

O código e os bancos já estão atualizados (migração 0007 aplicada no Postgres; webhook da `barbearia-demo` migrado no banco da Evolution; `WEBHOOK_SECRET` trocado no `.env` e no `backend/.env`). Falta recriar o backend do Docker, que ainda roda a versão anterior:

```bash
docker compose build backend && docker compose up -d --no-deps --force-recreate backend
```

O backend local da porta 8000 recarrega sozinho (`--reload`). No app, todos precisam entrar de novo (tokens novos de 7 dias).
