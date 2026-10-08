import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { repo, saved } from '../repo';
import { dayLabel, gapLabel, hm, money, phoneLabel } from '../format';
import { ACCESS } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Badge, Banner, BottomSheet, Button, Chips, Field, ListRow } from '../ui';
import { confirmAccess, saveWithConflictCheck } from './booking';
import { toMin } from './DayGrid';

// Busca com atraso para não chamar a API a cada letra
export function useDebounced(value, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// Aviso discreto: clientes em conflito com este que já têm horário no dia
export function ConflictDayWarning({ hits }) {
  if (!hits || !hits.length) return null;
  return (
    <View>
      {hits.map((h) => (
        <Banner key={h.appointment_id} tone="danger" icon="warning-outline" title="Não agendar junto"
                text={`${h.other_customer_name} tem horário às ${hm(h.start)} (${h.barber_name}) · `
                  + `${h.same_day_block ? 'nunca no mesmo dia' : `mínimo ${gapLabel(h.gap_minutes)} de distância`}`
                  + `${h.conflict_action === 'approval' ? ' · pelo WhatsApp vira pedido para aprovar' : ''}`} />
      ))}
    </View>
  );
}

/**
 * Agendamento rápido ao tocar num horário vago da agenda: horário e profissional já preenchidos.
 * slot: { day, start (ISO), freeEnd (ISO do fim do espaço livre), barber: { id, name } }
 */
export function QuickBookSheet({ slot, onClose, onBooked, services, barbers }) {
  const { s, c, v } = useTheme();
  const [q, setQ] = useState('');
  const query = useDebounced(q);
  const [found, setFound] = useState([]);
  const [customer, setCustomer] = useState(null);
  const [isNew, setIsNew] = useState(false);
  const [phone, setPhone] = useState('');
  const [name, setName] = useState('');
  const [serviceId, setServiceId] = useState(null);
  const [hits, setHits] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { // novo horário: começa do zero
    setQ(''); setFound([]); setCustomer(null); setIsNew(false); setPhone(''); setName(''); setServiceId(null); setHits([]);
  }, [slot?.start, slot?.barber?.id]);
  useEffect(() => {
    if (!slot || customer || isNew || query.trim().length < 2) { setFound([]); return; }
    repo.customers({ q: query, limit: 8 }).then(setFound).catch(() => setFound([]));
  }, [query, customer, isNew, slot]);
  useEffect(() => {
    if (!slot || !customer || typeof customer.id !== 'number') { setHits([]); return; }
    api.get('/customer-conflicts/day', { day: slot.day, customer_id: customer.id }).then(setHits).catch(() => setHits([]));
  }, [customer, slot]);

  if (!slot) return <BottomSheet visible={false} onClose={onClose} />;
  const pro = (barbers || []).find((b) => b.id === slot.barber.id);
  const offered = (services || []).filter((x) => x.active && (!pro || !pro.service_ids.length || pro.service_ids.includes(x.id)));
  const svc = offered.find((x) => x.id === serviceId);
  const room = slot.freeEnd ? toMin(slot.freeEnd) - toMin(slot.start) : null;
  const tooLong = svc && room !== null && svc.duration_minutes > room;
  const phoneDigits = phone.replace(/\D/g, '');
  const ready = svc && !tooLong && (customer || (isNew && phoneDigits.length >= 10));

  const save = () => confirmAccess(customer, async () => {
    setBusy(true);
    const r = await saveWithConflictCheck((force) => repo.createAppointment({
      customer_id: customer ? customer.id : undefined,
      customer_phone: customer ? customer.phone : phone, customer_name: customer ? '' : name,
      service_id: svc.id, barber_id: slot.barber.id, start: slot.start, force,
    }), saved(`Agendado às ${hm(slot.start)}. O ${v.customer} recebeu a confirmação no WhatsApp.`,
      `Agendado às ${hm(slot.start)} no aparelho (a confirmar). O WhatsApp sai quando o servidor confirmar.`));
    setBusy(false);
    if (r) onBooked(r);
  });

  return (
    <BottomSheet visible={!!slot} onClose={onClose} title={`${hm(slot.start)} · ${slot.barber.name}`}
                 footer={<Button title="Agendar" icon="checkmark" onPress={save} loading={busy} disabled={!ready}
                                 style={{ marginBottom: 0 }} />}>
      <Text style={[s.muted, { marginBottom: SPACE(4) }]}>
        {dayLabel(slot.day)}{room !== null ? ` · livre até ${hm(slot.freeEnd)} (${gapLabel(room)})` : ''}
      </Text>

      <Text style={s.label}>{v.Customer}</Text>
      {customer ? (
        <View style={[s.row, { gap: SPACE(2), marginBottom: SPACE(4), flexWrap: 'wrap' }]}>
          <Text style={[s.bodyBold, { flexShrink: 1 }]}>{customer.name || phoneLabel(customer.phone)}</Text>
          <Badge info={ACCESS[customer.access_status]} />
          <Button title="Trocar" kind="ghost" compact onPress={() => setCustomer(null)} style={{ marginLeft: 'auto' }} />
        </View>
      ) : isNew ? (
        <>
          <Field label={`WhatsApp do ${v.customer}`} mask="phone" value={phone} onChangeText={setPhone} autoFocus />
          <Field label="Nome" value={name} onChangeText={setName} autoCapitalize="words" />
          <Button title={`Buscar ${v.customer} cadastrado`} kind="ghost" compact icon="search"
                  onPress={() => setIsNew(false)} style={{ marginBottom: SPACE(4) }} />
        </>
      ) : (
        <>
          <Field value={q} onChangeText={setQ} placeholder="Nome ou telefone" autoFocus returnKeyType="search"
                 prefix={<Ionicons name="search" size={18} color={c.textMuted} style={{ marginRight: 6 }} />} style={{ marginBottom: SPACE(2) }} />
          {found.slice(0, 6).map((x, i) => (
            <ListRow key={x.id} icon="person-circle-outline" title={x.name || 'Sem nome'} subtitle={phoneLabel(x.phone)}
                     first={i === 0} last={i === Math.min(found.length, 6) - 1}
                     right={ACCESS[x.access_status] ? <Badge info={ACCESS[x.access_status]} /> : <View />}
                     onPress={() => setCustomer(x)} />
          ))}
          <Button title={`Cadastrar novo ${v.customer}`} kind="secondary" compact icon="person-add-outline"
                  onPress={() => { setIsNew(true); if (/^\D*\d{10,}/.test(q)) setPhone(q); else setName(q); }}
                  style={{ marginTop: SPACE(2), marginBottom: SPACE(4) }} />
        </>
      )}
      <ConflictDayWarning hits={hits} />

      <Text style={s.label}>Serviço</Text>
      <Chips value={serviceId} onChange={setServiceId}
             options={offered.map((x) => ({ value: x.id, label: `${x.name} · ${x.duration_minutes} min · ${money(x.price)}` }))} />
      {tooLong ? (
        <Banner tone="danger" icon="alert-circle-outline" title="Não cabe neste espaço"
                text={`${svc.name} leva ${gapLabel(svc.duration_minutes)}, mas o espaço livre é de ${gapLabel(room)}.`} />
      ) : null}
    </BottomSheet>
  );
}
