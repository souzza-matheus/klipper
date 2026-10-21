import React from 'react';
import { ScrollView, Text, View } from 'react-native';
import { LogoVertical } from '../brand/Logo';
import { SPACE, TYPE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Button } from '../ui';

// Versão web: o app só tem um endereço (/). Qualquer outro caminho chega aqui (o Caddy devolve 404 com o app).
export function unknownWebPath() {
  if (typeof window === 'undefined' || !window.location) return false;
  return !['/', '/index.html'].includes(window.location.pathname);
}

export default function NotFound() {
  const { c, s, font } = useTheme();
  return (
    <ScrollView role="main" style={{ flex: 1, backgroundColor: c.background }}
                contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: SPACE(6) }}>
      <View style={{ maxWidth: 440, width: '100%', alignItems: 'center' }}>
        <LogoVertical width={140} variant="dark" />
        <Text role="heading" aria-level={1}
              style={{ color: c.text, fontFamily: font.extrabold, fontSize: TYPE.title, textAlign: 'center',
                       marginTop: SPACE(8), marginBottom: SPACE(3) }}>
          Página não encontrada
        </Text>
        <Text style={[s.muted, { textAlign: 'center', marginBottom: SPACE(8) }]}>
          Esse endereço não existe no SyncServ. Talvez o link esteja incompleto.
        </Text>
        <Button title="Ir para o início" icon="home-outline" onPress={() => window.location.assign('/')} />
      </View>
    </ScrollView>
  );
}
