import { ask, confirm, haptic, run, toast } from '../ui';

// Salva um agendamento/remarcação. Se a API recusar por conflito entre clientes (409), mostra quem é o outro
// cliente e oferece "Agendar mesmo assim" (repete com force=true). call(force) faz a chamada.
export async function saveWithConflictCheck(call, okMsg) {
  try {
    const r = await call(false);
    if (okMsg) toast(okMsg);
    return r;
  } catch (e) {
    if (e.status !== 409 || e.data?.detail?.code !== 'customer_conflict') {
      toast(e.message, 'error');
      return undefined;
    }
    haptic.warning();
    return new Promise((resolve) => {
      ask('Clientes que não podem se encontrar', `${e.message}\n\nO cliente não fica sabendo disso.`, [
        { text: 'Voltar', style: 'cancel', onPress: () => resolve(undefined) },
        { text: 'Agendar mesmo assim', style: 'destructive', onPress: () => resolve(run(() => call(true), okMsg)) },
      ]);
    });
  }
}

const ACCESS_WARN = {
  approval: 'Este cliente precisa de aprovação para agendar pelo WhatsApp.',
  blocked: 'Este cliente está bloqueado para agendar pelo WhatsApp.',
};

// Confirma antes de agendar manualmente um cliente com acesso restrito
export function confirmAccess(customer, onYes) {
  const warn = customer && ACCESS_WARN[customer.access_status];
  if (!warn) return onYes();
  const reason = customer.access_reason ? `\nMotivo: ${customer.access_reason}` : '';
  return confirm('Atenção', `${warn}${reason}\n\nAgendar mesmo assim?`, onYes, 'Agendar');
}
