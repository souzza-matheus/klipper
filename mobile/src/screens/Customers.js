import React, { useEffect, useState } from 'react';
import { Linking, Text, View } from 'react-native';
import { api } from '../api';
import { dtLabel, money, phoneLabel } from '../format';
import { PAY, STATUS } from '../theme';
import {
  Badge, Button, Card, Empty, Field, ListRow, Loading, Muted, Screen, Section, Stat, Title, run, s, useLoad,
} from '../ui';

export function CustomersScreen({ navigation }) {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 350);
    return () => clearTimeout(t);
  }, [q]);
  const list = useLoad(() => api.get('/customers', { q: query, limit: 100 }), [query]);

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Field value={q} onChangeText={setQ} placeholder="Buscar por nome ou telefone" />
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Nenhum cliente encontrado." /> : null}
      <View style={{ borderRadius: 12, overflow: 'hidden' }}>
        {(list.data || []).map((c) => (
          <ListRow key={c.id} icon="person-circle-outline" title={c.name || 'Sem nome'} subtitle={phoneLabel(c.phone)}
                   onPress={() => navigation.navigate('Customer', { id: c.id })} />
        ))}
      </View>
    </Screen>
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
      <Title>{d.name || 'Sem nome'}</Title>
      <Muted style={{ marginBottom: 12 }}>{phoneLabel(d.phone)} · cliente desde {d.created_at.slice(8, 10)}/{d.created_at.slice(5, 7)}/{d.created_at.slice(0, 4)}</Muted>
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
