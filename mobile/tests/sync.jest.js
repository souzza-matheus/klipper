// Motor de sincronização offline (src/offline): banco SQLite real (node:sqlite) e servidor falso.
import { randomUUID } from 'node:crypto';
import { backoffDelay, BACKOFF_MAX, createEngine } from '../src/offline/engine';
import { createStore } from '../src/offline/store';
import { fakeServer } from './helpers/fakeServer';
import { openTestDb } from './helpers/sqlite';

async function setup() {
  const db = openTestDb();
  const store = createStore(db);
  await store.init();
  const server = fakeServer();
  const logs = [];
  const engine = createEngine({ store, transport: server.transport, uuid: randomUUID, batchSize: 2,
                                log: (...a) => logs.push(a) });
  return { db, store, server, engine, logs };
}

// Agendamento feito no aparelho (como o repositório local faz)
function book(engine, { start, barber = 'b1', name = 'Maria Cliente', phone = '5531999990000' }) {
  const id = randomUUID();
  return engine.submit({
    entity: 'appointments', action: 'create', id,
    data: { barber_id: barber, service_id: 's1', start, customer_phone: phone, customer_name: name },
    label: `Agendamento de ${name}`,
  }, (t) => t.put('appointments', { id, data: { id, start, barber_id: barber, status: 'scheduled' }, server: null }))
    .then((operationId) => ({ id, operationId }));
}

test('sem internet a operação fica na fila; ao reconectar sai na ordem em que foi feita', async () => {
  const { server, engine, store } = await setup();
  server.setOnline(false);
  const made = [];
  for (const h of ['09', '10', '11', '12', '13']) made.push(await book(engine, { start: `2030-01-07T${h}:00:00` }));
  const r = await engine.sync('interval');
  expect(r.ok).toBe(false);
  expect(await store.opCount()).toBe(5);
  expect(server.applied).toHaveLength(0);

  server.setOnline(true);
  expect((await engine.sync('network')).ok).toBe(true);
  expect(server.applied.map((o) => o.operation_id)).toEqual(made.map((m) => m.operationId));
  expect(await store.opCount()).toBe(0);
  // O pull trouxe a versão do servidor: deixou de ser "a confirmar"
  const row = await store.get('appointments', made[0].id);
  expect(row.server).not.toBeNull();
  expect(row.data.server_id).toBeGreaterThan(0);
});

test('resposta perdida: reenvia o mesmo operation_id e o servidor não aplica de novo', async () => {
  const { server, engine, store } = await setup();
  const { operationId } = await book(engine, { start: '2030-01-07T09:00:00' });
  server.loseNextResponse();
  expect((await engine.sync('write')).ok).toBe(false);
  expect(server.applied).toHaveLength(1);
  expect(await store.opCount()).toBe(1); // o aparelho não sabe que deu certo: continua na fila

  expect((await engine.sync('network')).ok).toBe(true);
  expect(server.applied).toHaveLength(1); // aplicado uma vez só
  expect(server.seen.get(operationId).status).toBe('aplicado');
  expect(await store.opCount()).toBe(0);
  expect(await store.attentionCount()).toBe(0);
});

test('conflito de horário vai para "Precisa da sua atenção" e desfaz o agendamento local', async () => {
  const { server, engine, store } = await setup();
  server.taken.add('b1|2030-01-07T14:00:00'); // alguém agendou pelo WhatsApp enquanto estava offline
  server.setOnline(false);
  const { id } = await book(engine, { start: '2030-01-07T14:00:00', name: 'João Offline' });
  // A comanda aberta para esse agendamento depende dele
  const comanda = randomUUID();
  await engine.submit({ entity: 'comandas', action: 'create', id: comanda, data: { appointment_id: id } },
    (t) => t.put('comandas', { id: comanda, data: { id: comanda, appointment_id: id, opened_at: '2030-01-07T14:00:00' },
                               server: null }));
  server.setOnline(true);
  await engine.sync('network');

  expect(await store.get('appointments', id)).toBeNull();
  expect(await store.get('comandas', comanda)).toBeNull();
  const [item] = await store.attention();
  expect(item).toMatchObject({ kind: 'conflict', reason: 'horario_ocupado', entity: 'appointments', rid: id,
                               label: 'Agendamento de João Offline', dropped: 1 });
  expect(item.op.data.start).toBe('2030-01-07T14:00:00'); // dá para refazer em outro horário
  expect(await store.opCount()).toBe(0);
  expect(server.applied).toHaveLength(0);
  await store.dismiss(item.id);
  expect(await store.attentionCount()).toBe(0);
});

