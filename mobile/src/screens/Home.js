import React, { useCallback, useState } from 'react';
import { Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../api';
import { Symbol as BrandSymbol } from '../brand/Logo';
import { AppointmentCard, QuickActions } from '../components/AppointmentCard';
import { toMin } from '../components/DayGrid';
import { dayLabel, hm, money, todayISO } from '../format';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Banner, Empty, IconButton, Loading, Screen, Section, Stat, useLoad } from '../ui';

const REFRESH_MS = 60000;

// Quantos horários cabem nos intervalos livres (pelo intervalo entre horários do negócio)
function freeSlots(agenda) {
  const step = agenda.slot_step_minutes || 30;
  return agenda.barbers.reduce((t, b) => t + b.free.reduce((u, f) => {
    const first = Math.ceil(toMin(f.start) / step) * step; // horários começam em múltiplos do intervalo
    return u + Math.max(0, Math.floor((toMin(f.end) - first) / step));
  }, 0), 0);
}

export function HomeScreen({ navigation }) {
  const { c, s, font, v } = useTheme();
  const insets = useSafeAreaInsets();
  const day = todayISO();
  const shop = useLoad(() => api.get('/me'), []);
  const agenda = useLoad(() => api.get('/agenda/day', { day }), [day]);
  const pix = useLoad(() => api.get('/payments', { status: 'pending' }), []);
  const approvals = useLoad(() => api.get('/approvals'), []);
  const [held, setHeld] = useState(null);

  const reloadAll = useCallback(() => { agenda.reload(); pix.reload(); approvals.reload(); }, []); // eslint-disable-line
  // Atualiza sozinho a cada 60 s enquanto a aba está aberta (sem o indicador de carregamento)
  useFocusEffect(useCallback(() => {
    const id = setInterval(() => {
      api.get('/agenda/day', { day }).then(agenda.setData).catch(() => {});
      api.get('/payments', { status: 'pending' }).then(pix.setData).catch(() => {});
      api.get('/approvals').then(approvals.setData).catch(() => {});
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, [day])); // eslint-disable-line react-hooks/exhaustive-deps

  const d = agenda.data;
  const appts = d ? d.barbers.flatMap((b) => b.appointments).sort((x, y) => x.start.localeCompare(y.start)) : [];
  const valid = appts.filter((a) => a.status !== 'no_show');
  const revenue = valid.reduce((t, a) => t + Number(a.price), 0);
  const now = d?.now || '';
  const upcoming = appts.filter((a) => a.end > now && ['scheduled', 'confirmed', 'pending_approval'].includes(a.status));
  const next = upcoming.find((a) => a.start >= now) || upcoming[0];
  const pixCount = pix.data?.length || 0;
  const apprCount = approvals.data?.length || 0;

  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <View style={[s.row, {
        paddingTop: insets.top + SPACE(3), paddingHorizontal: SPACE(4), paddingBottom: SPACE(3), gap: SPACE(3),
        backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider,
      }]}>
        <BrandSymbol size={36} color={c.accent} />
        <View style={{ flex: 1 }}>
          <Text style={{ fontFamily: font.extrabold, fontSize: 20, color: c.text }} numberOfLines={1}>
            {shop.data?.shop_name || ' '}
          </Text>
          <Text style={s.caption}>{dayLabel(day)}</Text>
        </View>
        <IconButton icon="add-circle" size={32} label="Novo agendamento" color={c.accentText}
                    onPress={() => navigation.navigate('NewAppointment', { day })} />
      </View>

      <Screen onRefresh={reloadAll} refreshing={agenda.loading && !!d}>
        {pixCount ? (
          <Banner tone="warning" icon="cash-outline"
                  title={pixCount === 1 ? '1 pagamento via Pix aguardando confirmação'
                    : `${pixCount} pagamentos via Pix aguardando confirmação`}
                  onPress={() => navigation.navigate('PixList')} />
        ) : null}
        {apprCount ? (
          <Banner tone="accent" icon="hourglass-outline"
                  title={apprCount === 1 ? '1 pedido aguardando aprovação' : `${apprCount} pedidos aguardando aprovação`}
                  onPress={() => navigation.navigate('Approvals')} />
        ) : null}

        {!d ? <Loading error={agenda.error} onRetry={agenda.reload} /> : (
          <>
            <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(3) }]}>
              <Stat icon="calendar-outline" label={v.Services} value={valid.length} />
              <Stat icon="trending-up-outline" label="Faturamento previsto" value={money(revenue)} />
            </View>
            <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(5) }]}>
              <Stat icon="person-outline" label={`Próximo ${v.customer}`}
                    value={next ? `${hm(next.start)} ${(next.customer_name || '').split(' ')[0]}` : '-'} />
              <Stat icon="time-outline" label="Horários livres" value={freeSlots(d)} />
            </View>

            <Section title={`Próximos ${v.services}`}>
              {!upcoming.length ? (
                <Empty text={appts.length ? `${v.allServices} de hoje já passaram.` : `${v.noService} hoje.`}
                       action={{ title: 'Agendar', icon: 'add', onPress: () => navigation.navigate('NewAppointment', { day }) }} />
              ) : upcoming.map((a) => (
                <AppointmentCard key={a.id} a={a} navigation={navigation} onChanged={reloadAll} onLongPress={setHeld} />
              ))}
            </Section>
          </>
        )}
      </Screen>
      <QuickActions a={held} visible={!!held} onClose={() => setHeld(null)} onChanged={reloadAll} navigation={navigation} />
    </View>
  );
}
