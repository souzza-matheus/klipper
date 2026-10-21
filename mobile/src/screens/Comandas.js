import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { api } from '../api';
import { PendingBadge } from '../components/Sync';
import { repo, saved } from '../repo';
import { BigButton, Keypad } from '../components/Layout';
import { useDebounced } from '../components/QuickBook';
import { dtLabel, hm, money, PAY_METHODS, payMethodLabel, phoneLabel, todayISO } from '../format';
import { fromValue, toApi, toNumber } from '../keypad';
import { useSession } from '../session';
import { STATUS } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, BottomSheet, Button, Card, Chips, confirm, Empty, Field, Loading, Screen, Section,
  SegmentedControl, run,
} from '../ui';
import { useLoad } from '../useLoad';

const METHOD_ICONS = { pix: 'qr-code-outline', dinheiro: 'cash-outline', debito: 'card-outline', credito: 'card' };
const KIND_ICONS = { service: 'cut-outline', product: 'cube-outline', package: 'albums-outline',
                     discount: 'pricetag-outline', tip: 'heart-outline' };
const COVER_LABEL = { package: 'pacote', subscription: 'assinatura' };

// ---------------------------------------------------------------- Caixa (lista)

function NewComandaSheet({ visible, onClose, navigation }) {
  const { c, s, v } = useTheme();
  const [q, setQ] = useState('');
  const query = useDebounced(q);
  const [found, setFound] = useState([]);
  useEffect(() => {
    if (!visible || query.length < 2) { setFound([]); return; }
    repo.customers({ q: query, limit: 8 }).then(setFound).catch(() => setFound([]));
  }, [query, visible]);
  const open = (customerId) => run(async () => {
    const r = await repo.openComanda(customerId ? { customer_id: customerId } : {});
    onClose();
    setQ('');
    navigation.navigate('Comanda', { id: r.id });
  });
  return (
    <BottomSheet visible={visible} onClose={onClose} title="Nova comanda">
      <Field value={q} onChangeText={setQ} placeholder={`Buscar ${v.customer} (nome ou telefone)`} autoFocus
             prefix={<Ionicons name="search" size={18} color={c.textMuted} style={{ marginRight: 6 }} />} />
      {found.map((x) => (
        <Card key={x.id} onPress={() => open(x.id)} style={{ paddingVertical: SPACE(3) }}>
          <Text style={s.bodyBold}>{x.name || 'Sem nome'}</Text>
          <Text style={s.caption}>{phoneLabel(x.phone)}</Text>
        </Card>
      ))}
      <Button title={`Sem ${v.customer} (venda avulsa)`} kind="ghost" icon="bag-outline" onPress={() => open(null)} />
    </BottomSheet>
  );
}

