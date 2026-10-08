// Monta, a partir do banco local, os mesmos formatos que a API devolve (as telas não sabem de onde veio).
// Funções puras, sem React Native: testadas no Jest. As regras seguem o backend (app/services/scheduling.py,
// comandas.py, benefits.py); dinheiro em centavos inteiros para não errar arredondamento.

import { localISO } from './engine';

export const OCCUPYING = ['scheduled', 'confirmed', 'pending_approval', 'awaiting_deposit', 'held'];

// ---------------------------------------------------------------- datas e dinheiro
export const cents = (v) => Math.round(Number(v || 0) * 100);
export const money2 = (c) => (c / 100).toFixed(2);
export const milli = (v) => Math.round(Number(v || 0) * 1000);
export const qty3 = (m) => String(m / 1000);
export const addMinutes = (iso, m) => {
  const d = new Date(iso);
  d.setMinutes(d.getMinutes() + m);
  return localISO(d);
};
export const addDaysISO = (day, n) => {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + n);
  return localISO(d).slice(0, 10);
};
// Segunda = 0 (como o Python)
export const pyWeekday = (day) => (new Date(`${day}T12:00:00`).getDay() + 6) % 7;
const minutesBetween = (a, b) => (new Date(b) - new Date(a)) / 60000;

// id que as telas usam: o número do servidor quando já existe, senão o uuid gerado no aparelho
export const pub = (row) => (row ? row.server_id ?? row.id : null);

// Índices por uuid das tabelas pequenas (serviços, profissionais, clientes...)
export function makeIndex(tables) {
  const idx = {};
  for (const [name, rows] of Object.entries(tables)) {
    idx[name] = new Map(rows.map((r) => [r.id, r]));
  }
  idx.pubOf = (name, uuid) => (uuid ? pub(idx[name]?.get(uuid)) ?? uuid : null);
  return idx;
}

// ---------------------------------------------------------------- agendamentos
export function appointmentOut(a, idx, pending = new Set()) {
  const cust = idx.customers.get(a.customer_id);
  const barber = idx.barbers.get(a.barber_id);
  const svc = idx.services.get(a.service_id);
  return {
    id: pub(a), uuid: a.id, start: a.start, end: a.end, status: a.status, payment_status: a.payment_status || 'none',
    payment_method: a.payment_method || null, price: a.price, notes: a.notes || '', created_via: a.created_via || 'app',
    customer_id: pub(cust) ?? a.customer_id, customer_name: cust?.name || a.customer_name || '',
    customer_phone: cust?.phone || a.customer_phone || '', barber_id: pub(barber) ?? a.barber_id,
    barber_name: barber?.name || '', service_id: pub(svc) ?? a.service_id, service_name: svc?.name || '',
    rating: a.rating ?? null, customer_access_status: cust?.access_status || 'normal',
    approval_deadline: a.approval_deadline || null, payment_id: a.payment_id ?? null,
    customer_reported_paid: !!a.customer_reported_paid, version: a.version || 0, checked_in_at: a.checked_in_at || null,
    deposit_amount: a.deposit_amount ?? null, deposit_status: a.deposit_status || 'none',
    customer_package_id: a.paid_with === 'package' ? true : null,
    subscription_id: a.paid_with === 'subscription' ? true : null,
    _pending: pending.has(a.id), _local: !a.server_id,
  };
}

// Expediente menos os intervalos ocupados (igual a scheduling._subtract)
export function subtract(intervals, busy) {
  const out = [];
  const sorted = [...busy].sort((x, y) => (x[0] < y[0] ? -1 : 1));
  for (const [s, e] of intervals) {
    let cur = s;
    for (const [bs, be] of sorted) {
      if (be <= cur || bs >= e) continue;
      if (bs > cur) out.push([cur, bs]);
      if (be > cur) cur = be;
      if (cur >= e) break;
    }
    if (cur < e) out.push([cur, e]);
  }
  return out;
}

const working = (b, day) => (b.working_hours || []).filter((w) => w.weekday === pyWeekday(day))
  .map((w) => [`${day}T${w.start}`, `${day}T${w.end}`]).sort((x, y) => (x[0] < y[0] ? -1 : 1));
const overlaps = (s, e, from, to) => s < to && e > from;
const dayRange = (day) => [`${day}T00:00:00`, `${addDaysISO(day, 1)}T00:00:00`];

