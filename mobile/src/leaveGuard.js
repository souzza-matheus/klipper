// Antes de sair da conta ou trocar de negócio: o banco offline e a fila de alterações do aparelho são apagados.
// Com alterações feitas sem internet ainda não enviadas, avisa e oferece enviar primeiro.
import { pendingChanges, sendPending } from './businessSwitch';
import { ask, confirm, toast } from './ui';

const plural = (n) => (n === 1 ? '1 alteração feita sem internet ainda não foi enviada'
  : `${n} alterações feitas sem internet ainda não foram enviadas`);

// title: pergunta; message: o que acontece; yesLabel: o botão de seguir; onGo: segue (sair ou trocar)
export function guardLeave({ title, message, yesLabel, onGo }) {
  const n = pendingChanges();
  if (!n) {
    confirm(title, message, onGo, yesLabel, true);
    return;
  }
  ask(title, `${plural(n)} e será(ão) perdida(s) se você continuar agora. ${message}`, [
    { text: 'Voltar', style: 'cancel' },
    {
      text: 'Enviar agora',
      onPress: async () => {
        const left = await sendPending();
        if (left) toast(`${plural(left)}. Confira a internet e tente de novo.`, 'error');
        else onGo();
      },
    },
    { text: `${yesLabel} sem enviar`, style: 'destructive', onPress: onGo },
  ]);
}
