import React, { useState } from 'react';
import { Image, Pressable, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as Sharing from 'expo-sharing';
import { Ionicons } from '@expo/vector-icons';
import { api, apiUrl, authHeaders, download } from '../api';
import { confirmPix } from '../components/AppointmentCard';
import { ago, dtLabel, money, phoneLabel } from '../format';
import { PAY_LIST } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Badge, BottomSheet, Button, Card, confirm, Empty, Loading, Screen, SegmentedControl, run, useLoad } from '../ui';

// Comprovante mandado no WhatsApp: imagem (com o login no cabeçalho) ou PDF (baixa e abre)
function Receipt({ p }) {
  const { c, s } = useTheme();
  const [open, setOpen] = useState(false);
  if (!p.has_receipt) return null;
  const src = { uri: apiUrl(`/payments/${p.id}/receipt`), headers: authHeaders() };
  if (p.receipt_mime === 'application/pdf') {
    return (
      <Button title="Abrir comprovante (PDF)" kind="ghost" icon="document-text-outline" compact
              style={{ marginBottom: SPACE(3), alignSelf: 'flex-start' }}
              onPress={() => run(async () => {
                const uri = await download(`/payments/${p.id}/receipt`, null, `comprovante-${p.id}.pdf`);
                await Sharing.shareAsync(uri, { mimeType: 'application/pdf' });
              })} />
    );
  }
  return (
    <>
      <Pressable onPress={() => setOpen(true)} accessibilityRole="imagebutton" accessibilityLabel="Ver comprovante"
                 style={[s.row, { gap: SPACE(3), marginBottom: SPACE(3) }]}>
        <Image source={src} style={{ width: 64, height: 64, borderRadius: 8, backgroundColor: c.neutralBg }} />
        <View style={{ flex: 1 }}>
          <Text style={s.bodyBold}>Comprovante</Text>
          <Text style={s.caption}>Recebido {ago(p.receipt_at)} · toque para ampliar</Text>
        </View>
      </Pressable>
      <BottomSheet visible={open} onClose={() => setOpen(false)} title="Comprovante">
        <Image source={src} resizeMode="contain" style={{ width: '100%', height: 480, backgroundColor: c.neutralBg }} />
      </BottomSheet>
    </>
  );
}

export function PaymentsScreen({ navigation }) {
  const { c, s, font } = useTheme();
  const [status, setStatus] = useState('pending');
  const pays = useLoad(() => api.get('/payments', { status }), [status]);

  const reject = (p) => confirm('Recusar este Pix?',
    `O pagamento de ${money(p.amount)} vira expirado e ${p.customer_name || 'o cliente'} recebe uma mensagem neutra `
    + 'dizendo que o Pix não foi localizado. O horário continua marcado.',
    () => run(async () => { await api.post(`/payments/${p.id}/reject`); pays.reload(); }, 'Pix recusado. O cliente foi avisado.'),
    'Recusar', true);

  return (
    <Screen onRefresh={pays.reload} refreshing={pays.loading && !!pays.data}>
      <SegmentedControl value={status} onChange={setStatus} options={[
        { value: 'pending', label: 'Pendentes' }, { value: 'paid', label: 'Pagos' },
        { value: 'expired', label: 'Expirados' }, { value: '', label: 'Todos' },
      ]} />
      {!pays.data ? <Loading error={pays.error} onRetry={pays.reload} /> : null}
      {pays.data && !pays.data.length ? (
        <Empty icon="cash-outline" text={status === 'pending' ? 'Nenhum Pix aguardando confirmação.' : 'Nenhum pagamento aqui.'} />
      ) : null}
      {(pays.data || []).map((p) => {
        const reported = p.customer_reported_at && p.status === 'pending';
        return (
          <Card key={p.id} style={reported && { borderColor: c.status.warning, borderWidth: 2 }}>
            <View style={[s.row, { alignItems: 'flex-start', gap: SPACE(3) }]}>
              <View style={{ flex: 1 }}>
                <Text style={s.bodyBold} numberOfLines={1}>{p.customer_name || phoneLabel(p.customer_phone)}</Text>
                <Text style={s.muted}>{p.service_name}{p.barber_name ? ` · ${p.barber_name}` : ''}</Text>
                <Text style={s.muted}>{dtLabel(p.appointment_start)}</Text>
              </View>
              <Text style={{ fontFamily: font.extrabold, fontSize: 24, color: c.text }} maxFontSizeMultiplier={1.3}>
                {money(p.amount)}
              </Text>
            </View>
            <View style={[s.row, { gap: SPACE(1.5), marginVertical: SPACE(3), flexWrap: 'wrap' }]}>
              <Badge info={PAY_LIST[p.status]} />
              {reported ? <Badge info={{ label: `Cliente disse que pagou ${ago(p.customer_reported_at)}`, tone: 'warning', icon: 'chatbubble-ellipses-outline' }} /> : null}
              {p.status === 'pending' ? <Text style={s.caption}>Pendente {ago(p.created_at)}</Text> : null}
            </View>
            <Receipt p={p} />
            {p.status === 'pending' ? (
              <>
                <View style={[s.row, { gap: SPACE(2) }]}>
                  <Button title="Confirmar" icon="checkmark-circle" style={{ flex: 1 }}
                          onPress={() => confirmPix({ ...p, payment_id: p.id, price: p.amount }, pays.reload)} />
                  <Button title="Recusar" icon="close-circle-outline" kind="danger" style={{ flex: 1 }} onPress={() => reject(p)} />
                </View>
                <View style={[s.row, { gap: SPACE(2) }]}>
                  <Button title="Copiar código Pix" kind="ghost" icon="copy-outline" compact style={{ flex: 1 }}
                          onPress={() => run(() => Clipboard.setStringAsync(p.brcode), 'Código copiado.')} />
                  <Button title="Agendamento" kind="ghost" icon="calendar-outline" compact style={{ flex: 1 }}
                          onPress={() => navigation.navigate('Appointment', {
                            id: p.appointment_id, item: { id: p.appointment_id, start: p.appointment_start },
                          })} />
                </View>
              </>
            ) : null}
            {p.status === 'paid' && p.confirmed_at ? (
              <View style={[s.row, { gap: SPACE(1.5) }]}>
                <Ionicons name="checkmark-circle" size={16} color={c.statusText.success} />
                <Text style={s.caption}>Confirmado {dtLabel(p.confirmed_at).toLowerCase()}</Text>
              </View>
            ) : null}
          </Card>
        );
      })}
    </Screen>
  );
}
