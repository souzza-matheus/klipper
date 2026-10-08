import React, { useState } from 'react';
import { Linking, Text, View } from 'react-native';
import { api } from '../api';
import { repo, saved } from '../repo';
import { PendingBadge } from './Sync';
import { hm, money, PAY_METHODS, payMethodLabel, phoneLabel } from '../format';
import { ACCESS, PAY, STATUS } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { useSession } from '../session';
import { Badge, BottomSheet, Button, Card, Chips, confirm, run } from '../ui';

export function confirmPix(a, onDone) {
  confirm('Confirmar recebimento?',
    `Confira no extrato se o Pix de ${money(a.deposit_status === 'pending' ? a.deposit_amount : (a.price ?? a.amount))} `
    + `de ${a.customer_name || 'cliente'} caiu na conta.`,
    () => run(async () => {
      await api.post(`/payments/${a.payment_id ?? a.id}/confirm`);
      onDone && onDone();
    }, 'Pix confirmado. O cliente foi avisado.'),
    'Recebi');
}

// Ações rápidas ao segurar o card: confirmar presença, concluir, faltou, WhatsApp
export function QuickActions({ a, visible, onClose, onChanged, navigation }) {
  const { s, v } = useTheme();
  const { can } = useSession();
  const [method, setMethod] = useState(null);
  const [completing, setCompleting] = useState(false);
  if (!a) return null;
  const close = () => { setCompleting(false); setMethod(null); onClose(); };
  const act = (body, msg) => run(async () => {
    const r = await repo.updateAppointment(a, body);
    close();
    onChanged && onChanged();
    return r;
  }, saved(msg));
  const active = a.status === 'scheduled' || a.status === 'confirmed';
  return (
    <BottomSheet visible={visible} onClose={close} title={`${hm(a.start)} · ${a.customer_name || phoneLabel(a.customer_phone)}`}>
      <Text style={[s.muted, { marginBottom: SPACE(4) }]}>{a.service_name} com {a.barber_name} · {money(a.price)}</Text>
      {completing ? (
        <>
          <Text style={s.label}>Forma de pagamento</Text>
          <Chips value={method} onChange={setMethod} options={PAY_METHODS} />
          <Button title={`Concluir ${v.service}`} icon="checkmark-done" disabled={!method}
                  onPress={() => act({ status: 'completed', payment_method: method }, `${v.Service} ${v.done}.`)} />
          <Button title="Voltar" kind="ghost" onPress={() => setCompleting(false)} />
        </>
      ) : (
        <>
          {a.status === 'scheduled' ? (
            <Button title="Confirmar presença" icon="checkmark" kind="secondary"
                    onPress={() => act({ status: 'confirmed' }, 'Presença confirmada.')} />
          ) : null}
          {active && can('comandas') ? (
            <Button title="Abrir comanda" icon="receipt-outline"
                    onPress={() => run(async () => {
                      const r = await repo.openComanda({ appointment_id: a.id });
                      close();
                      navigation.navigate('Comanda', { id: r.id });
                    })} />
          ) : null}
          {active && !a.checked_in_at ? (
            <Button title="Cliente chegou" icon="enter-outline" kind="secondary"
                    onPress={() => run(async () => {
                      const r = await repo.checkIn(a);
                      close();
                      onChanged && onChanged();
                      return r;
                    }, saved('Check-in feito.'))} />
          ) : null}
          {active && can('changePrice') ? (
            <Button title="Concluir sem comanda" icon="checkmark-done" kind="ghost"
                    onPress={() => { setMethod(a.payment_method || (a.payment_status === 'paid' ? 'pix' : null)); setCompleting(true); }} />
          ) : null}
          {active && !can('changePrice') ? (
            <Button title={`Marcar como ${v.done}`} icon="checkmark-done" kind="ghost"
                    onPress={() => act({ status: 'completed' }, `${v.Service} ${v.done}.`)} />
          ) : null}
          {active ? (
            <Button title={`${v.Customer} faltou`} icon="close-circle-outline" kind="danger"
                    onPress={() => act({ status: 'no_show' }, 'Falta registrada.')} />
          ) : null}
          <Button title="Abrir WhatsApp" icon="logo-whatsapp" kind="ghost"
                  onPress={() => { close(); Linking.openURL(`https://wa.me/${a.customer_phone}`); }} />
          <Button title="Ver detalhes" icon="open-outline" kind="ghost"
                  onPress={() => { close(); navigation.navigate('Appointment', { id: a.id, item: a }); }} />
        </>
      )}
    </BottomSheet>
  );
}

// Card de agendamento: horário grande, nome em destaque, serviço, profissional, valor e status
export function AppointmentCard({ a, navigation, onChanged, onLongPress }) {
  const { c, s, font } = useTheme();
  const cancelled = a.status === 'cancelled';
  const pixPending = a.payment_status === 'pending' && a.payment_id && !cancelled;
  const name = a.customer_name || phoneLabel(a.customer_phone);
  return (
    <Card onPress={() => navigation.navigate('Appointment', { id: a.id, item: a })}
          onLongPress={onLongPress ? () => onLongPress(a) : undefined}
          accessibilityLabel={`${hm(a.start)}, ${name}, ${a.service_name} com ${a.barber_name}, ${money(a.price)}, ${STATUS[a.status]?.label || ''}`}
          style={[cancelled && { opacity: 0.55 },
                  a.status === 'pending_approval' && { borderLeftWidth: 4, borderLeftColor: c.accent }]}>
      <View style={[s.row, { alignItems: 'flex-start', gap: SPACE(3) }]}>
        <View style={{ minWidth: 68 }}>
          <Text style={{ fontFamily: font.extrabold, fontSize: 24, color: c.text }} maxFontSizeMultiplier={1.3}>
            {hm(a.start)}
          </Text>
          <Text style={s.caption} maxFontSizeMultiplier={1.3}>até {hm(a.end)}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Text style={[s.bodyBold, { flex: 1 }]} numberOfLines={1}>{name}</Text>
            <Text style={[s.bodyBold, { color: c.text }]}>{money(a.price)}</Text>
          </View>
          <Text style={[s.muted, { marginTop: 2 }]} numberOfLines={2}>{a.service_name} · {a.barber_name}</Text>
          <View style={[s.row, { gap: SPACE(1.5), marginTop: SPACE(2), flexWrap: 'wrap' }]}>
            <Badge info={STATUS[a.status]} />
            <Badge info={a.customer_reported_paid && a.payment_status === 'pending'
              ? { label: 'Disse que pagou', tone: 'warning', icon: 'chatbubble-ellipses-outline' } : PAY[a.payment_status]} />
            {!cancelled ? <Badge info={ACCESS[a.customer_access_status]} /> : null}
            {a.status === 'completed' && a.payment_method ? <Badge info={{ label: payMethodLabel(a.payment_method), tone: 'neutral' }} /> : null}
            <PendingBadge item={a} />
            {a.created_via === 'bot' && a.status !== 'completed' ? (
              <Badge info={{ label: 'WhatsApp', tone: 'neutral', icon: 'logo-whatsapp' }} />
            ) : null}
          </View>
        </View>
      </View>
      {pixPending ? (
        <Button title="Confirmar Pix" icon="checkmark-circle-outline" kind="secondary" compact
                onPress={() => confirmPix(a, onChanged)} style={{ marginTop: SPACE(3) }} />
      ) : null}
    </Card>
  );
}
