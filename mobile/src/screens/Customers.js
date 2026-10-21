import React, { useEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { PendingBadge } from '../components/Sync';
import { repo, saved } from '../repo';
import { Stars } from './Agenda';
import { useDebounced } from '../components/QuickBook';
import { dmy, dtLabel, gapLabel, money, phoneLabel } from '../format';
import { ACCESS, PAY, STATUS } from '../status';
import { SPACE, TOUCH } from '../theme';
import { useTheme } from '../ThemeProvider';
import { useSession } from '../session';
import { DataTable } from '../components/Layout';
import { BalanceSection } from './Plans';
import {
  Badge, Banner, BottomSheet, Button, Card, Chips, confirm, Empty, Field, Group, ListRow, Loading, Screen, Section,
  SegmentedControl, Stat, Title, Toggle, run, toast, useLoad,
  ask,
} from '../ui';

export function CustomersScreen({ navigation, route }) {
  const { c, s, v } = useTheme();
  const { can, wide } = useSession();
  const [q, setQ] = useState('');
  const search = React.useRef(null);
  // Atalho "B" (buscar cliente) no computador
  useEffect(() => { if (route?.params?.focus) search.current?.focus(); }, [route?.params?.focus]);
  const [access, setAccess] = useState('');
  const query = useDebounced(q);
  const list = useLoad(() => repo.customers({ q: query, access_status: access || null, limit: 100 }), [query, access]);
  const items = list.data || [];

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Field value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" returnKeyType="search" ref={search}
             prefix={<Ionicons name="search" size={18} color={c.textMuted} style={{ marginRight: 6 }} />} />
      {can('customerAccess') ? (
        <SegmentedControl value={access} onChange={setAccess} options={[
          { value: '', label: 'Todos' }, { value: 'approval', label: 'Aprovação' }, { value: 'blocked', label: 'Bloqueados' },
        ]} />
      ) : null}
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty icon="people-outline" text={q.trim() ? `Nenhum ${v.customer} encontrado para "${q.trim()}".` : `Nenhum ${v.customer} encontrado.`}
               action={q.trim() && can('newAppointment') ? {
                 // o cadastro do cliente acontece no primeiro agendamento
                 title: `Cadastrar "${q.trim()}" e agendar`, icon: 'person-add-outline',
                 onPress: () => navigation.navigate('NewAppointment', {
                   prefill: /^[\d\s()+-]+$/.test(q.trim()) ? { phone: q.trim() } : { name: q.trim() },
                 }),
               } : null} />
      ) : null}
      {items.length && wide ? (
        <DataTable rows={items} searchKeys={['name', 'phone']} placeholder="Filtrar resultados"
                   onRowPress={(x) => navigation.navigate('Customer', { id: x.id })} initialSort={{ key: 'name', dir: 'asc' }}
                   columns={[
                     { key: 'name', label: 'Nome', flex: 2, render: (x) => <Text style={s.bodyBold}>{x.name || 'Sem nome'}</Text> },
                     { key: 'phone', label: 'WhatsApp', render: (x) => <Text style={s.body}>{phoneLabel(x.phone)}</Text> },
                     { key: 'created_at', label: `${v.Customer} desde`, render: (x) => <Text style={s.body}>{dmy(x.created_at)}</Text> },
                     { key: 'access_status', label: 'Acesso', render: (x) => <Badge info={ACCESS[x.access_status] || { label: 'Normal', tone: 'neutral' }} /> },
                   ]} />
      ) : items.length ? (
        <Group>
          {items.map((x, i) => (
            <ListRow key={x.id} icon="person-circle-outline" title={x.name || 'Sem nome'} subtitle={phoneLabel(x.phone)}
                     first={i === 0} last={i === items.length - 1}
                     right={x._pending ? <PendingBadge item={x} />
                       : ACCESS[x.access_status] ? <Badge info={ACCESS[x.access_status]} /> : undefined}
                     onPress={() => navigation.navigate('Customer', { id: x.id })} />
          ))}
        </Group>
      ) : null}
    </Screen>
  );
}