export function ComandasScreen({ navigation, route }) {
  const { s, v } = useTheme();
  const { can } = useSession();
  const day = todayISO();
  const open = useLoad(() => repo.comandas({ status: 'open' }), []);
  const closed = useLoad(() => repo.comandas({ status: 'closed', day }), [day]);
  const appts = useLoad(() => repo.appointmentsOfDay(day), [day]);
  const pix = useLoad(() => api.get('/payments', { status: 'pending' }), []);
  const [sheet, setSheet] = useState(false);

  // Atalho "C" (computador) e o botão do agendamento abrem direto
  useEffect(() => { if (route.params?.openNew) setSheet(true); }, [route.params?.openNew]);

  const withComanda = new Set([...(open.data || []), ...(closed.data || [])].map((x) => x.appointment_id));
  const pending = (appts.data || []).filter((a) => ['scheduled', 'confirmed'].includes(a.status) && !withComanda.has(a.id));
  const reload = () => { open.reload(); closed.reload(); appts.reload(); pix.reload(); };
  const openFor = (a) => run(async () => {
    const r = await repo.openComanda({ appointment_id: a.id });
    navigation.navigate('Comanda', { id: r.id });
  });
  const totalDay = (closed.data || []).reduce((t, x) => t + Number(x.paid), 0);

  return (
    <Screen onRefresh={reload} refreshing={open.loading && !!open.data}>
      {pix.data?.length && can('pix') ? (
        <Banner tone="warning" icon="cash-outline" onPress={() => navigation.navigate('PixList')}
                title={pix.data.length === 1 ? '1 Pix aguardando confirmação' : `${pix.data.length} Pix aguardando confirmação`} />
      ) : null}
      <Button title="Nova comanda" icon="add-circle-outline" onPress={() => setSheet(true)} />

      <Section title="Abertas">
        {!open.data ? <Loading error={open.error} onRetry={open.reload} rows={2} /> : !open.data.length ? (
          <Text style={[s.muted, { marginBottom: SPACE(3) }]}>Nenhuma comanda aberta.</Text>
        ) : open.data.map((x) => (
          <Card key={x.id} onPress={() => navigation.navigate('Comanda', { id: x.id })}>
            <View style={s.row}>
              <View style={{ flex: 1 }}>
                <View style={[s.row, { gap: SPACE(2) }]}>
                  <Text style={s.bodyBold}>{x.customer_name || 'Venda avulsa'}</Text>
                  <PendingBadge item={x} />
                </View>
                <Text style={s.caption}>Aberta às {hm(x.opened_at)} · {x.items.filter((i) => !i.reverses_id).length} item(ns)</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={s.bodyBold}>{money(x.due)}</Text>
                {Number(x.balance) > 0 ? <Text style={s.caption}>falta {money(x.balance)}</Text> : null}
              </View>
            </View>
          </Card>
        ))}
      </Section>

      <Section title={`${v.Services} de hoje sem comanda`}>
        {!pending.length ? <Text style={[s.muted, { marginBottom: SPACE(3) }]}>Tudo em dia.</Text> : pending.map((a) => (
          <Card key={a.id}>
            <View style={[s.row, { gap: SPACE(3) }]}>
              <View style={{ flex: 1 }}>
                <Text style={s.bodyBold}>{hm(a.start)} · {a.customer_name || phoneLabel(a.customer_phone)}</Text>
                <Text style={s.caption}>{a.service_name} com {a.barber_name}</Text>
                <View style={{ flexDirection: 'row', gap: SPACE(1), marginTop: SPACE(1) }}>
                  <Badge info={STATUS[a.status]} />
                  {a.checked_in_at ? <Badge info={{ label: 'Chegou', tone: 'success', icon: 'enter-outline' }} /> : null}
                </View>
              </View>
              <Button title="Abrir comanda" compact icon="receipt-outline" onPress={() => openFor(a)} />
            </View>
          </Card>
        ))}
      </Section>

      <Section title={`Fechadas hoje · ${money(totalDay)}`}>
        {(closed.data || []).map((x) => (
          <Card key={x.id} onPress={() => navigation.navigate('Comanda', { id: x.id })}>
            <View style={s.row}>
              <Text style={[s.body, { flex: 1 }]}>{x.customer_name || 'Venda avulsa'} · {hm(x.closed_at)}</Text>
              <PendingBadge item={x} />
              <Text style={s.bodyBold}>{money(x.paid)}</Text>
            </View>
          </Card>
        ))}
        {closed.data && !closed.data.length ? <Text style={s.muted}>Nenhuma comanda fechada hoje.</Text> : null}
      </Section>
      <NewComandaSheet visible={sheet} onClose={() => setSheet(false)} navigation={navigation} />
    </Screen>
  );
}

// ---------------------------------------------------------------- comanda

