import React, { useEffect, useLayoutEffect, useMemo, useState } from 'react';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { confirmPix, QuickActions } from '../components/AppointmentCard';
import { confirmAccess, saveWithConflictCheck } from '../components/booking';
import { DayGrid, fromMin, toMin } from '../components/DayGrid';
import { ConflictDayWarning, QuickBookSheet } from '../components/QuickBook';
import {
  addDays, addMonths, dayLabel, dtLabel, hm, money, moneyInput, monthLabel, parseMoney, PAY_METHODS,
  payMethodLabel, phoneLabel, todayISO, weekdayMonFirst,
} from '../format';
import { ACCESS, PAY, STATUS } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, Button, Card, Chips, confirm, Empty, Field, IconButton, Loading, Screen, Section,
  SegmentedControl, run, toast, Title, useLoad,
} from '../ui';

export { saveWithConflictCheck } from '../components/booking';

// Faixa no topo da agenda com os pedidos que precisam de aprovação
function ApprovalsBanner({ navigation }) {
  const r = useLoad(() => api.get('/approvals'), []);
  const n = r.data?.length || 0;
  if (!n) return null;
  return (
    <Banner tone="accent" icon="hourglass-outline" title={n === 1 ? '1 pedido para aprovar' : `${n} pedidos para aprovar`}
            onPress={() => navigation.navigate('Approvals')} />
  );
}

export function ApprovalsScreen({ navigation }) {
  const { s } = useTheme();
  const list = useLoad(() => api.get('/approvals'), []);
  const act = (a, action) => {
    const approve = action === 'approve';
    const go = () => run(async () => { await api.post(`/appointments/${a.id}/${action}`); list.reload(); },
      approve ? 'Pedido aprovado. O cliente foi avisado.' : 'Pedido recusado. O cliente foi avisado.');
    if (approve) go();
    else confirm('Recusar pedido?', 'O horário é liberado e o cliente recebe uma mensagem neutra dizendo que o horário não está disponível.',
      go, 'Recusar', true);
  };
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Nenhum pedido para aprovar." icon="hourglass-outline" /> : null}
      {(list.data || []).map((a) => (
        <Card key={a.id} onPress={() => navigation.navigate('Appointment', { id: a.id, item: a })}>
          <Text style={s.bodyBold}>{a.customer_name || phoneLabel(a.customer_phone)}</Text>
          <Text style={s.muted}>{dtLabel(a.start)} · {a.service_name} · {a.barber_name} · {money(a.price)}</Text>
          {a.approval_deadline ? <Text style={[s.caption, { marginTop: 4 }]}>Expira {dtLabel(a.approval_deadline).toLowerCase()}</Text> : null}
          <View style={[s.row, { gap: SPACE(2), marginTop: SPACE(3) }]}>
            <Button title="Aprovar" icon="checkmark" onPress={() => act(a, 'approve')} style={{ flex: 1, marginBottom: 0 }} />
            <Button title="Recusar" kind="danger" icon="close" onPress={() => act(a, 'refuse')} style={{ flex: 1, marginBottom: 0 }} />
          </View>
        </Card>
      ))}
    </Screen>
  );
}

function NavRow({ label, sub, onPrev, onNext, onCenter, prevLabel, nextLabel }) {
  const { s } = useTheme();
  return (
    <View style={[s.row, { marginBottom: SPACE(2) }]}>
      <IconButton icon="chevron-back" label={prevLabel} onPress={onPrev} />
      <Pressable onPress={onCenter} accessibilityRole="button" accessibilityHint={sub || undefined}
                 style={{ flex: 1, alignItems: 'center', minHeight: 48, justifyContent: 'center' }}>
        <Text style={s.heading} maxFontSizeMultiplier={1.3}>{label}</Text>
        {sub ? <Text style={s.caption}>{sub}</Text> : null}
      </Pressable>
      <IconButton icon="chevron-forward" label={nextLabel} onPress={onNext} />
    </View>
  );
}

export function DayNav({ day, onChange }) {
  return (
    <NavRow label={dayLabel(day)} sub={day !== todayISO() ? 'toque para voltar a hoje' : null}
            onPrev={() => onChange(addDays(day, -1))} onNext={() => onChange(addDays(day, 1))}
            onCenter={() => onChange(todayISO())} prevLabel="Dia anterior" nextLabel="Próximo dia" />
  );
}