// Acesso ao agendamento pelo bot: aprovação manual ou bloqueio (motivo só para o dono)
function AccessSection({ d, onSaved }) {
  const { s, v } = useTheme();
  const [status, setStatus] = useState(d.access_status);
  const [reason, setReason] = useState(d.access_reason);
  useEffect(() => { setStatus(d.access_status); setReason(d.access_reason); }, [d.access_status, d.access_reason]);

  const save = (cancelFuture = false, notify = false) => run(async () => {
    const r = await api.put(`/customers/${d.id}/access`, {
      access_status: status, access_reason: reason, cancel_future: cancelFuture, notify_customer: notify,
    });
    onSaved();
    return r;
  }).then((r) => {
    if (r) toast(r.cancelled ? `Acesso atualizado. ${r.cancelled} agendamento(s) cancelado(s).` : 'Acesso atualizado.');
  });

  const onSave = () => {
    if (status === 'blocked' && d.access_status !== 'blocked' && d.future_appointments > 0) {
      ask(
        'Cancelar os agendamentos futuros?',
        `${d.name || `Este ${v.customer}`} tem ${d.future_appointments} agendamento(s) futuro(s).`,
        [
          { text: 'Voltar', style: 'cancel' },
          { text: 'Manter os agendamentos', onPress: () => save(false) },
          { text: 'Cancelar sem avisar', style: 'destructive', onPress: () => save(true, false) },
          { text: `Cancelar e avisar o ${v.customer}`, style: 'destructive', onPress: () => save(true, true) },
        ],
      );
      return;
    }
    save();
  };

  const changed = status !== d.access_status || reason !== d.access_reason;
  return (
    <Section title="Agendamento pelo WhatsApp">
      {d.access_status === 'blocked' && d.future_appointments > 0 ? (
        <Banner tone="danger" icon="ban-outline" title={`Bloqueado com ${d.future_appointments} agendamento(s) futuro(s)`}
                text="Eles não foram cancelados. Abra no histórico abaixo para decidir." />
      ) : null}
      <Card>
        <Toggle label="Aprovação manual obrigatória" value={status === 'approval'} disabled={status === 'blocked'}
                onValueChange={(on) => setStatus(on ? 'approval' : 'normal')}
                hint={`O pedido fica reservado e só vale depois que você aprovar. O ${v.customer} não sabe o motivo.`} />
        <Toggle label="Bloqueado" value={status === 'blocked'} onValueChange={(on) => setStatus(on ? 'blocked' : 'normal')}
                hint={`O bot responde que não consegue agendar por aqui e pede para falar com a ${v.business}. O ${v.customer} não é avisado do bloqueio.`} />
        {status !== 'normal' ? (
          <Field label={`Motivo (interno, o ${v.customer} não vê)`} value={reason} onChangeText={setReason} multiline
                 placeholder="Ex.: faltou 3 vezes sem avisar" />
        ) : null}
        {d.access_changed_at && d.access_status !== 'normal' ? (
          <Text style={[s.caption, { marginBottom: SPACE(3) }]}>Desde {dmy(d.access_changed_at)}</Text>
        ) : null}
        {changed ? <Button title="Salvar" icon="checkmark" onPress={onSave} style={{ marginBottom: 0 }} /> : null}
      </Card>
    </Section>
  );
}

const GAP_OPTIONS = [60, 120, 240, 480];
const ACTIONS = [
  { value: 'block', label: 'Bloquear o horário' },
  { value: 'approval', label: 'Exigir minha aprovação' },
];

