// Motor de sincronização do modo offline. Sem dependência de React Native: testado no Jest (tests/*.jest.js).
//
// - push: envia a outbox em ordem (lotes), com o MESMO operation_id até o servidor responder. Se a resposta se
//   perder, o reenvio devolve o resultado guardado no servidor (idempotente): nada é aplicado duas vezes.
// - pull: busca as mudanças depois do cursor, página por página; exclusões chegam como tombstones.
// - conflito ou recusa: desfaz a alteração local e registra em "Precisa da sua atenção" (com as alterações que
//   dependiam dela). Quem está com a tela aberta e online recebe a resposta na hora (waitFor) e vê o erro ali.
// - falha de rede: tenta de novo com espera crescente (5 s, 10 s, 20 s... até 5 min).
//
// LGPD: o log recebe só eventos e contagens, nunca nome, telefone ou outros dados de clientes.

export const APPLIED = 'aplicado';
export const REJECTED = 'rejeitado';
export const CONFLICT = 'conflito';

// Conflitos em que o servidor já tem o registro "certo": o app troca o id local pelo do servidor e segue
const REMAP = new Set(['comanda_ja_aberta', 'cliente_ja_existe', 'ja_na_lista']);
// Gatilhos que ignoram a espera entre tentativas (alguém pediu, ou a internet acabou de voltar)
const URGENT = new Set(['manual', 'network', 'write', 'open']);

export const BACKOFF_BASE = 5000;
export const BACKOFF_MAX = 5 * 60000;
export const backoffDelay = (failures) => (failures <= 0 ? 0
  : Math.min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (failures - 1)));

const pad = (n) => String(n).padStart(2, '0');
export function localISO(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
    + `:${pad(d.getSeconds())}`;
}
const dayISO = (d) => localISO(d).slice(0, 10);

const isNetwork = (e) => !e || e.status === undefined || e.status === 0 || e.status >= 500 || e.status === 429;