export function MonthNav({ month, onChange }) {
  const current = todayISO().slice(0, 7);
  return (
    <NavRow label={monthLabel(month)} sub={month !== current ? 'toque para voltar ao mês atual' : null}
            onPrev={() => onChange(addMonths(month, -1))} onNext={() => onChange(addMonths(month, 1))}
            onCenter={() => onChange(current)} prevLabel="Mês anterior" nextLabel="Próximo mês" />
  );
}

const WEEK_HEAD = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];

// Calendário do mês: atendimentos e ocupação por dia. Tocar em um dia abre a Timeline.
function MonthView({ month, barber, onPick, onMonth }) {
  const { c, s, font, v } = useTheme();
  const [y, m] = month.split('-').map(Number);
  const r = useLoad(() => api.get('/appointments/month', { year: y, month: m, barber_id: barber }), [month, barber]);
  const days = r.data?.days || [];
  const today = todayISO();
  const lead = days.length ? weekdayMonFirst(days[0].date) : 0;
  const cells = [...Array(lead).fill(null), ...days];
  while (cells.length % 7) cells.push(null);
  const total = days.reduce((t, d) => t + d.total, 0);
  const revenue = days.reduce((t, d) => t + Number(d.revenue_expected), 0);
  const occ = (o) => (o >= 0.85 ? c.status.danger : o >= 0.5 ? c.status.warning : c.status.success);

  return (
    <ScrollView contentContainerStyle={{ paddingBottom: SPACE(10) }}>
      <MonthNav month={month} onChange={onMonth} />
      {!r.data ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Text style={[s.muted, { marginBottom: SPACE(3) }]}>{v.count(total, v.service, v.services)} · previsto {money(revenue)}</Text>
          <View style={[s.card, { padding: SPACE(1.5) }]}>
            <View style={s.row}>
              {WEEK_HEAD.map((w, i) => (
                <Text key={i} style={[s.caption, { width: `${100 / 7}%`, textAlign: 'center', paddingVertical: 6, fontFamily: font.bold }]}>{w}</Text>
              ))}
            </View>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              {cells.map((d, i) => (
                <View key={d ? d.date : `x${i}`} style={{ width: `${100 / 7}%`, padding: 2 }}>
                  {d ? (
                    <Pressable onPress={() => onPick(d.date)} accessibilityRole="button"
                               accessibilityLabel={`${dayLabel(d.date)}: ${v.count(d.total, v.service, v.services)}`}
                               style={({ pressed }) => [{
                                 borderRadius: 10, paddingVertical: 6, alignItems: 'center', minHeight: 64,
                                 backgroundColor: pressed ? c.surfaceElevated : d.date === today ? c.accentSoft : 'transparent',
                                 borderWidth: d.date === today ? 2 : 0, borderColor: c.accentText,
                                 opacity: d.working || d.total ? 1 : 0.4,
                               }]}>
                      <View style={[s.row, { gap: 2 }]}>
                        <Text style={{ fontSize: 16, fontFamily: d.date === today ? font.extrabold : font.semibold, color: c.text }}
                              maxFontSizeMultiplier={1.2}>
                          {Number(d.date.slice(8, 10))}
                        </Text>
                        {d.has_block ? <Ionicons name="lock-closed" size={10} color={c.textMuted} /> : null}
                      </View>
                      <Text style={[s.caption, { fontSize: 12, color: d.total ? c.text : c.textMuted }]} maxFontSizeMultiplier={1.2}>
                        {d.total ? d.total : d.working ? '-' : ''}
                      </Text>
                      {d.working ? (
                        <View style={{ height: 4, width: '80%', backgroundColor: c.neutralBg, borderRadius: 2, marginTop: 5 }}>
                          <View style={{ height: 4, width: `${Math.round(d.occupancy * 100)}%`, backgroundColor: occ(d.occupancy), borderRadius: 2 }} />
                        </View>
                      ) : null}
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </View>
          </View>
          <View style={[s.row, { gap: SPACE(3), flexWrap: 'wrap', marginTop: SPACE(1) }]}>
            {[[c.status.success, 'até 50%'], [c.status.warning, '50 a 85%'], [c.status.danger, 'acima de 85%']].map(([col, l]) => (
              <View key={l} style={[s.row, { gap: 4 }]}>
                <View style={{ width: 14, height: 4, borderRadius: 2, backgroundColor: col }} />
                <Text style={s.caption}>{l}</Text>
              </View>
            ))}
            <View style={[s.row, { gap: 4 }]}>
              <Ionicons name="lock-closed" size={11} color={c.textMuted} />
              <Text style={s.caption}>bloqueio</Text>
            </View>
          </View>
          <Text style={[s.caption, { marginTop: SPACE(2) }]}>
            Ocupação = {v.services} ÷ quantos cabem no expediente do dia (pela duração média dos serviços).
          </Text>
        </>
      )}
    </ScrollView>
  );
}

// Colunas da grade: uma por profissional, ou uma só juntando todos (Timeline)
function buildColumns(agenda, mode, barber) {
  const all = agenda.barbers.map((b) => ({ ...b, key: String(b.id) }));
  if (mode === 'pros') return all;
  if (barber) return all.filter((b) => b.id === barber);
  const seen = new Set();
  return [{
    key: 'all', id: null, name: 'Todos',
    working: all.flatMap((b) => b.working),
    blocks: all.flatMap((b) => b.blocks).filter((k) => k.whole_shop && !seen.has(k.id) && seen.add(k.id)),
    appointments: all.flatMap((b) => b.appointments),
    free: [],
  }];
}

export function AgendaScreen({ navigation }) {
  const { c, s, v } = useTheme();
  const [mode, setMode] = useState('timeline');
  const [day, setDay] = useState(todayISO());
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  const [barber, setBarber] = useState(null);
  const [slot, setSlot] = useState(null);
  const [held, setHeld] = useState(null);
  const agenda = useLoad(async () => (mode === 'month' ? null : api.get('/agenda/day', { day })), [day, mode]);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const services = useLoad(() => api.get('/services'), []);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <View style={s.row}>
          <IconButton icon="refresh" label="Atualizar agenda" onPress={() => agenda.reload()} />
          <IconButton icon="add-circle" size={30} label="Novo agendamento" onPress={() => navigation.navigate('NewAppointment', { day })} />
        </View>
      ),
    });
  }, [navigation, day, s, agenda.reload]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = agenda.data;
  const columns = useMemo(() => (d ? buildColumns(d, mode, barber) : []), [d, mode, barber]);
  const step = d?.slot_step_minutes || 30;

  // Toque num horário vago: acha o profissional livre naquele minuto e abre o agendamento rápido
  const onEmpty = (col, minute) => {
    const candidates = col.id ? d.barbers.filter((b) => b.id === col.id) : d.barbers;
    for (const b of candidates) {
      const f = b.free.find((x) => toMin(x.start) <= minute && minute < toMin(x.end));
      if (!f) continue;
      const floor = Math.ceil(toMin(f.start) / step) * step;
      const m = Math.max(floor, Math.floor(minute / step) * step);
      if (m >= toMin(f.end)) continue;
      setSlot({ day, start: fromMin(day, m), freeEnd: f.end, barber: { id: b.id, name: b.name } });
      return;
    }
    toast('Esse horário não está livre.', 'info');
  };

  const proChips = d && d.barbers.length > 1 && mode === 'timeline' ? (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }}>
      <Chips value={barber} onChange={setBarber}
             options={[{ value: null, label: 'Todos' }, ...d.barbers.map((b) => ({ value: b.id, label: b.name }))]} />
    </ScrollView>
  ) : null;

  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <View style={{ paddingHorizontal: SPACE(4), paddingTop: SPACE(3) }}>
        <ApprovalsBanner navigation={navigation} />
        <SegmentedControl value={mode} onChange={(m) => { setMode(m); if (m === 'month') setMonth(day.slice(0, 7)); }}
                          options={[
                            { value: 'timeline', label: 'Timeline', icon: 'time-outline' },
                            { value: 'pros', label: v.Pros, icon: 'people-outline' },
                            { value: 'month', label: 'Mês', icon: 'calendar-outline' },
                          ]} />
        {mode !== 'month' ? <DayNav day={day} onChange={setDay} /> : null}
        {proChips}
      </View>
      {mode === 'month' ? (
        <View style={{ flex: 1, paddingHorizontal: SPACE(4) }}>
          <MonthView month={month} barber={barber} onMonth={setMonth} onPick={(x) => { setDay(x); setMode('timeline'); }} />
        </View>
      ) : !d ? <Loading error={agenda.error} onRetry={agenda.reload} /> : !d.barbers.length ? (
        <Empty text={`Cadastre ${v.pros} com expediente em Mais > ${v.Pros}.`} />
      ) : (
        <View style={{ flex: 1 }}>
          <Text style={[s.caption, { paddingHorizontal: SPACE(4), marginBottom: SPACE(2) }]}>
            Toque num horário vago para agendar. Toque e segure {v.aService} para ações rápidas.
          </Text>
          <DayGrid day={day} columns={columns} now={d.now} showPro={mode === 'timeline' && !barber}
                   onEmpty={onEmpty} onAppt={(a) => navigation.navigate('Appointment', { id: a.id, item: a })}
                   onApptLong={setHeld} />
        </View>
      )}
      <QuickBookSheet slot={slot} onClose={() => setSlot(null)} services={services.data} barbers={barbers.data}
                      onBooked={() => { setSlot(null); agenda.reload(); }} />
      <QuickActions a={held} visible={!!held} onClose={() => setHeld(null)} onChanged={agenda.reload} navigation={navigation} />
    </View>
  );
}

