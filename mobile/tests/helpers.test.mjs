import assert from 'node:assert/strict';
import test from 'node:test';
import { fromValue, label, press, toApi } from '../src/keypad.js';
import { filterRows, nextSort, sortRows } from '../src/table.js';

test('teclado da comanda digita em centavos', () => {
  let d = '';
  for (const k of ['4', '0', '0', '0']) d = press(d, k);
  assert.equal(label(d), '40,00');
  assert.equal(toApi(d), '40.00');
  assert.equal(label(press(d, 'back')), '4,00');
  assert.equal(press('', '0'), '');
  assert.equal(label(press('1', '00')), '1,00');
  assert.equal(press('123456789', '1'), '123456789');
  assert.equal(label('123456'), '1.234,56');
  assert.equal(fromValue('36.5'), '3650');
  assert.equal(fromValue('0'), '');
});

const rows = [
  { name: 'Óleo', stock: '2.000', price: '39.90' },
  { name: 'pomada', stock: '10.000', price: '45.00' },
  { name: 'Shampoo', stock: '', price: '0' },
];

test('tabela ordena números como número e vazios por último', () => {
  assert.deepEqual(sortRows(rows, 'stock').map((r) => r.name), ['Óleo', 'pomada', 'Shampoo']);
  assert.deepEqual(sortRows(rows, 'stock', 'desc').map((r) => r.name), ['pomada', 'Óleo', 'Shampoo']);
  assert.deepEqual(sortRows(rows, 'name').map((r) => r.name), ['Óleo', 'pomada', 'Shampoo']);
  assert.deepEqual(sortRows(rows, 'price', 'desc').map((r) => r.name), ['pomada', 'Óleo', 'Shampoo']);
});

test('busca ignora acento e maiúscula', () => {
  assert.deepEqual(filterRows(rows, 'oleo', ['name']).map((r) => r.name), ['Óleo']);
  assert.equal(filterRows(rows, '', ['name']).length, 3);
  assert.deepEqual(nextSort({ key: 'name', dir: 'asc' }, 'name'), { key: 'name', dir: 'desc' });
  assert.deepEqual(nextSort({ key: 'name', dir: 'desc' }, 'price'), { key: 'price', dir: 'asc' });
});
