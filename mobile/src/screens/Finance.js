import React, { useLayoutEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { addDays, dmy, money, monthRange, parseBRDate, pct, todayISO } from '../format';
import { colors } from '../theme';
import {
  Badge, Button, Card, Chips, confirm, Empty, Field, Loading, Muted, Screen, Section, Stat, Toggle, run, s, useLoad,
} from '../ui';

const PERIODS = {
  month: () => monthRange(0),
  last: () => monthRange(-1),
  d30: () => [addDays(todayISO(), -29), todayISO()],
};

const brDate = (iso) => (iso ? dmy(iso + 'T') : '');
const isOpen = (v) => Number(v) > 0.004;

// ---------------------------------------------------------------- repasses do período

export function CommissionsScreen({ navigation }) {
  const [period, setPeriod] = useState('month');
  const [from, to] = PERIODS[period]();
  const r = useLoad(() => api.get('/finance/commissions', { date_from: from, date_to: to }), [period]);
  const d = r.data;

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={[s.row, { gap: 16 }]}>
          <Pressable onPress={() => navigation.navigate('Settlements')} hitSlop={10}>
            <Ionicons name="time-outline" size={26} color={colors.primary} />
          </Pressable>
          <Pressable onPress={() => navigation.navigate('CommissionRules')} hitSlop={10}>
            <Ionicons name="options-outline" size={26} color={colors.primary} />
          </Pressable>
        </View>
      ),
    });
  }, [navigation]);

  const settle = (b, due) => confirm('Registrar acerto?',
    `${b.barber_name} repassa ${money(due.open)} para ${due.beneficiary_name}, referente a ${brDate(from)} a ${brDate(to)}.`,
    () => run(async () => {
      await api.post('/finance/settlements', {
        payer_barber_id: b.barber_id, beneficiary_type: due.beneficiary_type,
        beneficiary_barber_id: due.beneficiary_barber_id, period_start: from, period_end: to, amount: due.open,
      });
      r.reload();
    }, 'Acerto registrado. O barbeiro foi avisado pelo WhatsApp.'),
    'Registrar');

  return (
    <Screen onRefresh={r.reload} refreshing={r.loading && !!d}>
      <Chips value={period} onChange={setPeriod} options={[
        { value: 'month', label: 'Este mês' }, { value: 'last', label: 'Mês passado' }, { value: 'd30', label: '30 dias' },
      ]} />
      {!d ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Muted style={{ marginBottom: 10 }}>{brDate(from)} a {brDate(to)} · só atendimentos concluídos</Muted>
          <View style={[s.row, { gap: 8, marginBottom: 18 }]}>
            <Stat label="Faturado" value={money(d.total_gross)} />
            <Stat label="Repasses" value={money(d.total_due)} />
            <Stat label="Em aberto" value={money(d.total_open)} />
          </View>
          {!d.barbers.length ? (
            <Empty text="Nenhum atendimento concluído no período. Cadastre as regras de repasse no ícone acima." />
          ) : null}
          {d.barbers.map((b) => (
            <Card key={b.barber_id}>
              <View style={s.row}>
                <Text style={[s.body, { flex: 1, fontWeight: '700' }]}>{b.barber_name}</Text>
                <Text style={[s.body, { fontWeight: '700' }]}>{money(b.gross)}</Text>
              </View>
              <Muted>{b.appointments} atendimento(s) · líquido {money(b.net)}
                {isOpen(b.received) ? ` · recebe ${money(b.received)} de repasses` : ''}</Muted>
              {b.dues.map((due) => (
                <View key={`${due.beneficiary_type}-${due.beneficiary_barber_id}`}
                      style={{ borderTopWidth: 1, borderTopColor: colors.line, marginTop: 10, paddingTop: 10 }}>
                  <View style={s.row}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.body}>Para {due.beneficiary_name}</Text>
                      <Muted>{due.percentages.map(pct).join(' / ') || '-'} sobre {money(due.base)}</Muted>
                    </View>
                    <Text style={[s.body, { fontWeight: '700' }]}>{money(due.amount)}</Text>
                  </View>
                  <View style={[s.row, { gap: 6, marginTop: 6 }]}>
                    {isOpen(due.settled) ? <Badge info={{ label: `Acertado ${money(due.settled)}`, fg: colors.good, bg: colors.goodBg }} /> : null}
                    {isOpen(due.open) ? <Badge info={{ label: `Em aberto ${money(due.open)}`, fg: colors.warn, bg: colors.warnBg }} /> : null}
                    {!isOpen(due.open) && isOpen(due.amount) ? <Badge info={{ label: 'Quitado', fg: colors.good, bg: colors.goodBg }} /> : null}
                  </View>
                  {isOpen(due.open) ? (
                    <Button title="Registrar acerto" kind="ghost" icon="checkmark-done-outline"
                            onPress={() => settle(b, due)} style={{ marginTop: 10, marginBottom: 0 }} />
                  ) : null}
                </View>
              ))}
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

// ---------------------------------------------------------------- histórico de acertos

export function SettlementsScreen() {
  const list = useLoad(() => api.get('/finance/settlements'), []);
  const remove = (x) => confirm('Excluir acerto?', 'O valor volta a aparecer como em aberto.',
    () => run(async () => { await api.del(`/finance/settlements/${x.id}`); list.reload(); }), 'Excluir', true);
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Nenhum acerto registrado ainda." /> : null}
      {(list.data || []).map((x) => (
        <Card key={x.id}>
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.body}>{x.payer_name} → {x.beneficiary_name}</Text>
              <Muted>Período {brDate(x.period_start)} a {brDate(x.period_end)}</Muted>
              <Muted>Pago em {dmy(x.paid_at)}{x.notes ? ` · ${x.notes}` : ''}</Muted>
            </View>
            <Text style={{ fontSize: 18, fontWeight: '800', color: colors.ink, marginRight: 12 }}>{money(x.amount)}</Text>
            <Pressable hitSlop={10} onPress={() => remove(x)}>
              <Ionicons name="trash-outline" size={22} color={colors.bad} />
            </Pressable>
          </View>
        </Card>
      ))}
    </Screen>
  );
}

// ---------------------------------------------------------------- regras de repasse

export function CommissionRulesScreen({ navigation }) {
  const list = useLoad(() => api.get('/commission-rules'), []);
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable onPress={() => navigation.navigate('CommissionRuleEdit', {})} hitSlop={10}>
          <Ionicons name="add-circle" size={30} color={colors.accent} />
        </Pressable>
      ),
    });
  }, [navigation]);

  const today = todayISO();
  const byBarber = {};
  (list.data || []).forEach((x) => { (byBarber[x.barber_name] = byBarber[x.barber_name] || []).push(x); });

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? (
        <Empty text="Cadastre quanto cada barbeiro repassa para a barbearia ou para um padrinho." />
      ) : null}
      {Object.entries(byBarber).map(([name, rules]) => (
        <Section key={name} title={`${name} paga`}>
          {rules.map((x) => {
            const ended = x.valid_to && x.valid_to < today;
            const future = x.valid_from > today;
            return (
              <Card key={x.id} onPress={() => navigation.navigate('CommissionRuleEdit', { item: x })}
                    style={ended && { opacity: 0.5 }}>
                <View style={s.row}>
                  <Text style={[s.body, { flex: 1 }]}>Para {x.beneficiary_name}</Text>
                  <Text style={[s.body, { fontWeight: '700' }]}>{pct(x.percentage)}</Text>
                </View>
                <Muted>{x.service_name || 'Todos os serviços'} · desde {brDate(x.valid_from)}
                  {x.valid_to ? ` até ${brDate(x.valid_to)}` : ''}</Muted>
                {ended ? <Muted>Encerrada</Muted> : null}
                {future ? <Muted>Começa no futuro</Muted> : null}
                {x.notes ? <Muted style={{ marginTop: 4 }}>{x.notes}</Muted> : null}
              </Card>
            );
          })}
        </Section>
      ))}
    </Screen>
  );
}