// Seletor de horário livre (usado em novo agendamento e remarcação)
// Com customerId, os horários perto demais de clientes em conflito com ele já vêm escondidos.
export function SlotPicker({ serviceId, barberId, customerId, value, onChange, initialDay, onDayChange }) {
  const { s } = useTheme();
  const [day, setDay] = useState(initialDay || todayISO());
  const [slots, setSlots] = useState(null);
  const [err, setErr] = useState('');
  useEffect(() => { if (onDayChange) onDayChange(day); }, [day]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!serviceId) return;
    setSlots(null);
    setErr('');
    api.get('/availability', { service_id: serviceId, day, barber_id: barberId, customer_id: customerId })
      .then(setSlots).catch((e) => setErr(e.message));
  }, [serviceId, barberId, customerId, day]);
  if (!serviceId) return <Text style={s.muted}>Escolha o serviço primeiro.</Text>;
  return (
    <View>
      <DayNav day={day} onChange={(x) => { setDay(x); onChange(null); }} />
      {!slots ? <Loading error={err} rows={1} /> : null}
      {slots && !slots.length ? <Empty text="Sem horários livres neste dia." icon="time-outline" /> : null}
      {slots && slots.length ? (
        <Chips value={value ? `${value.start}|${value.barber_id}` : null}
               onChange={(x) => { const [start, b] = x.split('|'); onChange({ start, barber_id: Number(b) }); }}
               options={slots.map((x) => ({ value: `${x.start}|${x.barber_id}`, label: barberId ? hm(x.start) : `${hm(x.start)} ${x.barber_name}` }))} />
      ) : null}
    </View>
  );
}

