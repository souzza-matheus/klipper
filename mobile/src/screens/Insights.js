import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../api';
import { addDays, dmy, money, todayISO } from '../format';
import { colors } from '../theme';
import { Card, Chips, Empty, Loading, Muted, Screen, Section, Stat, s, useLoad } from '../ui';

export function ReviewsScreen() {
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [barber, setBarber] = useState(null);
  const list = useLoad(() => api.get('/reviews', { barber_id: barber }), [barber]);
  const items = list.data || [];
  const avg = items.length ? items.reduce((t, r) => t + r.rating, 0) / items.length : null;
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {barbers.data && barbers.data.length > 1 ? (
        <Chips value={barber} onChange={setBarber}
               options={[{ value: null, label: 'Todos' }, ...barbers.data.map((b) => ({ value: b.id, label: b.name }))]} />
      ) : null}
      <View style={[s.row, { gap: 8, marginBottom: 14 }]}>
        <Stat label="Nota média" value={avg ? avg.toFixed(1) : '-'} />
        <Stat label="Avaliações" value={items.length} />
        <Stat label="Notas 1 e 2" value={items.filter((r) => r.rating <= 2).length} />
      </View>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? <Empty text="As avaliações chegam pelo WhatsApp depois de cada atendimento." /> : null}
      {items.map((r) => (
        <Card key={r.id} style={r.rating <= 2 && { borderColor: colors.bad }}>
          <View style={s.row}>
            <Text style={[s.body, { flex: 1 }]}>{r.customer_name}</Text>
            <Text>{'⭐'.repeat(r.rating)}</Text>
          </View>
          <Muted>{r.service_name} com {r.barber_name} · {dmy(r.appointment_start)}</Muted>
          {r.comment ? <Text style={[s.body, { marginTop: 8, fontStyle: 'italic' }]}>“{r.comment}”</Text> : null}
        </Card>
      ))}
    </Screen>
  );
}

const PERIODS = {
  today: () => [todayISO(), todayISO()],
  week: () => [addDays(todayISO(), -6), todayISO()],
  month: () => [addDays(todayISO(), -29), todayISO()],
  next: () => [todayISO(), addDays(todayISO(), 7)],
};

export function ReportsScreen() {
  const [period, setPeriod] = useState('week');
  const [from, to] = PERIODS[period]();
  const r = useLoad(() => api.get('/reports/summary', { date_from: from, date_to: to }), [period]);
  const d = r.data;
  return (
    <Screen onRefresh={r.reload} refreshing={r.loading && !!d}>
      <Chips value={period} onChange={setPeriod} options={[
        { value: 'today', label: 'Hoje' }, { value: 'week', label: '7 dias' },
        { value: 'month', label: '30 dias' }, { value: 'next', label: 'Próximos 7 dias' },
      ]} />
      {!d ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Muted style={{ marginBottom: 10 }}>{dmy(from + 'T')} a {dmy(to + 'T')}</Muted>
          <View style={[s.row, { gap: 8, marginBottom: 8 }]}>
            <Stat label="Faturamento previsto" value={money(d.revenue_expected)} />
            <Stat label="Já atendido" value={money(d.revenue_completed)} />
          </View>
          <View style={[s.row, { gap: 8, marginBottom: 8 }]}>
            <Stat label="Atendimentos" value={d.appointments} />
            <Stat label="Cancelados" value={d.cancelled} />
            <Stat label="Faltas" value={d.no_shows} />
          </View>
          <View style={[s.row, { gap: 8, marginBottom: 18 }]}>
            <Stat label="Pago via Pix" value={money(d.paid_pix)} />
            <Stat label="Nota média" value={d.avg_rating ?? '-'} />
          </View>
          <Section title="Por barbeiro">
            {d.by_barber.map((g) => <Row key={g.name} g={g} />)}
            {!d.by_barber.length ? <Muted>Sem dados no período.</Muted> : null}
          </Section>
          <Section title="Por serviço">
            {d.by_service.map((g) => <Row key={g.name} g={g} />)}
          </Section>
        </>
      )}
    </Screen>
  );
}

function Row({ g }) {
  return (
    <Card>
      <View style={s.row}>
        <Text style={[s.body, { flex: 1 }]}>{g.name}</Text>
        <Text style={[s.body, { fontWeight: '700' }]}>{money(g.revenue)}</Text>
      </View>
      <Muted>{g.appointments} atendimento(s){g.avg_rating ? ` · nota ${g.avg_rating}` : ''}</Muted>
    </Card>
  );
}
