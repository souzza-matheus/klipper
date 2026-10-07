import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Image, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import * as Clipboard from 'expo-clipboard';
import Constants from 'expo-constants';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { LogoVertical, Symbol as BrandSymbol } from '../brand/Logo';
import { phoneLabel } from '../format';
import { buildTheme, NICHE_INFO, NICHES, SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, Button, Card, Chips, confirm, Field, Group, ListRow, Loading, Screen, Section, SegmentedControl,
  Toggle, run, toast, useLoad,
} from '../ui';

export function MoreScreen({ navigation, onLogout, shopName }) {
  const { c, s, font, v } = useTheme();
  const items = [
    ['Services', 'pricetags-outline', 'Serviços e preços'],
    ['Barbers', 'people-outline', `${v.Pros} e expediente`],
    ['Blocks', 'lock-closed-outline', 'Bloqueios de agenda'],
    ['Reviews', 'star-outline', 'Avaliações'],
    ['Reports', 'bar-chart-outline', 'Relatórios'],
    ['Settings', 'settings-outline', 'Configurações e aparência'],
    ['WhatsApp', 'logo-whatsapp', 'Conexão do WhatsApp'],
    ['About', 'information-circle-outline', 'Sobre o SyncServ'],
  ];
  return (
    <Screen>
      <View style={[s.row, { gap: SPACE(3), marginBottom: SPACE(5) }]}>
        <BrandSymbol size={40} color={c.accent} />
        <Text style={{ fontFamily: font.extrabold, fontSize: 24, color: c.text, flex: 1 }} numberOfLines={2}>{shopName}</Text>
      </View>
      <Group>
        {items.map(([route, icon, title], i) => (
          <ListRow key={route} icon={icon} title={title} first={i === 0} last={i === items.length - 1}
                   onPress={() => navigation.navigate(route)} />
        ))}
      </Group>
      <Button title="Sair" kind="ghost" icon="log-out-outline" onPress={() => confirm('Sair do app?', '', onLogout, 'Sair', true)} />
    </Screen>
  );
}

export function AboutScreen() {
  const { c, s, mode } = useTheme();
  return (
    <Screen style={{ alignItems: 'center' }}>
      <View style={{ marginTop: SPACE(8), marginBottom: SPACE(6) }}>
        <LogoVertical width={160} variant={mode === 'light' ? 'light' : 'dark'} />
      </View>
      <Text style={[s.body, { textAlign: 'center', marginBottom: SPACE(2) }]}>
        Agendamento pelo WhatsApp para barbearias, salões, pet shops, clínicas e estúdios.
      </Text>
      <Text style={[s.muted, { textAlign: 'center' }]}>Versão {Constants.expoConfig?.version || '1.0.0'}</Text>
      <View style={{ marginTop: SPACE(10), opacity: 0.9 }}>
        <BrandSymbol size={28} color={c.textMuted} />
      </View>
    </Screen>
  );
}

// ---------------------------------------------------------------- configurações

const NUM = [
  ['reminder_minutes_before', 'Lembrete antes do horário (min)'],
  ['cancel_min_hours', 'Pode cancelar até (horas antes)'],
  ['survey_delay_minutes', 'Pesquisa após o fim do atendimento (min)'],
  ['slot_step_minutes', 'Intervalo entre horários (min)'],
  ['min_advance_minutes', 'Antecedência mínima para agendar (min)'],
  ['booking_days_ahead', 'Agenda aberta para os próximos (dias)'],
  ['pix_expire_hours', 'Pix pendente expira em (horas)'],
  ['daily_summary_hour', 'Hora do resumo diário (0-23)'],
  ['human_pause_hours', 'Pausa do bot ao pedir atendente (horas)'],
  ['approval_expire_hours', 'Pedido para aprovar expira em (horas)'],
  ['conflict_default_gap_minutes', 'Distância padrão entre clientes incompatíveis (min)'],
];

const MODE_LABEL = { dark: 'Escuro', light: 'Claro' };