export function CommissionRuleEditScreen({ navigation, route }) {
  const item = route.params?.item;
  const barbers = useLoad(() => api.get('/barbers'), []);
  const services = useLoad(() => api.get('/services'), []);
  const [barberId, setBarberId] = useState(item?.barber_id ?? null);
  // 'shop' ou id do barbeiro beneficiário
  const [beneficiary, setBeneficiary] = useState(item ? (item.beneficiary_barber_id ?? 'shop') : 'shop');
  const [percentage, setPercentage] = useState(item ? String(item.percentage).replace('.', ',') : '');
  const [serviceId, setServiceId] = useState(item?.service_id ?? null);
  const [from, setFrom] = useState(brDate(item?.valid_from || todayISO()));
  const [hasEnd, setHasEnd] = useState(!!item?.valid_to);
  const [to, setTo] = useState(brDate(item?.valid_to));
  const [notes, setNotes] = useState(item?.notes || '');

  const activeBarbers = (barbers.data || []).filter((b) => b.active || b.id === barberId || b.id === beneficiary);

  const save = () => run(async () => {
    const validFrom = parseBRDate(from);
    if (!validFrom) throw new Error('Início inválido. Use dd/mm/aaaa.');
    const validTo = hasEnd ? parseBRDate(to) : null;
    if (hasEnd && !validTo) throw new Error('Fim inválido. Use dd/mm/aaaa.');
    const body = {
      barber_id: barberId,
      beneficiary_type: beneficiary === 'shop' ? 'shop' : 'barber',
      beneficiary_barber_id: beneficiary === 'shop' ? null : beneficiary,
      percentage: Number(percentage.replace(',', '.')),
      service_id: serviceId, valid_from: validFrom, valid_to: validTo, notes,
    };
    if (item) await api.put(`/commission-rules/${item.id}`, body);
    else await api.post('/commission-rules', body);
    navigation.goBack();
  });

  if (!barbers.data || !services.data) return <Loading error={barbers.error || services.error} />;

  return (
    <Screen>
      <Section title="Quem repassa">
        <Chips value={barberId} onChange={setBarberId}
               options={activeBarbers.map((b) => ({ value: b.id, label: b.name }))} />
      </Section>
      <Section title="Para quem">
        <Chips value={beneficiary} onChange={setBeneficiary}
               options={[{ value: 'shop', label: 'Barbearia' },
                 ...activeBarbers.filter((b) => b.id !== barberId).map((b) => ({ value: b.id, label: b.name }))]} />
      </Section>
      <Field label="Porcentagem (%)" value={percentage} onChangeText={setPercentage} keyboardType="decimal-pad"
             placeholder="Ex.: 30" hint="A soma dos repasses de um barbeiro não pode passar de 100%." />
      <Section title="Serviço">
        <Chips value={serviceId} onChange={setServiceId}
               options={[{ value: null, label: 'Todos' }, ...services.data.map((x) => ({ value: x.id, label: x.name }))]} />
        <Muted>Uma regra de um serviço substitui a regra geral para o mesmo beneficiário.</Muted>
      </Section>
      <Field label="Vale a partir de" value={from} onChangeText={setFrom} placeholder="dd/mm/aaaa"
             keyboardType="numbers-and-punctuation" />
      <Toggle label="Tem data para acabar" value={hasEnd} onValueChange={setHasEnd} />
      {hasEnd ? (
        <Field label="Vale até" value={to} onChangeText={setTo} placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
      ) : null}
      <Field label="Observações" value={notes} onChangeText={setNotes} multiline placeholder="Ex.: padrinho nos 6 primeiros meses" />
      <Button title="Salvar" onPress={save} disabled={!barberId || !percentage || !from} />
      {item ? (
        <Button title="Excluir" kind="danger" onPress={() => confirm('Excluir regra?',
          'Os repasses de períodos passados serão recalculados sem ela. Para encerrar sem mexer no histórico, defina uma data de fim.',
          () => run(async () => { await api.del(`/commission-rules/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}
