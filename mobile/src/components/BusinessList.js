import React from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Symbol as BrandSymbol } from '../brand/Logo';
import { NICHE_INFO, SPACE, TYPE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { a11yState } from '../ui';

// Lista de negócios da conta ("Escolha o negócio" no login e Mais > Trocar de negócio): símbolo na cor do segmento,
// nome, segmento e papel. currentId marca o negócio aberto; busyId mostra o carregando no que foi tocado.
export function BusinessList({ businesses, currentId, busyId, onPick }) {
  const { c, s, font } = useTheme();
  return (
    <View role="list" style={{ gap: SPACE(3) }}>
      {businesses.map((b) => {
        const info = NICHE_INFO[b.niche] || NICHE_INFO.barbershop;
        const current = b.shop_id === currentId;
        const label = `${b.name}, ${info.label}, ${b.role_label}${current ? ', aberto agora' : ''}`;
        return (
          <Pressable key={b.shop_id} role="button" accessibilityLabel={label}
                     {...a11yState({ selected: current, disabled: !!busyId })}
                     disabled={!!busyId || current} onPress={() => onPick(b)}
                     style={({ pressed }) => [s.card, s.row, {
                       gap: SPACE(3), minHeight: 72, marginBottom: 0, opacity: pressed ? 0.8 : 1,
                       borderColor: current ? c.accentText : c.divider, borderWidth: current ? 2 : 1,
                     }]}>
            <BrandSymbol size={40} color={info.accent} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontFamily: font.bold, fontSize: TYPE.body, color: c.text }}>{b.name} </Text>
              <Text style={s.caption}>{info.label} · {b.role_label}</Text>
            </View>
            {busyId === b.shop_id ? <ActivityIndicator color={c.accentText} />
              : current ? <Text style={[s.caption, { color: c.accentText }]}>Aberto</Text>
                : <Ionicons name="chevron-forward" size={22} color={c.textMuted} />}
          </Pressable>
        );
      })}
    </View>
  );
}
