// Repositório do celular com modo offline: lê do banco local (criptografado) e grava a alteração local e a
// operação da fila na mesma transação. Com internet, envia na hora e espera a resposta por alguns segundos:
// conflito ou recusa aparecem na própria tela, igual à versão online. Sem resposta, fica "a confirmar" e vai
// quando a conexão voltar.
//
// Ids: o que a tela vê é o número do servidor quando já existe (igual à API) ou o uuid criado no aparelho.
import * as Crypto from 'expo-crypto';
import { api, ApiError } from './api';
import { dmy, hm } from './format';
import { isOnline } from './net';
import { localISO } from './offline/engine';
import { ctx as m } from './offline/manager';
import {
  addDaysISO, addMinutes, agendaDay, appointmentOut, balanceOut, cents, comandaOut, freeSlots, makeIndex,
  matchCustomer, monthDays, money2, OCCUPYING, offers, productOut, pub, waitlistOut,
} from './offline/shapes';

const uuid = () => Crypto.randomUUID();
const WAIT_MS = 8000;
const now = () => new Date();
const nowISO = () => localISO(now());
const today = () => nowISO().slice(0, 10);
// Número (ou texto só com dígitos) = id do servidor; o resto é o uuid do registro
const isUuid = (v) => !(typeof v === 'number' || /^\d+$/.test(String(v)));

// ---------------------------------------------------------------- leitura base

async function rows(entity) {
  return (await m.store().all(entity)).map((r) => r.data);
}

let cache = { v: -1 };
async function index() {
  const v = m.version();
  if (cache.v === v) return cache.idx;
  const names = ['services', 'barbers', 'customers', 'products', 'package_plans', 'subscription_plans',
                 'appointments'];
  const tables = {};
  for (const n of names) tables[n] = await rows(n);
  cache = { v, idx: makeIndex(tables), pending: await m.store().pendingIds() };
  return cache.idx;
}
const pendingSet = async () => { await index(); return cache.pending; };

// Acha pelo id que a tela tem (número do servidor ou uuid)
async function find(entity, id) {
  if (id == null) return null;
  const st = m.store();
  const r = isUuid(id) ? await st.get(entity, id) : await st.getBySid(entity, id);
  return r && !r.deleted ? r : null;
}
async function mustFind(entity, id, what) {
  const r = await find(entity, id);
  if (!r) throw new ApiError(`${what} não encontrado no aparelho. Sincronize e tente de novo.`, 404);
  return r;
}
const uuidOf = async (entity, id) => (id == null ? null : (await find(entity, id))?.id ?? null);

const shopCache = async () => {
  const s = await m.store().getMeta('shop');
  return s ? JSON.parse(s) : { slot_step_minutes: 30, min_advance_minutes: 0 };
};

// Barbeiro do profissional logado (o servidor já manda só a agenda dele)
async function ownBarber() {
  const { role, barberId } = m.session();
  if (role !== 'professional' || !barberId) return null;
  return (await find('barbers', barberId))?.id || '__nenhum__';
}

// ---------------------------------------------------------------- escrita base

function conflictError(res) {
  const code = res.reason === 'cliente_em_conflito' ? 'customer_conflict' : res.reason;
  return new ApiError(res.message || 'Não foi possível salvar.', res.status === 'conflito' ? 409 : 422,
    { detail: { code, message: res.message } });
}

// Grava local + fila; online, espera a resposta do servidor. read(id) devolve o formato da tela.
async function commit(op, applyLocal, read) {
  const engine = m.engine();
  const operationId = await engine.submit(op, applyLocal);
  m.bump();
  let res = null;
  if (isOnline()) {
    const waiting = engine.waitFor(operationId, WAIT_MS);
    engine.sync('write');
    res = await waiting;
  }
  if (res && res.status !== 'aplicado') throw conflictError(res);
  m.bump();
  const id = res?.server?.id || op.id;
  const out = read ? await read(id) : {};
  return out ? { ...out, _queued: !res } : { _queued: !res };
}

const label = {
  appt: (name, start) => `Agendamento de ${name || 'cliente'} · ${dmy(start)} ${hm(start)}`,
  comanda: (name) => `Comanda de ${name || 'venda avulsa'}`,
};