export function NewAppointmentScreen({ navigation, route }) {
  const { s, v } = useTheme();
  const services = useLoad(() => api.get('/services'), []);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [serviceId, setServiceId] = useState(null);
  const [barberId, setBarberId] = useState(null);
  const [slot, setSlot] = useState(null);
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [customer, setCustomer] = useState(null); // cliente já cadastrado com este telefone
  const [day, setDay] = useState(route.params?.day || todayISO());
  const [hits, setHits] = useState([]);
  const [showAll, setShowAll] = useState(false);

  // Procura o cliente pelo telefone para avisar sobre acesso restrito e conflitos
  const digits = phone.replace(/\D/g, '');
  useEffect(() => {
    if (digits.length < 10) { setCustomer(null); return undefined; }
    const t = setTimeout(() => {
      api.get('/customers', { q: digits, limit: 5 })
        .then((r) => setCustomer(r.find((x) => x.phone.endsWith(digits)) || null)).catch(() => setCustomer(null));
    }, 350);
    return () => clearTimeout(t);
  }, [digits]);
  useEffect(() => {
    if (!customer) { setHits([]); return; }
    api.get('/customer-conflicts/day', { day, customer_id: customer.id }).then(setHits).catch(() => setHits([]));
  }, [customer, day]);

  const save = () => confirmAccess(customer, async () => {
    setBusy(true);
    const r = await saveWithConflictCheck((force) => api.post('/appointments', {
      customer_phone: phone, customer_name: name, service_id: serviceId, barber_id: slot.barber_id, start: slot.start,
      notes, force,
    }), `Agendado. O ${v.customer} recebeu a confirmação no WhatsApp.`);
    setBusy(false);
    if (r) navigation.goBack();
  });

  return (
    <Screen footer={<Button title="Agendar" icon="checkmark" onPress={save} loading={busy}
                            disabled={!phone || !serviceId || !slot} style={{ marginBottom: 0 }} />}>
      <Field label={`WhatsApp do ${v.customer}`} mask="phone" value={phone} onChangeText={setPhone} />
      {customer ? (
        <View style={[s.row, { gap: SPACE(2), marginTop: -SPACE(2), marginBottom: SPACE(3) }]}>
          <Text style={s.muted}>{v.Customer}: {customer.name || 'sem nome'}</Text>
          <Badge info={ACCESS[customer.access_status]} />
        </View>
      ) : null}
      <Field label="Nome" value={name} onChangeText={setName} placeholder={`Opcional se já for ${v.customer}`} autoCapitalize="words" />
      <Section title="Serviço">
        <Chips value={serviceId} onChange={(x) => { setServiceId(x); setSlot(null); }}
               options={(services.data || []).filter((x) => x.active).map((x) => ({ value: x.id, label: `${x.name} · ${money(x.price)}` }))} />
      </Section>
      <Section title={v.Pro}>
        <Chips value={barberId} onChange={(x) => { setBarberId(x); setSlot(null); }}
               options={[{ value: null, label: 'Qualquer um' }, ...(barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
      </Section>
      <Section title="Horário">
        <ConflictDayWarning hits={hits} />
        {hits.length ? (
          <Chips value={showAll} onChange={(x) => { setShowAll(x); setSlot(null); }} options={[
            { value: false, label: 'Esconder horários próximos' }, { value: true, label: 'Mostrar todos' },
          ]} />
        ) : null}
        <SlotPicker serviceId={serviceId} barberId={barberId} customerId={showAll ? null : customer?.id} value={slot}
                    onChange={setSlot} initialDay={route.params?.day} onDayChange={setDay} />
      </Section>
      <Field label="Observação" value={notes} onChangeText={setNotes} multiline />
    </Screen>
  );
}

function InfoRow({ icon, children }) {
  const { c, s } = useTheme();
  return (
    <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(2.5), alignItems: 'flex-start' }]}>
      <Ionicons name={icon} size={20} color={c.accentText} style={{ marginTop: 2 }} />
      <Text style={[s.body, { flex: 1 }]}>{children}</Text>
    </View>
  );
}