// Cartão de um segmento com o símbolo na cor dele, sobre o fundo do próprio tema
function NicheCard({ niche, themeMode, selected, onPress }) {
  const { c, font } = useTheme();
  const t = buildTheme(niche, themeMode);
  const info = NICHE_INFO[niche];
  return (
    <Pressable onPress={onPress} accessibilityRole="radio" accessibilityState={{ checked: selected }}
               accessibilityLabel={`${info.label}, tema ${MODE_LABEL[t.mode].toLowerCase()}`}
               style={({ pressed }) => ({
                 width: '48%', minHeight: 112, borderRadius: 14, padding: SPACE(3), backgroundColor: t.c.background,
                 borderWidth: selected ? 3 : 1, borderColor: selected ? c.accentText : c.border, opacity: pressed ? 0.85 : 1,
               })}>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <BrandSymbol size={36} color={t.c.accent} />
        {selected ? <Ionicons name="checkmark-circle" size={24} color={c.accentText} /> : null}
      </View>
      <Text style={{ fontFamily: font.bold, fontSize: 15, color: t.c.text, marginTop: SPACE(2) }} numberOfLines={2}>
        {info.label}
      </Text>
      <Text style={{ fontFamily: font.medium, fontSize: 13, color: t.c.textMuted }}>{MODE_LABEL[t.mode]}</Text>
    </Pressable>
  );
}

// Segmento e modo: salva na hora e o app troca de tema imediatamente
function AppearanceSection({ onSaved }) {
  const { niche, themeMode, setAppearance, s } = useTheme();
  const apply = (body) => run(async () => {
    const r = await api.put('/shop', body);
    setAppearance(r.niche, r.theme_mode, r.name);
    onSaved(r);
  }, 'Aparência atualizada.');
  return (
    <Section title="Aparência">
      <Text style={[s.muted, { marginBottom: SPACE(3) }]}>Segmento do negócio: muda as cores, os ícones e os termos do app.</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: SPACE(3), marginBottom: SPACE(4) }}>
        {NICHES.map((n) => (
          <NicheCard key={n} niche={n} themeMode={themeMode} selected={n === niche}
                     onPress={() => n !== niche && apply({ niche: n })} />
        ))}
      </View>
      <Text style={s.label}>Modo</Text>
      <SegmentedControl value={themeMode} onChange={(m) => m !== themeMode && apply({ theme_mode: m })} options={[
        { value: 'auto', label: 'Automático', icon: 'sparkles-outline' },
        { value: 'dark', label: 'Escuro', icon: 'moon-outline' },
        { value: 'light', label: 'Claro', icon: 'sunny-outline' },
      ]} />
      <Text style={s.caption}>Automático usa o modo do segmento ({MODE_LABEL[NICHE_INFO[niche]?.mode || 'dark'].toLowerCase()}).</Text>
    </Section>
  );
}

// Atendimento com IA no WhatsApp: ligar/desligar, transcrição de áudio e uso do mês
function AISection() {
  const { c, s, font, v } = useTheme();
  const st = useLoad(() => api.get('/ai/settings'), []);
  const d = st.data;
  if (!d) return st.error ? null : <Loading rows={1} />;
  const put = (body) => run(async () => { st.setData(await api.put('/ai/settings', body)); },
    body.ai_enabled === false ? 'IA desligada. O bot responde com o menu.' : 'Atendimento com IA atualizado.');
  const used = d.calls_this_month;
  const pct = Math.min(1, used / Math.max(1, d.monthly_limit));
  return (
    <Section title="Atendimento com IA">
      {d.test_mode_warning ? <Banner tone="warning" icon="flask-outline" title={d.test_mode_warning} /> : null}
      <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
        O {v.customer} escreve do jeito dele ("quero cortar amanhã depois das 17h") e o robô entende, consulta a agenda e
        responde. O menu numerado continua funcionando, e o agendamento só é gravado quando o {v.customer} confirma.
      </Text>
      <Card>
        <Toggle label="Atender com IA" value={d.ai_enabled} onValueChange={(on) => put({ ai_enabled: on })}
                disabled={!d.configured || !d.free_tier_allowed}
                hint={!d.configured ? 'A IA ainda não foi configurada no servidor.'
                  : !d.free_tier_allowed ? 'Indisponível para este negócio enquanto o servidor estiver em modo de teste.' : undefined} />
        <Toggle label="Entender mensagens de áudio" value={d.ai_audio_enabled}
                onValueChange={(on) => put({ ai_audio_enabled: on })} disabled={!d.ai_enabled}
                hint="Transcreve áudios de até 2 minutos e responde como se fosse texto." />
        <Text style={s.label}>Uso neste mês</Text>
        <Text style={{ fontFamily: font.bold, fontSize: 17, color: c.text }}>
          {used.toLocaleString('pt-BR')} de {d.monthly_limit.toLocaleString('pt-BR')} respostas da IA
        </Text>
        <View style={{ height: 8, borderRadius: 4, backgroundColor: c.neutralBg, marginTop: SPACE(2) }}
              accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: d.monthly_limit, now: used }}>
          <View style={{ height: 8, borderRadius: 4, width: `${Math.round(pct * 100)}%`,
                         backgroundColor: pct >= 0.9 ? c.status.danger : c.accent }} />
        </View>
        <Text style={[s.caption, { marginTop: SPACE(2) }]}>
          Ao chegar no limite, o bot volta sozinho para o menu até o mês que vem e você recebe um aviso.
        </Text>
        {d.ai_enabled && !d.available && d.reason ? (
          <Text style={[s.caption, { marginTop: SPACE(2), color: c.statusText.warning }]}>{d.reason}</Text>
        ) : null}
      </Card>
    </Section>
  );
}