test('exclusão: tombstone do servidor apaga no aparelho; exclusão local some na hora e é enviada', async () => {
  const { server, engine, store } = await setup();
  server.seed('blocks', { id: 'k1', start: '2030-01-07T12:00:00', end: '2030-01-07T13:00:00' });
  server.seed('blocks', { id: 'k2', start: '2030-01-08T12:00:00', end: '2030-01-08T13:00:00' });
  await engine.sync('open');
  expect((await store.all('blocks')).map((b) => b.id).sort()).toEqual(['k1', 'k2']);

  server.del('blocks', 'k1'); // excluído em outro aparelho
  await engine.sync('manual');
  expect(await store.get('blocks', 'k1')).toBeNull();

  server.setOnline(false);
  const row = await store.get('blocks', 'k2');
  await engine.submit({ entity: 'blocks', action: 'delete', id: 'k2' },
    (t) => t.put('blocks', { id: 'k2', data: row.data, server: row.server, deleted: true }));
  expect(await store.all('blocks')).toEqual([]); // escondido enquanto não sincroniza
  server.setOnline(true);
  await engine.sync('network');
  expect(await store.get('blocks', 'k2')).toBeNull();
  expect(server.records.blocks.k2).toBeUndefined();
});

test('outra pessoa entrando no aparelho apaga todos os dados locais', async () => {
  const { server, engine, store } = await setup();
  expect(await engine.ensureOwner('shop1:user1:owner')).toBe(false);
  server.seed('customers', { id: 'c1', name: 'Cliente', phone: '5531999990001' });
  await engine.sync('open');
  await book(engine, { start: '2030-01-07T09:00:00' });
  expect((await store.counts()).records).toBeGreaterThan(0);

  expect(await engine.ensureOwner('shop1:user1:owner')).toBe(false); // mesma pessoa: mantém
  expect(await store.get('customers', 'c1')).not.toBeNull();

  expect(await engine.ensureOwner('shop1:user2:reception')).toBe(true);
  const counts = await store.counts();
  expect(counts).toEqual({ records: 0, outbox: 0, attention: 0, meta: 1 });
  expect(await store.getMeta('cursor')).toBeNull(); // o próximo pull começa do zero
});

test('a alteração local e a operação da fila são gravadas na mesma transação', async () => {
  const { db, engine, store } = await setup();
  db.failOn(/INSERT INTO outbox/);
  await expect(book(engine, { start: '2030-01-07T09:00:00' })).rejects.toThrow('falha simulada');
  expect(await store.all('appointments')).toEqual([]); // não ficou registro sem operação
  expect(await store.opCount()).toBe(0);
});

test('comanda aberta em dois aparelhos: o app passa a usar a do servidor e reenvia os itens', async () => {
  const { server, engine, store } = await setup();
  // Outro aparelho já abriu a comanda desse atendimento no servidor
  server.seed('appointments', { id: 'a1', start: '2030-01-07T09:00:00', barber_id: 'b1' });
  await server.transport.push([{ operation_id: randomUUID(), entity: 'comandas', action: 'create', id: 'srv-c2',
                                 data: { appointment_id: 'a1' } }]);
  server.setOnline(false);
  const local = randomUUID();
  await engine.submit({ entity: 'comandas', action: 'create', id: local, data: { appointment_id: 'a1' } },
    (t) => t.put('comandas', { id: local, data: { id: local, appointment_id: 'a1', opened_at: '2030-01-07T09:00:00' },
                               server: null }));
  const item = randomUUID();
  await engine.submit({ entity: 'comanda_items', action: 'create', id: item, data: { comanda_id: local, kind: 'tip' } },
    (t) => t.put('comanda_items', { id: item, data: { id: item, comanda_id: local, kind: 'tip' }, server: null }));
  server.setOnline(true);
  await engine.sync('network');
  expect(await store.attentionCount()).toBe(0);
  expect(await store.opCount()).toBe(0);
  expect(await store.get('comandas', local)).toBeNull();
  expect(server.records.comanda_items[item].comanda_id).toBe('srv-c2');
  expect((await store.get('comanda_items', item)).data.comanda_id).toBe('srv-c2');
});