function Stars({ n }) {
  const { c } = useTheme();
  return (
    <View style={{ flexDirection: 'row' }} accessibilityLabel={`Nota ${n} de 5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Ionicons key={i} name={i < n ? 'star' : 'star-outline'} size={16} color={i < n ? c.accentText : c.textMuted} />
      ))}
    </View>
  );
}
export { Stars };

export function AppointmentScreen({ navigation, route }) {
  const { s, v } = useTheme();
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
  }, `${v.Service} ${v.done}.`);
  const diff = (parseMoney(finalPrice) ?? Number(a.price)) - Number(a.price);
  const completePanel = completing ? (
    <Section title={a.status === 'completed' ? 'Pagamento' : `Concluir ${v.service}`}>
      <Card>
        <Text style={[s.label, { marginBottom: SPACE(2) }]}>Forma de pagamento</Text>
        <Chips value={method} onChange={setMethod} options={PAY_METHODS} />
        {a.payment_status === 'paid' ? <Text style={[s.caption, { marginTop: -SPACE(2), marginBottom: SPACE(3) }]}>Já pago via Pix pelo WhatsApp.</Text> : null}
        <Field label="Valor cobrado" mask="money" value={finalPrice} onChangeText={setFinalPrice}
               hint={Math.abs(diff) >= 0.005
                 ? `${diff < 0 ? 'Desconto' : 'Acréscimo'} de ${money(Math.abs(diff))} sobre ${money(a.price)}`
                 : 'Altere para dar desconto ou cobrar a mais.'} />
        <Button title={a.status === 'completed' ? 'Salvar pagamento' : `Concluir ${v.service}`} icon="checkmark-done"
                onPress={complete} disabled={!method} />
        <Button title="Voltar" kind="ghost" onPress={() => setCompleting(false)} style={{ marginBottom: 0 }} />
      </Card>
    </Section>
  ) : null;

  const setStatus = (status, msg) => run(async () => {
    await api.patch(`/appointments/${a.id}`, { status });
    appt.reload();
  }, msg);
  const active = a.status === 'scheduled' || a.status === 'confirmed';
  const pending = a.status === 'pending_approval';
  const decide = (action, msg) => run(async () => {
    await api.post(`/appointments/${a.id}/${action}`);
    appt.reload();
  }, msg);

  return (
    <Screen>
      <Title>{a.customer_name || phoneLabel(a.customer_phone)}</Title>
      <View style={[s.row, { gap: SPACE(1.5), marginBottom: SPACE(4), flexWrap: 'wrap' }]}>
        <Badge info={STATUS[a.status]} large />
        <Badge info={PAY[a.payment_status]} large />
        <Badge info={ACCESS[a.customer_access_status]} large />
        {a.rating ? <Stars n={a.rating} /> : null}
      </View>
      <Card>
        <InfoRow icon="pricetag-outline">{a.service_name} com {a.barber_name}</InfoRow>
        <InfoRow icon="calendar-outline">{dtLabel(a.start)} até {hm(a.end)}</InfoRow>
        <InfoRow icon="cash-outline">{money(a.price)}{a.payment_method ? ` · ${payMethodLabel(a.payment_method)}` : ''}</InfoRow>
        <InfoRow icon="call-outline">{phoneLabel(a.customer_phone)}</InfoRow>
        {a.notes ? <Text style={s.muted}>{a.notes}</Text> : null}
      </Card>

      {a.payment_status === 'pending' && a.payment_id ? (
        <Button title="Confirmar Pix" icon="checkmark-circle-outline" onPress={() => confirmPix(a, appt.reload)} />
      ) : null}
      <View style={[s.row, { gap: SPACE(2) }]}>
        <Button title="WhatsApp" kind="ghost" icon="logo-whatsapp" style={{ flex: 1 }}
                onPress={() => Linking.openURL(`https://wa.me/${a.customer_phone}`)} />
        <Button title="Ficha" kind="ghost" icon="person-outline" style={{ flex: 1 }}
                onPress={() => navigation.navigate('Customer', { id: a.customer_id })} />
      </View>

      {pending ? (
        <Section title="Pedido para aprovar">
          {a.approval_deadline ? <Text style={[s.muted, { marginBottom: SPACE(3) }]}>Expira {dtLabel(a.approval_deadline).toLowerCase()} se não for respondido.</Text> : null}
          <Button title="Aprovar" icon="checkmark" onPress={() => decide('approve', 'Pedido aprovado. O cliente foi avisado.')} />
          <Button title="Recusar" kind="danger" icon="close" onPress={() => confirm('Recusar pedido?',
            'O horário é liberado e o cliente recebe uma mensagem neutra.', () => decide('refuse', 'Pedido recusado.'), 'Recusar', true)} />
        </Section>
      ) : null}

      {active ? (
        <>
          <Section title="Ações">
            {a.status === 'scheduled' ? <Button title="Confirmar presença" kind="secondary" icon="checkmark" onPress={() => setStatus('confirmed', 'Presença confirmada.')} /> : null}
            {!completing ? <Button title={`Concluir ${v.service}`} icon="checkmark-done" onPress={openComplete} /> : null}
            {completePanel}
            <Button title={`${v.Customer} faltou`} kind="ghost" icon="close-circle-outline" onPress={() => setStatus('no_show', 'Falta registrada.')} />
            {a.payment_status !== 'paid' ? (
              <Button title="Enviar Pix pelo WhatsApp" kind="secondary" icon="qr-code-outline"
                      onPress={() => run(() => api.post(`/appointments/${a.id}/send-pix`).then(appt.reload), 'Pix enviado.')} />
            ) : null}
            <Button title={moving ? 'Fechar remarcação' : 'Remarcar'} kind="ghost" icon="swap-horizontal" onPress={() => setMoving(!moving)} />
          </Section>
          {moving ? (
            <Section title="Novo horário">
              <SlotPicker serviceId={a.service_id} barberId={a.barber_id} customerId={a.customer_id} value={slot}
                          onChange={setSlot} initialDay={a.start.slice(0, 10)} />
              <Button title="Confirmar remarcação" disabled={!slot} onPress={async () => {
                const r = await saveWithConflictCheck((force) => api.post(`/appointments/${a.id}/reschedule`, {
                  start: slot.start, barber_id: slot.barber_id, force,
                }), 'Remarcado. O cliente foi avisado.');
                if (r) { setMoving(false); appt.reload(); }
              }} />
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
          {a.status !== 'cancelled' && !pending ? <Button title="Voltar para agendado" kind="ghost" onPress={() => setStatus('scheduled')} /> : null}
        </>
      )}
    </Screen>
  );
}
