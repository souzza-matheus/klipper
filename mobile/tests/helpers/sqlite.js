// SQLite do próprio Node (node:sqlite) com a interface do expo-sqlite, para testar o banco local de verdade
const { DatabaseSync } = process.getBuiltinModule('node:sqlite');

function api(db) {
  const h = {
    async execAsync(sql) { db.exec(sql); },
    async runAsync(sql, params = []) {
      const r = db.prepare(sql).run(...params);
      return { lastInsertRowId: Number(r.lastInsertRowid), changes: Number(r.changes) };
    },
    async getAllAsync(sql, params = []) { return db.prepare(sql).all(...params).map((r) => ({ ...r })); },
    async getFirstAsync(sql, params = []) {
      const r = db.prepare(sql).get(...params);
      return r ? { ...r } : null;
    },
  };
  return h;
}

export function openTestDb() {
  const db = new DatabaseSync(':memory:');
  let failNext = null;
  const base = api(db);
  return {
    ...base,
    async runAsync(sql, params) {
      if (failNext && failNext.test(sql)) { // simula uma falha de gravação
        failNext = null;
        throw new Error('falha simulada');
      }
      return base.runAsync(sql, params);
    },
    // O app não usa withExclusiveTransactionAsync (abre outra conexão, sem a chave do SQLCipher)
    async withExclusiveTransactionAsync() { throw new Error('não use: abre outra conexão sem a chave'); },
    failOn(re) { failNext = re; },
    raw: db,
  };
}