function ItemRow({ it, canReverse, onReverse }) {
  const { c, s } = useTheme();
  const reversal = !!it.reverses_id;
  const dim = it.reversed || reversal;
  return (
    <View style={[s.row, { gap: SPACE(3), paddingVertical: SPACE(3), borderBottomWidth: 1, borderBottomColor: c.divider }]}>
      <Ionicons name={reversal ? 'return-down-back-outline' : KIND_ICONS[it.kind]} size={22}
                color={dim ? c.textMuted : c.accentText} />
      <View style={{ flex: 1 }}>
        <Text style={[s.body, dim && { color: c.textMuted, textDecorationLine: it.reversed ? 'line-through' : 'none' }]}>
          {it.quantity > 1 ? `${it.quantity}x ` : ''}{it.description}
        </Text>
        <Text style={s.caption}>
          {[it.barber_name, it.covered_by !== 'none' ? `pago com ${COVER_LABEL[it.covered_by]}` : null,
            it.reversed ? 'estornado' : null, it._pending ? 'a confirmar' : null].filter(Boolean).join(' · ')}
        </Text>
      </View>
      <Text style={[s.bodyBold, dim && { color: c.textMuted }]}>{money(it.amount)}</Text>
      {canReverse && !dim ? (
        <Button title="Estornar" kind="ghost" compact onPress={() => onReverse(it)}
                accessibilityLabel={`Estornar ${it.description}`} />
      ) : null}
    </View>
  );
}

