import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { login } from '../api';
import { IS_WEB } from '../storage';
import { LogoVertical } from '../brand/Logo';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Button, Field, haptic } from '../ui';

// Tela de login com a marca-base SyncServ. Lembra o endereço do servidor e o e-mail do último acesso.
export default function Login({ initialUrl, initialEmail, onLogged }) {
  const { c, s, mode } = useTheme();
  const insets = useSafeAreaInsets();
  // Web publicado (app.dominio): a API responde no mesmo endereço do site
  const [url, setUrl] = useState(initialUrl || (IS_WEB ? window.location.origin : 'http://192.168.0.10:8000'));
  const [email, setEmail] = useState(initialEmail || '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // Quem usa o app não precisa ver o servidor: na web é o próprio endereço do site; no celular, só no primeiro acesso
  const [showServer, setShowServer] = useState(!initialUrl && !IS_WEB);

  // Erro abaixo da senha, e não num aviso flutuante por cima do botão Entrar
  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const r = await login(url, email, password);
      setBusy(false);
      onLogged(r);
    } catch (e) {
      setBusy(false);
      haptic.error();
      setError(e.message);
    }
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView role="main" contentContainerStyle={{
        flexGrow: 1, justifyContent: 'center', padding: SPACE(6), paddingTop: insets.top + SPACE(8),
        paddingBottom: insets.bottom + SPACE(6),
      }} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: 'center', marginBottom: SPACE(10) }}>
          <View role="heading" aria-level={1} accessibilityLabel="SyncServ">
            <LogoVertical width={170} variant={mode === 'light' ? 'light' : 'dark'} />
          </View>
          <Text style={[s.muted, { marginTop: SPACE(4), textAlign: 'center' }]}>
            Agendamento pelo WhatsApp, do seu jeito.
          </Text>
        </View>
        <Field label="E-mail" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address"
               autoComplete="email" textContentType="username" returnKeyType="next" />
        <Field label="Senha" value={password} onChangeText={(t) => { setPassword(t); setError(''); }} secureTextEntry
               autoComplete="current-password" textContentType="password" returnKeyType="go" onSubmitEditing={submit}
               error={error} />
        <Button title="Entrar" icon="log-in-outline" onPress={submit} loading={busy} disabled={!email || !password} />
        {showServer ? (
          <Field label="Endereço do servidor" value={url} onChangeText={setUrl} autoCapitalize="none" keyboardType="url"
                 hint="Quem instalou o sistema passa este endereço." style={{ marginTop: SPACE(2) }} />
        ) : (
          <Button kind="ghost" compact icon="settings-outline" title="Configuração avançada"
                  onPress={() => setShowServer(true)} style={{ marginTop: SPACE(2), alignSelf: 'center' }}
                  accessibilityLabel={`Configuração avançada. Servidor atual: ${url}`} />
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
