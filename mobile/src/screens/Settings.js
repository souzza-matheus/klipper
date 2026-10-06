import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Image, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { api } from '../api';
import { phoneLabel } from '../format';
import { colors } from '../theme';
import {
  Badge, Button, Card, Chips, Field, ListRow, Loading, Muted, Screen, Section, Title, Toggle, confirm, run, useLoad,
} from '../ui';

export function MoreScreen({ navigation, onLogout, shopName }) {
  const items = [
    ['Services', 'pricetags-outline', 'Serviços e preços'],
    ['Barbers', 'cut-outline', 'Barbeiros e expediente'],
    ['Blocks', 'lock-closed-outline', 'Bloqueios de agenda'],
    ['Reviews', 'star-outline', 'Avaliações'],
    ['Reports', 'bar-chart-outline', 'Relatórios'],
    ['Settings', 'settings-outline', 'Configurações do bot e Pix'],
    ['WhatsApp', 'logo-whatsapp', 'Conexão do WhatsApp'],
  ];
  return (
    <Screen>
      <Title>{shopName}</Title>
      <View style={{ borderRadius: 12, overflow: 'hidden', marginBottom: 20 }}>
        {items.map(([route, icon, title]) => (
          <ListRow key={route} icon={icon} title={title} onPress={() => navigation.navigate(route)} />
        ))}
      </View>
      <Button title="Sair" kind="ghost" icon="log-out-outline" onPress={() => confirm('Sair do app?', '', onLogout, 'Sair')} />
    </Screen>
  );
}

const NUM = [
  ['reminder_minutes_before', 'Lembrete antes do horário (min)'],
  ['cancel_min_hours', 'Cliente pode cancelar até (horas antes)'],
  ['survey_delay_minutes', 'Pesquisa após o fim do atendimento (min)'],
  ['slot_step_minutes', 'Intervalo entre horários (min)'],
  ['min_advance_minutes', 'Antecedência mínima para agendar (min)'],
  ['booking_days_ahead', 'Agenda aberta para os próximos (dias)'],
  ['pix_expire_hours', 'Pix pendente expira em (horas)'],
  ['daily_summary_hour', 'Hora do resumo diário (0-23)'],
  ['human_pause_hours', 'Pausa do bot ao pedir atendente (horas)'],
  ['approval_expire_hours', 'Pedido para aprovar expira em (horas)'],
  ['conflict_default_gap_minutes', 'Distância padrão entre clientes que não podem se encontrar (min)'],
];

export function SettingsScreen() {
  const shop = useLoad(() => api.get('/shop'), []);
  const [f, setF] = useState(null);
  useEffect(() => { if (shop.data && !f) setF({ ...shop.data, owner_phone: phoneLabel(shop.data.owner_phone) }); }, [shop.data]);
  if (!f) return <Loading error={shop.error} onRetry={shop.reload} />;
  const set = (k) => (v) => setF({ ...f, [k]: v });

  const save = () => run(async () => {
    const body = { ...f };
    delete body.id; delete body.evolution_instance;
    NUM.forEach(([k]) => { body[k] = Number(body[k]); });
    const r = await api.put('/shop', body);
    setF({ ...r, owner_phone: phoneLabel(r.owner_phone) });
  }, 'Configurações salvas. O bot já usa os novos dados.');

  return (
    <Screen>
      <Section title="Barbearia">
        <Field label="Nome" value={f.name} onChangeText={set('name')} />
        <Field label="Endereço" value={f.address} onChangeText={set('address')} multiline />
        <Field label="Telefone fixo" value={f.phone} onChangeText={set('phone')} keyboardType="phone-pad" />
        <Field label="Instagram" value={f.instagram} onChangeText={set('instagram')} autoCapitalize="none" />
        <Field label="WhatsApp pessoal do dono" value={f.owner_phone} onChangeText={set('owner_phone')} keyboardType="phone-pad"
               hint="Recebe todos os alertas e acessa o menu do dono no bot. Não use o número conectado ao bot." />
        <Field label="Mensagem de boas-vindas" value={f.welcome_text} onChangeText={set('welcome_text')} multiline
               placeholder="Ex.: Aceitamos Pix e cartão. Estacionamento em frente." />
      </Section>

      <Section title="Pix antecipado">
        <Toggle label="Oferecer pagamento via Pix no bot" value={f.pix_enabled} onValueChange={set('pix_enabled')}
                hint="O dinheiro cai direto na sua conta. Você confirma o recebimento no app ou no WhatsApp." />
        {f.pix_enabled ? (
          <>
            <Muted style={{ marginBottom: 6 }}>Tipo da chave</Muted>
            <Chips value={f.pix_key_type} onChange={set('pix_key_type')} options={[
              { value: 'cpf', label: 'CPF' }, { value: 'cnpj', label: 'CNPJ' }, { value: 'email', label: 'E-mail' },
              { value: 'phone', label: 'Celular' }, { value: 'random', label: 'Aleatória' },
            ]} />
            <Field label="Chave Pix" value={f.pix_key} onChangeText={set('pix_key')} autoCapitalize="none" />
            <Field label="Nome do recebedor (até 25 letras)" value={f.pix_receiver_name} onChangeText={set('pix_receiver_name')} maxLength={25} />
            <Field label="Cidade (até 15 letras)" value={f.pix_city} onChangeText={set('pix_city')} maxLength={15} />
          </>
        ) : null}
      </Section>

      <Section title="Regras do bot">
        <Toggle label="Enviar pesquisa de satisfação" value={f.survey_enabled} onValueChange={set('survey_enabled')} />
        {NUM.map(([k, label]) => (
          <Field key={k} label={label} value={String(f[k])} onChangeText={set(k)} keyboardType="number-pad" />
        ))}
      </Section>
      <Button title="Salvar configurações" onPress={save} />
    </Screen>
  );
}

