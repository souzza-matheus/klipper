import React, { useState } from 'react';
import { Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { api } from '../api';
import { dtLabel, money } from '../format';
import { colors, PAY } from '../theme';
import { Badge, Button, Card, Chips, confirm, Empty, Loading, Muted, Screen, s, run, useLoad } from '../ui';

export function PaymentsScreen() {
  const [status, setStatus] = useState('pending');
  const pays = useLoad(() => api.get('/payments', { status }), [status]);

  const doConfirm = (p) => confirm('Confirmar recebimento?',
    `Confira no extrato se o Pix de ${money(p.amount)} de ${p.customer_name} caiu na conta.`,
    () => run(async () => { await api.post(`/payments/${p.id}/confirm`); pays.reload(); }, 'Pagamento confirmado. O cliente foi avisado.'),
    'Recebi');

  return (
    <Screen onRefresh={pays.reload} refreshing={pays.loading && !!pays.data}>
      <Chips value={status} onChange={setStatus} options={[
        { value: 'pending', label: 'Pendentes' }, { value: 'paid', label: 'Pagos' },
        { value: 'expired', label: 'Expirados' }, { value: '', label: 'Todos' },
      ]} />
      {!pays.data ? <Loading error={pays.error} onRetry={pays.reload} /> : null}
      {pays.data && !pays.data.length ? <Empty text="Nenhum pagamento aqui." /> : null}
      {(pays.data || []).map((p) => (
        <Card key={p.id}>
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.body}>{p.customer_name}</Text>
              <Muted>Horário: {dtLabel(p.appointment_start)}</Muted>
            </View>
            <Text style={{ fontSize: 18, fontWeight: '800', color: colors.ink }}>{money(p.amount)}</Text>
          </View>
          <View style={[s.row, { gap: 8, marginVertical: 8 }]}>
            <Badge info={PAY[p.status]} />
            {p.customer_reported_at && p.status === 'pending' ? (
              <Badge info={{ label: '💸 Cliente disse que pagou', fg: colors.warn, bg: colors.warnBg }} />
            ) : null}
          </View>
          {p.status === 'pending' ? (
            <>
              <Button title="Confirmar recebimento" icon="checkmark-circle-outline" onPress={() => doConfirm(p)} />
              <Button title="Copiar código Pix" kind="ghost" icon="copy-outline"
                      onPress={() => run(() => Clipboard.setStringAsync(p.brcode), 'Código copiado.')} />
            </>
          ) : null}
        </Card>
      ))}
    </Screen>
  );
}
