import React, { useEffect, useState } from 'react';
import { Image, View } from 'react-native';
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
    ['Commissions', 'wallet-outline', 'Comissões e repasses'],
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
  connecting: { label: 'Aguardando leitura do QR Code', fg: colors.warn, bg: colors.warnBg },
  close: { label: 'Desconectado', fg: colors.bad, bg: colors.badBg },
  nao_criada: { label: 'Ainda não conectado', fg: colors.bad, bg: colors.badBg },
  simulacao: { label: 'Modo simulação (sem WhatsApp)', fg: colors.muted, bg: '#EEECE8' },
  erro: { label: 'Erro ao consultar', fg: colors.bad, bg: colors.badBg },
};

export function WhatsAppScreen() {
  const st = useLoad(() => api.get('/whatsapp/status'), []);
  const [qr, setQr] = useState(null);
  const [busy, setBusy] = useState(false);

  const connect = async () => {
    setBusy(true);
    const r = await run(() => api.post('/whatsapp/connect'));
    setBusy(false);
    if (r) {
      setQr(r.qrcode);
      if (r.message) setQr(null);
      st.reload();
    }
  };
  const state = st.data?.state;
  const info = STATE_INFO[state] || { label: state || '...', fg: colors.muted, bg: '#EEECE8' };

  return (
    <Screen onRefresh={st.reload} refreshing={st.loading && !!st.data}>
      <Card>
        <Muted style={{ marginBottom: 6 }}>Status</Muted>
        <Badge info={info} />
        {st.data ? <Muted style={{ marginTop: 8 }}>Instância: {st.data.instance}</Muted> : null}
      </Card>
      {state !== 'open' ? (
        <>
          <Muted style={{ marginVertical: 10 }}>
            No celular da barbearia, abra o WhatsApp &gt; Aparelhos conectados &gt; Conectar aparelho e leia o QR Code abaixo.
          </Muted>
          <Button title={busy ? 'Gerando...' : 'Gerar QR Code'} icon="qr-code-outline" onPress={connect} disabled={busy} />
        </>
      ) : null}
      {qr ? (
        <Card style={{ alignItems: 'center' }}>
          <Image source={{ uri: qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}` }} style={{ width: 260, height: 260 }} />
          <Muted style={{ marginTop: 8 }}>O QR Code expira em cerca de 1 minuto. Gere outro se precisar.</Muted>
          <Button title="Já li, atualizar status" kind="ghost" onPress={() => { setQr(null); st.reload(); }} style={{ marginTop: 10 }} />
        </Card>
      ) : null}
    </Screen>
  );
}