// Agenda do dia: igual a GET /agenda/day
export function agendaDay({ day, now, step, barbers, appointments, blocks, idx, pending, onlyBarber }) {
  const [from, to] = dayRange(day);
  const nowISO = localISO(now);
  const today = nowISO.slice(0, 10);
  const appts = appointments.filter((a) => a.start >= from && a.start < to && a.status !== 'cancelled')
    .sort((x, y) => (x.start < y.start ? -1 : 1));
  const dayBlocks = blocks.filter((k) => overlaps(k.start, k.end, from, to)).sort((x, y) => (x.start < y.start ? -1 : 1));
  const out = [];
  for (const b of [...barbers].sort((x, y) => x.name.localeCompare(y.name))) {
    if (onlyBarber && b.id !== onlyBarber) continue;
    const mine = appts.filter((a) => a.barber_id === b.id);
    if (!b.active && !mine.length) continue;
    const work = working(b, day);
    const own = dayBlocks.filter((k) => !k.barber_id || k.barber_id === b.id);
    const busy = [...own.map((k) => [k.start, k.end]),
                  ...mine.filter((a) => OCCUPYING.includes(a.status)).map((a) => [a.start, a.end])];
    let free = day >= today ? subtract(work, busy) : [];
    if (day === today) free = free.filter(([, e]) => e > nowISO).map(([s, e]) => [s > nowISO ? s : nowISO, e]);
    out.push({
      id: pub(b), name: b.name,
      working: work.map(([start, end]) => ({ start, end })),
      blocks: own.map((k) => ({ id: pub(k), start: k.start, end: k.end, reason: k.reason || '', whole_shop: !k.barber_id,
                                _pending: pending.has(k.id) })),
      appointments: mine.map((a) => appointmentOut(a, idx, pending)),
      free: free.filter(([s, e]) => minutesBetween(s, e) >= 5).map(([start, end]) => ({ start, end })),
    });
  }
  return { day, now: nowISO, slot_step_minutes: step, barbers: out, _offline: true };
}

// Horários livres para um serviço (igual a scheduling.free_slots, sem os conflitos entre clientes)
export function freeSlots({ day, now, shop, service, barber, appointments, blocks, ignoreId }) {
  const earliest = localISO(new Date(now.getTime() + (shop.min_advance_minutes || 0) * 60000));
  const step = shop.slot_step_minutes || 30;
  const [from, to] = dayRange(day);
  const busy = [
    ...appointments.filter((a) => a.barber_id === barber.id && OCCUPYING.includes(a.status) && a.id !== ignoreId
      && overlaps(a.start, a.end, from, to)).map((a) => [a.start, a.end]),
    ...blocks.filter((k) => (!k.barber_id || k.barber_id === barber.id) && overlaps(k.start, k.end, from, to))
      .map((k) => [k.start, k.end]),
  ];
  const slots = new Set();
  for (const [s, e] of working(barber, day)) {
    for (let cur = s; addMinutes(cur, service.duration_minutes) <= e; cur = addMinutes(cur, step)) {
      const end = addMinutes(cur, service.duration_minutes);
      if (cur >= earliest && !busy.some(([bs, be]) => cur < be && end > bs)) slots.add(cur);
    }
  }
  return [...slots].sort();
}

export const offers = (b, serviceId) => b.active && (!(b.service_ids || []).length || b.service_ids.includes(serviceId));

// ---------------------------------------------------------------- mês (calendário)
export function monthDays({ year, month, barbers, appointments, blocks, services }) {
  const n = new Date(year, month, 0).getDate();
  const active = services.filter((s) => s.active);
  const avg = active.length ? active.reduce((t, s) => t + s.duration_minutes, 0) / active.length : 30;
  const days = [];
  for (let i = 1; i <= n; i += 1) {
    const day = `${year}-${String(month).padStart(2, '0')}-${String(i).padStart(2, '0')}`;
    const [from, to] = dayRange(day);
    const dayBlocks = blocks.filter((k) => overlaps(k.start, k.end, from, to));
    let work = 0;
    let free = 0;
    for (const b of barbers) {
      for (const [ws, we] of working(b, day)) {
        const minutes = minutesBetween(ws, we);
        work += minutes;
        const mine = subtract([[ws, we]], dayBlocks.filter((k) => !k.barber_id || k.barber_id === b.id)
          .map((k) => [k.start, k.end]));
        free += mine.reduce((t, [s, e]) => t + minutesBetween(s, e), 0);
      }
    }
    const appts = appointments.filter((a) => a.start >= from && a.start < to);
    const valid = appts.filter((a) => a.status !== 'cancelled');
    const capacity = Math.round((free / avg) * 10) / 10;
    days.push({
      date: day, total: valid.length, cancelled: appts.length - valid.length,
      revenue_expected: money2(valid.filter((a) => a.status !== 'no_show').reduce((t, a) => t + cents(a.price), 0)),
      capacity, occupancy: capacity ? Math.min(1, valid.length / capacity) : 0, working: work > 0,
      has_block: dayBlocks.length > 0,
    });
  }
  return days;
}

