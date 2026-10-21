import React, { useEffect, useState } from 'react';
import { Image, Pressable, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { api, apiUrl, authHeaders, download, saveFile } from '../api';
import { IS_WEB } from '../storage';
import { confirmPix } from '../components/AppointmentCard';
import { ReceiptReview } from '../components/ReceiptReview';
import { ago, dtLabel, money, phoneLabel } from '../format';
import { PAY_LIST } from '../status';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Badge, BottomSheet, Button, Card, confirm, Empty, Loading, Screen, SegmentedControl, run, useLoad } from '../ui';

// Comprovante antigo (guardado antes da leitura por IA): imagem (com o login no cabeçalho) ou PDF (baixa e abre)
function Receipt({ p }) {
  const { c, s } = useTheme();
  const [open, setOpen] = useState(false);
  // No navegador, <img> não manda o cabeçalho de login: baixa com o token e mostra pelo endereço blob:
  const [webUri, setWebUri] = useState(null);
  const isImage = p.has_receipt && p.receipt_mime !== 'application/pdf';
  useEffect(() => {
    if (!IS_WEB || !isImage) return undefined;
    let url = null;
    download(`/payments/${p.id}/receipt`, null, `comprovante-${p.id}`).then((u) => { url = u; setWebUri(u); })
      .catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [p.id, isImage]);
  if (!p.has_receipt) return null;
  const src = IS_WEB ? { uri: webUri || undefined } : { uri: apiUrl(`/payments/${p.id}/receipt`), headers: authHeaders() };
  if (p.receipt_mime === 'application/pdf') {
    return (
      <Button title="Abrir comprovante (PDF)" kind="ghost" icon="document-text-outline" compact
              style={{ marginBottom: SPACE(3), alignSelf: 'flex-start' }}
              onPress={() => run(() => saveFile(`/payments/${p.id}/receipt`, null, `comprovante-${p.id}.pdf`,
                                                'application/pdf'))} />
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

  // Com comprovante ainda sem decisão, confirmar e recusar passam por ele (fica registrado no histórico do cliente)
  const openReceipt = (p) => (p.receipt && !p.receipt.decision ? p.receipt : null);
  const reject = (p) => confirm('Recusar este Pix?',
    `O pagamento de ${money(p.amount)} vira expirado e ${p.customer_name || 'o cliente'} recebe uma mensagem neutra `
    + (openReceipt(p) ? 'pedindo para conferir o pagamento ou falar com vocês.' : 'dizendo que o Pix não foi localizado.')
    + ' O horário continua marcado.',
    () => run(async () => {
      const r = openReceipt(p);
      await api.post(r ? `/receipts/${r.id}/reject` : `/payments/${p.id}/reject`);
      pays.reload();
    }, 'Pix recusado. O cliente foi avisado.'),
    'Recusar', true);
  const accept = (p) => {
    const r = openReceipt(p);
    if (!r) return confirmPix({ ...p, payment_id: p.id, price: p.amount }, pays.reload);
    return confirm('Confirmar recebimento?',
      `Confira no extrato se o Pix de ${money(p.amount)} de ${p.customer_name || 'cliente'} caiu na conta. `
      + 'O comprovante sozinho não garante o pagamento.',
      () => run(async () => { await api.post(`/receipts/${r.id}/confirm`); pays.reload(); },
        'Pix confirmado. O cliente foi avisado.'),
      'Recebi');
  };

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
        const ok = p.status === 'pending' && p.receipt?.result === 'confere';
        return (
          <Card key={p.id} style={(ok || reported) && { borderColor: ok ? c.status.success : c.status.warning, borderWidth: 2 }}>
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
              {p.kind === 'deposit' ? <Badge info={{ label: 'Sinal', tone: 'info', icon: 'shield-checkmark-outline' }} /> : null}
              {reported && !p.receipt ? <Badge info={{ label: `Cliente disse que pagou ${ago(p.customer_reported_at)}`, tone: 'warning', icon: 'chatbubble-ellipses-outline' }} /> : null}
              {p.status === 'pending' ? <Text style={s.caption}>Pendente {ago(p.created_at)}</Text> : null}
            </View>
            {p.receipt ? <ReceiptReview receipt={p.receipt} paid={p.status === 'paid'} onChanged={pays.reload}
                                        onConfirm={p.status === 'pending' ? () => accept(p) : null}
                                        onReject={p.status === 'pending' ? () => reject(p) : null} />
              : <Receipt p={p} />}
            {p.status === 'pending' ? (
              <>
                <View style={[s.row, { gap: SPACE(2) }]}>
                  <Button title="Confirmar" icon="checkmark-circle" style={{ flex: 1 }} onPress={() => accept(p)} />
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