export function SettingsScreen() {
  const { s, v } = useTheme();
  const shop = useLoad(() => api.get('/shop'), []);
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (shop.data && !f) setF({ ...shop.data, owner_phone: phoneLabel(shop.data.owner_phone) }); }, [shop.data]); // eslint-disable-line
  if (!f) return <Loading error={shop.error} onRetry={shop.reload} />;
  const set = (k) => (val) => setF({ ...f, [k]: val });

  const save = async () => {
    setBusy(true);
    await run(async () => {
      const body = { ...f };
      delete body.id; delete body.evolution_instance; delete body.niche; delete body.theme_mode;
      NUM.forEach(([k]) => { body[k] = Number(body[k]); });
      const r = await api.put('/shop', body);
      setF({ ...r, owner_phone: phoneLabel(r.owner_phone) });
    }, 'Configurações salvas. O bot já usa os novos dados.');
    setBusy(false);
  };

  return (
    <Screen footer={<Button title="Salvar configurações" icon="checkmark" onPress={save} loading={busy} style={{ marginBottom: 0 }} />}>
      <AISection />
      <AppearanceSection onSaved={(r) => setF((x) => ({ ...x, niche: r.niche, theme_mode: r.theme_mode }))} />

      <Section title={`Dados do ${v.business === 'clínica' ? 'consultório' : 'negócio'}`}>
        <Field label="Nome" value={f.name} onChangeText={set('name')} />
        <Field label="Endereço" value={f.address} onChangeText={set('address')} multiline />
        <Field label="Telefone fixo" value={f.phone} onChangeText={set('phone')} keyboardType="phone-pad" />
        <Field label="Instagram" value={f.instagram} onChangeText={set('instagram')} autoCapitalize="none" />
        <Field label="WhatsApp pessoal do dono" mask="phone" value={f.owner_phone} onChangeText={set('owner_phone')}
               hint="Recebe todos os alertas e acessa o menu do dono no bot. Não use o número conectado ao bot." />
        <Field label="Mensagem de boas-vindas" value={f.welcome_text} onChangeText={set('welcome_text')} multiline
               placeholder="Ex.: Aceitamos Pix e cartão. Estacionamento em frente." />
      </Section>

      <Section title="Pix antecipado">
        <Toggle label="Oferecer pagamento via Pix no bot" value={f.pix_enabled} onValueChange={set('pix_enabled')}
                hint="O dinheiro cai direto na sua conta. Você confirma o recebimento no app ou no WhatsApp." />
        {f.pix_enabled ? (
          <>
            <Text style={s.label}>Tipo da chave</Text>
            <Chips value={f.pix_key_type} onChange={set('pix_key_type')} options={[
              { value: 'cpf', label: 'CPF' }, { value: 'cnpj', label: 'CNPJ' }, { value: 'email', label: 'E-mail' },
              { value: 'phone', label: 'Celular' }, { value: 'random', label: 'Aleatória' },
            ]} />
            <Field label="Chave Pix" value={f.pix_key} onChangeText={set('pix_key')} autoCapitalize="none"
                   keyboardType={f.pix_key_type === 'email' ? 'email-address' : ['cpf', 'cnpj', 'phone'].includes(f.pix_key_type) ? 'number-pad' : 'default'} />
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
    </Screen>
  );
}

// ---------------------------------------------------------------- WhatsApp

const STATE_INFO = {
  open: { label: 'Conectado', tone: 'success', icon: 'checkmark-circle' },
  connecting: { label: 'Aguardando conexão', tone: 'warning', icon: 'time-outline' },
  close: { label: 'Desconectado', tone: 'danger', icon: 'close-circle-outline' },
  nao_criada: { label: 'Ainda não conectado', tone: 'danger', icon: 'close-circle-outline' },
  simulacao: { label: 'Modo simulação (sem WhatsApp)', tone: 'neutral', icon: 'flask-outline' },
  erro: { label: 'Erro ao consultar', tone: 'danger', icon: 'alert-circle-outline' },
};

const QR_SECONDS = 40; // o WhatsApp troca o QR Code a cada ~20-40 s
const POLL_MS = 3000;

// O backend manda com o prefixo data:image/png;base64, mas aceita também só o base64
export function qrUri(raw) {
  if (!raw) return null;
  return raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
}

// "WZYEH1YY" -> "WZYE-H1YY", como o WhatsApp mostra
const formatCode = (x) => (x && x.length === 8 ? `${x.slice(0, 4)}-${x.slice(4)}` : x);

function Steps({ items }) {
  const { c, s, font } = useTheme();
  return (
    <View style={{ alignSelf: 'stretch', marginTop: SPACE(3) }}>
      {items.map((t, i) => (
        <View key={t} style={[s.row, { alignItems: 'flex-start', gap: SPACE(3), marginBottom: SPACE(2.5) }]}>
          <View style={{ width: 26, height: 26, borderRadius: 13, backgroundColor: c.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ fontFamily: font.bold, color: c.accentText, fontSize: 13 }}>{i + 1}</Text>
          </View>
          <Text style={[s.body, { flex: 1 }]}>{t}</Text>
        </View>
      ))}
    </View>
  );
}

export function WhatsAppScreen() {
  const { c, s, font, v } = useTheme();
  const st = useLoad(() => api.get('/whatsapp/status'), []);
  const [mode, setMode] = useState('qr');
  const [qr, setQr] = useState(null);
  const [code, setCode] = useState(null);
  const [number, setNumber] = useState('');
  const [busy, setBusy] = useState('');
  const [left, setLeft] = useState(0);

  // Status em tempo real: consulta a cada 3 s enquanto a tela está aberta; para ao sair
  useFocusEffect(useCallback(() => {
    const id = setInterval(async () => {
      try {
        const r = await api.get('/whatsapp/status');
        st.setData(r);
        if (r.state === 'open') { setQr(null); setCode(null); }
      } catch (e) {
        // falha passageira de rede: a próxima consulta tenta de novo
      }
    }, POLL_MS);
    return () => { clearInterval(id); setQr(null); setCode(null); };
  }, [])); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!qr || left <= 0) return undefined;
    const id = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(id);
  }, [qr, left]);

  const show = (r, field) => {
    if (!r) return; // erro (ex.: 502 da Evolution) já foi mostrado
    st.setData((d) => ({ ...d, state: r.state }));
    if (field === 'qrcode' && r.qrcode) { setCode(null); setQr(qrUri(r.qrcode)); setLeft(QR_SECONDS); return; }
    if (field === 'pairing_code' && r.pairing_code) { setQr(null); setCode(r.pairing_code); return; }
    setQr(null);
    setCode(null);
    Alert.alert(r.state === 'open' ? 'Já conectado' : 'Não foi possível gerar',
      r.message || 'O servidor não devolveu o código. Tente de novo em alguns segundos.');
  };
  const connect = async () => {
    setBusy('qr');
    show(await run(() => api.post('/whatsapp/connect')), 'qrcode');
    setBusy('');
  };
  const requestCode = async () => {
    if (number.replace(/\D/g, '').length < 10) {
      toast('Digite o número do WhatsApp do bot com DDD.', 'error');
      return;
    }
    setBusy('code');
    show(await run(() => api.post('/whatsapp/pairing-code', { number })), 'pairing_code');
    setBusy('');
  };
  const disconnect = () => confirm('Desconectar WhatsApp',
    `O bot para de responder os ${v.customers} até você conectar de novo. Desconectar?`, async () => {
      setBusy('disconnect');
      const r = await run(() => api.post('/whatsapp/disconnect'), 'WhatsApp desconectado.');
      setBusy('');
      if (r) st.setData((d) => ({ ...d, state: r.state }));
    }, 'Desconectar', true);

  const state = st.data?.state;
  if (!st.data && st.error) return <Loading error={st.error} onRetry={st.reload} />;

  return (
    <Screen onRefresh={st.reload} refreshing={st.loading && !!st.data}>
      <Card style={[s.row, { gap: SPACE(3) }]}>
        <Ionicons name="logo-whatsapp" size={32} color={state === 'open' ? c.statusText.success : c.textMuted} />
        <View style={{ flex: 1 }}>
          <Badge info={STATE_INFO[state] || { label: state || 'Consultando...', tone: 'neutral' }} large />
          {st.data ? <Text style={[s.caption, { marginTop: SPACE(1.5) }]}>Instância: {st.data.instance}</Text> : null}
        </View>
      </Card>

      {state === 'open' ? (
        <>
          <Text style={[s.muted, { marginVertical: SPACE(3) }]}>O bot está respondendo os {v.customers} por este WhatsApp.</Text>
          <Button title="Desconectar WhatsApp" icon="log-out-outline" kind="danger" onPress={disconnect} loading={busy === 'disconnect'} />
        </>
      ) : (
        <>
          <SegmentedControl value={mode} onChange={(m) => { setMode(m); setQr(null); setCode(null); }} style={{ marginTop: SPACE(2) }}
                            options={[{ value: 'qr', label: 'QR Code', icon: 'qr-code-outline' },
                                      { value: 'code', label: 'Código de pareamento', icon: 'keypad-outline' }]} />
          {mode === 'qr' ? (
            <>
              {qr ? (
                <Card style={{ alignItems: 'center' }}>
                  {left > 0 ? (
                    <>
                      <View style={{ backgroundColor: c.qrBackground, padding: SPACE(2), borderRadius: 12 }}>
                        <Image source={{ uri: qr }} style={{ width: 260, height: 260 }} resizeMode="contain"
                               accessibilityLabel="QR Code para conectar o WhatsApp" />
                      </View>
                      <Text style={[s.heading, { marginTop: SPACE(3) }]} accessibilityLiveRegion="polite">Expira em {left} s</Text>
                      <Text style={s.muted}>Aguardando a leitura...</Text>
                    </>
                  ) : (
                    <>
                      <Ionicons name="time-outline" size={40} color={c.textMuted} />
                      <Text style={[s.bodyBold, { marginVertical: SPACE(3) }]}>O QR Code venceu.</Text>
                      <Button title="Gerar novo QR Code" icon="refresh-outline" onPress={connect} loading={busy === 'qr'}
                              style={{ alignSelf: 'stretch' }} />
                    </>
                  )}
                </Card>
              ) : (
                <Button title="Gerar QR Code" icon="qr-code-outline" onPress={connect} loading={busy === 'qr'} disabled={!!busy} />
              )}
              <Steps items={[
                'No celular do número do negócio, abra o WhatsApp.',
                'Toque em Aparelhos conectados > Conectar aparelho.',
                'Aponte a câmera para o QR Code desta tela.',
              ]} />
            </>
          ) : (
            <>
              <Text style={[s.muted, { marginBottom: SPACE(3) }]}>
                Use quando não houver outro aparelho para ler o QR Code: você digita um código no próprio celular do bot.
              </Text>
              <Field label="Número do WhatsApp do bot" mask="phone" value={number} onChangeText={setNumber} />
              <Button title={code ? 'Gerar novo código' : 'Gerar código'} icon="keypad-outline" onPress={requestCode}
                      loading={busy === 'code'} disabled={!!busy} />
              {code ? (
                <Card style={{ alignItems: 'center' }}>
                  <Text style={s.caption}>Código de pareamento</Text>
                  <Text selectable accessibilityLabel={`Código ${code.split('').join(' ')}`}
                        style={{ fontSize: 40, fontFamily: font.extrabold, letterSpacing: 4, color: c.text, marginVertical: SPACE(3) }}
                        maxFontSizeMultiplier={1.2}>
                    {formatCode(code)}
                  </Text>
                  <Button title="Copiar código" icon="copy-outline" kind="secondary" compact
                          onPress={() => run(() => Clipboard.setStringAsync(code), 'Código copiado.')} />
                  <Text style={[s.muted, { marginTop: SPACE(3) }]}>Aguardando a conexão...</Text>
                </Card>
              ) : null}
              <Steps items={[
                'No celular do bot, abra o WhatsApp > Aparelhos conectados.',
                'Toque em Conectar aparelho > Conectar com número de telefone.',
                'Digite o código de 8 caracteres que aparece aqui.',
              ]} />
            </>
          )}
        </>
      )}
    </Screen>
  );
}
