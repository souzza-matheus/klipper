import React, { useLayoutEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { dtLabel, hm, isHM, money, normHM, parseBRDate, phoneLabel, todayISO, WEEKDAYS_MON_FIRST } from '../format';
import { colors } from '../theme';
import {
  Button, Card, Chips, confirm, Empty, Field, ListRow, Loading, Muted, Screen, Section, Toggle, run, s, useLoad,
} from '../ui';
import { BarberCommissionRules } from './Finance';

function AddButton({ onPress }) {
  return (
    <Pressable onPress={onPress} hitSlop={10}>
      <Ionicons name="add-circle" size={30} color={colors.accent} />
    </Pressable>
  );
}

// ---------------------------------------------------------------- serviços

export function ServicesScreen({ navigation }) {
  const list = useLoad(() => api.get('/services'), []);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => <AddButton onPress={() => navigation.navigate('ServiceEdit', {})} /> });
  }, [navigation]);
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Cadastre os serviços que aparecem no bot." /> : null}
      <View style={{ borderRadius: 12, overflow: 'hidden' }}>
        {(list.data || []).map((x) => (
          <ListRow key={x.id} title={x.name + (x.active ? '' : ' (inativo)')}
                   subtitle={`${money(x.price)} · ${x.duration_minutes} min`}
                   onPress={() => navigation.navigate('ServiceEdit', { item: x })} />
        ))}
      </View>
    </Screen>
  );
}

