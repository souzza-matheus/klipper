import React, { useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../api';
import {
  dtLabel, hm, isHM, money, moneyInput, normHM, parseBRDate, parseMoney, phoneLabel, todayISO, WEEKDAYS_MON_FIRST,
} from '../format';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Button, Card, Chips, confirm, Empty, Field, Group, IconButton, ListRow, Loading, Muted, Screen, Section, Toggle,
  run, useLoad,
} from '../ui';
import { BarberCommissionRules } from './Finance';

function AddButton({ onPress, label }) {
  return <IconButton icon="add-circle" size={30} label={label} onPress={onPress} />;
}

// ---------------------------------------------------------------- serviços

export function ServicesScreen({ navigation }) {
  const list = useLoad(() => api.get('/services'), []);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => <AddButton label="Novo serviço" onPress={() => navigation.navigate('ServiceEdit', {})} /> });
  }, [navigation]);
  const items = list.data || [];
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty text="Cadastre os serviços que aparecem no bot."
               action={{ title: 'Novo serviço', icon: 'add', onPress: () => navigation.navigate('ServiceEdit', {}) }} />
      ) : null}
      {items.length ? (
        <Group>
          {items.map((x, i) => (
            <ListRow key={x.id} icon="pricetag-outline" title={x.name + (x.active ? '' : ' (inativo)')}
                     subtitle={`${money(x.price)} · ${x.duration_minutes} min`} first={i === 0} last={i === items.length - 1}
                     onPress={() => navigation.navigate('ServiceEdit', { item: x })} />
          ))}
        </Group>
      ) : null}
    </Screen>
  );
}