export function createEngine({
  store, transport, uuid, now = () => new Date(), log = () => {}, batchSize = 50,
  window = { back: 30, ahead: 60 },
}) {
  let running = null;
  let again = false;
  let failures = 0;
  let nextRetryAt = 0;
  let lastError = '';
  const waiters = new Map();
  const listeners = new Set();

  const emit = (changed) => listeners.forEach((fn) => { try { fn(changed); } catch (e) { /* tela fechada */ } });

  function mentions(op, ids) {
    if (!ids.size) return false;
    if (op.id && ids.has(op.id)) return true;
    const text = JSON.stringify(op.data || {});
    for (const id of ids) if (text.includes(id)) return true;
    return false;
  }

  // Desfaz no aparelho o efeito de uma operação que o servidor não aceitou
  async function revert(t, op, server) {
    await t.removeByOp(op.operation_id);
    if (!op.id) return;
    if (server && server.id === op.id) {
      if (!(await t.hasPending(op.id, op.operation_id))) await t.put(op.entity, { id: op.id, data: server, server });
      return;
    }
    const row = await t.get(op.entity, op.id);
    if (op.action === 'create' || (row && !row.server)) {
      await t.remove(op.entity, op.id);
    } else if (row) {
      await t.put(op.entity, { id: op.id, data: row.server, server: row.server });
    }
  }

  async function applyServer(t, entity, op, server) {
    await t.removeByOp(op.operation_id);
    if (!server) return;
    if (op.action === 'delete') {
      await t.remove(entity, server.id);
      return;
    }
    const pending = await t.hasPending(server.id, op.operation_id);
    const row = await t.get(entity, server.id);
    await t.put(entity, { id: server.id, data: pending && row ? row.data : server, server });
  }

  // Processa as respostas de um lote, na ordem em que as operações foram feitas
  async function handleResults(ops, results) {
    const byOp = new Map(results.map((r) => [r.operation_id, r]));
    const dead = new Map(); // id local que não existe no servidor -> id da entrada de atenção
    const remapped = new Map(); // id local -> id do servidor
    let changed = false;
    await store.tx(async (t) => {
      for (const op of ops) {
        const res = byOp.get(op.operation_id);
        if (!res) continue; // sem resposta: fica na outbox e vai de novo
        changed = true;
        const waiter = waiters.get(op.operation_id);
        if (res.status === APPLIED) {
          await applyServer(t, res.entity || op.entity, op, res.server);
          await t.deleteOp(op.operation_id);
          if (waiter) waiter(res);
          continue;
        }
        // Dependia de um id que foi trocado pelo do servidor: reenvia já com o id certo
        const swap = [...remapped.keys()].find((id) => mentions(op, new Set([id])));
        if (swap && res.reason === 'nao_encontrado') {
          const to = remapped.get(swap);
          const data = JSON.parse(JSON.stringify(op.data || {}).split(swap).join(to));
          await t.rewriteOp(op.operation_id, { operation_id: uuid(), id: op.id === swap ? to : op.id, data });
          continue;
        }
        // Dependia de algo que o servidor recusou: cai junto, contado na mesma entrada de atenção
        const root = [...dead.keys()].find((id) => mentions(op, new Set([id])));
        if (root) {
          await revert(t, op, null);
          await t.deleteOp(op.operation_id);
          await t.bumpDropped(dead.get(root));
          if (op.id && op.action === 'create') dead.set(op.id, dead.get(root));
          if (waiter) waiter(res);
          continue;
        }
        if (res.status === CONFLICT && REMAP.has(res.reason) && res.server?.id && op.id) {
          remapped.set(op.id, res.server.id);
          await t.removeByOp(op.operation_id);
          await t.remove(op.entity, op.id);
          await t.put(op.entity, { id: res.server.id, data: res.server, server: res.server });
          await t.replaceRef(op.id, res.server.id);
          await t.deleteOp(op.operation_id);
          // Operações que ainda não foram enviadas passam a usar o id do servidor
          for (const later of await t.opsMentioning(op.id)) {
            const data = JSON.parse(JSON.stringify(later.data || {}).split(op.id).join(res.server.id));
            await t.rewriteOp(later.operation_id, { operation_id: later.operation_id,
                                                    id: later.id === op.id ? res.server.id : later.id, data });
          }
          if (waiter) waiter({ ...res, status: APPLIED, remapped: true });
          continue;
        }
        await revert(t, op, res.server);
        await t.deleteOp(op.operation_id);
        if (op.id && op.action === 'create') dead.set(op.id, op.operation_id);
        if (waiter) {
          waiter(res); // a tela aberta mostra o erro na hora; não precisa ir para a lista de atenção
        } else {
          await t.addAttention({
            id: op.operation_id, created_at: localISO(now()), kind: res.status === CONFLICT ? 'conflict' : 'rejected',
            entity: op.entity, action: op.action, rid: op.id, reason: res.reason, message: res.message,
            label: op.label, op, server: res.server || null,
          });
        }
      }
      // Operações ainda na fila que dependem de algo recusado neste lote
      for (const [id, attentionId] of dead) {
        for (const later of await t.opsMentioning(id)) {
          await revert(t, later, null);
          await t.deleteOp(later.operation_id);
          await t.bumpDropped(attentionId); // sem entrada (a tela mostrou o erro): não faz nada
        }
      }
    });
    return changed;
  }

  async function push() {
    let sent = 0;
    let changed = false;
    for (;;) {
      const ops = await store.ops(batchSize);
      if (!ops.length) break;
      let results;
      try {
        results = await transport.push(ops.map(({ operation_id, entity, action, id, version, data, base }) => ({
          operation_id, entity, action, id, version, data, base })));
      } catch (e) {
        if (!isNetwork(e) && e.status !== 401 && e.status >= 400 && e.status < 500) {
          // Lote recusado inteiro (dado malformado): a primeira operação sai da fila para não travar as outras
          const [bad] = ops;
          results = [{ operation_id: bad.operation_id, entity: bad.entity, status: REJECTED,
                       reason: 'dados_invalidos', message: e.message || 'Dados inválidos.' }];
        } else {
          throw e;
        }
      }
      changed = (await handleResults(ops, results || [])) || changed;
      sent += ops.length;
      if (!results || !results.length) break;
    }
    if (sent) log('push', { operations: sent });
    return changed;
  }

  async function prune(t) {
    const today = now();
    const from = new Date(today.getFullYear(), today.getMonth(), today.getDate() - window.back);
    const fromISO = dayISO(from);
    await t.removeOlder('appointments', fromISO);
    for (const c of await t.all('comandas')) {
      if (c.server && c.data.opened_at < fromISO && !(await t.hasPending(c.id))) {
        await t.removeWhereK('comanda_items', c.id);
        await t.removeWhereK('comanda_payments', c.id);
        await t.remove('comandas', c.id);
      }
    }
    for (const b of await t.all('blocks')) {
      if (b.server && b.data.end < fromISO) await t.remove('blocks', b.id);
    }
  }

  async function pull() {
    // Uma vez por dia, do zero: a janela da agenda anda com o calendário, e o pull incremental só traz o que mudou
    const today = dayISO(now());
    const full = (await store.getMeta('full_pull_day')) !== today;
    let cursor = full ? '0' : (await store.getMeta('cursor')) || '0';
    let rows = 0;
    for (;;) {
      const page = await transport.pull(cursor);
      await store.tx(async (t) => {
        const pending = await t.pendingIds();
        for (const [entity, list] of Object.entries(page.changes || {})) {
          for (const server of list) {
            const row = pending.has(server.id) ? await t.get(entity, server.id) : null;
            // Com alteração local ainda na fila, a tela continua mostrando a versão local
            await t.put(entity, { id: server.id, data: row ? row.data : server, server, deleted: row?.deleted });
            rows += 1;
          }
        }
        for (const [entity, ids] of Object.entries(page.deleted || {})) {
          for (const id of ids) {
            await t.remove(entity, id);
            rows += 1;
          }
        }
        await t.setMeta('cursor', page.cursor);
        if (!page.has_more) {
          await prune(t);
          if (full) await t.setMeta('full_pull_day', today);
        }
      });
      cursor = page.cursor;
      if (!page.has_more) break;
    }
    if (rows) log('pull', { rows });
    return rows > 0;
  }

  async function run() {
    do {
      again = false;
      const pushed = await push();
      const pulled = await pull();
      if (pushed || pulled) emit(true);
    } while (again);
  }

  const engine = {
    // Sincroniza agora (uma por vez; quem chamar no meio espera a mesma rodada e pede outra)
    sync(reason = 'manual') {
      if (running) {
        again = true;
        return running;
      }
      if (!URGENT.has(reason) && Date.now() < nextRetryAt) return Promise.resolve({ skipped: true });
      running = (async () => {
        try {
          await run();
          failures = 0;
          nextRetryAt = 0;
          lastError = '';
          await store.setMeta('last_sync', localISO(now()));
          return { ok: true };
        } catch (e) {
          if (e && e.status === 401) {
            lastError = 'auth';
            throw e;
          }
          failures += 1;
          nextRetryAt = Date.now() + backoffDelay(failures);
          lastError = isNetwork(e) ? 'network' : 'server';
          log('sync-failed', { failures, kind: lastError });
          return { ok: false, retryIn: backoffDelay(failures) };
        } finally {
          running = null;
          emit(false);
        }
      })();
      return running;
    },

    // Espera a resposta de uma operação (tela aberta). null = ainda sem resposta (fica na fila)
    waitFor(operationId, ms) {
      return new Promise((resolve) => {
        const timer = setTimeout(() => { waiters.delete(operationId); resolve(null); }, ms);
        waiters.set(operationId, (res) => { clearTimeout(timer); waiters.delete(operationId); resolve(res); });
      });
    },

    // Grava a alteração local e a operação juntas (mesma transação)
    async submit({ entity, action, id, version, data, base, label }, applyLocal) {
      const operationId = uuid();
      await store.tx(async (t) => {
        if (applyLocal) await applyLocal(t, operationId);
        await t.addOp({ operation_id: operationId, entity, action, id, version, data, base, label,
                        created_at: localISO(now()) });
      });
      emit(true);
      return operationId;
    },

    // Banco de outra pessoa (ou de outro papel) neste aparelho: apaga tudo antes de usar
    async ensureOwner(identity) {
      const owner = await store.getMeta('owner');
      if (owner && owner === identity) return false;
      await store.wipe();
      await store.setMeta('owner', identity);
      if (owner) log('wiped', { reason: 'owner-changed' });
      return !!owner;
    },

    async status() {
      return {
        pending: await store.opCount(), attention: await store.attentionCount(),
        lastSync: await store.getMeta('last_sync'), running: !!running, lastError, failures, nextRetryAt,
      };
    },

    onChange(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
  return engine;
}