// Cadastro e edição de um par de clientes incompatíveis
function ConflictSheet({ d, edit, visible, onClose, onSaved, defaultGap }) {
  const { s, c, v } = useTheme();
  const [q, setQ] = useState('');
  const query = useDebounced(q);
  const [found, setFound] = useState([]);
  const [other, setOther] = useState(null);
  const [gap, setGap] = useState('default');
  const [action, setAction] = useState('block');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!visible) return;
    setQ(''); setFound([]);
    setOther(edit ? { id: edit.other_customer_id, name: edit.other_customer_name, phone: edit.other_customer_phone } : null);
    setGap(edit ? (edit.same_day_block ? 'day' : edit.min_gap_minutes ?? 'default') : 'default');
    setAction(edit?.conflict_action || 'block');
    setNotes(edit?.notes || '');
  }, [visible, edit]);
  useEffect(() => {
    if (!visible || other || query.trim().length < 2) { setFound([]); return; }
    repo.customers({ q: query, limit: 10 }).then((r) => setFound(r.filter((x) => x.id !== d.id && typeof x.id === 'number')))
      .catch(() => setFound([]));
  }, [query, visible, other, d.id]);

  const body = () => ({
    min_gap_minutes: typeof gap === 'number' ? gap : null, same_day_block: gap === 'day', conflict_action: action, notes,
  });
  const save = async () => {
    setBusy(true);
    const r = await run(() => (edit ? api.put(`/customer-conflicts/${edit.id}`, body())
      : api.post('/customer-conflicts', { customer_id: d.id, other_customer_id: other.id, ...body() })),
    edit ? 'Regra atualizada.' : `Os dois não serão mais agendados perto um do outro.`);
    setBusy(false);
    if (r) onSaved();
  };
  const remove = () => confirm('Remover?', `${edit.other_customer_name} poderá ser agendado perto de ${d.name || `este ${v.customer}`} de novo.`,
    () => run(async () => { await api.del(`/customer-conflicts/${edit.id}`); onSaved(); }, 'Removido.'), 'Remover', true);

  return (
    <BottomSheet visible={visible} onClose={onClose} title={edit ? 'Incompatível com' : 'Adicionar incompatível'}
                 footer={other ? <Button title="Salvar" icon="checkmark" onPress={save} loading={busy} style={{ marginBottom: 0 }} /> : null}>
      {!other ? (
        <>
          <Field value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" autoFocus
                 prefix={<Ionicons name="search" size={18} color={c.textMuted} style={{ marginRight: 6 }} />} />
          {found.map((x, i) => (
            <ListRow key={x.id} icon="person-outline" title={x.name || 'Sem nome'} subtitle={phoneLabel(x.phone)}
                     first={i === 0} last={i === found.length - 1} onPress={() => setOther(x)} />
          ))}
          {query.trim().length >= 2 && !found.length ? <Text style={s.muted}>Nenhum {v.customer} encontrado.</Text> : null}
        </>
      ) : (
        <>
          <View style={[s.row, { marginBottom: SPACE(4), gap: SPACE(2) }]}>
            <Ionicons name="person-circle-outline" size={28} color={c.accentText} />
            <Text style={[s.bodyBold, { flex: 1 }]}>{other.name || phoneLabel(other.phone)}</Text>
            {!edit ? <Button title="Trocar" kind="ghost" compact onPress={() => setOther(null)} /> : null}
          </View>
          <Text style={s.label}>Distância mínima entre os {v.services}</Text>
          <Chips value={gap} onChange={setGap} options={[
            { value: 'default', label: `Padrão (${gapLabel(defaultGap)})` },
            ...GAP_OPTIONS.map((m) => ({ value: m, label: gapLabel(m) })),
            { value: 'day', label: 'Dia inteiro' },
          ]} />
          <Text style={[s.caption, { marginTop: -SPACE(2), marginBottom: SPACE(4) }]}>
            Vale entre o fim de um e o início do outro, com qualquer {v.pro}.
          </Text>
          <Text style={s.label}>Quando o horário ficar perto demais</Text>
          <Chips value={action} onChange={setAction} options={ACTIONS} />
          <Text style={[s.caption, { marginTop: -SPACE(2), marginBottom: SPACE(4) }]}>
            {action === 'block' ? 'O bot esconde os horários próximos, sem explicar o motivo.'
              : 'O bot deixa pedir o horário, mas ele só vale depois que você aprovar.'}
          </Text>
          <Field label="Motivo (interno)" value={notes} onChangeText={setNotes} multiline placeholder="Ex.: discutiram no atendimento" />
          {edit ? <Button title="Remover" kind="danger" icon="trash-outline" onPress={remove} /> : null}
        </>
      )}
    </BottomSheet>
  );
}