function AddItemSheet({ kind, comanda, onClose, onAdded }) {
  const { s, v } = useTheme();
  const services = useLoad(() => repo.services(), []);
  const barbers = useLoad(() => repo.barbers(), []);
  const products = useLoad(() => repo.products(), []);
  const plans = useLoad(() => repo.packagePlans(), []);
  const [serviceId, setServiceId] = useState(null);
  const [productId, setProductId] = useState(null);
  const [planId, setPlanId] = useState(null);
  const [barberId, setBarberId] = useState(null);
  const [qty, setQty] = useState(1);
  const [cover, setCover] = useState('none');
  const [digits, setDigits] = useState('');
  const [discMode, setDiscMode] = useState('value');
  const [percent, setPercent] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setServiceId(null); setProductId(null); setPlanId(null); setQty(1); setCover('none'); setDigits('');
    setPercent(null);
  }, [kind]);

  const pros = (barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }));
  const body = () => {
    if (kind === 'service') return { kind, service_id: serviceId, barber_id: barberId, quantity: qty, cover };
    if (kind === 'product') return { kind, product_id: productId, barber_id: barberId, quantity: qty };
    if (kind === 'package') return { kind, package_plan_id: planId, barber_id: barberId };
    if (kind === 'discount') {
      return discMode === 'percent' ? { kind, percent: String(percent) } : { kind, value: toApi(digits) };
    }
    return { kind, value: toApi(digits), barber_id: barberId };
  };
  const ready = {
    service: serviceId, product: productId, package: planId && comanda.customer_id,
    discount: discMode === 'percent' ? percent : toNumber(digits) > 0, tip: barberId && toNumber(digits) > 0,
  }[kind];
  const send = async (extra) => {
    setBusy(true);
    const r = await run(() => repo.addComandaItem(comanda, { ...body(), ...extra }), saved(null));
    setBusy(false);
    if (r) { onAdded(r); onClose(); } else if (kind === 'product') products.reload();
  };
  // Vender sem estoque é permitido (o produto pode estar na prateleira sem ter dado entrada), mas sempre com aviso.
  const product = kind === 'product' ? (products.data || []).find((p) => p.id === productId) : null;
  const add = () => {
    if (product && Number(product.stock) < qty) {
      const have = Number(product.stock).toLocaleString('pt-BR', { maximumFractionDigits: 3 });
      confirm('Estoque insuficiente', `${product.name} tem ${have} ${product.unit} no sistema. Vender mesmo assim? `
        + 'O estoque fica negativo até alguém dar entrada.', () => send({ allow_negative_stock: true }), 'Vender mesmo assim');
      return;
    }
    send({});
  };
  const title = { service: 'Lançar serviço', product: 'Vender produto', package: 'Vender pacote', discount: 'Desconto',
                  tip: 'Gorjeta' }[kind];
  const Qty = (
    <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(4) }]}>
      <Text style={[s.label, { flex: 1, marginBottom: 0 }]}>Quantidade</Text>
      <Button title="−" kind="ghost" compact onPress={() => setQty(Math.max(1, qty - 1))} accessibilityLabel="Menos um" />
      <Text style={[s.heading, { minWidth: 32, textAlign: 'center' }]}>{qty}</Text>
      <Button title="+" kind="ghost" compact onPress={() => setQty(qty + 1)} accessibilityLabel="Mais um" />
    </View>
  );
  return (
    <BottomSheet visible={!!kind} onClose={onClose} title={title || ''}
                 footer={<Button title="Lançar" icon="add" onPress={add} loading={busy} disabled={!ready}
                                 style={{ marginBottom: 0 }} />}>
      {kind === 'service' ? (
        <>
          <Text style={s.label}>Serviço</Text>
          <Chips value={serviceId} onChange={setServiceId} options={(services.data || []).filter((x) => x.active)
            .map((x) => ({ value: x.id, label: `${x.name} · ${money(x.price)}` }))} />
          <Text style={s.label}>{v.Pro}</Text>
          <Chips value={barberId} onChange={setBarberId} options={pros} />
          {comanda.customer_id ? (
            <>
              <Text style={s.label}>Pagamento</Text>
              <Chips value={cover} onChange={(x) => { setCover(x); if (x !== 'none') setQty(1); }} options={[
                { value: 'none', label: 'Cobrar' }, { value: 'package', label: 'Usar pacote' },
                { value: 'subscription', label: 'Usar assinatura' },
              ]} />
            </>
          ) : null}
          {cover === 'none' ? Qty : null}
        </>
      ) : null}
      {kind === 'product' ? (
        <>
          <Chips value={productId} onChange={setProductId} options={(products.data || []).filter((p) => p.kind !== 'internal')
            .map((p) => ({ value: p.id, label: `${p.name} · ${money(p.price)} (${Number(p.stock)} em estoque)` }))} />
          {Qty}
          <Text style={s.label}>Vendido por (comissão)</Text>
          <Chips value={barberId} onChange={setBarberId} options={[{ value: null, label: 'Ninguém' }, ...pros]} />
        </>
      ) : null}
      {kind === 'package' ? (
        comanda.customer_id ? (
          <Chips value={planId} onChange={setPlanId} options={(plans.data || []).filter((p) => p.active)
            .map((p) => ({ value: p.id, label: `${p.name} · ${money(p.price)}` }))} />
        ) : <Text style={s.muted}>Escolha o {v.customer} da comanda para vender um pacote.</Text>
      ) : null}
      {kind === 'discount' ? (
        <>
          <SegmentedControl value={discMode} onChange={setDiscMode} options={[
            { value: 'value', label: 'Em R$' }, { value: 'percent', label: 'Em %' }]} />
          {discMode === 'percent' ? (
            <Chips value={percent} onChange={setPercent} options={[5, 10, 15, 20, 25, 30, 50]
              .map((p) => ({ value: p, label: `${p}%` }))} />
          ) : <Keypad value={digits} onChange={setDigits} />}
        </>
      ) : null}
      {kind === 'tip' ? (
        <>
          <Text style={s.label}>Para</Text>
          <Chips value={barberId} onChange={setBarberId} options={pros} />
          <Keypad value={digits} onChange={setDigits} />
        </>
      ) : null}
    </BottomSheet>
  );
}

