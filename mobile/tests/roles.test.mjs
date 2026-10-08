// Papéis no app: abas, menu, permissões e atalhos, espelhando a API.
import assert from 'node:assert/strict';
import test from 'node:test';
import { can, isWide, moreItemsFor, shortcutFor, tabsFor } from '../src/roles.js';

const names = (role) => tabsFor(role).map((t) => t.name);
const routes = (role) => moreItemsFor(role).map((m) => m.route);

test('dono vê tudo', () => {
  assert.deepEqual(names('owner'), ['Hoje', 'Agenda', 'Caixa', 'Clientes', 'Financeiro', 'Mais']);
  for (const r of ['Team', 'Settings', 'WhatsApp', 'Reports', 'Products', 'Subscriptions']) assert.ok(routes('owner').includes(r), r);
});

test('recepção: agenda, caixa e clientes, sem financeiro, equipe e configurações', () => {
  assert.deepEqual(names('reception'), ['Hoje', 'Agenda', 'Caixa', 'Clientes', 'Mais']);
  for (const r of ['Team', 'Settings', 'WhatsApp', 'Reports', 'Services', 'Barbers']) {
    assert.ok(!routes('reception').includes(r), r);
  }
  assert.ok(can('reception', 'comandas') && can('reception', 'waitlist') && can('reception', 'subscriptions'));
  assert.ok(!can('reception', 'finance') && !can('reception', 'commissions') && !can('reception', 'productCost'));
  assert.ok(!can('reception', 'reverseClosed') && !can('reception', 'mrr'));
});

test('profissional: só agenda, clientes e as próprias comissões', () => {
  assert.deepEqual(names('professional'), ['Agenda', 'Clientes', 'Comissoes', 'Mais']);
  assert.deepEqual(routes('professional'), ['Reviews', 'Sync', 'ChangePassword', 'About']);
  // Sincronização (modo offline) só existe no app do celular
  assert.deepEqual(moreItemsFor('professional', undefined, true).map((m) => m.route), ['Reviews', 'ChangePassword', 'About']);
  for (const f of ['newAppointment', 'comandas', 'pix', 'customerEdit', 'customerBalance', 'finance']) {
    assert.ok(!can('professional', f), f);
  }
  assert.ok(can('professional', 'checkIn') && can('professional', 'commissions'));
});

test('permissão desconhecida é erro (não libera por engano)', () => {
  assert.throws(() => can('owner', 'nao-existe'));
});

test('atalhos respeitam o papel', () => {
  assert.equal(shortcutFor('owner', 'N').label, 'Novo agendamento');
  assert.equal(shortcutFor('reception', 'c').label, 'Abrir comanda');
  assert.equal(shortcutFor('professional', 'n'), null);
  assert.equal(shortcutFor('professional', 'c'), null);
  assert.equal(shortcutFor('owner', 'x'), null);
});

test('layout de computador a partir de 900 px', () => {
  assert.ok(!isWide(375) && !isWide(768) && isWide(900) && isWide(1440));
});