// Clientes que não podem estar no local ao mesmo tempo que este
function ConflictsSection({ d, navigation }) {
  const { c, s, font, v } = useTheme();
  const list = useLoad(() => api.get('/customer-conflicts', { customer_id: d.id }), [d.id]);
  const shop = useLoad(() => api.get('/shop'), []);
  const [sheet, setSheet] = useState(null); // { edit } ou {} para adicionar
  const defaultGap = shop.data?.conflict_default_gap_minutes ?? 240;
  const items = list.data || [];
  const rule = (x) => (x.same_day_block ? 'dia inteiro' : gapLabel(x.effective_gap_minutes));

  return (
    <Section title="Incompatível com">
      {!list.data ? <Loading error={list.error} onRetry={list.reload} rows={1} /> : null}
      {list.data && !items.length ? (
        <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
          Ninguém. Use quando dois {v.customers} não podem estar no local ao mesmo tempo.
        </Text>
      ) : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: SPACE(2), marginBottom: SPACE(3) }}>
        {items.map((x) => (
          <Pressable key={x.id} onPress={() => setSheet({ edit: x })} onLongPress={() => navigation.push('Customer', { id: x.other_customer_id })}
                     accessibilityRole="button" accessibilityHint="Toque para editar; segure para abrir a ficha"
                     style={{
                       flexDirection: 'row', alignItems: 'center', gap: SPACE(1.5), minHeight: TOUCH, paddingHorizontal: SPACE(3),
                       borderRadius: 999, borderWidth: 1, borderColor: c.statusText.danger, backgroundColor: c.statusBg.danger,
                     }}>
            <Ionicons name={x.conflict_action === 'approval' ? 'shield-checkmark-outline' : 'ban-outline'} size={16} color={c.statusText.danger} />
            <Text style={{ fontFamily: font.semibold, fontSize: 15, color: c.statusText.danger }}>
              {x.other_customer_name || phoneLabel(x.other_customer_phone)} · {rule(x)}
            </Text>
          </Pressable>
        ))}
        <Pressable onPress={() => setSheet({})} accessibilityRole="button" accessibilityLabel={`Adicionar ${v.customer} incompatível`}
                   style={{
                     flexDirection: 'row', alignItems: 'center', gap: SPACE(1.5), minHeight: TOUCH, paddingHorizontal: SPACE(4),
                     borderRadius: 999, borderWidth: 1, borderColor: c.border, borderStyle: 'dashed',
                   }}>
          <Ionicons name="add" size={18} color={c.accentText} />
          <Text style={{ fontFamily: font.semibold, fontSize: 15, color: c.accentText }}>Adicionar</Text>
        </Pressable>
      </View>
      <ConflictSheet d={d} edit={sheet?.edit} visible={!!sheet} defaultGap={defaultGap}
                     onClose={() => setSheet(null)} onSaved={() => { setSheet(null); list.reload(); }} />
    </Section>
  );
}

