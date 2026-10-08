// Modo offline na tela: aviso de conexão, pendências, "Sincronizar agora" e "Precisa da sua atenção".
import React, { useEffect, useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { dtLabel } from '../format';
import {
  attentionList, dismissAttention, onSyncStatus, pendingList, syncNow,
} from '../offline/manager';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Badge, Banner, Button, Card, Empty, Screen, Section, toast, useLoad } from '../ui';

export function useSyncStatus() {
  const [s, setS] = useState(null);
  useEffect(() => onSyncStatus(setS), []);
  return s || { available: false, online: true, pending: 0, attention: 0 };
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// Faixa no topo do app (celular): sem conexão, pendências e itens que precisam de atenção
export function SyncBanner({ onOpen }) {
  const { c, font } = useTheme();
  const st = useSyncStatus();
  if (Platform.OS === 'web') return null;
  let tone = null;
  let icon = 'cloud-offline-outline';
  let text = '';
  let target = 'Sync';
  if (st.attention) {
    tone = 'danger';
    icon = 'alert-circle-outline';
    text = `${plural(st.attention, 'item precisa', 'itens precisam')} da sua atenção`;
    target = 'Attention';
  } else if (!st.online && st.available) {
    tone = 'warning';
    text = 'Sem conexão: suas alterações serão sincronizadas'
      + (st.pending ? ` (${plural(st.pending, 'pendente', 'pendentes')})` : '');
  } else if (!st.online) {
    tone = 'warning';
    text = 'Sem conexão. Este aplicativo não tem o modo offline: alterações só com internet.';
  } else if (st.pending) {
    tone = 'info';
    icon = st.running ? 'sync-outline' : 'cloud-upload-outline';
    text = st.running ? `Enviando ${plural(st.pending, 'alteração', 'alterações')}...`
      : `${plural(st.pending, 'alteração aguardando', 'alterações aguardando')} envio`;
  }
  if (!tone) return null;
  const bg = { warning: c.status.warning, danger: c.status.danger, info: c.accentSoft }[tone];
  const fg = { warning: c.onWarning, danger: '#FFFFFF', info: c.accentText }[tone];
  return (
    <Pressable onPress={() => onOpen(target)} accessibilityRole="button" accessibilityHint="Abre os detalhes da sincronização"
               style={{ flexDirection: 'row', alignItems: 'center', gap: SPACE(2), paddingHorizontal: SPACE(4),
                        paddingVertical: SPACE(2.5), backgroundColor: bg }}>
      <Ionicons name={icon} size={20} color={fg} />
      <Text style={{ flex: 1, color: fg, fontFamily: font.bold, fontSize: 15 }}>{text}</Text>
      <Ionicons name="chevron-forward" size={18} color={fg} />
    </Pressable>
  );
}

// Selo de item salvo no aparelho e ainda não confirmado pelo servidor
export const PENDING = { label: 'A confirmar', tone: 'warning', icon: 'cloud-upload-outline' };
export function PendingBadge({ item }) {
  if (!item || !(item._pending || item._local)) return null;
  return <Badge info={PENDING} />;
}

const KIND = {
  horario_ocupado: 'Horário ocupado',
  cliente_em_conflito: 'Clientes que não podem se encontrar',
  status_alterado: 'Mudou no servidor',
  campo_alterado: 'Outra pessoa alterou o mesmo campo',
  sem_permissao: 'Sem permissão',
  nao_encontrado: 'Registro não existe mais',
  regra: 'Não foi aceito',
  dados_invalidos: 'Dados inválidos',
};

export function SyncScreen({ navigation }) {
  const { s, c } = useTheme();
  const st = useSyncStatus();
  const pending = useLoad(() => pendingList(), [st.pending]);
  const [busy, setBusy] = useState(false);
  const now = async () => {
    setBusy(true);
    const r = await syncNow('manual');
    setBusy(false);
    if (r.ok) toast('Sincronizado.');
    else toast(st.online ? 'Não foi possível falar com o servidor. Tentaremos de novo.' : 'Sem conexão agora.', 'error');
  };
  if (Platform.OS === 'web' || !st.available) {
    return (
      <Screen>
        <Banner tone="info" icon="cloud-outline" title="Modo offline desligado"
                text={st.reason === 'no-cipher'
                  ? 'Este aplicativo de teste (Expo Go) não tem o banco criptografado. Os dados não ficam no aparelho e as alterações precisam de internet. No aplicativo SyncServ instalado, o modo offline funciona.'
                  : 'Aqui os dados vêm direto do servidor e as alterações precisam de internet.'} />
      </Screen>
    );
  }
  return (
    <Screen onRefresh={now} refreshing={busy}>
      <Card>
        <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(3) }]}>
          <Ionicons name={st.online ? 'cloud-done-outline' : 'cloud-offline-outline'} size={28}
                    color={st.online ? c.status.success : c.status.warning} />
          <View style={{ flex: 1 }}>
            <Text style={s.bodyBold}>{st.online ? 'Com internet' : 'Sem conexão'}</Text>
            <Text style={s.caption}>
              {st.lastSync ? `Última sincronização ${dtLabel(st.lastSync).toLowerCase()}` : 'Ainda não sincronizou'}
            </Text>
          </View>
        </View>
        <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
          {st.pending ? plural(st.pending, 'alteração aguardando', 'alterações aguardando') + ' envio.'
            : 'Nada pendente: tudo o que foi feito aqui já está no servidor.'}
          {st.lastError === 'network' && st.online ? ' A última tentativa falhou; o app tenta de novo sozinho.' : ''}
        </Text>
        <Button title="Sincronizar agora" icon="sync-outline" onPress={now} loading={busy} disabled={!st.online}
                style={{ marginBottom: 0 }} />
      </Card>
      {st.attention ? (
        <Banner tone="danger" icon="alert-circle-outline"
                title={`${plural(st.attention, 'item precisa', 'itens precisam')} da sua atenção`}
                onPress={() => navigation.navigate('Attention')} />
      ) : null}
      {pending.data?.length ? (
        <Section title="Aguardando envio">
          {pending.data.map((o) => (
            <View key={o.operation_id} style={[s.row, { gap: SPACE(2), marginBottom: SPACE(2) }]}>
              <Ionicons name="cloud-upload-outline" size={18} color={c.textMuted} />
              <Text style={[s.body, { flex: 1 }]}>{o.label || o.entity}</Text>
              <Text style={s.caption}>{dtLabel(o.created_at)}</Text>
            </View>
          ))}
        </Section>
      ) : null}
      <Section title="Como funciona">
        <Text style={s.muted}>
          A agenda (30 dias para trás e 60 para frente), clientes, serviços, profissionais, produtos, pacotes,
          assinaturas e as comandas dos últimos 30 dias ficam neste aparelho, criptografados. Sem internet dá para
          agendar, remarcar, fazer check-in, lançar comanda, receber, mexer no estoque e na lista de espera: tudo
          sincroniza quando a conexão voltar. Agendamento feito offline aparece como "a confirmar" e o cliente só
          recebe o WhatsApp depois que o servidor aceitar. Ao sair da conta, os dados do aparelho são apagados.
        </Text>
      </Section>
    </Screen>
  );
}

