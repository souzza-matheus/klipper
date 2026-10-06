import React, { useEffect, useLayoutEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import {
  addDays, addMonths, dayLabel, dtLabel, hm, money, moneyInput, monthLabel, parseMoney, PAY_METHODS, payMethodLabel,
  phoneLabel, todayISO, weekdayMonFirst,
} from '../format';
import { colors, PAY, STATUS } from '../theme';
import {
  Badge, Button, Card, Chips, confirm, Empty, Field, Loading, Muted, Screen, Section, s, Title, run, useLoad,
} from '../ui';

export function DayNav({ day, onChange }) {
  return (
    <View style={[s.row, { marginBottom: 12 }]}>
      <Pressable onPress={() => onChange(addDays(day, -1))} hitSlop={12} style={{ padding: 6 }}>
        <Ionicons name="chevron-back" size={24} color={colors.primary} />
      </Pressable>
      <Pressable onPress={() => onChange(todayISO())} style={{ flex: 1, alignItems: 'center' }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: colors.ink }}>{dayLabel(day)}</Text>
        {day !== todayISO() ? <Muted>toque para voltar a hoje</Muted> : null}
      </Pressable>
      <Pressable onPress={() => onChange(addDays(day, 1))} hitSlop={12} style={{ padding: 6 }}>
        <Ionicons name="chevron-forward" size={24} color={colors.primary} />
      </Pressable>
    </View>
  );
}

export function MonthNav({ month, onChange }) {
  const current = todayISO().slice(0, 7);
  return (
    <View style={[s.row, { marginBottom: 12 }]}>
      <Pressable onPress={() => onChange(addMonths(month, -1))} hitSlop={12} style={{ padding: 6 }}>
        <Ionicons name="chevron-back" size={24} color={colors.primary} />
      </Pressable>
      <Pressable onPress={() => onChange(current)} style={{ flex: 1, alignItems: 'center' }}>
        <Text style={{ fontSize: 17, fontWeight: '700', color: colors.ink }}>{monthLabel(month)}</Text>
        {month !== current ? <Muted>toque para voltar ao mês atual</Muted> : null}
      </Pressable>
      <Pressable onPress={() => onChange(addMonths(month, 1))} hitSlop={12} style={{ padding: 6 }}>
        <Ionicons name="chevron-forward" size={24} color={colors.primary} />
      </Pressable>
    </View>
  );
}

const WEEK_HEAD = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];

// Cor da ocupação do dia
function occColor(o) {
  if (o >= 0.85) return colors.bad;
  if (o >= 0.5) return colors.warn;
  return colors.good;
}