export function CustomerScreen({ route, navigation }) {
  const { s, v } = useTheme();
  const { can } = useSession();
  const cust = useLoad(() => repo.customer(route.params.id), [route.params.id]);
  const [name, setName] = useState(null);
  const [notes, setNotes] = useState(null);
  if (!cust.data) return <Loading error={cust.error} onRetry={cust.reload} />;
  const d = cust.data;
  const dirty = (name !== null && name !== d.name) || (notes !== null && notes !== d.notes);
  const save = () => run(async () => {
    const r = await repo.updateCustomer(d, { name: name ?? d.name, notes: notes ?? d.notes });
    setName(null); setNotes(null);
    cust.reload();
    return r;
  }, saved(`${v.Customer} atualizado.`));

  return (
    <Screen footer={dirty ? <Button title="Salvar dados" icon="checkmark" onPress={save} style={{ marginBottom: 0 }} /> : null}>
      <View style={[s.row, { gap: SPACE(2), flexWrap: 'wrap' }]}>
        <Title style={{ flexShrink: 1, marginBottom: 0 }}>{d.name || 'Sem nome'}</Title>
        <Badge info={ACCESS[d.access_status]} large />
      </View>
      <Text style={[s.muted, { marginBottom: SPACE(4), marginTop: SPACE(1) }]}>
        {phoneLabel(d.phone)}{d.created_at ? ` · desde ${dmy(d.created_at)}` : ''}
      </Text>
      {d._partial ? (
        <Banner tone="info" icon="cloud-offline-outline" title="Sem internet: dados do aparelho"
                text={`Histórico e totais contam só os ${v.services} dos últimos 30 dias e dos próximos 60.`} />
      ) : null}
      <View style={[s.row, { gap: SPACE(2), marginBottom: SPACE(4), flexWrap: 'wrap' }]}>
        <Stat label={v.Services} value={d.visits} />
        <Stat label="Faltas" value={d.no_shows} tone={d.no_shows ? 'danger' : undefined} icon={d.no_shows ? 'alert-circle-outline' : undefined} />
        <Stat label="Total gasto" value={money(d.total_spent)} />
      </View>
      <View style={[s.row, { gap: SPACE(2), flexWrap: 'wrap' }]}>
        <Button title="WhatsApp" kind="ghost" icon="logo-whatsapp" style={{ flex: 1 }}
                onPress={() => Linking.openURL(`https://wa.me/${d.phone}`)} />
        {can('comandas') ? (
          <Button title="Nova comanda" kind="ghost" icon="receipt-outline" style={{ flex: 1 }}
                  onPress={() => run(async () => {
                    const r = await repo.openComanda({ customer_id: d.id });
                    navigation.navigate('Comanda', { id: r.id });
                  })} />
        ) : null}
      </View>
      {can('customerBalance') ? (
        <BalanceSection balance={d.balance} customer={d} navigation={navigation} onChanged={cust.reload} />
      ) : null}
      {can('customerEdit') ? (
        <Section title="Dados">
          <Field label="Nome" value={name ?? d.name} onChangeText={setName} autoCapitalize="words" />
          <Field label="Observações" value={notes ?? d.notes} onChangeText={setNotes} multiline placeholder="Preferências, cuidados, histórico" />
        </Section>
      ) : d.notes ? <Section title="Observações"><Text style={s.body}>{d.notes}</Text></Section> : null}
      {can('customerAccess') && !d._partial ? <AccessSection d={d} onSaved={cust.reload} /> : null}
      {can('customerAccess') && !d._partial ? <ConflictsSection d={d} navigation={navigation} /> : null}
      <Section title="Histórico">
        {!d.appointments.length ? <Empty text={`Sem ${v.services} ainda.`} /> : null}
        {d.appointments.map((a) => (
          <Card key={a.id} onPress={() => navigation.navigate('Appointment', { id: a.id, item: a })}>
            <Text style={s.bodyBold}>{dtLabel(a.start)}</Text>
            <Text style={s.muted}>{a.service_name} · {a.barber_name} · {money(a.price)}</Text>
            <View style={[s.row, { gap: SPACE(1.5), marginTop: SPACE(2), flexWrap: 'wrap' }]}>
              <Badge info={STATUS[a.status]} />
              <Badge info={PAY[a.payment_status]} />
              {a.rating ? <Stars n={a.rating} /> : null}
            </View>
          </Card>
        ))}
      </Section>
    </Screen>
  );
}
