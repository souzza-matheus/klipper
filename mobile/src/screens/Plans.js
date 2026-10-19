import React, { useEffect, useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { api } from '../api';
import { DataTable } from '../components/Layout';
import { useDebounced } from '../components/QuickBook';
import { ReceiptReview } from '../components/ReceiptReview';
import { dmy, money, moneyInput, parseMoney, phoneLabel } from '../format';
import { useSession } from '../session';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, Button, Card, Chips, confirm, Empty, Field, IconButton, Loading, Screen, Section, SegmentedControl,
  Stat, Toggle, run, toast, useLoad,
} from '../ui';

export const SUB_STATUS = {
  ativa: { label: 'Em dia', tone: 'success', icon: 'checkmark-circle-outline' },
  atrasada: { label: 'Atrasada', tone: 'warning', icon: 'alert-circle-outline' },
  cancelada: { label: 'Cancelada', tone: 'neutral', icon: 'close-circle-outline' },
};
const CHARGE_STATUS = {
  pending: { label: 'Pendente', tone: 'warning', icon: 'time-outline' },
  paid: { label: 'Paga', tone: 'success', icon: 'checkmark-circle' },
  cancelled: { label: 'Cancelada', tone: 'neutral', icon: 'close-circle-outline' },
  expired: { label: 'Expirada', tone: 'neutral', icon: 'close-circle-outline' },
};

function useAddButton(navigation, route, label, feature, params = {}) {
  const { can } = useSession();
  useLayoutEffect(() => {
    if (!can(feature)) return;
    navigation.setOptions({ headerRight: () => (
      <IconButton icon="add-circle" size={30} label={label} onPress={() => navigation.navigate(route, params)} />
    ) });
  }, [navigation]); // eslint-disable-line react-hooks/exhaustive-deps
}

// ---------------------------------------------------------------- pacotes

export function PackagesScreen({ navigation }) {
  const { s } = useTheme();
  const { can } = useSession();
  const list = useLoad(() => api.get('/package-plans'), []);
  const services = useLoad(() => api.get('/services'), []);
  useAddButton(navigation, 'PackageEdit', 'Novo pacote', 'packageEdit');
  const svc = Object.fromEntries((services.data || []).map((x) => [x.id, x]));
  const items = list.data || [];
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Text style={[s.muted, { marginBottom: SPACE(4) }]}>
        Sessões pré-pagas com desconto. O pacote é vendido na comanda ou pelo WhatsApp (opção 8 do menu) e usado
        sozinho no agendamento.
      </Text>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty icon="albums-outline" text="Nenhum pacote cadastrado."
               action={can('packageEdit') ? { title: 'Novo pacote', icon: 'add', onPress: () => navigation.navigate('PackageEdit', {}) } : null} />
      ) : null}
      {items.map((p) => {
        const each = Number(p.price) / p.sessions;
        const full = svc[p.service_id] ? Number(svc[p.service_id].price) * p.sessions : null;
        return (
          <Card key={p.id} onPress={can('packageEdit') ? () => navigation.navigate('PackageEdit', { item: p }) : undefined}>
            <View style={[s.row, { gap: SPACE(2) }]}>
              <Text style={[s.bodyBold, { flex: 1 }]}>{p.name}{p.active ? '' : ' (inativo)'}</Text>
              <Text style={s.bodyBold}>{money(p.price)}</Text>
            </View>
            <Text style={s.caption}>
              {p.sessions}x {svc[p.service_id]?.name || 'serviço'} · {money(each)} por sessão
              {full && full > Number(p.price) ? ` · economia de ${money(full - Number(p.price))}` : ''}
              {p.validity_days ? ` · validade ${p.validity_days} dias` : ' · sem validade'}
            </Text>
          </Card>
        );
      })}
    </Screen>
  );
}