// ---------------------------------------------------------------- comanda
export function comandaOut(c, items, payments, idx, pending = new Set()) {
  const its = [...items].sort((x, y) => ((x.created_at || '') < (y.created_at || '') ? -1 : 1));
  const pays = [...payments].sort((x, y) => ((x.created_at || '') < (y.created_at || '') ? -1 : 1));
  const revItems = new Set(its.filter((i) => i.reverses_id).map((i) => i.reverses_id));
  const revPays = new Set(pays.filter((p) => p.reverses_id).map((p) => p.reverses_id));
  let sub = 0;
  let disc = 0;
  let tips = 0;
  let covered = 0;
  for (const it of its) {
    if (it.kind === 'discount') disc += cents(it.amount);
    else if (it.kind === 'tip') tips += cents(it.amount);
    else {
      sub += cents(it.amount);
      if (it.covered_by && it.covered_by !== 'none') covered += cents(it.commission_base);
    }
  }
  const paid = pays.reduce((t, p) => t + cents(p.amount), 0);
  const due = sub + disc + tips;
  const cust = c.customer_id ? idx.customers.get(c.customer_id) : null;
  const appt = c.appointment_id ? idx.appointments?.get(c.appointment_id) : null;
  const itemOf = new Map(its.map((i) => [i.id, i]));
  const payOf = new Map(pays.map((p) => [p.id, p]));
  return {
    id: pub(c), uuid: c.id, version: c.version || 0, status: c.status, customer_id: cust ? pub(cust) : c.customer_id,
    customer_name: cust ? (cust.name || cust.phone) : null, appointment_id: appt ? pub(appt) : c.appointment_id,
    opened_at: c.opened_at, closed_at: c.closed_at || null, notes: c.notes || '',
    items: its.map((i) => ({
      id: pub(i), uuid: i.id, kind: i.kind, description: i.description, service_id: idx.pubOf('services', i.service_id),
      product_id: idx.pubOf('products', i.product_id), package_plan_id: idx.pubOf('package_plans', i.package_plan_id),
      barber_id: idx.pubOf('barbers', i.barber_id), barber_name: idx.barbers.get(i.barber_id)?.name || null,
      quantity: i.quantity, unit_price: i.unit_price, amount: i.amount, percent: i.percent ?? null,
      covered_by: i.covered_by || 'none', commission_base: i.commission_base ?? '0.00',
      reverses_id: i.reverses_id ? pub(itemOf.get(i.reverses_id)) ?? i.reverses_id : null,
      reversed: revItems.has(i.id), created_at: i.created_at, _pending: pending.has(i.id) || !i.server_id,
    })),
    payments: pays.map((p) => ({
      id: pub(p), uuid: p.id, method: p.method, amount: p.amount, from_deposit: !!p.from_deposit,
      reverses_id: p.reverses_id ? pub(payOf.get(p.reverses_id)) ?? p.reverses_id : null, reversed: revPays.has(p.id),
      created_at: p.created_at, _pending: pending.has(p.id) || !p.server_id,
    })),
    subtotal: money2(sub), discount: money2(disc), tips: money2(tips), due: money2(due), paid: money2(paid),
    balance: money2(due - paid), covered: money2(covered),
    _pending: pending.has(c.id) || !c.server_id || its.some((i) => !i.server_id) || pays.some((p) => !p.server_id),
  };
}

// ---------------------------------------------------------------- estoque
export function productOut(p, movements, { showCost }) {
  const stock = movements.reduce((t, m) => t + milli(m.delta), 0);
  const min = milli(p.min_stock);
  return {
    id: pub(p), uuid: p.id, name: p.name, kind: p.kind, unit: p.unit, cost: showCost ? (p.cost ?? null) : null,
    price: p.price, min_stock: p.min_stock, commission_pct: p.commission_pct ?? null, active: p.active,
    stock: qty3(stock), low_stock: stock < 0 || (min > 0 && stock <= min),
  };
}

