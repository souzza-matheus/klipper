// Banco local do modo offline (SQLite; no celular, criptografado com SQLCipher: ver db.js).
//
// Funciona sobre qualquer "driver" com a interface do expo-sqlite (execAsync, runAsync, getAllAsync,
// getFirstAsync). Nos testes, o driver é o SQLite do Node.
//
// Transações: na MESMA conexão (a que recebeu a chave do SQLCipher), uma por vez. Não usamos o
// withExclusiveTransactionAsync do expo-sqlite porque ele abre outra conexão, que não teria a chave.
//
// Tabelas:
// - records: uma linha por registro sincronizado (agendamento, cliente, comanda...). `data` é o que o app mostra
//   (com as alterações locais ainda não enviadas); `server` é a última versão confirmada pelo servidor (null =
//   criado no aparelho). `op` marca linhas provisórias que só existem até a operação dela ser respondida (ex.: o
//   serviço que o servidor lança sozinho ao abrir a comanda). `deleted` = excluído aqui, aguardando envio.
// - outbox: operações pendentes, em ordem, cada uma com operation_id (UUID) único. É gravada na MESMA transação
//   da alteração local: ou as duas ficam, ou nenhuma.
// - attention: o que voltou com conflito ou recusa e precisa de alguém olhar ("Precisa da sua atenção").
// - meta: cursor do pull, dono do banco, última sincronização.

const SCHEMA = `
CREATE TABLE IF NOT EXISTS records (
  entity TEXT NOT NULL, id TEXT NOT NULL, sid INTEGER, k TEXT, data TEXT NOT NULL, server TEXT, op TEXT,
  deleted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (entity, id));
CREATE INDEX IF NOT EXISTS records_k ON records (entity, k);
CREATE INDEX IF NOT EXISTS records_sid ON records (entity, sid);
CREATE INDEX IF NOT EXISTS records_op ON records (op);
CREATE TABLE IF NOT EXISTS outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL UNIQUE, entity TEXT NOT NULL,
  action TEXT NOT NULL, rid TEXT, version INTEGER, data TEXT NOT NULL, base TEXT NOT NULL, label TEXT,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS outbox_rid ON outbox (rid);
CREATE TABLE IF NOT EXISTS attention (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, entity TEXT, action TEXT, rid TEXT,
  reason TEXT, message TEXT, label TEXT, op TEXT, server TEXT, dropped INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
`;

export const TABLES = ['records', 'outbox', 'attention', 'meta'];

// Chave indexada de cada entidade (consultas por dia, por comanda, por produto...)
const KEY_FIELD = {
  appointments: 'start', blocks: 'start', comandas: 'opened_at', comanda_items: 'comanda_id',
  comanda_payments: 'comanda_id', stock_movements: 'product_id', package_uses: 'customer_package_id',
  subscription_uses: 'subscription_id', customer_packages: 'customer_id', subscriptions: 'customer_id',
  waitlist_entries: 'day', customers: 'phone',
};
export const keyOf = (entity, data) => {
  const f = KEY_FIELD[entity];
  return f && data[f] != null ? String(data[f]) : null;
};

const parse = (s) => (s == null ? null : JSON.parse(s));
const json = (v) => (v == null ? null : JSON.stringify(v));

function rowOut(r) {
  if (!r) return null;
  return { entity: r.entity, id: r.id, sid: r.sid, data: parse(r.data), server: parse(r.server), op: r.op,
           deleted: !!r.deleted };
}

const opOut = (r) => r && ({
  seq: r.seq, operation_id: r.operation_id, entity: r.entity, action: r.action, id: r.rid, version: r.version,
  data: parse(r.data), base: parse(r.base), label: r.label, created_at: r.created_at,
});