function busyFor(appts, blocks, barberUuid, start, end, ignoreId) {
  return appts.some((a) => a.barber_id === barberUuid && a.id !== ignoreId && OCCUPYING.includes(a.status)
    && a.start < end && a.end > start)
    || blocks.some((k) => (!k.barber_id || k.barber_id === barberUuid) && k.start < end && k.end > start);
}

// Cliente pelo telefone (cliente novo digitado offline vira um registro provisório até o servidor criar o real)
async function customerByPhone(phone) {
  const digits = String(phone || '').replace(/\D/g, '');
  const all = await rows('customers');
  return all.find((c) => c.phone === digits || (digits.length >= 10 && c.phone.endsWith(digits))) || null;
}
const normPhone = (phone) => {
  const d = String(phone || '').replace(/\D/g, '');
  return d.length <= 11 ? `55${d}` : d;
};

// ---------------------------------------------------------------- comanda (leitura)

async function comandaView(c) {
  const st = m.store();
  const idx = await index();
  const items = (await st.byK('comanda_items', c.id)).map((r) => r.data);
  const pays = (await st.byK('comanda_payments', c.id)).map((r) => r.data);
  return comandaOut(c, items, pays, idx, await pendingSet());
}

async function readComanda(id) {
  const r = await find('comandas', id);
  return r ? comandaView(r.data) : null;
}

async function stockOf(productUuid) {
  const moves = (await m.store().byK('stock_movements', productUuid)).map((r) => r.data);
  return moves.reduce((t, x) => t + Math.round(Number(x.delta) * 1000), 0) / 1000;
}

// ---------------------------------------------------------------- repositório

