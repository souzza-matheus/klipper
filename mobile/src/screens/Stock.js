import React, { useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../api';
import { DataTable } from '../components/Layout';
import { dtLabel, money, moneyInput, parseMoney } from '../format';
import { useSession } from '../session';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, Button, Card, Chips, confirm, Empty, Field, IconButton, Loading, Screen, Section, Toggle, run, useLoad,
} from '../ui';

const KINDS = [{ value: 'sale', label: 'Venda' }, { value: 'internal', label: 'Uso interno' }, { value: 'both', label: 'Os dois' }];
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label]));
const REASONS = {
  purchase: 'Entrada', sale: 'Venda', consumption: 'Consumo em serviço', internal: 'Uso interno', adjust: 'Ajuste',
  reversal: 'Estorno',
};
const qty = (v) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 });
const LOW = { label: 'Estoque baixo', tone: 'warning', icon: 'alert-circle-outline' };

export function ProductsScreen({ navigation }) {
  const { s } = useTheme();
  const { wide, can } = useSession();
  const list = useLoad(() => api.get('/products', { include_inactive: true }), []);
  useLayoutEffect(() => {
    if (!can('productEdit')) return;
    navigation.setOptions({ headerRight: () => (
      <IconButton icon="add-circle" size={30} label="Novo produto" onPress={() => navigation.navigate('ProductEdit', {})} />
    ) });
  }, [navigation]); // eslint-disable-line react-hooks/exhaustive-deps
  const items = list.data || [];
  const low = items.filter((p) => p.low_stock && p.active);
  const open = (p) => navigation.navigate('ProductEdit', { item: p });
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {low.length ? (
        <Banner tone="danger" icon="alert-circle-outline"
                title={low.length === 1 ? '1 produto com estoque baixo' : `${low.length} produtos com estoque baixo`}
                text={low.map((p) => p.name).join(', ')} />
      ) : null}
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty icon="cube-outline" text="Cadastre os produtos que você vende ou usa nos atendimentos."
               action={can('productEdit') ? { title: 'Novo produto', icon: 'add', onPress: () => navigation.navigate('ProductEdit', {}) } : null} />
      ) : null}
      {items.length && wide ? (
        <DataTable rows={items} onRowPress={open} placeholder="Buscar produto" searchKeys={['name']}
                   initialSort={{ key: 'name', dir: 'asc' }} columns={[
                     { key: 'name', label: 'Produto', flex: 2, render: (p) => (
                       <View style={{ flexDirection: 'row', gap: SPACE(2), alignItems: 'center' }}>
                         <Text style={s.bodyBold} numberOfLines={1}>{p.name}{p.active ? '' : ' (inativo)'}</Text>
                         {p.low_stock ? <Badge info={LOW} /> : null}
                       </View>) },
                     { key: 'kind', label: 'Tipo', render: (p) => <Text style={s.body}>{KIND_LABEL[p.kind]}</Text> },
                     { key: 'stock', label: 'Estoque', align: 'right', render: (p) => <Text style={s.body}>{qty(p.stock)} {p.unit}</Text> },
                     { key: 'min_stock', label: 'Mínimo', align: 'right', render: (p) => <Text style={s.body}>{qty(p.min_stock)}</Text> },
                     { key: 'price', label: 'Preço', align: 'right', render: (p) => <Text style={s.body}>{money(p.price)}</Text> },
                     ...(can('productCost') ? [{ key: 'cost', label: 'Custo', align: 'right',
                                                 render: (p) => <Text style={s.body}>{money(p.cost)}</Text> }] : []),
                   ]} />
      ) : items.map((p) => (
        <Card key={p.id} onPress={() => open(p)}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Text style={[s.bodyBold, { flex: 1 }]}>{p.name}{p.active ? '' : ' (inativo)'}</Text>
            {p.low_stock ? <Badge info={LOW} /> : null}
          </View>
          <Text style={s.caption}>
            {qty(p.stock)} {p.unit} em estoque · mínimo {qty(p.min_stock)} · {KIND_LABEL[p.kind]}
            {p.kind !== 'internal' ? ` · ${money(p.price)}` : ''}
          </Text>
        </Card>
      ))}
    </Screen>
  );
}

function MovementForm({ product, onDone }) {
  const { s } = useTheme();
  const { can } = useSession();
  const reasons = can('stockPurchase')
    ? [{ value: 'purchase', label: 'Entrada' }, { value: 'internal', label: 'Uso interno' }, { value: 'adjust', label: 'Ajuste' }]
    : [{ value: 'internal', label: 'Uso interno' }];
  const [reason, setReason] = useState(reasons[0].value);
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const save = () => run(async () => {
    const delta = Number(String(amount).replace(',', '.'));
    if (!delta) throw new Error('Informe a quantidade.');
    await api.post(`/products/${product.id}/movements`, { delta: String(delta), reason, notes });
    setAmount('');
    setNotes('');
    onDone();
  }, 'Estoque atualizado.');
  return (
    <Card>
      <Chips value={reason} onChange={setReason} options={reasons} />
      <Field label={reason === 'adjust' ? `Diferença (${product.unit}); use - para tirar` : `Quantidade (${product.unit})`}
             value={amount} onChangeText={setAmount} keyboardType="numbers-and-punctuation"
             hint={reason === 'adjust' ? 'O ajuste registra a diferença; o histórico nunca é apagado.' : undefined} />
      <Field label="Observação" value={notes} onChangeText={setNotes} />
      <Text style={[s.caption, { marginBottom: SPACE(3) }]}>
        Vendas e o consumo dos serviços baixam o estoque sozinhos, pela comanda.
      </Text>
      <Button title="Registrar" icon="swap-vertical" onPress={save} disabled={!amount} style={{ marginBottom: 0 }} />
    </Card>
  );
}

