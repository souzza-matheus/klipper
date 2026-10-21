// Trocar de negócio sem sair da conta (Mais > Trocar de negócio). Ordem: pede o token do negócio novo, apaga o banco
// offline e a fila de alterações do anterior e só então quem chama carrega o novo (applySession). Se o pedido falhar
// (sem internet), nada é apagado e a pessoa continua no negócio atual.
import { switchBusiness } from './api';
import { offlineState, stopOffline, syncNow } from './offline/manager';

// Alterações feitas sem internet que ainda não foram enviadas (são perdidas na troca)
export const pendingChanges = () => offlineState().pending || 0;

// "Enviar agora": tenta mandar a fila antes de trocar; devolve quantas ainda ficaram
export async function sendPending() {
  await syncNow('troca de negócio');
  return pendingChanges();
}

export async function changeBusiness(shopId, applySession) {
  const r = await switchBusiness(shopId);
  await stopOffline({ wipe: true }); // banco local e fila de sincronização do negócio anterior
  await applySession(r);
  return r;
}
