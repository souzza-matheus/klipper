import React, { useEffect, useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { api } from '../api';
import { DayNav } from './Agenda';
import { dayLabel, dtLabel, normHM, phoneLabel, todayISO } from '../format';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, BottomSheet, Button, Card, Chips, confirm, Empty, Field, IconButton, Loading, Screen, Toggle, run, useLoad,
} from '../ui';

const WAIT = {
  waiting: { label: 'Na fila', tone: 'info', icon: 'list-outline' },
  offered: { label: 'Vaga reservada', tone: 'accent', icon: 'hourglass-outline' },
  booked: { label: 'Agendou', tone: 'success', icon: 'checkmark-circle-outline' },
  expired: { label: 'Não respondeu', tone: 'neutral', icon: 'time-outline' },
  cancelled: { label: 'Saiu da lista', tone: 'neutral', icon: 'close-circle-outline' },
};

function AddSheet({ visible, onClose, day, onAdded }) {
  const { s, v } = useTheme();
  const services = useLoad(() => api.get('/services'), []);
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [serviceId, setServiceId] = useState(null);
  const [barberId, setBarberId] = useState(null);
  const [after, setAfter] = useState('');
  const [before, setBefore] = useState('');
  useEffect(() => { if (!visible) { setPhone(''); setName(''); setAfter(''); setBefore(''); } }, [visible]);
  const save = () => run(async () => {
    await api.post('/waitlist', {
      customer_phone: phone, customer_name: name, service_id: serviceId, barber_id: barberId, day,
      after_time: after ? normHM(after) : null, before_time: before ? normHM(before) : null,
    });
    onAdded();
    onClose();
  }, 'Adicionado à lista de espera.');
  return (
    <BottomSheet visible={visible} onClose={onClose} title={`Lista de espera de ${dayLabel(day).toLowerCase()}`}
                 footer={<Button title="Adicionar" icon="add" onPress={save} disabled={!phone || !serviceId}
                                 style={{ marginBottom: 0 }} />}>
      <Field label={`WhatsApp do ${v.customer}`} mask="phone" value={phone} onChangeText={setPhone} />
      <Field label="Nome" value={name} onChangeText={setName} autoCapitalize="words" />
      <Text style={s.label}>Serviço</Text>
      <Chips value={serviceId} onChange={setServiceId} options={(services.data || []).filter((x) => x.active)
        .map((x) => ({ value: x.id, label: x.name }))} />
      <Text style={s.label}>{v.Pro}</Text>
      <Chips value={barberId} onChange={setBarberId} options={[{ value: null, label: 'Qualquer um' },
        ...(barbers.data || []).filter((b) => b.active).map((b) => ({ value: b.id, label: b.name }))]} />
      <View style={[s.row, { gap: SPACE(3) }]}>
        <Field label="A partir de" value={after} onChangeText={setAfter} placeholder="14:00" style={{ flex: 1 }} />
        <Field label="Até" value={before} onChangeText={setBefore} placeholder="18:00" style={{ flex: 1 }} />
      </View>
    </BottomSheet>
  );
}

export function WaitlistScreen({ navigation }) {
  const { s, v } = useTheme();
  const [day, setDay] = useState(todayISO());
  const [all, setAll] = useState(false);
  const [adding, setAdding] = useState(false);
  const list = useLoad(() => api.get('/waitlist', { day, include_closed: all }), [day, all]);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => (
      <IconButton icon="add-circle" size={30} label="Adicionar à lista" onPress={() => setAdding(true)} />
    ) });
  }, [navigation]);
  const items = list.data || [];
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
        Quando um horário abre, a primeira pessoa da fila que cabe nele é avisada no WhatsApp e a vaga fica reservada
        por alguns minutos. Sem resposta, passa para a próxima.
      </Text>
      <DayNav day={day} onChange={setDay} />
      <Toggle label="Mostrar também quem já saiu da fila" value={all} onValueChange={setAll} />
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? (
        <Empty icon="list-outline" text="Ninguém na lista de espera deste dia."
               action={{ title: 'Adicionar', icon: 'add', onPress: () => setAdding(true) }} />
      ) : null}
      {items.map((e) => (
        <Card key={e.id} onPress={() => navigation.navigate('Customer', { id: e.customer_id })}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            {e.position ? <Text style={[s.heading, { minWidth: 28 }]}>{e.position}º</Text> : null}
            <View style={{ flex: 1 }}>
              <Text style={s.bodyBold}>{e.customer_name}</Text>
              <Text style={s.caption}>
                {e.service_name}{e.barber_name ? ` com ${e.barber_name}` : ''}
                {e.after_time || e.before_time ? ` · ${e.after_time ? `das ${e.after_time.slice(0, 5)}` : ''}`
                  + `${e.before_time ? ` até ${e.before_time.slice(0, 5)}` : ''}` : ''}
                {' · '}{phoneLabel(e.customer_phone)}
              </Text>
              {e.status === 'offered' && e.offer_expires_at ? (
                <Text style={s.caption}>Reservado até {dtLabel(e.offer_expires_at).toLowerCase()}</Text>
              ) : null}
            </View>
            <Badge info={WAIT[e.status]} />
          </View>
          {['waiting', 'offered'].includes(e.status) ? (
            <Button title="Tirar da lista" kind="ghost" compact style={{ marginTop: SPACE(2), alignSelf: 'flex-start' }}
                    onPress={() => confirm('Tirar da lista de espera?', `${e.customer_name} não será mais avisado.`,
                      () => run(() => api.del(`/waitlist/${e.id}`).then(list.reload), 'Removido da lista.'), 'Tirar', true)} />
          ) : null}
        </Card>
      ))}
      <AddSheet visible={adding} onClose={() => setAdding(false)} day={day} onAdded={list.reload} />
    </Screen>
  );
}