function PaymentPanel({ c: comanda, onChanged, canReverse }) {
  const { c, s, font } = useTheme();
  const [method, setMethod] = useState('pix');
  const [digits, setDigits] = useState(fromValue(comanda.balance));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDigits(fromValue(comanda.balance)); }, [comanda.balance]);
  const open = comanda.status === 'open';
  const pay = async () => {
    setBusy(true);
    const r = await run(() => repo.addComandaPayment(comanda, { method, amount: toApi(digits) }), saved(null));
    setBusy(false);
    if (r) onChanged(r);
  };
  const reversePay = (p) => confirm('Estornar pagamento?', `${payMethodLabel(p.method)} de ${money(p.amount)} vira um lançamento negativo.`,
    () => run(() => repo.reverseComandaPayment(comanda, p).then((r) => { onChanged(r); return r; }), saved('Pagamento estornado.')),
    'Estornar', true);
  const close = async () => {
    setBusy(true);
    const r = await run(() => repo.closeComanda(comanda), saved('Comanda fechada.',
      'Comanda fechada no aparelho. Vai para o caixa do servidor quando a internet voltar.'));
    setBusy(false);
    if (r) onChanged(r);
  };
  const Line = ({ label, value, strong }) => (
    <View style={[s.row, { marginBottom: SPACE(1.5) }]}>
      <Text style={[strong ? s.bodyBold : s.body, { flex: 1 }]}>{label}</Text>
      <Text style={strong ? { fontFamily: font.extrabold, fontSize: 22, color: c.text } : s.body}>{value}</Text>
    </View>
  );
  return (
    <Card>
      <Line label="Subtotal" value={money(comanda.subtotal)} />
      {Number(comanda.discount) ? <Line label="Desconto" value={money(comanda.discount)} /> : null}
      {Number(comanda.tips) ? <Line label="Gorjeta" value={money(comanda.tips)} /> : null}
      {Number(comanda.covered) ? <Line label="Pago com saldo" value={money(comanda.covered)} /> : null}
      <Line label="Total" value={money(comanda.due)} strong />
      <Line label="Pago" value={money(comanda.paid)} />
      <Line label={Number(comanda.balance) >= 0 ? 'Falta' : 'Troco / excedente'} value={money(Math.abs(comanda.balance))} strong />
      {comanda.payments.map((p) => (
        <View key={p.id} style={[s.row, { gap: SPACE(2), marginTop: SPACE(1) }]}>
          <Ionicons name={p.reverses_id ? 'return-down-back-outline' : METHOD_ICONS[p.method]} size={18} color={c.textMuted} />
          <Text style={[s.muted, { flex: 1 }, p.reversed && { textDecorationLine: 'line-through' }]}>
            {payMethodLabel(p.method)}{p.from_deposit ? ' (sinal)' : ''}{p.reverses_id ? ' · estorno' : ''}
          </Text>
          <Text style={s.body}>{money(p.amount)}</Text>
          {canReverse && !p.reversed && !p.reverses_id ? (
            <Button title="Estornar" kind="ghost" compact onPress={() => reversePay(p)} />
          ) : null}
        </View>
      ))}
      {open ? (
        <View style={{ marginTop: SPACE(4) }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: SPACE(2), marginBottom: SPACE(3) }}>
            {PAY_METHODS.map((m) => (
              <BigButton key={m.value} icon={METHOD_ICONS[m.value]} label={m.label} selected={method === m.value}
                         onPress={() => setMethod(m.value)} />
            ))}
          </View>
          <Keypad value={digits} onChange={setDigits} />
          <Button title={`Lançar ${payMethodLabel(method)}`} icon="add" kind="secondary" onPress={pay} loading={busy}
                  disabled={toNumber(digits) <= 0} />
          <Button title="Fechar comanda" icon="checkmark-done" onPress={close} loading={busy}
                  disabled={Number(comanda.balance) !== 0 || !comanda.items.length} />
        </View>
      ) : (
        <Badge large info={comanda.status === 'closed'
          ? { label: `Fechada ${dtLabel(comanda.closed_at).toLowerCase()}`, tone: 'success', icon: 'checkmark-circle' }
          : { label: 'Cancelada', tone: 'neutral', icon: 'close-circle-outline' }} />
      )}
    </Card>
  );
}

