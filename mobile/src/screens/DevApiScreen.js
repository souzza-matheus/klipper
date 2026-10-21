import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { currentApiUrl, resolveApiUrl } from '../api';
import { buildApiUrl, PROFILE } from '../config';
import { setDevApiUrl } from '../devApi';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { Button, Field, toast } from '../ui';

// Modo desenvolvedor (só nos perfis development e preview; 7 toques no logo do login): troca o endereço da API para
// testar com o PC (IP da rede) ou com um túnel. Em produção este arquivo não entra no pacote.
export default function DevApiScreen({ onClose }) {
  const { c, s, font } = useTheme();
  const [inUse, setInUse] = useState(currentApiUrl());
  const [url, setUrl] = useState(currentApiUrl());
  const fromBuild = buildApiUrl();

  useEffect(() => { resolveApiUrl().then((u) => { setInUse(u); setUrl(u); }); }, []);

  const save = async (value) => {
    const v = (value || '').trim();
    if (v && !/^https?:\/\/[^\s/]+/i.test(v)) {
      toast('Endereço inválido. Ex.: http://192.168.0.10:8002', 'error');
      return;
    }
    await setDevApiUrl(v === fromBuild ? '' : v);
    const now = await resolveApiUrl();
    setInUse(now);
    setUrl(now);
    toast('Endereço da API trocado');
  };

  return (
    <View style={{ gap: SPACE(3) }}>
      <Text role="heading" aria-level={1} style={{ fontFamily: font.extrabold, fontSize: 24, color: c.text }}>
        Modo desenvolvedor
      </Text>
      <Text style={s.muted}>Perfil do build: {PROFILE}</Text>
      <Text style={s.body}>Endereço da API em uso: {inUse || '(nenhum)'}</Text>
      <Text style={s.muted}>Endereço do build: {fromBuild || '(nenhum)'}</Text>
      <Field label="Endereço da API" value={url} onChangeText={setUrl} autoCapitalize="none" keyboardType="url"
             hint="IP do PC na rede (ex.: http://192.168.0.10:8002) ou o endereço do túnel (https://...)." />
      <Button title="Usar este endereço" icon="checkmark" onPress={() => save(url)} />
      <Button title="Voltar ao endereço do build" kind="ghost" icon="refresh" onPress={() => save('')} />
      <Button title="Fechar" kind="ghost" icon="close" onPress={onClose} />
    </View>
  );
}
