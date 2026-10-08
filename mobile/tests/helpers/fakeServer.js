// Servidor de sincronização falso, com as mesmas regras do backend que importam para o app:
// operation_id idempotente, ordem, conflito de horário, comanda já aberta, cursor e tombstones.
export function fakeServer() {
  const seen = new Map(); // operation_id -> resultado (reenvio devolve o mesmo)
  const applied = []; // operações executadas de verdade, em ordem
  const records = {}; // entity -> id -> registro
  const log = []; // [seq, entity, id | null, deleted]
  let seq = 0;
  let online = true;
  let loseNextResponse = false;
  const taken = new Set(); // horários ocupados (barber|start)
  const comandaByAppt = new Map();

  const save = (entity, obj) => {
    seq += 1;
    records[entity] = records[entity] || {};
    const prev = records[entity][obj.id];
    const row = { ...prev, ...obj, version: (prev?.version || 0) + 1, server_id: prev?.server_id || seq };
    records[entity][obj.id] = row;
    log.push([seq, entity, obj.id, false]);
    return row;
  };
  const remove = (entity, id) => {
    seq += 1;
    delete records[entity][id];
    log.push([seq, entity, id, true]);
  };

  function apply(op) {
    const d = op.data || {};
    if (op.entity === 'appointments' && op.action === 'create') {
      const key = `${d.barber_id}|${d.start}`;
      if (taken.has(key)) {
        return { status: 'conflito', reason: 'horario_ocupado', message: 'Esse horário foi ocupado.' };
      }
      taken.add(key);
      return { status: 'aplicado', server: save('appointments', { id: op.id, ...d, status: 'scheduled' }) };
    }
    if (op.entity === 'comandas' && op.action === 'create') {
      if (d.appointment_id && !records.appointments?.[d.appointment_id] && !comandaByAppt.has(d.appointment_id)) {
        return { status: 'rejeitado', reason: 'nao_encontrado', message: 'appointment_id: registro não encontrado.' };
      }
      if (d.appointment_id && comandaByAppt.has(d.appointment_id)) {
        return { status: 'conflito', reason: 'comanda_ja_aberta', message: 'Já aberta.',
                 server: records.comandas[comandaByAppt.get(d.appointment_id)] };
      }
      if (d.appointment_id) comandaByAppt.set(d.appointment_id, op.id);
      return { status: 'aplicado', server: save('comandas', { id: op.id, ...d, status: 'open' }) };
    }
    if (op.entity === 'comanda_items' && op.action === 'create') {
      if (!records.comandas?.[d.comanda_id]) {
        return { status: 'rejeitado', reason: 'nao_encontrado', message: 'comanda_id: registro não encontrado.' };
      }
      return { status: 'aplicado', server: save('comanda_items', { id: op.id, ...d }) };
    }
    if (op.entity === 'blocks' && op.action === 'delete') {
      const b = records.blocks?.[op.id];
      if (!b) return { status: 'rejeitado', reason: 'nao_encontrado', message: 'id: registro não encontrado.' };
      remove('blocks', op.id);
      return { status: 'aplicado', server: b };
    }
    const rec = records[op.entity]?.[op.id];
    if (op.action === 'update' && rec) return { status: 'aplicado', server: save(op.entity, { id: op.id, ...d }) };
    if (op.action === 'create') return { status: 'aplicado', server: save(op.entity, { id: op.id, ...d }) };
    return { status: 'rejeitado', reason: 'nao_encontrado', message: 'id: registro não encontrado.' };
  }

  const netError = () => Object.assign(new Error('Sem conexão com o servidor.'), { status: 0 });

  return {
    records, applied, seen, taken,
    setOnline(v) { online = v; },
    loseNextResponse() { loseNextResponse = true; },
    seed(entity, obj) { return save(entity, obj); },
    del(entity, id) { remove(entity, id); },
    transport: {
      async push(ops) {
        if (!online) throw netError();
        const results = ops.map((op) => {
          if (seen.has(op.operation_id)) return { ...seen.get(op.operation_id), replayed: true };
          const r = { operation_id: op.operation_id, entity: op.entity, action: op.action, id: op.id, ...apply(op) };
          if (r.status === 'aplicado') applied.push(op);
          seen.set(op.operation_id, r);
          return r;
        });
        if (loseNextResponse) { // o servidor gravou, mas a resposta não chegou ao aparelho
          loseNextResponse = false;
          throw netError();
        }
        return results;
      },
      async pull(cursor, limit = 3) {
        if (!online) throw netError();
        const after = log.filter(([s]) => s > Number(cursor));
        const page = after.slice(0, limit);
        const changes = {};
        const deleted = {};
        for (const [, entity, id, gone] of page) {
          if (gone) (deleted[entity] = deleted[entity] || []).push(id);
          else if (records[entity]?.[id]) (changes[entity] = changes[entity] || []).push(records[entity][id]);
        }
        const last = page.length ? page[page.length - 1][0] : Number(cursor);
        return { cursor: String(last), has_more: after.length > page.length, changes, deleted };
      },
    },
  };
}
