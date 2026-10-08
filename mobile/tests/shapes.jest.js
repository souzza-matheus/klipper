// Formatos montados no aparelho (modo offline) iguais aos da API: agenda, horários livres, comanda, estoque.
import {
  agendaDay, comandaOut, freeSlots, makeIndex, matchCustomer, monthDays, periodStart, productOut, subtract,
} from '../src/offline/shapes';

const DAY = '2030-01-07'; // segunda-feira
const barber = { id: 'b1', server_id: 7, name: 'Ana', active: true, service_ids: ['s1'],
                 working_hours: [{ weekday: 0, start: '09:00:00', end: '12:00:00' }] };
const service = { id: 's1', server_id: 3, name: 'Corte', duration_minutes: 30, price: '50.00', active: true };
const customer = { id: 'c1', server_id: 11, name: 'Maria', phone: '5531999990000' };
const idx = () => makeIndex({ services: [service], barbers: [barber], customers: [customer], products: [],
                              package_plans: [], subscription_plans: [], appointments: [] });
const appt = (start, end, extra = {}) => ({ id: `a-${start}`, start: `${DAY}T${start}`, end: `${DAY}T${end}`,
                                           status: 'scheduled', barber_id: 'b1', service_id: 's1', customer_id: 'c1',
                                           price: '50.00', ...extra });

test('subtrai ocupados do expediente', () => {
  expect(subtract([['09', '12']], [['10', '11']])).toEqual([['09', '10'], ['11', '12']]);
  expect(subtract([['09', '12']], [['08', '13']])).toEqual([]);
});

test('agenda do dia: ids públicos, livres e "a confirmar" para o que foi feito no aparelho', () => {
  const a1 = { ...appt('09:30:00', '10:00:00'), server_id: 99 };
  const a2 = appt('10:30:00', '11:00:00'); // criado offline: sem server_id
  const block = { id: 'k1', server_id: 5, barber_id: null, start: `${DAY}T11:30:00`, end: `${DAY}T12:00:00`, reason: 'x' };
  const d = agendaDay({ day: DAY, now: new Date(2030, 0, 6, 8), step: 30, barbers: [barber], appointments: [a1, a2],
                        blocks: [block], idx: idx(), pending: new Set([a2.id]) });
  const [b] = d.barbers;
  expect(b.id).toBe(7);
  expect(b.appointments.map((a) => [a.id, a.customer_name, a.service_name, a._local, a._pending]))
    .toEqual([[99, 'Maria', 'Corte', false, false], [a2.id, 'Maria', 'Corte', true, true]]);
  expect(b.free).toEqual([{ start: `${DAY}T09:00:00`, end: `${DAY}T09:30:00` },
                          { start: `${DAY}T10:00:00`, end: `${DAY}T10:30:00` },
                          { start: `${DAY}T11:00:00`, end: `${DAY}T11:30:00` }]);
  expect(b.blocks[0]).toMatchObject({ id: 5, whole_shop: true });
});

test('horários livres respeitam ocupados, bloqueios, antecedência e cancelados', () => {
  const slots = freeSlots({
    day: DAY, now: new Date(2030, 0, 7, 9, 10), shop: { slot_step_minutes: 30, min_advance_minutes: 0 }, service, barber,
    appointments: [appt('10:00:00', '10:30:00'), appt('11:00:00', '11:30:00', { status: 'cancelled' })],
    blocks: [{ barber_id: 'b1', start: `${DAY}T11:30:00`, end: `${DAY}T12:00:00` }],
  });
  expect(slots).toEqual([`${DAY}T09:30:00`, `${DAY}T10:30:00`, `${DAY}T11:00:00`]);
});

test('comanda: totais em centavos, estorno e saldo pago com pacote', () => {
  const c = { id: 'cm', status: 'open', customer_id: 'c1', opened_at: `${DAY}T10:00:00` };
  const items = [
    { id: 'i1', server_id: 1, kind: 'service', description: 'Corte', amount: '0.00', covered_by: 'package',
      commission_base: '35.00', quantity: 1, created_at: '1' },
    { id: 'i2', server_id: 2, kind: 'product', description: 'Pomada', amount: '45.10', quantity: 1, created_at: '2' },
    { id: 'i3', kind: 'product', description: 'Estorno: Pomada', amount: '-45.10', quantity: -1, reverses_id: 'i2',
      created_at: '3' },
    { id: 'i4', kind: 'service', description: 'Barba', amount: '30.00', quantity: 1, created_at: '4' },
    { id: 'i5', kind: 'discount', description: 'Desconto 10%', amount: '-3.00', quantity: 1, created_at: '5' },
    { id: 'i6', kind: 'tip', description: 'Gorjeta', amount: '0.10', quantity: 1, created_at: '6' },
  ];
  const pays = [{ id: 'p1', server_id: 4, method: 'pix', amount: '20.00', created_at: '1' }];
  const out = comandaOut(c, items, pays, idx());
  expect(out).toMatchObject({ subtotal: '30.00', discount: '-3.00', tips: '0.10', due: '27.10', paid: '20.00',
                              balance: '7.10', covered: '35.00', customer_name: 'Maria', _pending: true });
  expect(out.items.find((i) => i.uuid === 'i2')).toMatchObject({ id: 2, reversed: true });
  expect(out.items.find((i) => i.uuid === 'i3')).toMatchObject({ reverses_id: 2, _pending: true });
});

test('estoque: soma das movimentações; negativo conta como baixo', () => {
  const p = { id: 'p', server_id: 9, name: 'Pomada', kind: 'sale', unit: 'un', price: '45', min_stock: '0',
              cost: '10', active: true };
  expect(productOut(p, [{ delta: '1' }, { delta: '-2' }], { showCost: false }))
    .toMatchObject({ id: 9, stock: '-1', low_stock: true, cost: null });
  expect(productOut({ ...p, min_stock: '3' }, [{ delta: '5.5' }], { showCost: true }))
    .toMatchObject({ stock: '5.5', low_stock: false, cost: '10' });
});

test('mês: total, cancelados e ocupação pelo expediente', () => {
  const days = monthDays({ year: 2030, month: 1, barbers: [barber], services: [service],
                           appointments: [appt('09:00:00', '09:30:00'), appt('10:00:00', '10:30:00', { status: 'cancelled' })],
                           blocks: [] });
  const d = days.find((x) => x.date === DAY);
  expect(days).toHaveLength(31);
  expect(d).toMatchObject({ total: 1, cancelled: 1, working: true, capacity: 6, revenue_expected: '50.00' });
  expect(days.find((x) => x.date === '2030-01-08').working).toBe(false);
});

test('ciclo da assinatura e busca de cliente', () => {
  expect(periodStart('2030-01-31', '2030-02-27')).toBe('2030-01-31');
  expect(periodStart('2030-01-31', '2030-02-28')).toBe('2030-02-28');
  expect(periodStart('2030-01-15', '2030-03-20')).toBe('2030-03-15');
  expect(matchCustomer({ name: 'João Évora', phone: '5531999990000' }, 'joao evo')).toBe(true);
  expect(matchCustomer({ name: 'João', phone: '5531999990000' }, '99990')).toBe(true);
  expect(matchCustomer({ name: 'João', phone: '5531999990000' }, 'maria')).toBe(false);
});
