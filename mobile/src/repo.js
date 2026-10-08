// Repositório: a mesma interface para as telas, venha o dado da API ou do banco local.
// - Web (e celular sem o banco criptografado disponível): API, só online (src/repo.remote.js).
// - Celular: banco local com sincronização (src/repo.local.js e src/offline/).
import { offlineReady } from './offline/manager';
import { local } from './repo.local';
import { remote } from './repo.remote';

const impl = () => (offlineReady() ? local : remote);

export const repo = new Proxy({}, {
  get: (_, name) => {
    const target = impl();
    const v = target[name];
    return typeof v === 'function' ? v.bind(target) : v;
  },
});

// Resultado de uma gravação que ficou na fila (sem resposta do servidor ainda)
export const queued = (r) => !!(r && r._queued);
export const QUEUED_MSG = 'Salvo no aparelho. Vai para o servidor quando a internet voltar.';
// Mensagem de sucesso que muda quando a alteração ficou na fila: run(fn, saved('Pronto.'))
export const saved = (msg, queuedMsg = QUEUED_MSG) => (r) => (queued(r) ? queuedMsg : msg);