export const local = {
  mode: 'offline',

  async agendaDay(day) {
    const st = m.store();
    const [from, to] = [`${day}T00:00:00`, `${addDaysISO(day, 1)}T00:00:00`];
    const shop = await shopCache();
    return agendaDay({
      day, now: now(), step: shop.slot_step_minutes || 30, barbers: await rows('barbers'),
      appointments: (await st.byK('appointments', from, to)).map((r) => r.data), blocks: await rows('blocks'),
      idx: await index(), pending: await pendingSet(), onlyBarber: await ownBarber(),
    });
  },

  async appointmentsMonth(year, month, barberId) {
    if (isOnline()) {
      try {
        const b = barberId ? (await find('barbers', barberId))?.data : null;
        return await api.get('/appointments/month', { year, month, barber_id: b?.server_id || undefined });
      } catch (e) { /* sem resposta: calcula com o que está no aparelho */ }
    }
    const own = await ownBarber();
    const bid = own || (await uuidOf('barbers', barberId));
    const barbers = (await rows('barbers')).filter((b) => (bid ? b.id === bid : b.active));
    return {
      year, month, _offline: true,
      days: monthDays({
        year, month, barbers, services: await rows('services'),
        appointments: (await rows('appointments')).filter((a) => !bid || a.barber_id === bid),
        blocks: (await rows('blocks')).filter((k) => !bid || !k.barber_id || k.barber_id === bid),
      }),
    };
  },

  async appointmentsOfDay(day, includeCancelled = false) {
    const st = m.store();
    const idx = await index();
    const pending = await pendingSet();
    const own = await ownBarber();
    return (await st.byK('appointments', `${day}T00:00:00`, `${addDaysISO(day, 1)}T00:00:00`)).map((r) => r.data)
      .filter((a) => (includeCancelled || a.status !== 'cancelled') && (!own || a.barber_id === own))
      .sort((x, y) => (x.start < y.start ? -1 : 1)).map((a) => appointmentOut(a, idx, pending));
  },

  async appointment(id, hint) {
    const r = await find('appointments', id ?? hint?.uuid);
    if (!r) {
      if (hint && !hint._local) return hint; // fora da janela do aparelho
      throw new ApiError('Esse agendamento não está mais no aparelho.', 404);
    }
    return appointmentOut(r.data, await index(), await pendingSet());
  },

  async availability({ service_id: serviceId, day, barber_id: barberId, customer_id: customerId }) {
    const svc = await mustFind('services', serviceId, 'Serviço');
    if (isOnline() && svc.data.server_id) {
      try { // online: o servidor também esconde horários perto de clientes em conflito
        const b = barberId ? (await find('barbers', barberId))?.data : null;
        const c = customerId && !isUuid(customerId) ? customerId : undefined;
        return await api.get('/availability', { service_id: svc.data.server_id, day, barber_id: b?.server_id,
                                                customer_id: c });
      } catch (e) { /* calcula no aparelho */ }
    }
    const shop = await shopCache();
    const appts = (await m.store().byK('appointments', `${addDaysISO(day, -1)}T00:00:00`,
      `${addDaysISO(day, 1)}T23:59:59`)).map((r) => r.data);
    const blocks = await rows('blocks');
    const all = (await rows('barbers')).sort((x, y) => x.name.localeCompare(y.name));
    const chosen = barberId ? all.filter((b) => b.id === barberId || pub(b) === barberId)
      : all.filter((b) => offers(b, svc.data.id));
    const seen = new Map();
    for (const b of chosen) {
      for (const start of freeSlots({ day, now: now(), shop, service: svc.data, barber: b, appointments: appts, blocks })) {
        if (!seen.has(start)) seen.set(start, { start, barber_id: pub(b), barber_name: b.name });
      }
    }
    return [...seen.values()].sort((x, y) => (x.start < y.start ? -1 : 1));
  },

  async customers({ q = '', access_status: access, limit = 50 } = {}) {
    const pending = await pendingSet();
    const own = await ownBarber();
    let list = (await rows('customers')).filter((c) => matchCustomer(c, q) && (!access || c.access_status === access));
    if (own) { // profissional: só quem ele já atendeu (o que está no aparelho)
      const mine = new Set((await rows('appointments')).filter((a) => a.barber_id === own).map((a) => a.customer_id));
      list = list.filter((c) => mine.has(c.id));
    }
    return list.sort((x, y) => (x.name || '~').localeCompare(y.name || '~')).slice(0, limit).map((c) => ({
      id: pub(c), uuid: c.id, name: c.name, phone: c.phone, notes: c.notes || '', access_status: c.access_status || 'normal',
      access_reason: c.access_reason || '', access_changed_at: null, created_at: c.created_at || null,
      _pending: pending.has(c.id) || !c.server_id,
    }));
  },

  async customer(id) {
    const r = await find('customers', id);
    const pending = await pendingSet();
    if (isOnline() && r?.data.server_id) {
      try {
        const d = await api.get(`/customers/${r.data.server_id}`);
        // Alteração feita no aparelho e ainda não enviada continua aparecendo
        return pending.has(r.id) ? { ...d, name: r.data.name, notes: r.data.notes, _pending: true } : d;
      } catch (e) {
        if (e.status && e.status !== 0 && e.status < 500) throw e;
      }
    }
    if (!r) throw new ApiError('Cadastro não encontrado no aparelho.', 404);
    const c = r.data;
    const idx = await index();
    const appts = (await rows('appointments')).filter((a) => a.customer_id === c.id)
      .sort((x, y) => (x.start < y.start ? 1 : -1));
    const done = appts.filter((a) => a.status === 'completed');
    const { role } = m.session();
    const nowS = nowISO();
    return {
      id: pub(c), uuid: c.id, name: c.name, phone: c.phone, notes: c.notes || '', access_status: c.access_status || 'normal',
      access_reason: c.access_reason || '', access_changed_at: null, created_at: c.created_at || null,
      visits: done.length, no_shows: appts.filter((a) => a.status === 'no_show').length,
      total_spent: money2(done.reduce((t, a) => t + cents(a.price), 0)),
      future_appointments: appts.filter((a) => a.start >= nowS && OCCUPYING.includes(a.status)).length,
      appointments: appts.slice(0, 50).map((a) => appointmentOut(a, idx, pending)),
      balance: role === 'professional' ? null : balanceOut({
        customerId: c.id, today: today(), idx, packages: await rows('customer_packages'),
        packageUses: await rows('package_uses'), subscriptions: await rows('subscriptions'),
        subUses: await rows('subscription_uses'), plans: idx.subscription_plans,
      }),
      _partial: true, _pending: pending.has(c.id),
    };
  },

  async comandas({ status, day } = {}) {
    const list = (await rows('comandas')).filter((c) => (!status || c.status === status)
      && (!day || (c.opened_at || '').slice(0, 10) === day)).sort((x, y) => (x.opened_at < y.opened_at ? 1 : -1));
    return Promise.all(list.slice(0, 200).map(comandaView));
  },

  async comanda(id) {
    const c = await readComanda(id);
    if (!c) throw new ApiError('Comanda não encontrada no aparelho.', 404);
    return c;
  },

  async services() {
    return (await rows('services')).sort((x, y) => (x.sort_order - y.sort_order) || x.name.localeCompare(y.name))
      .map((s) => ({ id: pub(s), uuid: s.id, name: s.name, duration_minutes: s.duration_minutes, price: s.price,
                     active: s.active, sort_order: s.sort_order, deposit_mode: s.deposit_mode || '',
                     deposit_value: s.deposit_value ?? '0' }));
  },

  async barbers() {
    const idx = await index();
    return (await rows('barbers')).sort((x, y) => x.name.localeCompare(y.name)).map((b) => ({
      id: pub(b), uuid: b.id, name: b.name, phone: '', bio: '', active: b.active,
      service_ids: (b.service_ids || []).map((s) => idx.pubOf('services', s)), working_hours: b.working_hours || [],
    }));
  },

  async products(includeInactive = false) {
    const { role } = m.session();
    const all = (await rows('products')).filter((p) => includeInactive || p.active)
      .sort((x, y) => x.name.localeCompare(y.name));
    const out = [];
    for (const p of all) {
      out.push(productOut(p, (await m.store().byK('stock_movements', p.id)).map((r) => r.data),
        { showCost: role === 'owner' }));
    }
    return out;
  },

  async productMovements(id) {
    if (isOnline() && !isUuid(id)) {
      try { return await api.get(`/products/${id}/movements`); } catch (e) { /* lista do aparelho */ }
    }
    const p = await mustFind('products', id, 'Produto');
    return (await m.store().byK('stock_movements', p.id)).map((r) => r.data)
      .sort((x, y) => ((x.created_at || '~') < (y.created_at || '~') ? 1 : -1))
      .map((x) => ({ id: pub(x), delta: x.delta, reason: x.reason, notes: x.notes || '', created_at: x.created_at }));
  },

  async packagePlans() {
    const idx = await index();
    return (await rows('package_plans')).map((p) => ({ ...p, id: pub(p), uuid: p.id,
                                                      service_id: idx.pubOf('services', p.service_id) }));
  },

  async waitlist(day, includeClosed) {
    const list = (await m.store().byK('waitlist_entries', day)).map((r) => r.data)
      .filter((e) => includeClosed || ['waiting', 'offered'].includes(e.status));
    return waitlistOut(list, await index(), await pendingSet());
  },

  async blocks() {
    const idx = await index();
    const pending = await pendingSet();
    const own = await ownBarber();
    const from = `${today()}T00:00:00`;
    return (await rows('blocks')).filter((k) => k.end >= from && (!own || !k.barber_id || k.barber_id === own))
      .sort((x, y) => (x.start < y.start ? -1 : 1))
      .map((k) => ({ id: pub(k), uuid: k.id, barber_id: idx.pubOf('barbers', k.barber_id), start: k.start, end: k.end,
                     reason: k.reason || '', _pending: pending.has(k.id) || !k.server_id }));
  },

  async shop() {
    if (isOnline()) {
      try {
        const s = await api.get('/shop');
        await m.store().setMeta('shop', JSON.stringify(s));
        return s;
      } catch (e) { /* usa a cópia do aparelho */ }
    }
    return shopCache();
  },

  // ------------------------------------------------ agendamentos

  async createAppointment(body) {
    const svc = await mustFind('services', body.service_id, 'Serviço');
    const barber = await mustFind('barbers', body.barber_id, 'Profissional');
    const start = String(body.start).slice(0, 19);
    const end = addMinutes(start, svc.data.duration_minutes);
    const appts = (await m.store().byK('appointments', `${start.slice(0, 10)}T00:00:00`,
      `${addDaysISO(start.slice(0, 10), 1)}T00:00:00`)).map((r) => r.data);
    if (busyFor(appts, await rows('blocks'), barber.id, start, end)) {
      throw new ApiError('Esse horário não está mais livre.', 409);
    }
    const known = body.customer_id ? (await find('customers', body.customer_id))?.data
      : await customerByPhone(body.customer_phone);
    const id = uuid();
    const shadowCustomer = known ? null : { id: uuid(), name: body.customer_name || '', phone: normPhone(body.customer_phone),
                                            notes: '', access_status: 'normal', created_at: nowISO() };
    const cust = known || shadowCustomer;
    const data = {
      barber_id: barber.id, service_id: svc.id, start, notes: body.notes || '', force: !!body.force,
      use_balance: body.use_balance !== false, require_deposit: !!body.require_deposit,
      ...(known ? { customer_id: known.id } : { customer_phone: shadowCustomer.phone, customer_name: body.customer_name || '' }),
    };
    const row = { id, start, end, status: 'scheduled', price: svc.data.price, notes: data.notes, barber_id: barber.id,
                  service_id: svc.id, customer_id: cust.id, payment_status: 'none', deposit_status: 'none',
                  created_via: 'app', customer_name: cust.name, customer_phone: cust.phone };
    return commit({ entity: 'appointments', action: 'create', id, data, label: label.appt(cust.name || cust.phone, start) },
      async (t, opId) => {
        if (shadowCustomer) await t.put('customers', { id: shadowCustomer.id, data: shadowCustomer, server: null, op: opId });
        await t.put('appointments', { id, data: row, server: null });
      }, (rid) => local.appointment(rid));
  },

  async updateAppointment(a, body) {
    const r = await mustFind('appointments', a.uuid || a.id, 'Agendamento');
    const fields = Object.fromEntries(Object.entries(body).filter(([k, v]) => v !== undefined
      && ['status', 'notes', 'payment_method', 'price', 'notify_customer'].includes(k)));
    const base = Object.fromEntries(Object.keys(fields).filter((k) => k !== 'notify_customer')
      .map((k) => [k, r.server?.[k] ?? null]));
    const next = { ...r.data, ...fields };
    delete next.notify_customer;
    return commit({ entity: 'appointments', action: 'update', id: r.id, version: r.server?.version ?? null, data: fields,
                    base, label: label.appt(a.customer_name, r.data.start) },
      (t) => t.put('appointments', { id: r.id, data: next, server: r.server }), (rid) => local.appointment(rid));
  },

  async checkIn(a) {
    const r = await mustFind('appointments', a.uuid || a.id, 'Agendamento');
    const at = nowISO();
    return commit({ entity: 'appointments', action: 'update', id: r.id, version: r.server?.version ?? null,
                    data: { check_in: true, checked_in_at: at }, base: {}, label: label.appt(a.customer_name, r.data.start) },
      (t) => t.put('appointments', { id: r.id, data: { ...r.data, checked_in_at: r.data.checked_in_at || at,
                                                       status: 'confirmed' }, server: r.server }),
      (rid) => local.appointment(rid));
  },

  async reschedule(a, body) {
    const r = await mustFind('appointments', a.uuid || a.id, 'Agendamento');
    const svc = await find('services', r.data.service_id);
    const barber = body.barber_id ? await mustFind('barbers', body.barber_id, 'Profissional') : null;
    const start = String(body.start).slice(0, 19);
    const end = addMinutes(start, svc?.data.duration_minutes || 30);
    const bid = barber?.id || r.data.barber_id;
    const appts = (await m.store().byK('appointments', `${start.slice(0, 10)}T00:00:00`,
      `${addDaysISO(start.slice(0, 10), 1)}T00:00:00`)).map((x) => x.data);
    if (busyFor(appts, await rows('blocks'), bid, start, end, r.id)) {
      throw new ApiError('Esse horário não está mais livre.', 409);
    }
    return commit({ entity: 'appointments', action: 'update', id: r.id, version: r.server?.version ?? null,
                    data: { start, barber_id: bid, force: !!body.force, notify_customer: body.notify_customer !== false },
                    base: { start: r.server?.start ?? null }, label: label.appt(a.customer_name, start) },
      (t) => t.put('appointments', { id: r.id, data: { ...r.data, start, end, barber_id: bid }, server: r.server }),
      (rid) => local.appointment(rid));
  },

  async updateCustomer(c, body) {
    const r = await mustFind('customers', c.uuid || c.id, 'Cadastro');
    const data = Object.fromEntries(Object.entries(body).filter(([k]) => ['name', 'notes'].includes(k)));
    const base = Object.fromEntries(Object.keys(data).map((k) => [k, r.server?.[k] ?? null]));
    return commit({ entity: 'customers', action: 'update', id: r.id, version: r.server?.version ?? null, data, base,
                    label: `Cadastro de ${r.data.name || r.data.phone}` },
      (t) => t.put('customers', { id: r.id, data: { ...r.data, ...data }, server: r.server }),
      async (rid) => { const x = await find('customers', rid); return x ? { id: pub(x.data), ...x.data } : null; });
  },

  // ------------------------------------------------ comandas

  async openComanda({ appointment_id: appointmentId, customer_id: customerId } = {}) {
    const appt = appointmentId ? await mustFind('appointments', appointmentId, 'Agendamento') : null;
    if (appt) {
      const existing = (await rows('comandas')).find((c) => c.appointment_id === appt.id);
      if (existing) return comandaView(existing);
      if (['cancelled', 'held'].includes(appt.data.status)) throw new ApiError('Esse agendamento foi cancelado.', 409);
    }
    const cust = appt ? await find('customers', appt.data.customer_id) : customerId ? await find('customers', customerId) : null;
    const svc = appt ? await find('services', appt.data.service_id) : null; // antes da transação (ver store.tx)
    const id = uuid();
    const at = nowISO();
    const comanda = { id, status: 'open', opened_at: at, closed_at: null, notes: '', customer_id: cust?.id || null,
                      appointment_id: appt?.id || null };
    return commit({ entity: 'comandas', action: 'create', id,
                    data: { appointment_id: appt?.id || null, customer_id: cust?.id || null },
                    label: label.comanda(cust?.data.name) },
      async (t, opId) => {
        await t.put('comandas', { id, data: comanda, server: null });
        if (!appt) return;
        // O servidor lança sozinho o serviço agendado (e o sinal já pago): aparece provisório até ele responder
        const a = appt.data;
        const covered = a.paid_with || 'none';
        await t.put('comanda_items', { op: opId, server: null, id: uuid(), data: {
          comanda_id: id, kind: 'service', description: svc?.data.name || 'Serviço', service_id: a.service_id,
          barber_id: a.barber_id, quantity: 1, unit_price: a.price, amount: covered === 'none' ? a.price : '0.00',
          covered_by: covered, commission_base: a.price, created_at: at } });
        if (a.deposit_status === 'paid' && Number(a.deposit_amount) > 0) {
          await t.put('comanda_payments', { op: opId, server: null, id: uuid(), data: {
            comanda_id: id, method: 'pix', amount: a.deposit_amount, from_deposit: true, created_at: at } });
        }
      }, readComanda);
  },

  async addComandaItem(cv, body) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    if (c.data.status !== 'open') throw new ApiError('Essa comanda já foi fechada.', 409);
    const view = await comandaView(c.data);
    const id = uuid();
    const at = nowISO();
    const qty = Number(body.quantity || 1);
    const barber = body.barber_id ? await mustFind('barbers', body.barber_id, 'Profissional') : null;
    const item = { id, comanda_id: c.id, kind: body.kind, quantity: qty, barber_id: barber?.id || null,
                   covered_by: 'none', commission_base: '0.00', created_at: at };
    const data = { comanda_id: c.id, kind: body.kind, quantity: qty, barber_id: barber?.id || null };
    let stockMove = null;
    if (body.kind === 'service') {
      const svc = await mustFind('services', body.service_id, 'Serviço');
      const cover = body.cover || 'none';
      if (cover !== 'none' && !c.data.customer_id) throw new ApiError('Escolha o cliente da comanda para usar o saldo.', 409);
      Object.assign(data, { service_id: svc.id, cover });
      const total = money2(cents(svc.data.price) * qty);
      Object.assign(item, { description: svc.data.name, service_id: svc.id, unit_price: svc.data.price,
                            amount: cover === 'none' ? total : '0.00', covered_by: cover,
                            commission_base: cover === 'none' ? total : svc.data.price });
    } else if (body.kind === 'product') {
      const p = await mustFind('products', body.product_id, 'Produto');
      if (p.data.kind === 'internal') throw new ApiError('Esse produto é só de uso interno.', 409);
      const have = await stockOf(p.id);
      if (!body.allow_negative_stock && have < qty) {
        throw new ApiError(`Estoque insuficiente: ${p.data.name} tem ${String(have).replace('.', ',')} ${p.data.unit}.`, 409);
      }
      Object.assign(data, { product_id: p.id, allow_negative_stock: !!body.allow_negative_stock });
      const total = money2(cents(p.data.price) * qty);
      Object.assign(item, { description: p.data.name, product_id: p.id, unit_price: p.data.price, amount: total,
                            commission_base: total });
      stockMove = { id: uuid(), product_id: p.id, delta: String(-qty), reason: 'sale', created_at: at };
    } else if (body.kind === 'package') {
      const plan = await mustFind('package_plans', body.package_plan_id, 'Pacote');
      if (!c.data.customer_id) throw new ApiError('Escolha o cliente da comanda para vender o pacote.', 409);
      Object.assign(data, { package_plan_id: plan.id });
      Object.assign(item, { description: plan.data.name, package_plan_id: plan.id, unit_price: plan.data.price,
                            amount: plan.data.price, quantity: 1 });
    } else if (body.kind === 'discount') {
      const sub = cents(view.subtotal);
      const amount = body.percent != null ? Math.round((sub * Number(body.percent)) / 100) : cents(body.value);
      if (amount <= 0 || amount > sub + cents(view.discount)) {
        throw new ApiError('O desconto não pode passar do valor da comanda.', 409);
      }
      Object.assign(data, body.percent != null ? { percent: String(body.percent) } : { value: body.value });
      Object.assign(item, { description: body.percent != null ? `Desconto ${Number(body.percent)}%` : 'Desconto',
                            unit_price: money2(-amount), amount: money2(-amount), percent: body.percent ?? null, quantity: 1 });
    } else {
      if (!barber || !body.value) throw new ApiError('Gorjeta: informe o valor e o profissional.', 422);
      Object.assign(data, { value: body.value });
      Object.assign(item, { description: `Gorjeta para ${barber.data.name}`, unit_price: body.value, amount: body.value,
                            quantity: 1 });
    }
    return commit({ entity: 'comanda_items', action: 'create', id, data, label: label.comanda(view.customer_name) },
      async (t, opId) => {
        await t.put('comanda_items', { id, data: item, server: null });
        if (stockMove) await t.put('stock_movements', { id: stockMove.id, data: stockMove, server: null, op: opId });
      }, () => readComanda(c.id));
  },

  async reverseComandaItem(cv, it) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    const item = await mustFind('comanda_items', it.uuid || it.id, 'Lançamento');
    const rid = uuid();
    const at = nowISO();
    const neg = (v) => money2(-cents(v));
    const rev = { ...item.data, id: rid, description: `Estorno: ${item.data.description}`.slice(0, 120),
                  quantity: -item.data.quantity, amount: neg(item.data.amount), commission_base: neg(item.data.commission_base),
                  reverses_id: item.id, created_at: at, server_id: undefined, version: undefined };
    return commit({ entity: 'comanda_items', action: 'reverse', id: item.id, data: { reversal_id: rid },
                    label: label.comanda(cv.customer_name) },
      async (t, opId) => {
        await t.put('comanda_items', { id: rid, data: rev, server: null });
        if (item.data.product_id) {
          const mv = { id: uuid(), product_id: item.data.product_id, delta: String(Math.abs(item.data.quantity)),
                       reason: 'reversal', created_at: at };
          await t.put('stock_movements', { id: mv.id, data: mv, server: null, op: opId });
        }
      }, () => readComanda(c.id));
  },

  async addComandaPayment(cv, body) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    if (c.data.status !== 'open') throw new ApiError('Essa comanda já foi fechada.', 409);
    const id = uuid();
    const pay = { id, comanda_id: c.id, method: body.method, amount: money2(cents(body.amount)), from_deposit: false,
                  created_at: nowISO() };
    return commit({ entity: 'comanda_payments', action: 'create', id,
                    data: { comanda_id: c.id, method: body.method, amount: pay.amount },
                    label: label.comanda(cv.customer_name) },
      (t) => t.put('comanda_payments', { id, data: pay, server: null }), () => readComanda(c.id));
  },

  async reverseComandaPayment(cv, p) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    const pay = await mustFind('comanda_payments', p.uuid || p.id, 'Pagamento');
    const rid = uuid();
    const rev = { id: rid, comanda_id: c.id, method: pay.data.method, amount: money2(-cents(pay.data.amount)),
                  from_deposit: pay.data.from_deposit, reverses_id: pay.id, created_at: nowISO() };
    return commit({ entity: 'comanda_payments', action: 'reverse', id: pay.id, data: { reversal_id: rid },
                    label: label.comanda(cv.customer_name) },
      (t) => t.put('comanda_payments', { id: rid, data: rev, server: null }), () => readComanda(c.id));
  },

  async closeComanda(cv) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    const view = await comandaView(c.data);
    if (!view.items.length) throw new ApiError('A comanda está vazia.', 409);
    if (cents(view.balance) !== 0) {
      throw new ApiError(`Faltam ${view.balance.replace('.', ',')} para fechar a comanda.`, 409);
    }
    return commit({ entity: 'comandas', action: 'close', id: c.id, data: {}, label: label.comanda(view.customer_name) },
      (t) => t.put('comandas', { id: c.id, data: { ...c.data, status: 'closed', closed_at: nowISO() }, server: c.server }),
      () => readComanda(c.id));
  },

  async cancelComanda(cv) {
    const c = await mustFind('comandas', cv.uuid || cv.id, 'Comanda');
    return commit({ entity: 'comandas', action: 'cancel', id: c.id, data: {}, label: label.comanda(cv.customer_name) },
      (t) => t.put('comandas', { id: c.id, data: { ...c.data, status: 'cancelled' }, server: c.server }),
      () => readComanda(c.id));
  },

  // ------------------------------------------------ estoque, lista de espera e bloqueios

  async addStockMovement(pv, body) {
    const p = await mustFind('products', pv.uuid || pv.id, 'Produto');
    const raw = Number(String(body.delta).replace(',', '.'));
    const delta = body.reason === 'internal' ? -Math.abs(raw) : body.reason === 'purchase' ? Math.abs(raw) : raw;
    const id = uuid();
    const mv = { id, product_id: p.id, delta: String(delta), reason: body.reason, notes: body.notes || '',
                 created_at: nowISO() };
    return commit({ entity: 'stock_movements', action: 'create', id,
                    data: { product_id: p.id, delta: String(raw), reason: body.reason, notes: body.notes || '' },
                    label: `Estoque de ${p.data.name}` },
      (t) => t.put('stock_movements', { id, data: mv, server: null }));
  },

  async joinWaitlist(body) {
    const svc = await mustFind('services', body.service_id, 'Serviço');
    const barber = body.barber_id ? await mustFind('barbers', body.barber_id, 'Profissional') : null;
    const known = await customerByPhone(body.customer_phone);
    const id = uuid();
    const shadow = known ? null : { id: uuid(), name: body.customer_name || '', phone: normPhone(body.customer_phone),
                                    notes: '', access_status: 'normal', created_at: nowISO() };
    const cust = known || shadow;
    const entry = { id, customer_id: cust.id, service_id: svc.id, barber_id: barber?.id || null, day: body.day,
                    after_time: body.after_time || null, before_time: body.before_time || null, status: 'waiting',
                    created_at: nowISO(), customer_name: cust.name, customer_phone: cust.phone };
    return commit({ entity: 'waitlist_entries', action: 'create', id,
                    data: { service_id: svc.id, barber_id: barber?.id || null, day: body.day,
                            after_time: body.after_time || null, before_time: body.before_time || null,
                            ...(known ? { customer_id: known.id } : { customer_phone: shadow.phone,
                                                                      customer_name: shadow.name }) },
                    label: `Lista de espera: ${cust.name || cust.phone}` },
      async (t, opId) => {
        if (shadow) await t.put('customers', { id: shadow.id, data: shadow, server: null, op: opId });
        await t.put('waitlist_entries', { id, data: entry, server: null });
      });
  },

  async createBlock(body) {
    const barber = body.barber_id ? await mustFind('barbers', body.barber_id, 'Profissional') : null;
    const id = uuid();
    const blk = { id, barber_id: barber?.id || null, start: body.start, end: body.end, reason: body.reason || '' };
    return commit({ entity: 'blocks', action: 'create', id, data: blk, label: `Bloqueio ${dmy(body.start)}` },
      (t) => t.put('blocks', { id, data: blk, server: null }));
  },

  async deleteBlock(b) {
    const r = await mustFind('blocks', b.uuid || b.id, 'Bloqueio');
    if (!r.server) { // criado aqui e ainda não enviado: some da fila também
      const engine = m.engine();
      await m.store().tx(async (t) => {
        for (const op of await t.opsMentioning(r.id)) await t.deleteOp(op.operation_id);
        await t.remove('blocks', r.id);
      });
      m.bump();
      engine.sync('write');
      return { _queued: false };
    }
    return commit({ entity: 'blocks', action: 'delete', id: r.id, data: {}, label: `Bloqueio ${dmy(r.data.start)}` },
      (t) => t.put('blocks', { id: r.id, data: r.data, server: r.server, deleted: true }));
  },
};