// ---------------------------------------------------------------- pacotes e assinatura (ficha do cliente)
const addMonthsDay = (day, n) => {
  const [y, m, d] = day.split('-').map(Number);
  const last = new Date(y, m - 1 + n + 1, 0).getDate();
  const t = new Date(y, m - 1 + n, Math.min(d, last));
  return localISO(t).slice(0, 10);
};
export function periodStart(startedAt, day) {
  const s = startedAt.slice(0, 10);
  const months = (Number(day.slice(0, 4)) - Number(s.slice(0, 4))) * 12 + Number(day.slice(5, 7)) - Number(s.slice(5, 7));
  let start = addMonthsDay(s, months);
  if (start > day) start = addMonthsDay(s, months - 1);
  return start > s ? start : s;
}

export function balanceOut({ customerId, today, idx, packages, packageUses, subscriptions, subUses, plans }) {
  const out = { packages: [], subscriptions: [] };
  for (const cp of packages.filter((x) => x.customer_id === customerId && x.status !== 'cancelled')) {
    const used = packageUses.filter((u) => u.customer_package_id === cp.id).reduce((t, u) => t + Number(u.delta), 0);
    const balance = cp.sessions - used;
    const expired = cp.expires_at && today > cp.expires_at;
    out.packages.push({
      id: pub(cp), uuid: cp.id, name: cp.name, service_id: idx.pubOf('services', cp.service_id),
      service_name: idx.services.get(cp.service_id)?.name || '', sessions: cp.sessions, balance,
      expires_at: cp.expires_at, session_value: cp.session_value,
      state: cp.status === 'pending_payment' ? 'aguardando_pagamento' : expired ? 'vencido'
        : balance > 0 ? 'ativo' : 'esgotado',
    });
  }
  for (const sub of subscriptions.filter((x) => x.customer_id === customerId)) {
    const plan = plans.get(sub.plan_id);
    const start = periodStart(sub.started_at, today);
    out.subscriptions.push({
      id: pub(sub), uuid: sub.id, plan_name: plan?.name || '', status: sub.status, price: sub.price,
      next_due_date: sub.next_due_date, days_late: null, benefits_blocked: sub.status === 'cancelled',
      period_start: start,
      items: (plan?.items || []).map((it) => {
        const used = subUses.filter((u) => u.subscription_id === sub.id && u.service_id === it.service_id
          && u.period_start === start).reduce((t, u) => t + Number(u.delta), 0);
        return { service_id: idx.pubOf('services', it.service_id), service_name: idx.services.get(it.service_id)?.name || '',
                 limit: it.limit_per_period, used,
                 remaining: it.limit_per_period == null ? null : Math.max(0, it.limit_per_period - used) };
      }),
    });
  }
  return out;
}

// ---------------------------------------------------------------- lista de espera
export function waitlistOut(entries, idx, pending = new Set()) {
  const waiting = entries.filter((e) => e.status === 'waiting')
    .sort((x, y) => ((x.created_at || '~') < (y.created_at || '~') ? -1 : (x.created_at || '~') > (y.created_at || '~') ? 1
      : (x.server_id || Infinity) - (y.server_id || Infinity)));
  const pos = new Map(waiting.map((e, i) => [e.id, i + 1]));
  return entries.map((e) => {
    const cust = idx.customers.get(e.customer_id);
    return {
      id: pub(e), uuid: e.id, customer_id: pub(cust) ?? e.customer_id, customer_name: cust?.name || e.customer_name || '',
      customer_phone: cust?.phone || e.customer_phone || '', service_id: idx.pubOf('services', e.service_id),
      service_name: idx.services.get(e.service_id)?.name || '', barber_id: idx.pubOf('barbers', e.barber_id),
      barber_name: idx.barbers.get(e.barber_id)?.name || null, day: e.day, after_time: e.after_time || null,
      before_time: e.before_time || null, status: e.status, position: pos.get(e.id) || null,
      offer_expires_at: e.offer_expires_at || null, created_at: e.created_at || null, _pending: pending.has(e.id),
    };
  }).sort((x, y) => (x.position || 999) - (y.position || 999));
}

// Busca de cliente igual à da API: nome (sem acento) ou parte do telefone
const fold = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
export function matchCustomer(c, q) {
  const query = String(q || '').trim();
  if (!query) return true;
  const digits = query.replace(/\D/g, '');
  if (digits.length >= 3 && String(c.phone || '').includes(digits)) return true;
  return fold(c.name).includes(fold(query));
}
