import React, { useEffect, useState } from 'react';
import { Alert, Linking, Text, View } from 'react-native';
import { api } from '../api';
import { ACCESS_OPTIONS, dmy, dtLabel, gapLabel, money, phoneLabel } from '../format';
import { ACCESS, colors, PAY, STATUS } from '../theme';
import {
  Badge, Button, Card, Chips, confirm, Empty, Field, Label, ListRow, Loading, Muted, Screen, Section, Stat, Title, run,
  s, useLoad,
} from '../ui';

const FILTERS = [
  { value: null, label: 'Todos' },
  { value: 'approval', label: 'Precisa de aprovação' },
  { value: 'blocked', label: 'Bloqueados' },
];

// Busca com atraso para não chamar a API a cada letra
function useDebounced(value, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function CustomersScreen({ navigation }) {
  const [q, setQ] = useState('');
  const [access, setAccess] = useState(null);
  const query = useDebounced(q);
  const list = useLoad(() => api.get('/customers', { q: query, access_status: access, limit: 100 }), [query, access]);

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Field value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" />
      <Chips value={access} onChange={setAccess} options={FILTERS} />
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Nenhum cliente encontrado." /> : null}
      <View style={{ borderRadius: 12, overflow: 'hidden' }}>
        {(list.data || []).map((c) => (
          <ListRow key={c.id} icon="person-circle-outline" title={c.name || 'Sem nome'} subtitle={phoneLabel(c.phone)}
                   right={ACCESS[c.access_status] ? <Badge info={ACCESS[c.access_status]} /> : undefined}
                   onPress={() => navigation.navigate('Customer', { id: c.id })} />
        ))}
      </View>
    </Screen>
  );
}

// Acesso ao agendamento pelo bot: normal, precisa de aprovação ou bloqueado (motivo só para o dono)
function AccessSection({ d, onSaved }) {
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
    if (!r) return;
    Alert.alert('Pronto', r.cancelled ? `Acesso atualizado. ${r.cancelled} agendamento(s) cancelado(s).` : 'Acesso atualizado.');
  });

  const onSave = () => {
    if (status === 'blocked' && d.access_status !== 'blocked' && d.future_appointments > 0) {
      Alert.alert(
        'Cancelar os agendamentos futuros?',
        `${d.name || 'Este cliente'} tem ${d.future_appointments} agendamento(s) futuro(s).`,
        [
          { text: 'Voltar', style: 'cancel' },
          { text: 'Manter os agendamentos', onPress: () => save(false) },
          { text: 'Cancelar sem avisar', style: 'destructive', onPress: () => save(true, false) },
          { text: 'Cancelar e avisar o cliente', style: 'destructive', onPress: () => save(true, true) },
        ],
      );
      return;
    }
    save();
  };

  const hint = {
    normal: 'Agenda normalmente pelo WhatsApp.',
    approval: 'O pedido fica reservado e só vale depois que você aprovar (no WhatsApp ou na Agenda). O cliente não sabe o motivo.',
    blocked: 'O bot responde que não consegue agendar por aqui e pede para falar com a barbearia. Informações continuam funcionando. O cliente não é avisado do bloqueio.',
  }[status];

  return (
    <Section title="Acesso ao agendamento">
      {d.access_status === 'blocked' && d.future_appointments > 0 ? (
        <Card style={{ backgroundColor: colors.badBg, borderColor: colors.badBg }}>
          <Text style={[s.body, { color: colors.bad }]}>
            Cliente bloqueado com {d.future_appointments} agendamento(s) futuro(s).
          </Text>
          <Muted>Eles não foram cancelados. Abra no histórico abaixo para decidir.</Muted>
        </Card>
      ) : null}
      <Chips value={status} onChange={setStatus} options={ACCESS_OPTIONS} />
      <Muted style={{ marginTop: -6, marginBottom: 12 }}>{hint}</Muted>
      {status !== 'normal' ? (
        <Field label="Motivo (interno, o cliente não vê)" value={reason} onChangeText={setReason} multiline
               placeholder="Ex.: faltou 3 vezes sem avisar" />
      ) : null}
      {d.access_changed_at && d.access_status !== 'normal' ? (
        <Muted style={{ marginBottom: 10 }}>Desde {dmy(d.access_changed_at)}</Muted>
      ) : null}
      <Button title="Salvar acesso" kind="ghost" onPress={onSave}
              disabled={status === d.access_status && reason === d.access_reason} />
    </Section>
  );
}

