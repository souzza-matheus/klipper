// Repositório local do celular (src/repo.local.js) de ponta a ponta: banco SQLite real, motor de sincronização
// real e um servidor falso. Simula só o que é nativo (rede, API, gerador de uuid).
import { randomUUID } from 'node:crypto';
import { createEngine } from '../src/offline/engine';
import { createStore } from '../src/offline/store';
import { openTestDb } from './helpers/sqlite';

const mockNet = { online: true };
const mockCtx = {};
jest.mock('expo-crypto', () => ({ randomUUID: () => require('node:crypto').randomUUID() }));
jest.mock('../src/net', () => ({ isOnline: () => mockNet.online }));
jest.mock('../src/offline/manager', () => ({ ctx: {
  store: () => mockCtx.store, engine: () => mockCtx.engine, session: () => mockCtx.session,
  version: () => mockCtx.version, bump: () => { mockCtx.version += 1; },
} }));
jest.mock('../src/api', () => {
  class ApiError extends Error {
    constructor(message, status, data) { super(message); this.status = status; this.data = data; }
  }
  return { ApiError, api: { get: () => Promise.reject(new ApiError('offline', 0)) } };
});

// eslint-disable-next-line import/first
import { local as repo } from '../src/repo.local';

const DAY = (() => { // próxima segunda-feira
  const d = new Date();
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
})();

// Servidor falso com as regras que importam aqui
function server() {
  const db = {};
  const log = [];
  let seq = 0;
  let sid = 100;
  const save = (entity, row) => {
    seq += 1;
    db[entity] = db[entity] || {};
    const prev = db[entity][row.id];
    db[entity][row.id] = { ...prev, ...row, server_id: prev?.server_id || (sid += 1), version: (prev?.version || 0) + 1 };
    log.push([seq, entity, row.id]);
    return db[entity][row.id];
  };
  const all = (e) => Object.values(db[e] || {});
  const handlers = {
    'appointments.create': (op) => {
      const d = op.data;
      const svc = db.services[d.service_id];
      const end = new Date(new Date(d.start).getTime() + svc.duration_minutes * 60000);
      const pad = (n) => String(n).padStart(2, '0');
      const endISO = `${d.start.slice(0, 11)}${pad(end.getHours())}:${pad(end.getMinutes())}:00`;
      if (all('appointments').some((a) => a.barber_id === d.barber_id && a.status !== 'cancelled'
        && a.start < endISO && a.end > d.start)) {
        return { status: 'conflito', reason: 'horario_ocupado', message: 'Esse horário foi ocupado.' };
      }
      let cust = d.customer_id ? db.customers[d.customer_id] : all('customers').find((c) => c.phone === d.customer_phone);
      if (!cust) cust = save('customers', { id: randomUUID(), name: d.customer_name, phone: d.customer_phone });
      return { status: 'aplicado', server: save('appointments', { id: op.id, start: d.start, end: endISO,
        status: 'scheduled', barber_id: d.barber_id, service_id: d.service_id, customer_id: cust.id, price: svc.price }) };
    },
    'appointments.update': (op) => {
      const a = db.appointments[op.id];
      const d = { ...op.data };
      if (d.check_in) { d.checked_in_at = d.checked_in_at || 'agora'; d.status = 'confirmed'; }
      delete d.check_in; delete d.force; delete d.notify_customer;
      return { status: 'aplicado', server: save('appointments', { ...a, ...d }) };
    },
    'comandas.create': (op) => {
      const a = op.data.appointment_id && db.appointments[op.data.appointment_id];
      const c = save('comandas', { id: op.id, status: 'open', opened_at: `${DAY}T10:00:00`,
                                   customer_id: a ? a.customer_id : op.data.customer_id, appointment_id: a ? a.id : null });
      if (a) {
        save('comanda_items', { id: randomUUID(), comanda_id: c.id, kind: 'service', description: 'Corte',
                                service_id: a.service_id, quantity: 1, unit_price: a.price, amount: a.price,
                                covered_by: 'none', commission_base: a.price, created_at: '1' });
      }
      return { status: 'aplicado', server: c };
    },
    'comanda_items.create': (op) => {
      const d = op.data;
      const p = d.product_id && db.products[d.product_id];
      if (p) save('stock_movements', { id: randomUUID(), product_id: p.id, delta: String(-d.quantity), reason: 'sale' });
      return { status: 'aplicado', server: save('comanda_items', { id: op.id, comanda_id: d.comanda_id, kind: d.kind,
        description: p ? p.name : 'Gorjeta', quantity: d.quantity, unit_price: p ? p.price : d.value,
        amount: p ? (Number(p.price) * d.quantity).toFixed(2) : d.value, covered_by: 'none',
        commission_base: '0.00', product_id: d.product_id || null, created_at: '2' }) };
    },
    'comanda_payments.create': (op) => ({ status: 'aplicado', server: save('comanda_payments', {
      id: op.id, comanda_id: op.data.comanda_id, method: op.data.method, amount: op.data.amount, created_at: '3' }) }),
    'comandas.close': (op) => ({ status: 'aplicado', server: save('comandas', { ...db.comandas[op.id], status: 'closed',
                                                                               closed_at: `${DAY}T11:00:00` }) }),
  };
  const seen = new Map();
  return {
    db, save, all,
    transport: {
      async push(ops) {
        if (!mockNet.online) throw Object.assign(new Error('rede'), { status: 0 });
        return ops.map((op) => {
          if (seen.has(op.operation_id)) return seen.get(op.operation_id);
          const r = { operation_id: op.operation_id, entity: op.entity, action: op.action, id: op.id,
                      ...handlers[`${op.entity}.${op.action}`](op) };
          seen.set(op.operation_id, r);
          return r;
        });
      },
      async pull(cursor) {
        if (!mockNet.online) throw Object.assign(new Error('rede'), { status: 0 });
        const changes = {};
        for (const [s, e, id] of log) if (s > Number(cursor)) (changes[e] = changes[e] || []).push(db[e][id]);
        return { cursor: String(seq), has_more: false, changes, deleted: {} };
      },
    },
  };
}

