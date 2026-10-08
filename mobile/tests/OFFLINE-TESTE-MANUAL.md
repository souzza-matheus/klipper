# Teste manual do modo offline (celular, modo avião)

Use só o backend local e os dados fictícios do `seed_mock` (nunca a produção nem clientes reais).

## Preparação

1. **Build com SQLCipher.** O Expo Go não traz o SQLCipher. Nele o modo offline fica desligado e o app
   funciona só online, como a versão web. Gere um build do próprio app com um destes comandos:
   - `cd mobile && eas build --profile apk -p android` (APK interno);
   - `npx expo run:android`, que precisa do Android SDK instalado.
2. **Backend na rede local** (`docker compose up -d` ou o `uvicorn` local) com os dados fictícios.
   Logins de teste: `recepcao@demo.com` e `profissional@demo.com`, senha `demo123`.
3. **Login no app** como recepção. Abra **Mais › Sincronização e modo offline**: deve aparecer
   "Com internet", o horário da última sincronização e "Nada pendente".
4. **Confira a criptografia.** Só funciona em build *debuggable*. O comando abaixo não pode mostrar o texto
   `SQLite format 3`: o arquivo precisa estar ilegível.
   ```
   adb shell run-as br.com.barberbot.admin head -c 16 files/SQLite/syncserv-offline.db | xxd
   ```

## Roteiro

| # | Ação | Esperado |
|---|------|----------|
| 1 | Ligue o **modo avião**. | Faixa amarela "Sem conexão: suas alterações serão sincronizadas". Agenda, clientes e caixa continuam abrindo. |
| 2 | Agende um **cliente novo** (telefone que não existe) para amanhã às 10:00. | O agendamento aparece na agenda com o selo **"A confirmar"**. A mensagem diz que o WhatsApp sai quando o servidor confirmar. A faixa mostra "(1 pendente)". |
| 3 | Tente agendar outro cliente no mesmo horário com o mesmo profissional. | Recusado na hora: "Esse horário não está mais livre." |
| 4 | Em outro agendamento de hoje: **Cliente chegou (check-in)** › **Abrir comanda**. | A comanda abre com o serviço agendado e o selo "A confirmar". |
| 5 | Na comanda, venda 2 unidades de um produto com estoque 1. | Aparece "Estoque insuficiente… Vender mesmo assim?". Depois de confirmar, o produto fica com estoque negativo e marcado como "estoque baixo". |
| 6 | Receba o total em dinheiro e **feche a comanda**. | Fecha. O item aparece em "Fechadas hoje" com o selo "A confirmar". |
| 7 | **Lista de espera**: adicione alguém. **Produtos**: registre um uso interno. | Os dois aparecem com "A confirmar". |
| 8 | Ainda offline, **feche o app** (tire da lista de recentes) e abra de novo. | As pendências continuam lá: nada se perde ao fechar. |
| 9 | No computador (versão web), agende **outro cliente** amanhã às 10:00 com o mesmo profissional. | É o conflito do passo 2. |
| 10 | Desligue o modo avião. | A faixa mostra "Enviando…" e depois some. O contador vai a zero. Os selos "A confirmar" somem. |
| 11 | Veja a faixa vermelha **"1 item precisa da sua atenção"**. | A tela "Precisa da sua atenção" mostra "Horário ocupado" com o nome do cliente. O agendamento do passo 2 sumiu da agenda. |
| 12 | Toque em **Agendar em outro horário**. | Abre o novo agendamento já com o telefone, o nome e o serviço preenchidos. |
| 13 | No backend, confira as mensagens de WhatsApp que saíram (fila de saída). | Só há mensagem dos agendamentos aceitos. Nada foi enviado para o cliente do passo 2. |
| 14 | Na web, confira a comanda do passo 6, o estoque e o caixa do dia. | Iguais ao celular. Nenhum lançamento duplicado. |
| 15 | **Sair** do app (Mais › Sair). | Se houver pendências, o aviso diz que elas serão perdidas e que os dados do aparelho serão apagados. Ao entrar com `profissional@demo.com`, só aparece a agenda dele. |
| 16 | Na web, como dono, use **Sair de todos os aparelhos**. Volte ao celular e puxe para atualizar. | O app volta para o login e o banco do aparelho é apagado. O passo 4 da preparação mostra que o arquivo não existe mais. |

## Segundo plano

Deixe uma alteração pendente, desligue o modo avião e mande o app para o segundo plano. O sistema
roda a sincronização a cada ~15 minutos, quando quiser. Para não esperar, use
`BackgroundTask.triggerTaskWorkerForTestingAsync()` num build de desenvolvimento.

## Expo Go (só desenvolvimento)

Para testar a interface offline no Expo Go, use `EXPO_PUBLIC_OFFLINE_PLAINTEXT=1 npx expo start`.
Nesse modo o banco **não é criptografado**: use só com os dados fictícios. Em build de produção, essa
opção não existe.