export function ProductEditScreen({ navigation, route }) {
  const { s } = useTheme();
  const { can } = useSession();
  const item = route.params?.item;
  const edit = can('productEdit');
  const [name, setName] = useState(item?.name || '');
  const [kind, setKind] = useState(item?.kind || 'both');
  const [unit, setUnit] = useState(item?.unit || 'un');
  const [price, setPrice] = useState(item ? moneyInput(item.price) : '');
  const [cost, setCost] = useState(item?.cost != null ? moneyInput(item.cost) : '');
  const [minimum, setMinimum] = useState(item ? qty(item.min_stock) : '0');
  const [pct, setPct] = useState(item?.commission_pct ? String(Number(item.commission_pct)) : '');
  const [active, setActive] = useState(item ? item.active : true);
  const moves = useLoad(async () => (item && can('stockPurchase') ? api.get(`/products/${item.id}/movements`) : null),
    [item?.id]);
  const current = useLoad(async () => (item ? (await api.get('/products', { include_inactive: true }))
    .find((p) => p.id === item.id) : null), [item?.id]);

  const save = () => run(async () => {
    const body = {
      name, kind, unit, price: (parseMoney(price) ?? 0).toFixed(2), cost: (parseMoney(cost) ?? 0).toFixed(2),
      min_stock: String(Number(String(minimum).replace(',', '.')) || 0), active,
      commission_pct: pct ? String(Number(pct.replace(',', '.'))) : null,
    };
    if (item) await api.put(`/products/${item.id}`, body);
    else await api.post('/products', body);
    navigation.goBack();
  }, 'Produto salvo.');

  const p = current.data || item;
  return (
    <Screen footer={edit ? <Button title="Salvar" icon="checkmark" onPress={save} disabled={!name} style={{ marginBottom: 0 }} /> : null}>
      {p ? (
        <Card>
          <Text style={s.caption}>Em estoque</Text>
          <Text style={s.title}>{qty(p.stock)} {p.unit}</Text>
          {p.low_stock ? <Badge info={LOW} /> : null}
        </Card>
      ) : null}
      {edit ? (
        <>
          <Field label="Nome" value={name} onChangeText={setName} placeholder="Ex.: Pomada modeladora" />
          <Text style={s.label}>Tipo</Text>
          <Chips value={kind} onChange={setKind} options={KINDS} />
          <Field label="Unidade" value={unit} onChangeText={setUnit} hint="un, ml, g, par..." />
          {kind !== 'internal' ? <Field label="Preço de venda" mask="money" value={price} onChangeText={setPrice} /> : null}
          <Field label="Custo" mask="money" value={cost} onChangeText={setCost} />
          <Field label="Estoque mínimo (avisa abaixo disso)" value={minimum} onChangeText={setMinimum}
                 keyboardType="numbers-and-punctuation" />
          {kind !== 'internal' ? (
            <Field label="Comissão de quem vende (%)" value={pct} onChangeText={setPct} keyboardType="decimal-pad"
                   hint="Opcional." />
          ) : null}
          <Toggle label="Ativo" value={active} onValueChange={setActive} />
        </>
      ) : <Text style={s.title}>{item?.name}</Text>}
      {item ? (
        <Section title="Movimentar estoque">
          <MovementForm product={item} onDone={() => { moves.reload(); current.reload(); }} />
        </Section>
      ) : null}
      {moves.data?.length ? (
        <Section title="Histórico">
          {moves.data.map((m) => (
            <View key={m.id} style={[s.row, { gap: SPACE(3), marginBottom: SPACE(2) }]}>
              <Text style={[s.body, { flex: 1 }]}>{REASONS[m.reason]}{m.notes ? ` · ${m.notes}` : ''}</Text>
              <Text style={s.caption}>{dtLabel(m.created_at)}</Text>
              <Text style={[s.bodyBold, { minWidth: 64, textAlign: 'right' }]}>
                {Number(m.delta) > 0 ? '+' : ''}{qty(m.delta)}
              </Text>
            </View>
          ))}
        </Section>
      ) : null}
      {item && edit ? (
        <Button title="Excluir" kind="danger" icon="trash-outline" onPress={() => confirm('Excluir produto?',
          'Se já tiver movimentações, ele só será desativado.',
          () => run(async () => { await api.del(`/products/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}