export function AttentionScreen({ navigation }) {
  const { s } = useTheme();
  const list = useLoad(() => attentionList(), []);
  const dismiss = async (a) => { await dismissAttention(a.id); list.reload(); };
  const redo = (a) => {
    const d = a.op?.data || {};
    dismiss(a);
    navigation.navigate('NewAppointment', {
      day: String(d.start || '').slice(0, 10) || undefined,
      prefill: { phone: d.customer_phone || a.server?.customer_phone || '', name: d.customer_name || '',
                 customerUuid: d.customer_id || null, serviceUuid: d.service_id, barberUuid: d.barber_id,
                 notes: d.notes || '' },
    });
  };
  const items = list.data || [];
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
        Alterações feitas sem internet que o servidor não aceitou. Elas foram desfeitas no aparelho; decida o que fazer.
      </Text>
      {list.data && !items.length ? <Empty icon="checkmark-done-outline" text="Nada precisa da sua atenção." /> : null}
      {items.map((a) => (
        <Card key={a.id}>
          <Badge info={{ label: KIND[a.reason] || (a.kind === 'conflict' ? 'Conflito' : 'Não aceito'),
                         tone: 'danger', icon: 'alert-circle-outline' }} />
          <Text style={[s.bodyBold, { marginTop: SPACE(2) }]}>{a.label || a.entity}</Text>
          <Text style={[s.muted, { marginTop: SPACE(1) }]}>{a.message}</Text>
          {a.dropped ? (
            <Text style={[s.caption, { marginTop: SPACE(1) }]}>
              {plural(a.dropped, 'alteração que dependia disso também foi desfeita',
                'alterações que dependiam disso também foram desfeitas')}.
            </Text>
          ) : null}
          <Text style={[s.caption, { marginTop: SPACE(1) }]}>Feito {dtLabel(a.created_at).toLowerCase()}</Text>
          <View style={[s.row, { gap: SPACE(2), marginTop: SPACE(3), flexWrap: 'wrap' }]}>
            {a.entity === 'appointments' && a.action === 'create' ? (
              <Button title="Agendar em outro horário" icon="calendar-outline" compact onPress={() => redo(a)} />
            ) : null}
            <Button title="Dispensar" kind="ghost" compact onPress={() => dismiss(a)} />
          </View>
        </Card>
      ))}
    </Screen>
  );
}
