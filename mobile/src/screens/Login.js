import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { login } from '../api';
import { colors } from '../theme';
import { Button, Field, Muted, Screen, run } from '../ui';

export default function Login({ initialUrl, onLogged }) {
  const [url, setUrl] = useState(initialUrl || 'http://192.168.0.10:8000');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    const r = await run(() => login(url, email, password));
    setBusy(false);
    if (r) onLogged(r);
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen style={{ justifyContent: 'center' }}>
        <View style={{ alignItems: 'center', marginBottom: 32 }}>
          <Text style={{ fontSize: 40 }}>💈</Text>
          <Text style={{ fontSize: 26, fontWeight: '800', color: colors.primary }}>BarberBot</Text>
          <Muted>Painel da barbearia</Muted>
        </View>
        <Field label="Endereço do servidor" value={url} onChangeText={setUrl} autoCapitalize="none"
               keyboardType="url" hint="Quem instalou o sistema passa este endereço." />
        <Field label="E-mail" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
        <Field label="Senha" value={password} onChangeText={setPassword} secureTextEntry />
        <Button title={busy ? 'Entrando...' : 'Entrar'} onPress={submit} disabled={busy || !email || !password} />
      </Screen>
    </KeyboardAvoidingView>
  );
}
