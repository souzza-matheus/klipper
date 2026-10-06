import React, { useEffect, useLayoutEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { addDays, dayLabel, dtLabel, hm, money, phoneLabel, todayISO } from '../format';
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

export function AgendaScreen({ navigation }) {
  const [day, setDay] = useState(todayISO());
  const [barber, setBarber] = useState(null);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const appts = useLoad(() => api.get('/appointments', { date_from: day, barber_id: barber, include_cancelled: true }), [day, barber]);

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

  return (
    <Screen onRefresh={appts.reload} refreshing={appts.loading && !!appts.data}>
      <DayNav day={day} onChange={setDay} />
      {barbers.data && barbers.data.length > 1 ? (
        <Chips value={barber} onChange={setBarber}
               options={[{ value: null, label: 'Todos' }, ...barbers.data.filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
      ) : null}
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
                {a.created_via === 'bot' ? <Muted>via WhatsApp</Muted> : null}
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
  const a = appt.data;
  if (!a) return <Loading error={appt.error} onRetry={appt.reload} />;

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
        <Text style={[s.body, { marginTop: 6 }]}>💰 {money(a.price)}</Text>
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
            <Button title="Marcar como atendido" icon="checkmark-done" onPress={() => setStatus('completed')} />
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
        a.status !== 'cancelled' ? <Button title="Voltar para agendado" kind="ghost" onPress={() => setStatus('scheduled')} /> : null
      )}
    </Screen>
  );
}