beforeEach(async () => {
  const store = createStore(openTestDb());
  await store.init();
  const srv = server();
  srv.save('services', { id: 's1', name: 'Corte', duration_minutes: 30, price: '50.00', active: true, sort_order: 0 });
  srv.save('barbers', { id: 'b1', name: 'Ana', active: true, service_ids: [],
                        working_hours: [{ weekday: 0, start: '09:00:00', end: '18:00:00' }] });
  srv.save('customers', { id: 'c1', name: 'Maria', phone: '5531999990000' });
  srv.save('products', { id: 'p1', name: 'Pomada', kind: 'sale', unit: 'un', price: '45.00', min_stock: '0', active: true });
  srv.save('stock_movements', { id: 'm1', product_id: 'p1', delta: '1', reason: 'purchase' });
  Object.assign(mockCtx, {
    store, srv, version: 0, session: { role: 'owner', barberId: null },
    engine: createEngine({ store, transport: srv.transport, uuid: randomUUID }),
  });
  mockCtx.engine.onChange((changed) => { if (changed) mockCtx.version += 1; }); // igual ao manager.js
  mockNet.online = true;
  await mockCtx.engine.sync('open');
});

const serverIds = async () => ({
  service: (await repo.services())[0].id, barber: (await repo.barbers())[0].id,
  customer: (await repo.customers({ q: 'maria' }))[0],
});

test('lê do aparelho no formato da API (ids do servidor)', async () => {
  const { service, barber, customer } = await serverIds();
  expect(typeof service).toBe('number');
  expect(typeof barber).toBe('number');
  expect(customer).toMatchObject({ name: 'Maria', _pending: false });
  const slots = await repo.availability({ service_id: service, day: DAY, barber_id: barber });
  expect(slots[0]).toEqual({ start: `${DAY}T09:00:00`, barber_id: barber, barber_name: 'Ana' });
  const [p] = await repo.products();
  expect(p).toMatchObject({ name: 'Pomada', stock: '1', low_stock: false });
});