test('quem está com a tela aberta recebe a resposta na hora e não cai na lista de atenção', async () => {
  const { server, engine, store } = await setup();
  server.taken.add('b1|2030-01-07T15:00:00');
  const { operationId } = await book(engine, { start: '2030-01-07T15:00:00' });
  const waiting = engine.waitFor(operationId, 2000);
  await engine.sync('write');
  expect(await waiting).toMatchObject({ status: 'conflito', reason: 'horario_ocupado' });
  expect(await store.attentionCount()).toBe(0);
  expect(await store.all('appointments')).toEqual([]);
});

test('pull paginado: traz tudo uma vez e guarda o cursor', async () => {
  const { server, engine, store } = await setup();
  for (let i = 0; i < 7; i += 1) server.seed('customers', { id: `c${i}`, name: `C ${i}`, phone: `55319999900${i}` });
  await engine.sync('open');
  expect(await store.all('customers')).toHaveLength(7);
  expect(await store.getMeta('cursor')).toBe('7');
  expect(await store.getMeta('last_sync')).not.toBeNull();
});

test('espera crescente entre tentativas; volta da internet tenta na hora', async () => {
  expect([1, 2, 3, 4].map(backoffDelay)).toEqual([5000, 10000, 20000, 40000]);
  expect(backoffDelay(30)).toBe(BACKOFF_MAX);
  const { server, engine } = await setup();
  server.setOnline(false);
  await book(engine, { start: '2030-01-07T09:00:00' });
  expect((await engine.sync('interval')).ok).toBe(false);
  expect((await engine.sync('interval')).skipped).toBe(true); // ainda dentro da espera
  expect((await engine.status()).failures).toBe(1);
  server.setOnline(true);
  expect((await engine.sync('network')).ok).toBe(true);
  expect((await engine.status())).toMatchObject({ failures: 0, pending: 0 });
});

test('o log não recebe dados de clientes', async () => {
  const { server, engine, logs } = await setup();
  server.seed('customers', { id: 'c1', name: 'Fulana Sigilosa', phone: '5531988887777' });
  server.taken.add('b1|2030-01-07T16:00:00');
  await book(engine, { start: '2030-01-07T16:00:00', name: 'Fulana Sigilosa', phone: '5531988887777' });
  server.setOnline(false);
  await engine.sync('write');
  server.setOnline(true);
  await engine.sync('network');
  const text = JSON.stringify(logs);
  expect(logs.length).toBeGreaterThan(0);
  expect(text).not.toMatch(/Fulana|Sigilosa|988887777/);
});

test('uma vez por dia o pull recomeça do zero (a janela da agenda anda com o calendário)', async () => {
  const { server, store } = await setup();
  let day = new Date(2030, 0, 7, 9);
  const cursors = [];
  const pull = server.transport.pull;
  const engine = createEngine({ store, uuid: randomUUID, now: () => day,
                                transport: { ...server.transport, pull: (c) => { cursors.push(c); return pull(c); } } });
  server.seed('customers', { id: 'c1', name: 'A', phone: '1' });
  await engine.sync('open');
  await engine.sync('manual');
  expect(cursors).toEqual(['0', '1']); // mesmo dia: incremental
  day = new Date(2030, 0, 8, 9);
  await engine.sync('manual');
  expect(cursors[cursors.length - 1]).toBe('0'); // dia seguinte: completo
  expect(await store.getMeta('full_pull_day')).toBe('2030-01-08');
});