const GAP_OPTIONS = [60, 120, 240, 480];

// Clientes que não podem estar na barbearia ao mesmo tempo que este
function ConflictsSection({ d, navigation }) {
  const list = useLoad(() => api.get('/customer-conflicts', { customer_id: d.id }), [d.id]);
  const shop = useLoad(() => api.get('/shop'), []);
  const [adding, setAdding] = useState(false);
  const [q, setQ] = useState('');
  const query = useDebounced(q);
  const [found, setFound] = useState([]);
  const [other, setOther] = useState(null);
  const [gap, setGap] = useState('default');
  const [notes, setNotes] = useState('');
  const defaultGap = shop.data?.conflict_default_gap_minutes ?? 240;

  useEffect(() => {
    if (!adding || query.trim().length < 2) { setFound([]); return; }
    api.get('/customers', { q: query, limit: 10 }).then((r) => setFound(r.filter((c) => c.id !== d.id))).catch(() => setFound([]));
  }, [query, adding, d.id]);

  const reset = () => { setAdding(false); setQ(''); setOther(null); setGap('default'); setNotes(''); };
  const add = () => run(async () => {
    await api.post('/customer-conflicts', {
      customer_id: d.id, other_customer_id: other.id, notes,
      min_gap_minutes: typeof gap === 'number' ? gap : null, same_day_block: gap === 'day',
    });
    reset();
    list.reload();
  }, 'Os dois não serão mais agendados perto um do outro.');
  const remove = (c) => confirm('Remover?', `${c.other_customer_name} poderá ser agendado perto de ${d.name || 'este cliente'} de novo.`,
    () => run(async () => { await api.del(`/customer-conflicts/${c.id}`); list.reload(); }), 'Remover', true);

  const ruleLabel = (c) => (c.same_day_block ? 'nunca no mesmo dia'
    : `${gapLabel(c.effective_gap_minutes)} de distância${c.min_gap_minutes === null ? ' (padrão)' : ''}`);

  return (
    <Section title="Não agendar junto com"
             right={!adding ? <Button title="Adicionar" kind="ghost" icon="add" onPress={() => setAdding(true)}
                                      style={{ marginBottom: 0, paddingVertical: 6 }} /> : null}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length && !adding ? (
        <Muted style={{ marginBottom: 10 }}>
          Ninguém. Use quando dois clientes não podem estar na barbearia ao mesmo tempo: o bot esconde os horários próximos, sem explicar o motivo.
        </Muted>
      ) : null}
      {(list.data || []).map((c) => (
        <Card key={c.id}>
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.body} onPress={() => navigation.push('Customer', { id: c.other_customer_id })}>
                {c.other_customer_name || phoneLabel(c.other_customer_phone)}
              </Text>
              <Muted>{ruleLabel(c)}</Muted>
              {c.notes ? <Muted style={{ marginTop: 4 }}>{c.notes}</Muted> : null}
            </View>
            <Button title="Remover" kind="ghost" onPress={() => remove(c)} style={{ marginBottom: 0, paddingVertical: 6 }} />
          </View>
        </Card>
      ))}
      {adding ? (
        <Card>
          {!other ? (
            <>
              <Field label="Outro cliente" value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" autoFocus />
              {found.map((c) => (
                <ListRow key={c.id} icon="person-outline" title={c.name || 'Sem nome'} subtitle={phoneLabel(c.phone)}
                         onPress={() => setOther(c)} />
              ))}
              {query.trim().length >= 2 && !found.length ? <Muted style={{ marginBottom: 10 }}>Nenhum cliente encontrado.</Muted> : null}
            </>
          ) : (
            <>
              <Label>Outro cliente</Label>
              <View style={[s.row, { marginBottom: 14 }]}>
                <Text style={[s.body, { flex: 1 }]}>{other.name || phoneLabel(other.phone)}</Text>
                <Button title="Trocar" kind="ghost" onPress={() => setOther(null)} style={{ marginBottom: 0, paddingVertical: 6 }} />
              </View>
              <Label>Distância mínima entre os atendimentos</Label>
              <Chips value={gap} onChange={setGap} options={[
                { value: 'default', label: `Padrão (${gapLabel(defaultGap)})` },
                ...GAP_OPTIONS.map((m) => ({ value: m, label: gapLabel(m) })),
                { value: 'day', label: 'Dia inteiro' },
              ]} />
              <Muted style={{ marginTop: -6, marginBottom: 12 }}>
                Vale entre o fim de um e o início do outro, com qualquer barbeiro.
              </Muted>
              <Field label="Motivo (interno)" value={notes} onChangeText={setNotes} multiline placeholder="Ex.: discutiram na barbearia" />
              <Button title="Salvar" onPress={add} />
            </>
          )}
          <Button title="Cancelar" kind="ghost" onPress={reset} style={{ marginBottom: 0 }} />
        </Card>
      ) : null}
    </Section>
  );
}