test('agenda offline: "a confirmar" no aparelho e confirmado quando a internet volta', async () => {
  const { service, barber } = await serverIds();
  mockNet.online = false;
  const r = await repo.createAppointment({ customer_phone: '(31) 98888-7777', customer_name: 'Novo', service_id: service,
                                          barber_id: barber, start: `${DAY}T10:00:00` });
  expect(r).toMatchObject({ _queued: true, _local: true, customer_name: 'Novo', service_name: 'Corte' });
  const day = await repo.agendaDay(DAY);
  expect(day.barbers[0].appointments.map((a) => [a.customer_name, a._local])).toEqual([['Novo', true]]);
  expect(day.barbers[0].free.some((f) => f.start <= `${DAY}T10:00:00` && f.end > `${DAY}T10:00:00`)).toBe(false);
  // Horário já ocupado no aparelho: recusa na hora
  await expect(repo.createAppointment({ customer_phone: '31977776666', service_id: service, barber_id: barber,
                                        start: `${DAY}T10:15:00` })).rejects.toThrow('não está mais livre');

  mockNet.online = true;
  await mockCtx.engine.sync('network');
  const [a] = (await repo.agendaDay(DAY)).barbers[0].appointments;
  expect(a).toMatchObject({ customer_name: 'Novo', customer_phone: '5531988887777', _local: false, _pending: false });
  expect(typeof a.id).toBe('number');
  expect(mockCtx.srv.all('customers').filter((c) => c.phone === '5531988887777')).toHaveLength(1);
});

test('online: o conflito aparece na hora para quem está agendando (sem ir para a fila)', async () => {
  const { service, barber } = await serverIds();
  mockCtx.srv.save('appointments', { id: 'x', start: `${DAY}T15:00:00`, end: `${DAY}T15:30:00`, status: 'scheduled',
                                     barber_id: 'b1', service_id: 's1', customer_id: 'c1', price: '50.00' });
  // o aparelho ainda não sabe desse horário (não sincronizou)
  await expect(repo.createAppointment({ customer_id: (await serverIds()).customer.id, service_id: service,
                                        barber_id: barber, start: `${DAY}T15:00:00` }))
    .rejects.toMatchObject({ status: 409, message: 'Esse horário foi ocupado.' });
  expect(await mockCtx.store.attentionCount()).toBe(0);
  expect(await mockCtx.store.opCount()).toBe(0);
});

test('caixa offline: comanda do agendamento, venda, pagamento e fechamento; sincroniza sem duplicar', async () => {
  const { service, barber, customer } = await serverIds();
  const appt = await repo.createAppointment({ customer_id: customer.id, service_id: service, barber_id: barber,
                                             start: `${DAY}T11:00:00` });
  expect(appt._queued).toBe(false);
  mockNet.online = false;
  await repo.checkIn(appt);
  let c = await repo.openComanda({ appointment_id: appt.id });
  expect(c).toMatchObject({ _queued: true, customer_name: 'Maria', due: '50.00' }); // serviço provisório
  await expect(repo.addComandaItem(c, { kind: 'product', product_id: (await repo.products())[0].id, quantity: 2 }))
    .rejects.toThrow('Estoque insuficiente');
  c = await repo.addComandaItem(c, { kind: 'product', product_id: (await repo.products())[0].id, quantity: 2,
                                     allow_negative_stock: true });
  expect(c.due).toBe('140.00');
  expect((await repo.products())[0]).toMatchObject({ stock: '-1', low_stock: true });
  c = await repo.addComandaPayment(c, { method: 'dinheiro', amount: '140.00' });
  expect(c.balance).toBe('0.00');
  c = await repo.closeComanda(c);
  expect(c.status).toBe('closed');
  expect((await repo.appointment(appt.id)).checked_in_at).toBeTruthy();

  mockNet.online = true;
  await mockCtx.engine.sync('network');
  expect(await mockCtx.store.opCount()).toBe(0);
  expect(await mockCtx.store.attentionCount()).toBe(0);
  const [done] = await repo.comandas({ status: 'closed' });
  // O serviço provisório deu lugar ao do servidor: nada duplicado
  expect(done).toMatchObject({ due: '140.00', paid: '140.00', balance: '0.00', _pending: false });
  expect(done.items.filter((i) => i.kind === 'service')).toHaveLength(1);
  expect((await repo.products())[0].stock).toBe('-1');
  expect(mockCtx.srv.all('appointments')[0].status).toBe('confirmed');
});