export function PackageEditScreen({ navigation, route }) {
  const { s } = useTheme();
  const item = route.params?.item;
  const services = useLoad(() => api.get('/services'), []);
  const [name, setName] = useState(item?.name || '');
  const [serviceId, setServiceId] = useState(item?.service_id || null);
  const [sessions, setSessions] = useState(item ? String(item.sessions) : '4');
  const [price, setPrice] = useState(item ? moneyInput(item.price) : '');
  const [validity, setValidity] = useState(item ? String(item.validity_days) : '90');
  const [active, setActive] = useState(item ? item.active : true);
  const save = () => run(async () => {
    const body = { name, service_id: serviceId, sessions: Number(sessions), price: (parseMoney(price) ?? 0).toFixed(2),
                   validity_days: Number(validity) || 0, active };
    if (item) await api.put(`/package-plans/${item.id}`, body);
    else await api.post('/package-plans', body);
    navigation.goBack();
  }, 'Pacote salvo.');
  return (
    <Screen footer={<Button title="Salvar" icon="checkmark" onPress={save} style={{ marginBottom: 0 }}
                            disabled={!name || !serviceId || !price || !Number(sessions)} />}>
      <Field label="Nome" value={name} onChangeText={setName} placeholder="Ex.: 4 cortes" />
      <Text style={s.label}>Serviço</Text>
      <Chips value={serviceId} onChange={setServiceId} options={(services.data || []).filter((x) => x.active)
        .map((x) => ({ value: x.id, label: `${x.name} · ${money(x.price)}` }))} />
      <Field label="Número de sessões" value={sessions} onChangeText={setSessions} keyboardType="number-pad" />
      <Field label="Preço do pacote" mask="money" value={price} onChangeText={setPrice}
             hint={Number(sessions) && parseMoney(price) ? `${money(parseMoney(price) / Number(sessions))} por sessão (base da comissão)` : undefined} />
      <Field label="Validade (dias, 0 = sem validade)" value={validity} onChangeText={setValidity} keyboardType="number-pad" />
      <Toggle label="À venda" value={active} onValueChange={setActive} />
      {item ? (
        <Button title="Excluir" kind="danger" icon="trash-outline" onPress={() => confirm('Excluir pacote?',
          'Quem já comprou continua com o saldo.',
          () => run(async () => { await api.del(`/package-plans/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- clube de assinatura

function Charges({ list, onChanged }) {
  const { s } = useTheme();
  const { can } = useSession();
  if (!list.data) return <Loading error={list.error} onRetry={list.reload} />;
  if (!list.data.length) return <Empty icon="receipt-outline" text="Nenhuma cobrança pendente." />;
  const openReceipt = (ch) => (ch.receipt && !ch.receipt.decision ? ch.receipt : null);
  const confirmCh = (ch) => confirm('Confirmar Pix?', `Confira no extrato: ${money(ch.amount)} de ${ch.customer_name}.`,
    () => run(() => api.post(openReceipt(ch) ? `/receipts/${ch.receipt.id}/confirm` : `/charges/${ch.id}/confirm`)
      .then(onChanged), 'Pagamento confirmado. O cliente foi avisado.'),
    'Recebi');
  const rejectReceipt = (ch) => confirm('Recusar o comprovante?',
    `${ch.customer_name} recebe uma mensagem neutra pedindo para conferir o pagamento. A cobrança continua aberta.`,
    () => run(() => api.post(`/receipts/${ch.receipt.id}/reject`).then(onChanged), 'Comprovante recusado. O cliente foi avisado.'),
    'Recusar', true);
  return list.data.map((ch) => (
    <Card key={ch.id}>
      <View style={[s.row, { gap: SPACE(2) }]}>
        <Text style={[s.bodyBold, { flex: 1 }]}>{ch.customer_name}</Text>
        <Text style={s.bodyBold}>{money(ch.amount)}</Text>
      </View>
      <Text style={s.caption}>
        {ch.kind === 'subscription' ? 'Mensalidade' : 'Pacote'} · vencimento {dmy(ch.due_date)}
        {ch.customer_reported_at ? ' · cliente disse que pagou' : ''}
      </Text>
      {ch.receipt ? (
        <View style={{ marginTop: SPACE(3) }}>
          <ReceiptReview receipt={ch.receipt} paid={ch.status === 'paid'} onChanged={onChanged} />
        </View>
      ) : null}
      <View style={[s.row, { gap: SPACE(2), marginTop: SPACE(3), flexWrap: 'wrap' }]}>
        <Badge info={CHARGE_STATUS[ch.status]} />
        <View style={{ flex: 1 }} />
        {ch.status === 'pending' ? (
          <>
            <Button title="Reenviar Pix" kind="ghost" compact icon="logo-whatsapp"
                    onPress={() => run(() => api.post(`/charges/${ch.id}/resend`).then(onChanged), 'Pix reenviado.')} />
            {ch.brcode ? (
              <Button title="Copiar Pix" kind="ghost" compact icon="copy-outline"
                      onPress={() => Clipboard.setStringAsync(ch.brcode).then(() => toast('Código Pix copiado.'))} />
            ) : null}
            {can('chargeCancel') ? (
              <Button title="Cancelar" kind="ghost" compact onPress={() => confirm('Cancelar cobrança?', '',
                () => run(() => api.post(`/charges/${ch.id}/cancel`).then(onChanged), 'Cobrança cancelada.'),
                'Cancelar cobrança', true)} />
            ) : null}
            {openReceipt(ch) ? (
              <Button title="Recusar" kind="danger" compact icon="close-circle-outline" onPress={() => rejectReceipt(ch)} />
            ) : null}
            <Button title="Recebi" compact icon="checkmark" onPress={() => confirmCh(ch)} />
          </>
        ) : null}
      </View>
    </Card>
  ));
}

export function SubscriptionsScreen({ navigation }) {
  const { s, v } = useTheme();
  const { can, wide } = useSession();
  const [tab, setTab] = useState('subs');
  const [status, setStatus] = useState(null);
  const subs = useLoad(() => api.get('/subscriptions'), []);
  const report = useLoad(async () => (can('mrr') ? api.get('/subscriptions/report') : null), []);
  const charges = useLoad(() => api.get('/charges', { status: 'pending' }), []);
  const plans = useLoad(() => api.get('/subscription-plans'), []);
  const reload = () => { subs.reload(); report.reload(); charges.reload(); plans.reload(); };
  const rows = (subs.data || []).filter((x) => !status || x.status === status);
  const r = report.data;
  return (
    <Screen onRefresh={reload} refreshing={subs.loading && !!subs.data}>
      {r ? (
        <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(4), flexWrap: 'wrap' }]}>
          <Stat icon="trending-up-outline" label="Receita recorrente (MRR)" value={money(r.mrr)} />
          <Stat icon="people-outline" label="Em dia" value={r.active} />
          <Stat icon="alert-circle-outline" label="Atrasadas" value={r.late} tone="warning" />
        </View>
      ) : null}
      {charges.data?.length ? (
        <Banner tone="warning" icon="cash-outline" onPress={() => setTab('charges')}
                title={`${charges.data.length} cobrança(s) aguardando confirmação`} />
      ) : null}
      <SegmentedControl value={tab} onChange={setTab} options={[
        { value: 'subs', label: 'Assinantes' }, { value: 'charges', label: 'Cobranças' }, { value: 'plans', label: 'Planos' },
      ]} />
      {tab === 'subs' ? (
        <>
          <Button title={`Assinar plano para um ${v.customer}`} icon="add" kind="secondary"
                  onPress={() => navigation.navigate('Subscribe', {})} />
          <Chips value={status} onChange={setStatus} options={[{ value: null, label: 'Todas' },
            ...Object.entries(SUB_STATUS).map(([k, x]) => ({ value: k, label: x.label }))]} />
          {!subs.data ? <Loading error={subs.error} onRetry={subs.reload} /> : !rows.length ? (
            <Empty icon="repeat-outline" text="Nenhum assinante." />
          ) : wide ? (
            <DataTable rows={rows} searchKeys={['customer_name', 'plan_name']} placeholder={`Buscar ${v.customer} ou plano`}
                       onRowPress={(x) => navigation.navigate('Customer', { id: x.customer_id })}
                       initialSort={{ key: 'next_due_date', dir: 'asc' }} columns={[
                         { key: 'customer_name', label: v.Customer, flex: 2 },
                         { key: 'plan_name', label: 'Plano', flex: 1.5 },
                         { key: 'price', label: 'Valor', align: 'right', render: (x) => <Text style={s.body}>{money(x.price)}</Text> },
                         { key: 'next_due_date', label: 'Próx. cobrança', render: (x) => <Text style={s.body}>{dmy(x.next_due_date)}</Text> },
                         { key: 'status', label: 'Status', render: (x) => <Badge info={SUB_STATUS[x.status]} /> },
                       ]} />
          ) : rows.map((x) => (
            <Card key={x.id} onPress={() => navigation.navigate('Customer', { id: x.customer_id })}>
              <View style={[s.row, { gap: SPACE(2) }]}>
                <Text style={[s.bodyBold, { flex: 1 }]}>{x.customer_name}</Text>
                <Badge info={SUB_STATUS[x.status]} />
              </View>
              <Text style={s.caption}>
                {x.plan_name} · {money(x.price)}/mês · próxima cobrança {dmy(x.next_due_date)}
                {x.days_late ? ` · ${x.days_late} dia(s) de atraso` : ''}{x.benefits_blocked ? ' · benefícios bloqueados' : ''}
              </Text>
            </Card>
          ))}
        </>
      ) : null}
      {tab === 'charges' ? <Charges list={charges} onChanged={reload} /> : null}
      {tab === 'plans' ? (
        <>
          {can('planEdit') ? <Button title="Novo plano" icon="add" kind="secondary" onPress={() => navigation.navigate('PlanEdit', {})} /> : null}
          {(plans.data || []).map((p) => (
            <Card key={p.id} onPress={can('planEdit') ? () => navigation.navigate('PlanEdit', { item: p }) : undefined}>
              <View style={[s.row, { gap: SPACE(2) }]}>
                <Text style={[s.bodyBold, { flex: 1 }]}>{p.name}{p.active ? '' : ' (inativo)'}</Text>
                <Text style={s.bodyBold}>{money(p.price)}/mês</Text>
              </View>
              <Text style={s.caption}>{p.items.length} serviço(s) incluído(s) · bloqueia após {p.block_after_days} dia(s) de atraso</Text>
            </Card>
          ))}
          {plans.data && !plans.data.length ? <Empty icon="repeat-outline" text="Nenhum plano cadastrado." /> : null}
        </>
      ) : null}
    </Screen>
  );
}

export function PlanEditScreen({ navigation, route }) {
  const { s } = useTheme();
  const item = route.params?.item;
  const services = useLoad(() => api.get('/services'), []);
  const [name, setName] = useState(item?.name || '');
  const [price, setPrice] = useState(item ? moneyInput(item.price) : '');
  const [block, setBlock] = useState(item ? String(item.block_after_days) : '5');
  const [active, setActive] = useState(item ? item.active : true);
  // { service_id: limite ('' = sem limite) }
  const [limits, setLimits] = useState(Object.fromEntries((item?.items || [])
    .map((i) => [i.service_id, i.limit_per_period ? String(i.limit_per_period) : ''])));
  const toggle = (id) => setLimits((l) => {
    const n = { ...l };
    if (id in n) delete n[id]; else n[id] = '';
    return n;
  });
  const save = () => run(async () => {
    const body = { name, price: (parseMoney(price) ?? 0).toFixed(2), block_after_days: Number(block) || 0, active,
                   items: Object.entries(limits).map(([id, lim]) => ({ service_id: Number(id),
                                                                        limit_per_period: lim ? Number(lim) : null })) };
    if (item) await api.put(`/subscription-plans/${item.id}`, body);
    else await api.post('/subscription-plans', body);
    navigation.goBack();
  }, 'Plano salvo.');
  return (
    <Screen footer={<Button title="Salvar" icon="checkmark" onPress={save} style={{ marginBottom: 0 }}
                            disabled={!name || !price || !Object.keys(limits).length} />}>
      <Field label="Nome do plano" value={name} onChangeText={setName} placeholder="Ex.: Clube Mensal" />
      <Field label="Mensalidade" mask="money" value={price} onChangeText={setPrice} />
      <Field label="Bloquear benefícios após (dias de atraso)" value={block} onChangeText={setBlock} keyboardType="number-pad" />
      <Toggle label="Aceitando novos assinantes" value={active} onValueChange={setActive} />
      <Section title="Serviços incluídos">
        {(services.data || []).filter((x) => x.active).map((x) => {
          const on = x.id in limits;
          return (
            <Card key={x.id}>
              <Toggle label={x.name} value={on} onValueChange={() => toggle(x.id)} />
              {on ? (
                <Field label="Limite por mês (vazio = sem limite)" value={limits[x.id]} keyboardType="number-pad"
                       onChangeText={(t) => setLimits((l) => ({ ...l, [x.id]: t.replace(/\D/g, '') }))}
                       style={{ marginBottom: 0 }} />
              ) : null}
            </Card>
          );
        })}
      </Section>
      {item ? (
        <Button title="Excluir" kind="danger" icon="trash-outline" onPress={() => confirm('Excluir plano?',
          'Quem já assina continua com a assinatura até cancelar.',
          () => run(async () => { await api.del(`/subscription-plans/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

export function SubscribeScreen({ navigation, route }) {
  const { c, s, v } = useTheme();
  const plans = useLoad(() => api.get('/subscription-plans'), []);
  const [customer, setCustomer] = useState(route.params?.customer || null);
  const [q, setQ] = useState('');
  const query = useDebounced(q);
  const [found, setFound] = useState([]);
  const [planId, setPlanId] = useState(null);
  const [chargeNow, setChargeNow] = useState(true);
  useEffect(() => {
    if (customer || query.length < 2) { setFound([]); return; }
    api.get('/customers', { q: query, limit: 8 }).then(setFound).catch(() => setFound([]));
  }, [query, customer]);
  const save = () => run(async () => {
    await api.post('/subscriptions', { customer_id: customer.id, plan_id: planId, charge_now: chargeNow });
    navigation.goBack();
  }, chargeNow ? 'Assinatura criada. O Pix da mensalidade foi enviado pelo WhatsApp.' : 'Assinatura criada.');
  return (
    <Screen footer={<Button title="Assinar" icon="checkmark" onPress={save} disabled={!customer || !planId} style={{ marginBottom: 0 }} />}>
      {customer ? (
        <Card>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Ionicons name="person-circle-outline" size={28} color={c.accentText} />
            <View style={{ flex: 1 }}>
              <Text style={s.bodyBold}>{customer.name || 'Sem nome'}</Text>
              <Text style={s.caption}>{phoneLabel(customer.phone)}</Text>
            </View>
            <Button title="Trocar" kind="ghost" compact onPress={() => setCustomer(null)} />
          </View>
        </Card>
      ) : (
        <>
          <Field label={v.Customer} value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" />
          {found.map((x) => (
            <Card key={x.id} onPress={() => setCustomer(x)}>
              <Text style={s.bodyBold}>{x.name || 'Sem nome'}</Text>
              <Text style={s.caption}>{phoneLabel(x.phone)}</Text>
            </Card>
          ))}
        </>
      )}
      <Section title="Plano">
        <Chips value={planId} onChange={setPlanId} options={(plans.data || []).filter((p) => p.active)
          .map((p) => ({ value: p.id, label: `${p.name} · ${money(p.price)}/mês` }))} />
      </Section>
      <Toggle label="Cobrar a primeira mensalidade agora (Pix pelo WhatsApp)" value={chargeNow} onValueChange={setChargeNow}
              hint="A cobrança dos meses seguintes sai sozinha no dia do vencimento. A confirmação do Pix é manual." />
    </Screen>
  );
}

// Saldo do cliente (ficha): pacotes e assinatura
export function BalanceSection({ balance, customer, navigation, onChanged }) {
  const { s } = useTheme();
  if (!balance) return null;
  const pk = balance.packages.filter((p) => p.state !== 'cancelado');
  const subs = balance.subscriptions.filter((x) => x.status !== 'cancelada');
  const PKG = {
    ativo: { label: 'Ativo', tone: 'success' }, vencido: { label: 'Vencido', tone: 'neutral' },
    esgotado: { label: 'Esgotado', tone: 'neutral' }, aguardando_pagamento: { label: 'Aguardando Pix', tone: 'warning' },
  };
  return (
    <Section title="Pacotes e assinatura">
      {!pk.length && !subs.length ? <Text style={[s.muted, { marginBottom: SPACE(3) }]}>Sem pacote nem assinatura.</Text> : null}
      {pk.map((p) => (
        <Card key={`p${p.id}`}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Text style={[s.bodyBold, { flex: 1 }]}>{p.name}</Text>
            <Badge info={PKG[p.state]} />
          </View>
          <Text style={s.caption}>
            {p.balance} de {p.sessions} sessões de {p.service_name}{p.expires_at ? ` · vale até ${dmy(p.expires_at)}` : ''}
          </Text>
        </Card>
      ))}
      {subs.map((x) => (
        <Card key={`s${x.id}`}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Text style={[s.bodyBold, { flex: 1 }]}>{x.plan_name}</Text>
            <Badge info={SUB_STATUS[x.status]} />
          </View>
          <Text style={s.caption}>
            {x.items.map((i) => `${i.service_name}: ${i.limit == null ? 'à vontade' : `${i.remaining} de ${i.limit}`}`).join(' · ')}
            {x.benefits_blocked ? ' · benefícios bloqueados pelo atraso' : ''}
          </Text>
          <Button title="Cancelar assinatura" kind="ghost" compact style={{ marginTop: SPACE(2), alignSelf: 'flex-start' }}
                  onPress={() => confirm('Cancelar assinatura?', 'As cobranças pendentes também são canceladas.',
                    () => run(() => api.post(`/subscriptions/${x.id}/cancel`).then(onChanged),
                      'Assinatura cancelada.'), 'Cancelar assinatura', true)} />
        </Card>
      ))}
      <Button title="Assinar plano" kind="ghost" icon="repeat-outline"
              onPress={() => navigation.navigate('Subscribe', { customer })} />
    </Section>
  );
}
