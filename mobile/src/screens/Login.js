import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { login } from '../api';
import { LogoVertical } from '../brand/Logo';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Button, Field, run } from '../ui';

// Tela de login com a marca-base SyncServ. Lembra o endereço do servidor e o e-mail do último acesso.
export default function Login({ initialUrl, initialEmail, onLogged }) {
  const { c, s, mode } = useTheme();
  const insets = useSafeAreaInsets();
  const [url, setUrl] = useState(initialUrl || 'http://192.168.0.10:8000');
  const [email, setEmail] = useState(initialEmail || '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [showServer, setShowServer] = useState(!initialUrl);

  const submit = async () => {
    setBusy(true);
    const r = await run(() => login(url, email, password));
    setBusy(false);
    if (r) onLogged(r);
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{
        flexGrow: 1, justifyContent: 'center', padding: SPACE(6), paddingTop: insets.top + SPACE(8),
        paddingBottom: insets.bottom + SPACE(6),
      }} keyboardShouldPersistTaps="handled">
        <View style={{ alignItems: 'center', marginBottom: SPACE(10) }}>
          <LogoVertical width={170} variant={mode === 'light' ? 'light' : 'dark'} />
          <Text style={[s.muted, { marginTop: SPACE(4), textAlign: 'center' }]}>
            Agendamento pelo WhatsApp, do seu jeito.
          </Text>
        </View>
        <Field label="E-mail" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address"
               autoComplete="email" textContentType="username" returnKeyType="next" />
        <Field label="Senha" value={password} onChangeText={setPassword} secureTextEntry autoComplete="password"
               textContentType="password" returnKeyType="go" onSubmitEditing={submit} />
        {showServer ? (
          <Field label="Endereço do servidor" value={url} onChangeText={setUrl} autoCapitalize="none" keyboardType="url"
                 hint="Quem instalou o sistema passa este endereço." />
        ) : (
          <Button kind="ghost" compact icon="server-outline" title={`Servidor: ${url.replace(/^https?:\/\//, '')}`}
                  onPress={() => setShowServer(true)} style={{ marginBottom: SPACE(4) }}
                  accessibilityLabel={`Servidor ${url}. Toque para trocar`} />
        )}
        <Button title="Entrar" icon="log-in-outline" onPress={submit} loading={busy} disabled={!email || !password} />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
