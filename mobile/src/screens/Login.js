import React, { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { login, selectBusiness } from '../api';
import { LogoVertical } from '../brand/Logo';
import { BusinessList } from '../components/BusinessList';
import { loginErrorMessage } from '../loginErrors';
import { isOnline } from '../net';
import { IS_WEB } from '../storage';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { ask, Button, Field, haptic } from '../ui';

// Modo desenvolvedor (development e preview): 7 toques no logo abrem a troca do endereço da API. Em produção a
// condição vira false no build e a tela nem entra no pacote.
const DevApiScreen = process.env.EXPO_PUBLIC_APP_PROFILE !== 'production' ? require('./DevApiScreen').default : null;
const DEV_TAPS = 7;

const online = () => (IS_WEB ? typeof navigator === 'undefined' || navigator.onLine !== false : isOnline());

// Login com a marca-base SyncServ: só e-mail e senha (o endereço da API vem do build e o servidor descobre o
// negócio). Quem entra em mais de um negócio escolhe em seguida ("Escolha o negócio").
export default function Login({ initialEmail, onLogged }) {
  const { c, s, mode, font } = useTheme();
  const insets = useSafeAreaInsets();
  const [email, setEmail] = useState(initialEmail || '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [choice, setChoice] = useState(null); // { businesses, selection_token } de quem tem mais de um negócio
  const [picking, setPicking] = useState(null);
  const [dev, setDev] = useState(false);
  const taps = useRef({ n: 0, at: 0 });

  // Erro abaixo da senha, e não num aviso flutuante por cima do botão Entrar
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const r = await login(email, password);
      setBusy(false);
      if (r.choose) setChoice(r);
      else onLogged(r);
    } catch (e) {
      setBusy(false);
      haptic.error();
      setError(loginErrorMessage(e, online()));
    }
  };

  const pick = async (b) => {
    setPicking(b.shop_id);
    try {
      onLogged(await selectBusiness(choice.selection_token, b.shop_id));
    } catch (e) {
      setPicking(null);
      haptic.error();
      // O token de escolha vale 5 minutos: passou disso, entra de novo
      setChoice(null);
      setError(e.status === 401 ? 'O tempo para escolher acabou. Entre de novo.' : loginErrorMessage(e, online()));
    }
  };

  const forgot = () => ask('Esqueci minha senha',
    'Peça uma senha provisória ao responsável pelo negócio: ele gera em Mais > Equipe e permissões. '
    + 'Se você é o dono, fale com o suporte do SyncServ.');

  const tapLogo = () => {
    const now = Date.now();
    const t = taps.current;
    t.n = now - t.at < 1500 ? t.n + 1 : 1;
    t.at = now;
    if (t.n >= DEV_TAPS) {
      t.n = 0;
      setDev(true);
    }
  };

  const logo = <LogoVertical width={170} variant={mode === 'light' ? 'light' : 'dark'} />;

  let body;
  if (dev && DevApiScreen) {
    body = <DevApiScreen onClose={() => setDev(false)} />;
  } else if (choice) {
    body = (
      <View>
        <Text role="heading" aria-level={1}
              style={{ fontFamily: font.extrabold, fontSize: 24, color: c.text, marginBottom: SPACE(1) }}>
          Escolha o negócio
        </Text>
        <Text style={[s.muted, { marginBottom: SPACE(5) }]}>
          Você entra em mais de um negócio. Qual quer abrir agora?
        </Text>
        <BusinessList businesses={choice.businesses} busyId={picking} onPick={pick} />
        <Button title="Voltar" kind="ghost" icon="arrow-back" onPress={() => { setChoice(null); setPassword(''); }}
                style={{ marginTop: SPACE(5) }} disabled={!!picking} />
      </View>
    );
  } else {
    body = (
      <>
        <View style={{ alignItems: 'center', marginBottom: SPACE(10) }}>
          <View role="heading" aria-level={1} accessibilityLabel="SyncServ">
            {DevApiScreen ? (
              // Sem papel nem foco: para o leitor de tela continua sendo só o título "SyncServ"
              <Pressable onPress={tapLogo} accessible={false} focusable={false}>
                {logo}
              </Pressable>
            ) : logo}
          </View>
          <Text style={[s.muted, { marginTop: SPACE(4), textAlign: 'center' }]}>
            Agendamento pelo WhatsApp, do seu jeito.
          </Text>
        </View>
        <Field label="E-mail" value={email} onChangeText={(t) => { setEmail(t); setError(''); }}
               autoCapitalize="none" keyboardType="email-address" autoComplete="email" textContentType="username"
               returnKeyType="next" />
        <Field label="Senha" value={password} onChangeText={(t) => { setPassword(t); setError(''); }} secureTextEntry
               autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit}
               error={error} />
        <Button title="Entrar" icon="log-in-outline" onPress={submit} loading={busy} disabled={!email || !password} />
        <Button kind="ghost" compact title="Esqueci minha senha" onPress={forgot}
                style={{ marginTop: SPACE(2), alignSelf: 'center' }} />
      </>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView role="main" contentContainerStyle={{
        flexGrow: 1, justifyContent: 'center', padding: SPACE(6), paddingTop: insets.top + SPACE(8),
        paddingBottom: insets.bottom + SPACE(6),
      }} keyboardShouldPersistTaps="handled">
        {body}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