// Métodos sobre um "handle" (o banco ou a transação em andamento)
function bind(h) {
  const s = {
    async get(entity, id) {
      return rowOut(await h.getFirstAsync('SELECT * FROM records WHERE entity = ? AND id = ?', [entity, String(id)]));
    },
    async getBySid(entity, sid) {
      return rowOut(await h.getFirstAsync('SELECT * FROM records WHERE entity = ? AND sid = ?', [entity, Number(sid)]));
    },
    async all(entity, { withDeleted = false } = {}) {
      const rows = await h.getAllAsync(`SELECT * FROM records WHERE entity = ?${withDeleted ? '' : ' AND deleted = 0'}`,
        [entity]);
      return rows.map(rowOut);
    },
    // k entre from e to (inclusive), ou igual a from quando to é omitido
    async byK(entity, from, to) {
      const rows = to === undefined
        ? await h.getAllAsync('SELECT * FROM records WHERE entity = ? AND k = ? AND deleted = 0', [entity, from])
        : await h.getAllAsync('SELECT * FROM records WHERE entity = ? AND k >= ? AND k <= ? AND deleted = 0',
          [entity, from, to]);
      return rows.map(rowOut);
    },
    async put(entity, { id, data, server, op = null, deleted = false }) {
      const d = { ...data, id: String(id) };
      await h.runAsync(
        `INSERT INTO records (entity, id, sid, k, data, server, op, deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (entity, id) DO UPDATE SET sid = excluded.sid, k = excluded.k, data = excluded.data,
           server = excluded.server, op = excluded.op, deleted = excluded.deleted`,
        [entity, String(id), d.server_id ?? server?.server_id ?? null, keyOf(entity, d), json(d), json(server), op,
         deleted ? 1 : 0]);
    },
    async remove(entity, id) {
      await h.runAsync('DELETE FROM records WHERE entity = ? AND id = ?', [entity, String(id)]);
    },
    async removeWhereK(entity, k) {
      await h.runAsync('DELETE FROM records WHERE entity = ? AND k = ?', [entity, String(k)]);
    },
    async removeByOp(operationId) {
      await h.runAsync('DELETE FROM records WHERE op = ?', [operationId]);
    },
    async removeOlder(entity, before) {
      // Não apaga o que ainda tem alteração local pendente
      await h.runAsync(`DELETE FROM records WHERE entity = ? AND k < ? AND op IS NULL AND server IS NOT NULL
        AND id NOT IN (SELECT rid FROM outbox WHERE rid IS NOT NULL)`, [entity, before]);
    },
    // Troca um id local pelo do servidor em todos os registros que o citam (ex.: comanda aberta em dois aparelhos)
    async replaceRef(fromId, toId) {
      const rows = await h.getAllAsync('SELECT entity, id, data FROM records WHERE data LIKE ?', [`%${fromId}%`]);
      for (const r of rows) {
        const d = JSON.parse(r.data.split(fromId).join(toId));
        await h.runAsync('UPDATE records SET data = ?, k = ? WHERE entity = ? AND id = ?',
          [JSON.stringify(d), keyOf(r.entity, d), r.entity, r.id]);
      }
    },

    // ------------------------------------------------ outbox
    async addOp(o) {
      await h.runAsync(
        `INSERT INTO outbox (operation_id, entity, action, rid, version, data, base, label, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [o.operation_id, o.entity, o.action, o.id ?? null, o.version ?? null, json(o.data || {}), json(o.base || {}),
         o.label || '', o.created_at]);
    },
    async ops(limit = 50) {
      return (await h.getAllAsync('SELECT * FROM outbox ORDER BY seq LIMIT ?', [limit])).map(opOut);
    },
    async opCount() {
      return (await h.getFirstAsync('SELECT COUNT(*) AS n FROM outbox')).n;
    },
    async pendingIds() {
      return new Set((await h.getAllAsync('SELECT DISTINCT rid FROM outbox WHERE rid IS NOT NULL')).map((r) => r.rid));
    },
    async hasPending(rid, exceptOperationId = '') {
      return !!(await h.getFirstAsync('SELECT 1 AS x FROM outbox WHERE rid = ? AND operation_id != ? LIMIT 1',
        [String(rid), exceptOperationId]));
    },
    async deleteOp(operationId) {
      await h.runAsync('DELETE FROM outbox WHERE operation_id = ?', [operationId]);
    },
    // Reenvio depois de trocar um id: operation_id novo (o antigo já tem resposta guardada no servidor)
    async rewriteOp(oldOperationId, { operation_id, id, data }) {
      await h.runAsync('UPDATE outbox SET operation_id = ?, rid = ?, data = ? WHERE operation_id = ?',
        [operation_id, id ?? null, json(data), oldOperationId]);
    },
    async opsMentioning(id) {
      return (await h.getAllAsync('SELECT * FROM outbox WHERE rid = ? OR data LIKE ? ORDER BY seq',
        [String(id), `%${id}%`])).map(opOut);
    },

    // ------------------------------------------------ atenção
    async addAttention(a) {
      await h.runAsync(
        `INSERT OR REPLACE INTO attention (id, created_at, kind, entity, action, rid, reason, message, label, op, server,
          dropped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [a.id, a.created_at, a.kind, a.entity, a.action, a.rid ?? null, a.reason || '', a.message || '',
         a.label || '', json(a.op), json(a.server), a.dropped || 0]);
    },
    async bumpDropped(id, n = 1) {
      await h.runAsync('UPDATE attention SET dropped = dropped + ? WHERE id = ?', [n, id]);
    },
    async attention() {
      const rows = await h.getAllAsync('SELECT * FROM attention ORDER BY created_at DESC');
      return rows.map((r) => ({ ...r, op: parse(r.op), server: parse(r.server) }));
    },
    async attentionCount() {
      return (await h.getFirstAsync('SELECT COUNT(*) AS n FROM attention')).n;
    },
    async dismiss(id) {
      await h.runAsync('DELETE FROM attention WHERE id = ?', [id]);
    },

    // ------------------------------------------------ meta
    async getMeta(key) {
      return (await h.getFirstAsync('SELECT value FROM meta WHERE key = ?', [key]))?.value ?? null;
    },
    async setMeta(key, value) {
      await h.runAsync('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', [key, value == null ? null : String(value)]);
    },
  };
  return s;
}

// Fila: uma operação no banco por vez (transação inteira ou consulta solta)
function mutex() {
  let tail = Promise.resolve();
  return (fn) => {
    const run = tail.then(fn, fn);
    tail = run.then(() => {}, () => {});
    return run;
  };
}

export function createStore(db) {
  const exclusive = mutex();
  const inner = bind(db);
  // Fora de transação, cada método espera a vez (não entra no meio de uma transação aberta)
  const outer = Object.fromEntries(Object.entries(inner).map(([k, fn]) => [k, (...a) => exclusive(() => fn(...a))]));
  const store = {
    ...outer,
    db,
    async init() {
      await exclusive(() => db.execAsync(SCHEMA));
    },
    // Tudo dentro de fn é atômico. Dentro de fn, use só o `t` recebido (o store de fora espera a transação acabar).
    tx(fn) {
      return exclusive(async () => {
        await db.execAsync('BEGIN IMMEDIATE');
        try {
          const out = await fn(inner);
          await db.execAsync('COMMIT');
          return out;
        } catch (e) {
          await db.execAsync('ROLLBACK');
          throw e;
        }
      });
    },
    // Apaga todos os dados (o arquivo e a chave são apagados em db.js; aqui é o conteúdo)
    wipe() {
      return exclusive(() => db.execAsync(TABLES.map((t) => `DELETE FROM ${t};`).join('\n')));
    },
    async counts() {
      const out = {};
      for (const t of TABLES) out[t] = (await exclusive(() => db.getFirstAsync(`SELECT COUNT(*) AS n FROM ${t}`))).n;
      return out;
    },
  };
  return store;
}