export function ServiceEditScreen({ navigation, route }) {
  const item = route.params?.item;
  const [name, setName] = useState(item?.name || '');
  const [price, setPrice] = useState(item ? String(item.price).replace('.', ',') : '');
  const [duration, setDuration] = useState(item ? String(item.duration_minutes) : '30');
  const [order, setOrder] = useState(item ? String(item.sort_order) : '0');
  const [active, setActive] = useState(item ? item.active : true);

  const save = () => run(async () => {
    const body = { name, price: Number(price.replace(',', '.')), duration_minutes: Number(duration), sort_order: Number(order) || 0, active };
    if (item) await api.put(`/services/${item.id}`, body);
    else await api.post('/services', body);
    navigation.goBack();
  });

  return (
    <Screen>
      <Field label="Nome" value={name} onChangeText={setName} placeholder="Ex.: Corte degradê" />
      <Field label="Preço (R$)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
      <Field label="Duração (minutos)" value={duration} onChangeText={setDuration} keyboardType="number-pad" />
      <Field label="Ordem no menu" value={order} onChangeText={setOrder} keyboardType="number-pad" hint="Menor aparece primeiro." />
      <Toggle label="Ativo (aparece no bot)" value={active} onValueChange={setActive} />
      <Button title="Salvar" onPress={save} disabled={!name || !price || !duration} />
      {item ? (
        <Button title="Excluir" kind="danger" onPress={() => confirm('Excluir serviço?', 'Se já tiver agendamentos, ele só será desativado.',
          () => run(async () => { await api.del(`/services/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- barbeiros

export function BarbersScreen({ navigation }) {
  const list = useLoad(() => api.get('/barbers'), []);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => <AddButton onPress={() => navigation.navigate('BarberEdit', {})} /> });
  }, [navigation]);
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Cadastre pelo menos um barbeiro com expediente." /> : null}
      <View style={{ borderRadius: 12, overflow: 'hidden' }}>
        {(list.data || []).map((b) => (
          <ListRow key={b.id} icon="cut-outline" title={b.name + (b.active ? '' : ' (inativo)')}
                   subtitle={`${new Set(b.working_hours.map((w) => w.weekday)).size} dias por semana · ${phoneLabel(b.phone) || 'sem WhatsApp'}`}
                   onPress={() => navigation.navigate('BarberEdit', { item: b })} />
        ))}
      </View>
    </Screen>
  );
}

function hoursToDays(whs) {
  const days = Array.from({ length: 7 }, () => ({ on: false, a1: '09:00', b1: '12:00', a2: '', b2: '' }));
  const byDay = {};
  whs.forEach((w) => { (byDay[w.weekday] = byDay[w.weekday] || []).push(w); });
  Object.entries(byDay).forEach(([d, list]) => {
    list.sort((x, y) => x.start.localeCompare(y.start));
    days[d] = {
      on: true,
      a1: list[0].start.slice(0, 5), b1: list[0].end.slice(0, 5),
      a2: list[1] ? list[1].start.slice(0, 5) : '', b2: list[1] ? list[1].end.slice(0, 5) : '',
    };
  });
  return days;
}

function daysToHours(days) {
  const out = [];
  for (let d = 0; d < 7; d++) {
    const x = days[d];
    if (!x.on) continue;
    if (!isHM(x.a1) || !isHM(x.b1)) throw new Error(`Horário inválido em ${WEEKDAYS_MON_FIRST[d]}. Use HH:MM.`);
    out.push({ weekday: d, start: normHM(x.a1) + ':00', end: normHM(x.b1) + ':00' });
    if (x.a2 || x.b2) {
      if (!isHM(x.a2) || !isHM(x.b2)) throw new Error(`Segundo turno inválido em ${WEEKDAYS_MON_FIRST[d]}.`);
      out.push({ weekday: d, start: normHM(x.a2) + ':00', end: normHM(x.b2) + ':00' });
    }
  }
  return out;
}

const HMInput = (props) => <Field {...props} keyboardType="numbers-and-punctuation" maxLength={5} />;

export function BarberEditScreen({ navigation, route }) {
  const item = route.params?.item;
  const services = useLoad(() => api.get('/services'), []);
  const [name, setName] = useState(item?.name || '');
  const [phone, setPhone] = useState(item?.phone ? phoneLabel(item.phone) : '');
  const [bio, setBio] = useState(item?.bio || '');
  const [active, setActive] = useState(item ? item.active : true);
  const [serviceIds, setServiceIds] = useState(item?.service_ids || []);
  const [days, setDays] = useState(item ? hoursToDays(item.working_hours) : hoursToDays(
    [0, 1, 2, 3, 4, 5].flatMap((d) => [{ weekday: d, start: '09:00:00', end: '12:00:00' }, ...(d < 5 ? [{ weekday: d, start: '13:00:00', end: '19:00:00' }] : [])]),
  ));
  const setDay = (d, patch) => setDays(days.map((x, i) => (i === d ? { ...x, ...patch } : x)));

  const save = () => run(async () => {
    const body = { name, phone, bio, active, service_ids: serviceIds, working_hours: daysToHours(days) };
    if (item) await api.put(`/barbers/${item.id}`, body);
    else await api.post('/barbers', body);
    navigation.goBack();
  });

  return (
    <Screen>
      <Field label="Nome" value={name} onChangeText={setName} />
      <Field label="WhatsApp" value={phone} onChangeText={setPhone} keyboardType="phone-pad"
             hint="Recebe alertas da própria agenda e acessa o menu do barbeiro no bot." />
      <Field label="Apresentação curta" value={bio} onChangeText={setBio} placeholder="Ex.: especialista em degradê" />
      <Toggle label="Ativo" value={active} onValueChange={setActive} />
      <Section title="Serviços que faz">
        <Muted style={{ marginBottom: 8 }}>Nenhum marcado = faz todos.</Muted>
        <Chips multi value={serviceIds} onChange={setServiceIds}
               options={(services.data || []).map((x) => ({ value: x.id, label: x.name }))} />
      </Section>
      <Section title="Expediente">
        {days.map((x, d) => (
          <Card key={d}>
            <Toggle label={WEEKDAYS_MON_FIRST[d]} value={x.on} onValueChange={(on) => setDay(d, { on })} />
            {x.on ? (
              <>
                <View style={[s.row, { gap: 10 }]}>
                  <View style={{ flex: 1 }}><HMInput label="Início" value={x.a1} onChangeText={(v) => setDay(d, { a1: v })} /></View>
                  <View style={{ flex: 1 }}><HMInput label="Fim" value={x.b1} onChangeText={(v) => setDay(d, { b1: v })} /></View>
                </View>
                <View style={[s.row, { gap: 10 }]}>
                  <View style={{ flex: 1 }}><HMInput label="2º turno início" value={x.a2} onChangeText={(v) => setDay(d, { a2: v })} placeholder="opcional" /></View>
                  <View style={{ flex: 1 }}><HMInput label="2º turno fim" value={x.b2} onChangeText={(v) => setDay(d, { b2: v })} placeholder="opcional" /></View>
                </View>
              </>
            ) : null}
          </Card>
        ))}
      </Section>
      <Button title="Salvar" onPress={save} disabled={!name} />
      {item ? <BarberCommissionRules barberId={item.id} navigation={navigation} /> : null}
      {item ? (
        <Button title="Excluir" kind="danger" onPress={() => confirm('Excluir barbeiro?', 'Se já tiver agendamentos, ele só será desativado.',
          () => run(async () => { await api.del(`/barbers/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- bloqueios

export function BlocksScreen() {
  const list = useLoad(() => api.get('/blocks'), []);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [date, setDate] = useState('');
  const [start, setStart] = useState('12:00');
  const [end, setEnd] = useState('13:00');
  const [reason, setReason] = useState('');
  const [barberId, setBarberId] = useState(null);
  const [allDay, setAllDay] = useState(false);

  const add = () => run(async () => {
    const iso = date.trim().toLowerCase() === 'hoje' ? todayISO() : parseBRDate(date);
    if (!iso) throw new Error('Data inválida. Use dd/mm, ex.: 15/10.');
    const a = allDay ? '00:00' : start;
    const b = allDay ? '23:59' : end;
    if (!isHM(a) || !isHM(b)) throw new Error('Horário inválido. Use HH:MM.');
    await api.post('/blocks', { barber_id: barberId, start: `${iso}T${normHM(a)}:00`, end: `${iso}T${normHM(b)}:00`, reason });
    setReason('');
    list.reload();
  }, 'Horário bloqueado. O bot não oferece mais esse intervalo.');

  const name = (id) => (barbers.data || []).find((b) => b.id === id)?.name || 'Barbearia inteira';

  return (
    <Screen onRefresh={list.reload}>
      <Section title="Novo bloqueio">
        <Field label="Data" value={date} onChangeText={setDate} placeholder="dd/mm ou hoje" />
        <Toggle label="Dia inteiro" value={allDay} onValueChange={setAllDay} />
        {!allDay ? (
          <View style={[s.row, { gap: 10 }]}>
            <View style={{ flex: 1 }}><Field label="Início" value={start} onChangeText={setStart} maxLength={5} /></View>
            <View style={{ flex: 1 }}><Field label="Fim" value={end} onChangeText={setEnd} maxLength={5} /></View>
          </View>
        ) : null}
        <Field label="Motivo" value={reason} onChangeText={setReason} placeholder="Almoço, folga, feriado..." />
        <Chips value={barberId} onChange={setBarberId}
               options={[{ value: null, label: 'Barbearia inteira' }, ...(barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
        <Button title="Bloquear" icon="lock-closed-outline" onPress={add} disabled={!date} />
      </Section>
      <Section title="Próximos bloqueios">
        {list.data && !list.data.length ? <Empty text="Nenhum bloqueio." /> : null}
        {(list.data || []).map((b) => (
          <Card key={b.id}>
            <View style={s.row}>
              <View style={{ flex: 1 }}>
                <Text style={s.body}>{dtLabel(b.start)} até {hm(b.end)}</Text>
                <Muted>{name(b.barber_id)}{b.reason ? ` · ${b.reason}` : ''}</Muted>
              </View>
              <Pressable hitSlop={10} onPress={() => confirm('Remover bloqueio?', '', () => run(async () => { await api.del(`/blocks/${b.id}`); list.reload(); }), 'Remover', true)}>
                <Ionicons name="trash-outline" size={22} color={colors.bad} />
              </Pressable>
            </View>
          </Card>
        ))}
      </Section>
    </Screen>
  );
}