export function ComandaScreen({ route, navigation }) {
  const { s, v } = useTheme();
  const { wide, can } = useSession();
  const r = useLoad(() => repo.comanda(route.params.id), [route.params.id]);
  const [kind, setKind] = useState(null);
  const comanda = r.data;
  if (!comanda) return <Loading error={r.error} onRetry={r.reload} />;
  const open = comanda.status === 'open';
  const canReverse = open || can('reverseClosed');
  const update = (x) => (x && x.id ? r.setData(x) : r.reload());
  const reverse = (it) => confirm('Estornar lançamento?',
    `"${it.description}" (${money(it.amount)}) vira um lançamento negativo. Estoque e saldo de pacote voltam.`,
    () => run(() => repo.reverseComandaItem(comanda, it).then((x) => { update(x); return x; }), saved('Estornado.')),
    'Estornar', true);
  const cancel = () => confirm('Cancelar comanda?', 'Só dá para cancelar a comanda sem valor.',
    () => run(() => repo.cancelComanda(comanda).then((x) => { update(x); return x; }), saved('Comanda cancelada.')),
    'Cancelar', true);

  const items = (
    <View style={{ flex: wide ? 1.3 : undefined }}>
      <View style={[s.row, { gap: SPACE(2), marginBottom: SPACE(2) }]}>
        <Text style={[s.title, { flex: 1, marginBottom: 0 }]}>{comanda.customer_name || 'Venda avulsa'}</Text>
        {comanda.customer_id ? (
          <Button title="Ficha" kind="ghost" compact icon="person-outline"
                  onPress={() => navigation.navigate('Customer', { id: comanda.customer_id })} />
        ) : null}
      </View>
      <Text style={[s.caption, { marginBottom: SPACE(4) }]}>Aberta {dtLabel(comanda.opened_at).toLowerCase()}</Text>
      {comanda._pending ? (
        <Banner tone="warning" icon="cloud-upload-outline" title="A confirmar"
                text="Lançamentos feitos sem internet vão para o servidor quando a conexão voltar." />
      ) : null}
      {open ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: SPACE(2), marginBottom: SPACE(4) }}>
          <BigButton icon="cut-outline" label={v.Service} onPress={() => setKind('service')} />
          <BigButton icon="cube-outline" label="Produto" onPress={() => setKind('product')} />
          <BigButton icon="albums-outline" label="Pacote" onPress={() => setKind('package')} disabled={!comanda.customer_id} />
          <BigButton icon="pricetag-outline" label="Desconto" onPress={() => setKind('discount')} />
          <BigButton icon="heart-outline" label="Gorjeta" onPress={() => setKind('tip')} />
        </View>
      ) : null}
      <Section title="Lançamentos">
        {!comanda.items.length ? <Empty icon="receipt-outline" text="Nenhum item lançado." /> : (
          <Card style={{ paddingVertical: 0 }}>
            {comanda.items.map((it) => <ItemRow key={it.id} it={it} canReverse={canReverse} onReverse={reverse} />)}
          </Card>
        )}
      </Section>
      {open && Number(comanda.due) === 0 && Number(comanda.paid) === 0 ? (
        <Button title="Cancelar comanda" kind="danger" icon="close" onPress={cancel} />
      ) : null}
    </View>
  );
  const payment = (
    <View style={wide ? { width: 400 } : undefined}>
      <Section title="Pagamento"><PaymentPanel c={comanda} onChanged={update} canReverse={canReverse} /></Section>
    </View>
  );
  return (
    <Screen onRefresh={r.reload} refreshing={r.loading} maxWidth={1400}>
      {wide ? <View style={{ flexDirection: 'row', gap: SPACE(6), alignItems: 'flex-start' }}>{items}{payment}</View>
        : <>{items}{payment}</>}
      <AddItemSheet kind={kind} comanda={comanda} onClose={() => setKind(null)} onAdded={update} />
    </Screen>
  );
}

// Abre (ou retoma) a comanda de um agendamento e navega até ela
export function openComandaFor(navigation, appointmentId) {
  return run(async () => {
    const r = await repo.openComanda({ appointment_id: appointmentId });
    navigation.navigate('Comanda', { id: r.id });
    return r;
  });
}