export function CustomerScreen({ route, navigation }) {
  const c = useLoad(() => api.get(`/customers/${route.params.id}`), [route.params.id]);
  const [name, setName] = useState(null);
  const [notes, setNotes] = useState(null);
  if (!c.data) return <Loading error={c.error} onRetry={c.reload} />;
  const d = c.data;
  const save = () => run(async () => {
    await api.put(`/customers/${d.id}`, { name: name ?? d.name, notes: notes ?? d.notes });
    c.reload();
  }, 'Cliente atualizado.');

  return (
    <Screen>
      <View style={[s.row, { gap: 8 }]}>
        <Title style={{ flexShrink: 1 }}>{d.name || 'Sem nome'}</Title>
        <View style={{ marginBottom: 8 }}><Badge info={ACCESS[d.access_status]} /></View>
      </View>
      <Muted style={{ marginBottom: 12 }}>{phoneLabel(d.phone)} · cliente desde {dmy(d.created_at)}</Muted>
      <View style={[s.row, { gap: 8, marginBottom: 14 }]}>
        <Stat label="Atendimentos" value={d.visits} />
        <Stat label="Faltas" value={d.no_shows} />
        <Stat label="Total gasto" value={money(d.total_spent)} />
      </View>
      <Button title="Abrir no WhatsApp" kind="ghost" icon="logo-whatsapp" onPress={() => Linking.openURL(`https://wa.me/${d.phone}`)} />
      <Section title="Dados">
        <Field label="Nome" value={name ?? d.name} onChangeText={setName} />
        <Field label="Observações" value={notes ?? d.notes} onChangeText={setNotes} multiline placeholder="Ex.: prefere máquina 2 nas laterais" />
        <Button title="Salvar" onPress={save} />
      </Section>
      <AccessSection d={d} onSaved={c.reload} />
      <ConflictsSection d={d} navigation={navigation} />
      <Section title="Histórico">
        {!d.appointments.length ? <Empty text="Sem atendimentos ainda." /> : null}
        {d.appointments.map((a) => (
          <Card key={a.id} onPress={() => navigation.navigate('Appointment', { id: a.id, item: a })}>
            <Text style={s.body}>{dtLabel(a.start)}</Text>
            <Muted>{a.service_name} · {a.barber_name} · {money(a.price)}</Muted>
            <View style={[s.row, { gap: 6, marginTop: 6 }]}>
              <Badge info={STATUS[a.status]} />
              <Badge info={PAY[a.payment_status]} />
              {a.rating ? <Muted>{'⭐'.repeat(a.rating)}</Muted> : null}
            </View>
          </Card>
        ))}
      </Section>
    </Screen>
  );
}