// Calendário do mês: atendimentos e ocupação por dia. Tocar em um dia abre a visão Dia.
function MonthView({ month, barber, onPick, onMonth }) {
  const [y, m] = month.split('-').map(Number);
  const r = useLoad(() => api.get('/appointments/month', { year: y, month: m, barber_id: barber }), [month, barber]);
  const days = r.data?.days || [];
  const today = todayISO();
  const lead = days.length ? weekdayMonFirst(days[0].date) : 0;
  const cells = [...Array(lead).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  const total = days.reduce((t, d) => t + d.total, 0);
  const revenue = days.reduce((t, d) => t + Number(d.revenue_expected), 0);

  return (
    <View>
      <MonthNav month={month} onChange={onMonth} />
      {!r.data ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Muted style={{ marginBottom: 10 }}>{total} atendimento(s) · previsto {money(revenue)}</Muted>
          <View style={[s.card, { padding: 6 }]}>
            <View style={s.row}>
              {WEEK_HEAD.map((w, i) => (
                <Text key={i} style={{ width: `${100 / 7}%`, textAlign: 'center', fontSize: 12, fontWeight: '700', color: colors.muted, paddingVertical: 6 }}>{w}</Text>
              ))}
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              {cells.map((d, i) => (
                <View key={d ? d.date : `x${i}`} style={{ width: `${100 / 7}%`, padding: 2 }}>
                  {d ? (
                    <Pressable onPress={() => onPick(d.date)}
                               style={({ pressed }) => [{
                                 borderRadius: 8, paddingVertical: 6, alignItems: 'center', minHeight: 62,
                                 backgroundColor: d.date === today ? colors.infoBg : 'transparent',
                                 borderWidth: d.date === today ? 1.5 : 0, borderColor: colors.primary,
                                 opacity: d.working || d.total ? 1 : 0.35,
                               }, pressed && { backgroundColor: '#F0EDE7' }]}>
                      <View style={[s.row, { gap: 2 }]}>
                        <Text style={{ fontSize: 15, fontWeight: d.date === today ? '800' : '600', color: colors.ink }}>
                          {Number(d.date.slice(8, 10))}
                        </Text>
                        {d.has_block ? <Ionicons name="lock-closed" size={10} color={colors.accent} /> : null}
                      </View>
                      <Text style={{ fontSize: 11, color: d.total ? colors.ink : colors.muted, marginTop: 2 }}>
                        {d.total ? `${d.total} at.` : d.working ? '-' : ''}
                      </Text>
                      {d.working ? (
                        <View style={{ height: 4, width: '80%', backgroundColor: colors.bg, borderRadius: 2, marginTop: 5 }}>
                          <View style={{ height: 4, width: `${Math.round(d.occupancy * 100)}%`, backgroundColor: occColor(d.occupancy), borderRadius: 2 }} />
                        </View>
                      ) : null}
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </View>
          </View>
          <View style={[s.row, { gap: 12, flexWrap: 'wrap', marginTop: 4 }]}>
            {[[colors.good, 'até 50%'], [colors.warn, '50 a 85%'], [colors.bad, 'acima de 85%']].map(([c, l]) => (
              <View key={l} style={[s.row, { gap: 4 }]}>
                <View style={{ width: 12, height: 4, borderRadius: 2, backgroundColor: c }} />
                <Muted style={{ fontSize: 12 }}>{l}</Muted>
              </View>
            ))}
            <View style={[s.row, { gap: 4 }]}>
              <Ionicons name="lock-closed" size={10} color={colors.accent} />
              <Muted style={{ fontSize: 12 }}>bloqueio</Muted>
            </View>
          </View>
          <Muted style={{ marginTop: 6, fontSize: 12 }}>
            Ocupação = atendimentos ÷ quantos cabem no expediente do dia (pela duração média dos serviços).
          </Muted>
        </>
      )}
    </View>
  );
}

export function AgendaScreen({ navigation }) {
  const [mode, setMode] = useState('day');
  const [day, setDay] = useState(todayISO());
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  const [barber, setBarber] = useState(null);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const appts = useLoad(async () => (mode === 'day'
    ? api.get('/appointments', { date_from: day, barber_id: barber, include_cancelled: true }) : null), [day, barber, mode]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <Pressable onPress={() => navigation.navigate('NewAppointment', { day })} hitSlop={10}>
          <Ionicons name="add-circle" size={30} color={colors.accent} />
        </Pressable>
      ),
    });
  }, [navigation, day]);

  const list = appts.data || [];
  const active = list.filter((a) => a.status !== 'cancelled');
  const total = active.filter((a) => a.status !== 'no_show').reduce((t, a) => t + Number(a.price), 0);

  const barberChips = barbers.data && barbers.data.length > 1 ? (
    <Chips value={barber} onChange={setBarber}
           options={[{ value: null, label: 'Todos' }, ...barbers.data.filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
  ) : null;
  const modeSwitch = (
    <View style={[s.row, { backgroundColor: colors.line, borderRadius: 10, padding: 3, marginBottom: 12 }]}>
      {[['day', 'Dia'], ['month', 'Mês']].map(([v, l]) => (
        <Pressable key={v} onPress={() => { setMode(v); if (v === 'month') setMonth(day.slice(0, 7)); }}
                   style={{ flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: 'center', backgroundColor: mode === v ? colors.card : 'transparent' }}>
          <Text style={{ fontWeight: '700', color: mode === v ? colors.primary : colors.muted }}>{l}</Text>
        </Pressable>
      ))}
    </View>
  );

  if (mode === 'month') {
    return (
      <Screen>
        {modeSwitch}
        {barberChips}
        <MonthView month={month} barber={barber} onMonth={setMonth}
                   onPick={(d) => { setDay(d); setMode('day'); }} />
      </Screen>
    );
  }

  return (
    <Screen onRefresh={appts.reload} refreshing={appts.loading && !!appts.data}>
      {modeSwitch}
      <DayNav day={day} onChange={setDay} />
      {barberChips}
      <Muted style={{ marginBottom: 10 }}>{active.length} atendimento(s) · previsto {money(total)}</Muted>
      {!appts.data ? <Loading error={appts.error} onRetry={appts.reload} /> : null}
      {appts.data && !list.length ? <Empty text="Nenhum agendamento neste dia." /> : null}
      {list.map((a) => (
        <Card key={a.id} onPress={() => navigation.navigate('Appointment', { id: a.id, item: a })}
              style={a.status === 'cancelled' && { opacity: 0.5 }}>
          <View style={s.row}>
            <Text style={{ fontSize: 18, fontWeight: '800', color: colors.primary, width: 62 }}>{hm(a.start)}</Text>
            <View style={{ flex: 1 }}>
              <Text style={s.body} numberOfLines={1}>{a.customer_name || phoneLabel(a.customer_phone)}</Text>
              <Muted>{a.service_name} · {a.barber_name} · {money(a.price)}</Muted>
              <View style={[s.row, { gap: 6, marginTop: 6 }]}>
                <Badge info={STATUS[a.status]} />
                <Badge info={PAY[a.payment_status]} />
                {a.status === 'completed' && a.payment_method ? <Muted>{payMethodLabel(a.payment_method)}</Muted> : null}
                {a.created_via === 'bot' && a.status !== 'completed' ? <Muted>via WhatsApp</Muted> : null}
              </View>
            </View>
          </View>
        </Card>
      ))}
    </Screen>
  );
}

// Seletor de horário livre (usado em novo agendamento e remarcação)
export function SlotPicker({ serviceId, barberId, value, onChange, initialDay }) {
  const [day, setDay] = useState(initialDay || todayISO());
  const [slots, setSlots] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    if (!serviceId) return;
    setSlots(null);
    setErr('');
    api.get('/availability', { service_id: serviceId, day, barber_id: barberId })
      .then(setSlots).catch((e) => setErr(e.message));
  }, [serviceId, barberId, day]);
  if (!serviceId) return <Muted>Escolha o serviço primeiro.</Muted>;
  return (
    <View>
      <DayNav day={day} onChange={(d) => { setDay(d); onChange(null); }} />
      {!slots ? <Loading error={err} /> : null}
      {slots && !slots.length ? <Empty text="Sem horários livres neste dia." /> : null}
      {slots && slots.length ? (
        <Chips value={value ? `${value.start}|${value.barber_id}` : null}
               onChange={(v) => { const [start, b] = v.split('|'); onChange({ start, barber_id: Number(b) }); }}
               options={slots.map((x) => ({ value: `${x.start}|${x.barber_id}`, label: barberId ? hm(x.start) : `${hm(x.start)} ${x.barber_name}` }))} />
      ) : null}
    </View>
  );
}

export function NewAppointmentScreen({ navigation, route }) {
  const services = useLoad(() => api.get('/services'), []);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [serviceId, setServiceId] = useState(null);
  const [barberId, setBarberId] = useState(null);
  const [slot, setSlot] = useState(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    const r = await run(() => api.post('/appointments', {
      customer_phone: phone, customer_name: name, service_id: serviceId, barber_id: slot.barber_id, start: slot.start, notes,
    }), 'Agendado. O cliente recebeu a confirmação no WhatsApp.');
    setBusy(false);
    if (r) navigation.goBack();
  };

  return (
    <Screen>
      <Field label="WhatsApp do cliente" value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholder="(31) 99999-8888" />
      <Field label="Nome" value={name} onChangeText={setName} placeholder="Opcional se já for cliente" />
      <Section title="Serviço">
        <Chips value={serviceId} onChange={(v) => { setServiceId(v); setSlot(null); }}
               options={(services.data || []).filter((x) => x.active).map((x) => ({ value: x.id, label: `${x.name} · ${money(x.price)}` }))} />
      </Section>
      <Section title="Barbeiro">
        <Chips value={barberId} onChange={(v) => { setBarberId(v); setSlot(null); }}
               options={[{ value: null, label: 'Qualquer um' }, ...(barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
      </Section>
      <Section title="Horário">
        <SlotPicker serviceId={serviceId} barberId={barberId} value={slot} onChange={setSlot} initialDay={route.params?.day} />
      </Section>
      <Field label="Observação" value={notes} onChangeText={setNotes} multiline />
      <Button title={busy ? 'Salvando...' : 'Agendar'} onPress={save} disabled={busy || !phone || !serviceId || !slot} />
    </Screen>
  );
}

export function AppointmentScreen({ navigation, route }) {
  const { id } = route.params;
  const appt = useLoad(async () => {
    const list = await api.get('/appointments', { date_from: route.params.item.start.slice(0, 10), include_cancelled: true });
    return list.find((x) => x.id === id) || route.params.item;
  }, [id]);
  const [moving, setMoving] = useState(false);
  const [slot, setSlot] = useState(null);
  const [completing, setCompleting] = useState(false);
  const [method, setMethod] = useState(null);
  const [finalPrice, setFinalPrice] = useState('');
  const a = appt.data;
  if (!a) return <Loading error={appt.error} onRetry={appt.reload} />;

  const openComplete = () => {
    setMethod(a.payment_method || (a.payment_status === 'paid' ? 'pix' : null));
    setFinalPrice(moneyInput(a.price));
    setMoving(false);
    setCompleting(true);
  };
  const complete = () => run(async () => {
    const price = parseMoney(finalPrice);
    if (price === null || price < 0) throw new Error('Valor inválido.');
    await api.patch(`/appointments/${a.id}`, { status: 'completed', payment_method: method, price: price.toFixed(2) });
    setCompleting(false);
    appt.reload();
  }, 'Atendimento concluído.');
  const diff = (parseMoney(finalPrice) ?? Number(a.price)) - Number(a.price);
  const completePanel = completing ? (
    <Section title={a.status === 'completed' ? 'Pagamento' : 'Concluir atendimento'}>
      <Card>
        <Muted style={{ marginBottom: 8 }}>Forma de pagamento</Muted>
        <Chips value={method} onChange={setMethod} options={PAY_METHODS} />
        {a.payment_status === 'paid' ? <Muted style={{ marginTop: -6, marginBottom: 12 }}>Já pago via Pix pelo WhatsApp.</Muted> : null}
        <Field label="Valor cobrado (R$)" value={finalPrice} onChangeText={setFinalPrice} keyboardType="decimal-pad"
               hint={Math.abs(diff) >= 0.005
                 ? `${diff < 0 ? 'Desconto' : 'Acréscimo'} de ${money(Math.abs(diff))} sobre ${money(a.price)}`
                 : 'Altere para dar desconto ou cobrar a mais.'} />
        <Button title={a.status === 'completed' ? 'Salvar pagamento' : 'Confirmar atendimento'} icon="checkmark-done"
                onPress={complete} disabled={!method} style={{ marginBottom: 6 }} />
        <Button title="Voltar" kind="ghost" onPress={() => setCompleting(false)} style={{ marginBottom: 0 }} />
      </Card>
    </Section>
  ) : null;

  const setStatus = (status, msg) => run(async () => {
    await api.patch(`/appointments/${a.id}`, { status });
    appt.reload();
  }, msg);
  const active = a.status === 'scheduled' || a.status === 'confirmed';

  return (
    <Screen>
      <Title>{a.customer_name || phoneLabel(a.customer_phone)}</Title>
      <View style={[s.row, { gap: 6, marginBottom: 14 }]}>
        <Badge info={STATUS[a.status]} />
        <Badge info={PAY[a.payment_status]} />
        {a.rating ? <Muted>{'⭐'.repeat(a.rating)}</Muted> : null}
      </View>
      <Card>
        <Text style={s.body}>✂️ {a.service_name} com {a.barber_name}</Text>
        <Text style={[s.body, { marginTop: 6 }]}>📅 {dtLabel(a.start)} até {hm(a.end)}</Text>
        <Text style={[s.body, { marginTop: 6 }]}>💰 {money(a.price)}
          {a.payment_method ? ` · ${payMethodLabel(a.payment_method)}` : ''}</Text>
        <Text style={[s.body, { marginTop: 6 }]}>📱 {phoneLabel(a.customer_phone)}</Text>
        {a.notes ? <Muted style={{ marginTop: 8 }}>{a.notes}</Muted> : null}
      </Card>

      <Button title="Abrir conversa no WhatsApp" kind="ghost" icon="logo-whatsapp"
              onPress={() => Linking.openURL(`https://wa.me/${a.customer_phone}`)} />
      <Button title="Ver ficha do cliente" kind="ghost" icon="person-outline"
              onPress={() => navigation.navigate('Customer', { id: a.customer_id })} />

      {active ? (
        <>
          <Section title="Ações">
            {a.status === 'scheduled' ? <Button title="Confirmar presença" icon="checkmark" onPress={() => setStatus('confirmed')} /> : null}
            {!completing ? <Button title="Marcar como atendido" icon="checkmark-done" onPress={openComplete} /> : null}
            {completePanel}
            <Button title="Cliente faltou" kind="ghost" icon="close-circle-outline" onPress={() => setStatus('no_show')} />
            {a.payment_status !== 'paid' ? (
              <Button title="Enviar Pix pelo WhatsApp" kind="accent" icon="qr-code-outline"
                      onPress={() => run(() => api.post(`/appointments/${a.id}/send-pix`).then(appt.reload), 'Pix enviado para o cliente.')} />
            ) : null}
            <Button title={moving ? 'Fechar remarcação' : 'Remarcar'} kind="ghost" icon="swap-horizontal" onPress={() => setMoving(!moving)} />
          </Section>
          {moving ? (
            <Section title="Novo horário">
              <SlotPicker serviceId={a.service_id} barberId={a.barber_id} value={slot} onChange={setSlot} initialDay={a.start.slice(0, 10)} />
              <Button title="Confirmar remarcação" disabled={!slot} onPress={() => run(async () => {
                await api.post(`/appointments/${a.id}/reschedule`, { start: slot.start, barber_id: slot.barber_id });
                setMoving(false);
                appt.reload();
              }, 'Remarcado. O cliente foi avisado.')} />
            </Section>
          ) : null}
          <Button title="Cancelar agendamento" kind="danger" icon="trash-outline"
                  onPress={() => confirm('Cancelar?', 'O cliente será avisado pelo WhatsApp.', () => setStatus('cancelled', 'Cancelado.'), 'Cancelar', true)} />
        </>
      ) : (
        <>
          {a.status === 'completed' ? (completePanel || (
            <Button title="Alterar pagamento ou valor" kind="ghost" icon="card-outline" onPress={openComplete} />
          )) : null}
          {a.status !== 'cancelled' ? <Button title="Voltar para agendado" kind="ghost" onPress={() => setStatus('scheduled')} /> : null}
        </>
      )}
    </Screen>
  );
}