export function ServiceEditScreen({ navigation, route }) {
  const { v } = useTheme();
  const item = route.params?.item;
  const [name, setName] = useState(item?.name || '');
  const [price, setPrice] = useState(item ? moneyInput(item.price) : '');
  const [duration, setDuration] = useState(item ? String(item.duration_minutes) : '30');
  const [order, setOrder] = useState(item ? String(item.sort_order) : '0');
  const [active, setActive] = useState(item ? item.active : true);
  const [depMode, setDepMode] = useState(item?.deposit_mode || '');
  const [depValue, setDepValue] = useState(item && Number(item.deposit_value)
    ? (item.deposit_mode === 'percent' ? String(Number(item.deposit_value)) : moneyInput(item.deposit_value)) : '');
  const products = useLoad(() => api.get('/products'), []);
  const consumption = useLoad(async () => (item ? api.get(`/services/${item.id}/consumption`) : []), [item?.id]);
  const [cons, setCons] = useState(null); // { product_id: 'quantidade' }
  const consMap = cons ?? Object.fromEntries((consumption.data || []).map((x) => [x.product_id, String(Number(x.quantity))]));

  const save = () => run(async () => {
    const value = parseMoney(price);
    if (value === null) throw new Error('Preço inválido.');
    const dep = depMode === 'percent' ? Number(String(depValue).replace(',', '.')) || 0 : parseMoney(depValue) ?? 0;
    const body = { name, price: value, duration_minutes: Number(duration), sort_order: Number(order) || 0, active,
                   deposit_mode: depMode, deposit_value: dep.toFixed(2) };
    const saved = item ? await api.put(`/services/${item.id}`, body) : await api.post('/services', body);
    if (cons) {
      await api.put(`/services/${saved.id}/consumption`, Object.entries(cons).filter(([, q]) => Number(String(q).replace(',', '.')) > 0)
        .map(([pid, q]) => ({ product_id: Number(pid), quantity: String(Number(String(q).replace(',', '.'))) })));
    }
    navigation.goBack();
  });
  const internal = (products.data || []).filter((p) => p.kind !== 'sale' && p.active);

  return (
    <Screen footer={<Button title="Salvar" icon="checkmark" onPress={save} disabled={!name || !price || !duration} style={{ marginBottom: 0 }} />}>
      <Field label="Nome" value={name} onChangeText={setName} placeholder={v.serviceExample} />
      <Field label="Preço" mask="money" value={price} onChangeText={setPrice} />
      <Field label="Duração (minutos)" value={duration} onChangeText={setDuration} keyboardType="number-pad" />
      <Field label="Ordem no menu" value={order} onChangeText={setOrder} keyboardType="number-pad" hint="Menor aparece primeiro." />
      <Toggle label="Ativo (aparece no bot)" value={active} onValueChange={setActive} />
      <Section title="Sinal neste serviço">
        <Chips value={depMode} onChange={setDepMode} options={[
          { value: '', label: 'Regra do negócio' }, { value: 'off', label: 'Sem sinal' },
          { value: 'fixed', label: 'Valor fixo' }, { value: 'percent', label: '%' },
        ]} />
        {depMode === 'fixed' ? <Field label="Valor do sinal" mask="money" value={depValue} onChangeText={setDepValue} /> : null}
        {depMode === 'percent' ? <Field label="Porcentagem" value={depValue} onChangeText={setDepValue} keyboardType="decimal-pad" /> : null}
      </Section>
      {internal.length ? (
        <Section title="Produtos que o serviço consome">
          <Muted style={{ marginBottom: SPACE(3) }}>Baixados do estoque quando o serviço entra na comanda.</Muted>
          {internal.map((p) => (
            <Field key={p.id} label={`${p.name} (${p.unit})`} value={consMap[p.id] || ''} keyboardType="decimal-pad"
                   placeholder="0" onChangeText={(t) => setCons({ ...consMap, [p.id]: t })} />
          ))}
        </Section>
      ) : null}
      {item ? (
        <Button title="Excluir" kind="danger" icon="trash-outline" onPress={() => confirm('Excluir serviço?', 'Se já tiver agendamentos, ele só será desativado.',
          () => run(async () => { await api.del(`/services/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- barbeiros

export function BarbersScreen({ navigation }) {
  const { v } = useTheme();
  const list = useLoad(() => api.get('/barbers'), []);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => <AddButton label={`Novo ${v.pro}`} onPress={() => navigation.navigate('BarberEdit', {})} /> });
  }, [navigation, v.pro]);
  const items = list.data || [];
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty text={`Cadastre pelo menos um ${v.proHint} com expediente.`}
               action={{ title: `Novo ${v.pro}`, icon: 'add', onPress: () => navigation.navigate('BarberEdit', {}) }} />
      ) : null}
      {items.length ? (
        <Group>
          {items.map((b, i) => (
            <ListRow key={b.id} icon="person-outline" title={b.name + (b.active ? '' : ' (inativo)')} first={i === 0}
                     last={i === items.length - 1}
                     subtitle={`${new Set(b.working_hours.map((w) => w.weekday)).size} dias por semana · ${phoneLabel(b.phone) || 'sem WhatsApp'}`}
                     onPress={() => navigation.navigate('BarberEdit', { item: b })} />
          ))}
        </Group>
      ) : null}
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
  const { s, v } = useTheme();
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
    <Screen footer={<Button title="Salvar" icon="checkmark" onPress={save} disabled={!name} style={{ marginBottom: 0 }} />}>
      <Field label="Nome" value={name} onChangeText={setName} autoCapitalize="words" />
      <Field label="WhatsApp" mask="phone" value={phone} onChangeText={setPhone}
             hint={`Recebe alertas da própria agenda e acessa o menu do ${v.pro} no bot.`} />
      <Field label="Apresentação curta" value={bio} onChangeText={setBio} placeholder="Ex.: especialista em degradê" />
      <Toggle label="Ativo" value={active} onValueChange={setActive} />
      <Section title="Serviços que faz">
        <Muted style={{ marginBottom: SPACE(2) }}>Nenhum marcado = faz todos.</Muted>
        <Chips multi value={serviceIds} onChange={setServiceIds}
               options={(services.data || []).map((x) => ({ value: x.id, label: x.name }))} />
      </Section>
      <Section title="Expediente">
        {days.map((x, d) => (
          <Card key={d}>
            <Toggle label={WEEKDAYS_MON_FIRST[d]} value={x.on} onValueChange={(on) => setDay(d, { on })} />
            {x.on ? (
              <>
                <View style={[s.row, { gap: SPACE(2.5) }]}>
                  <View style={{ flex: 1 }}><HMInput label="Início" value={x.a1} onChangeText={(t) => setDay(d, { a1: t })} /></View>
                  <View style={{ flex: 1 }}><HMInput label="Fim" value={x.b1} onChangeText={(t) => setDay(d, { b1: t })} /></View>
                </View>
                <View style={[s.row, { gap: SPACE(2.5) }]}>
                  <View style={{ flex: 1 }}><HMInput label="2º turno início" value={x.a2} onChangeText={(t) => setDay(d, { a2: t })} placeholder="opcional" /></View>
                  <View style={{ flex: 1 }}><HMInput label="2º turno fim" value={x.b2} onChangeText={(t) => setDay(d, { b2: t })} placeholder="opcional" /></View>
                </View>
              </>
            ) : null}
          </Card>
        ))}
      </Section>
      {item ? <BarberCommissionRules barberId={item.id} navigation={navigation} /> : null}
      {item ? (
        <Button title="Excluir" kind="danger" icon="trash-outline" onPress={() => confirm(`Excluir ${v.pro}?`, 'Se já tiver agendamentos, só será desativado.',
          () => run(async () => { await api.del(`/barbers/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- bloqueios

export function BlocksScreen() {
  const { s, v } = useTheme();
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

  const whole = `${v.Business} ${['clínica', 'barbearia'].includes(v.business) ? 'inteira' : 'inteiro'}`;
  const name = (id) => (barbers.data || []).find((b) => b.id === id)?.name || whole;

  return (
    <Screen onRefresh={list.reload}>
      <Section title="Novo bloqueio">
        <Field label="Data" value={date} onChangeText={setDate} placeholder="dd/mm ou hoje" />
        <Toggle label="Dia inteiro" value={allDay} onValueChange={setAllDay} />
        {!allDay ? (
          <View style={[s.row, { gap: SPACE(2.5) }]}>
            <View style={{ flex: 1 }}><Field label="Início" value={start} onChangeText={setStart} maxLength={5} keyboardType="numbers-and-punctuation" /></View>
            <View style={{ flex: 1 }}><Field label="Fim" value={end} onChangeText={setEnd} maxLength={5} keyboardType="numbers-and-punctuation" /></View>
          </View>
        ) : null}
        <Field label="Motivo" value={reason} onChangeText={setReason} placeholder="Almoço, folga, feriado..." />
        <Chips value={barberId} onChange={setBarberId}
               options={[{ value: null, label: whole }, ...(barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
        <Button title="Bloquear" icon="lock-closed-outline" onPress={add} disabled={!date} />
      </Section>
      <Section title="Próximos bloqueios">
        {list.data && !list.data.length ? <Empty icon="lock-open-outline" text="Nenhum bloqueio." /> : null}
        {(list.data || []).map((b) => (
          <Card key={b.id}>
            <View style={s.row}>
              <View style={{ flex: 1 }}>
                <Text style={s.bodyBold}>{dtLabel(b.start)} até {hm(b.end)}</Text>
                <Muted>{name(b.barber_id)}{b.reason ? ` · ${b.reason}` : ''}</Muted>
              </View>
              <RemoveBlock onPress={() => confirm('Remover bloqueio?', '', () => run(async () => { await api.del(`/blocks/${b.id}`); list.reload(); }, 'Bloqueio removido.'), 'Remover', true)} />
            </View>
          </Card>
        ))}
      </Section>
    </Screen>
  );
}

function RemoveBlock({ onPress }) {
  const { c } = useTheme();
  return <IconButton icon="trash-outline" label="Remover bloqueio" color={c.statusText.danger} onPress={onPress} />;
}