const STATE_INFO = {
  open: { label: 'Conectado', fg: colors.good, bg: colors.goodBg },
  connecting: { label: 'Aguardando conexão', fg: colors.warn, bg: colors.warnBg },
  close: { label: 'Desconectado', fg: colors.bad, bg: colors.badBg },
  nao_criada: { label: 'Ainda não conectado', fg: colors.bad, bg: colors.badBg },
  simulacao: { label: 'Modo simulação (sem WhatsApp)', fg: colors.muted, bg: '#EEECE8' },
  erro: { label: 'Erro ao consultar', fg: colors.bad, bg: colors.badBg },
};

const QR_SECONDS = 40; // o WhatsApp troca o QR Code a cada ~20-40 s
const POLL_MS = 3000;

// O backend manda com o prefixo data:image/png;base64, mas aceita também só o base64
export function qrUri(raw) {
  if (!raw) return null;
  return raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
}

// "WZYEH1YY" -> "WZYE-H1YY", como o WhatsApp mostra
const formatCode = (c) => (c && c.length === 8 ? `${c.slice(0, 4)}-${c.slice(4)}` : c);

export function WhatsAppScreen() {
  const st = useLoad(() => api.get('/whatsapp/status'), []);
  const [mode, setMode] = useState('qr');
  const [qr, setQr] = useState(null);
  const [code, setCode] = useState(null);
  const [number, setNumber] = useState('');
  const [busy, setBusy] = useState('');
  const [left, setLeft] = useState(0);
  const waiting = !!(qr || code);

  // Ao sair da tela o QR Code/código some e a consulta de status para
  useFocusEffect(useCallback(() => () => { setQr(null); setCode(null); }, []));

  // Enquanto o QR Code ou o código está na tela, consulta o status até conectar
  useEffect(() => {
    if (!waiting) return undefined;
    const id = setInterval(async () => {
      try {
        const r = await api.get('/whatsapp/status');
        st.setData(r);
        if (r.state === 'open') {
          setQr(null);
          setCode(null);
        }
      } catch (e) {
        // falha passageira de rede: a próxima consulta tenta de novo
      }
    }, POLL_MS);
    return () => clearInterval(id);
  }, [waiting]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!qr || left <= 0) return undefined;
    const id = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(id);
  }, [qr, left]);

  const show = (r, field) => {
    if (!r) return; // erro (ex.: 502 da Evolution) já foi mostrado pelo run
    st.setData((d) => ({ ...d, state: r.state }));
    if (field === 'qrcode' && r.qrcode) {
      setCode(null);
      setQr(qrUri(r.qrcode));
      setLeft(QR_SECONDS);
      return;
    }
    if (field === 'pairing_code' && r.pairing_code) {
      setQr(null);
      setCode(r.pairing_code);
      return;
    }
    setQr(null);
    setCode(null);
    Alert.alert(r.state === 'open' ? 'Já conectado' : 'Não foi possível gerar',
      r.message || 'O servidor não devolveu o QR Code. Tente de novo em alguns segundos.');
  };

  const connect = async () => {
    setBusy('qr');
    const r = await run(() => api.post('/whatsapp/connect'));
    setBusy('');
    show(r, 'qrcode');
  };
  const requestCode = async () => {
    if (number.replace(/\D/g, '').length < 10) {
      Alert.alert('Número do bot', 'Digite o número do WhatsApp da barbearia com DDD, ex.: (31) 99999-8888.');
      return;
    }
    setBusy('code');
    const r = await run(() => api.post('/whatsapp/pairing-code', { number }));
    setBusy('');
    show(r, 'pairing_code');
  };
  const disconnect = () => confirm('Desconectar WhatsApp',
    'O bot para de responder os clientes até você conectar de novo. Desconectar?', async () => {
      setBusy('disconnect');
      const r = await run(() => api.post('/whatsapp/disconnect'));
      setBusy('');
      if (r) st.setData((d) => ({ ...d, state: r.state }));
      st.reload();
    }, 'Desconectar', true);

  const state = st.data?.state;
  const info = STATE_INFO[state] || { label: state || '...', fg: colors.muted, bg: '#EEECE8' };
  if (!st.data && st.error) return <Loading error={st.error} onRetry={st.reload} />;

  return (
    <Screen onRefresh={st.reload} refreshing={st.loading && !!st.data}>
      <Card>
        <Muted style={{ marginBottom: 6 }}>Status</Muted>
        <Badge info={info} />
        {st.data ? <Muted style={{ marginTop: 8 }}>Instância: {st.data.instance}</Muted> : null}
      </Card>

      {state === 'open' ? (
        <>
          <Muted style={{ marginVertical: 10 }}>O bot está respondendo os clientes por este WhatsApp.</Muted>
          <Button title={busy === 'disconnect' ? 'Desconectando...' : 'Desconectar WhatsApp'} icon="log-out-outline"
                  kind="danger" onPress={disconnect} disabled={!!busy} />
        </>
      ) : (
        <>
          <View style={{ marginTop: 10 }}>
            <Chips options={[{ value: 'qr', label: 'Ler QR Code' }, { value: 'code', label: 'Conectar com código' }]}
                   value={mode} onChange={(m) => { setMode(m); setQr(null); setCode(null); }} />
          </View>
          {mode === 'qr' ? (
            <>
              <Muted style={{ marginVertical: 10 }}>
                No celular da barbearia, abra o WhatsApp &gt; Aparelhos conectados &gt; Conectar aparelho e leia o QR Code.
              </Muted>
              {!qr ? (
                <Button title={busy === 'qr' ? 'Gerando QR Code...' : 'Gerar QR Code'} icon="qr-code-outline"
                        onPress={connect} disabled={!!busy} />
              ) : null}
            </>
          ) : (
            <>
              <Muted style={{ marginVertical: 10 }}>
                Use quando não houver outro aparelho para ler o QR Code: você digita um código no próprio celular da barbearia.
              </Muted>
              <Field label="Número do WhatsApp do bot" value={number} onChangeText={setNumber} keyboardType="phone-pad"
                     placeholder="(31) 99999-8888" />
              <Button title={busy === 'code' ? 'Gerando código...' : code ? 'Gerar novo código' : 'Gerar código'}
                      icon="keypad-outline" onPress={requestCode} disabled={!!busy} />
            </>
          )}
          {busy === 'qr' || busy === 'code' ? (
            <Card style={{ alignItems: 'center', marginTop: 12 }}>
              <ActivityIndicator color={colors.primary} />
              <Muted style={{ marginTop: 8 }}>Pedindo para a Evolution API, pode levar alguns segundos...</Muted>
            </Card>
          ) : null}
        </>
      )}

      {qr ? (
        <Card style={{ alignItems: 'center', marginTop: 12 }}>
          {left > 0 ? (
            <>
              <Image source={{ uri: qr }} style={{ width: 260, height: 260 }} resizeMode="contain" />
              <Muted style={{ marginTop: 8 }}>Expira em {left} s. Aguardando a leitura...</Muted>
            </>
          ) : (
            <>
              <Muted style={{ marginBottom: 10 }}>O QR Code venceu.</Muted>
              <Button title={busy === 'qr' ? 'Gerando QR Code...' : 'Gerar novo QR Code'} icon="refresh-outline"
                      onPress={connect} disabled={!!busy} />
            </>
          )}
        </Card>
      ) : null}

      {code ? (
        <Card style={{ alignItems: 'center', marginTop: 12 }}>
          <Muted>Código de pareamento</Muted>
          <Text selectable style={{ fontSize: 34, fontWeight: '700', letterSpacing: 4, color: colors.ink, marginVertical: 10 }}>
            {formatCode(code)}
          </Text>
          <Muted style={{ alignSelf: 'stretch' }}>
            No celular da barbearia: WhatsApp &gt; Aparelhos conectados &gt; Conectar aparelho &gt; Conectar com número de
            telefone, e digite o código acima. Aguardando a conexão...
          </Muted>
        </Card>
      ) : null}
    </Screen>
  );
}
