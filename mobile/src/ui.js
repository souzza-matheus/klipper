import React, { useCallback, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import {
  ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors } from './theme';

// Carrega dados sempre que a tela ganha foco; expõe reload para "puxar para atualizar".
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useFocusEffect(useCallback(() => { load(); }, [load]));
  return { data, setData, loading, error, reload: load };
}

export async function run(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) Alert.alert('Pronto', okMsg);
    return r;
  } catch (e) {
    Alert.alert('Ops', e.message);
    return undefined;
  }
}

export function confirm(title, msg, onYes, yesLabel = 'Confirmar', destructive = false) {
  Alert.alert(title, msg, [
    { text: 'Voltar', style: 'cancel' },
    { text: yesLabel, style: destructive ? 'destructive' : 'default', onPress: onYes },
  ]);
}

export function Screen({ children, onRefresh, refreshing, scroll = true, style }) {
  if (!scroll) return <View style={[s.screen, style]}>{children}</View>;
  return (
    <ScrollView
      style={s.screenScroll}
      contentContainerStyle={[s.screen, style]}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined}
    >
      {children}
    </ScrollView>
  );
}

export function Card({ children, style, onPress }) {
  const body = <View style={[s.card, style]}>{children}</View>;
  return onPress ? <Pressable onPress={onPress} style={({ pressed }) => pressed && { opacity: 0.7 }}>{body}</Pressable> : body;
}

export function Title({ children, style }) {
  return <Text style={[s.title, style]}>{children}</Text>;
}

export function Label({ children, style }) {
  return <Text style={[s.label, style]}>{children}</Text>;
}

export function Muted({ children, style, numberOfLines }) {
  return <Text style={[s.muted, style]} numberOfLines={numberOfLines}>{children}</Text>;
}

export function Badge({ info }) {
  if (!info) return null;
  return (
    <View style={[s.badge, { backgroundColor: info.bg }]}>
      <Text style={[s.badgeText, { color: info.fg }]}>{info.label}</Text>
    </View>
  );
}

export function Button({ title, onPress, kind = 'primary', icon, disabled, style }) {
  const st = {
    primary: [s.btn, { backgroundColor: colors.primary }],
    accent: [s.btn, { backgroundColor: colors.accent }],
    ghost: [s.btn, s.btnGhost],
    danger: [s.btn, { backgroundColor: colors.bad }],
  }[kind];
  const fg = kind === 'ghost' ? colors.primary : '#fff';
  return (
    <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [st, style, (pressed || disabled) && { opacity: 0.6 }]}>
      {icon ? <Ionicons name={icon} size={18} color={fg} style={{ marginRight: 6 }} /> : null}
      <Text style={[s.btnText, { color: fg }]}>{title}</Text>
    </Pressable>
  );
}

export function Field({ label, hint, ...props }) {
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Label>{label}</Label> : null}
      <TextInput placeholderTextColor="#9A9DA4" style={[s.input, props.multiline && { minHeight: 80, textAlignVertical: 'top' }]} {...props} />
      {hint ? <Muted style={{ marginTop: 4 }}>{hint}</Muted> : null}
    </View>
  );
}

export function Toggle({ label, value, onValueChange, hint }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <View style={s.row}>
        <Text style={[s.body, { flex: 1 }]}>{label}</Text>
        <Switch value={!!value} onValueChange={onValueChange} trackColor={{ true: colors.primary }} />
      </View>
      {hint ? <Muted>{hint}</Muted> : null}
    </View>
  );
}

export function Chips({ options, value, onChange, multi = false }) {
  const isOn = (v) => (multi ? (value || []).includes(v) : value === v);
  const toggle = (v) => {
    if (!multi) return onChange(v);
    const cur = value || [];
    onChange(cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
  };
  return (
    <View style={s.chips}>
      {options.map((o) => (
        <Pressable key={String(o.value)} onPress={() => toggle(o.value)} style={[s.chip, isOn(o.value) && s.chipOn]}>
          <Text style={[s.chipText, isOn(o.value) && { color: '#fff' }]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function ListRow({ icon, title, subtitle, right, onPress }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.listRow, pressed && { backgroundColor: '#F0EDE7' }]}>
      {icon ? <Ionicons name={icon} size={22} color={colors.primary} style={{ marginRight: 14 }} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={s.body}>{title}</Text>
        {subtitle ? <Muted>{subtitle}</Muted> : null}
      </View>
      {right ?? (onPress ? <Ionicons name="chevron-forward" size={18} color={colors.muted} /> : null)}
    </Pressable>
  );
}

export function Empty({ text }) {
  return (
    <View style={s.empty}>
      <Ionicons name="cut-outline" size={32} color={colors.line} />
      <Muted style={{ marginTop: 8, textAlign: 'center' }}>{text}</Muted>
    </View>
  );
}

export function Loading({ error, onRetry }) {
  return (
    <View style={s.empty}>
      {error ? (
        <>
          <Muted style={{ textAlign: 'center', marginBottom: 12 }}>{error}</Muted>
          {onRetry ? <Button title="Tentar de novo" kind="ghost" onPress={onRetry} /> : null}
        </>
      ) : (
        <ActivityIndicator color={colors.primary} />
      )}
    </View>
  );
}

export function Section({ title, children, right }) {
  return (
    <View style={{ marginBottom: 18 }}>
      <View style={[s.row, { marginBottom: 8 }]}>
        <Text style={[s.section, { flex: 1 }]}>{title}</Text>
        {right}
      </View>
      {children}
    </View>
  );
}

export function Stat({ label, value }) {
  return (
    <View style={s.stat}>
      <Text style={s.statValue}>{value}</Text>
      <Muted>{label}</Muted>
    </View>
  );
}

export const s = StyleSheet.create({
  screenScroll: { flex: 1, backgroundColor: colors.bg },
  screen: { padding: 16, paddingBottom: 40, backgroundColor: colors.bg, flexGrow: 1 },
  card: { backgroundColor: colors.card, borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: colors.line },
  title: { fontSize: 20, fontWeight: '700', color: colors.ink, marginBottom: 8 },
  section: { fontSize: 13, fontWeight: '700', color: colors.muted, textTransform: 'uppercase', letterSpacing: 0.6 },
  label: { fontSize: 13, fontWeight: '600', color: colors.ink, marginBottom: 6 },
  body: { fontSize: 16, color: colors.ink },
  muted: { fontSize: 13, color: colors.muted },
  row: { flexDirection: 'row', alignItems: 'center' },
  badge: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3, alignSelf: 'flex-start' },
  badgeText: { fontSize: 12, fontWeight: '600' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 10, paddingVertical: 13, paddingHorizontal: 16, marginBottom: 10 },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.primary },
  btnText: { fontSize: 15, fontWeight: '700' },
  input: { backgroundColor: '#fff', borderWidth: 1, borderColor: colors.line, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, fontSize: 16, color: colors.ink },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 },
  chip: { borderWidth: 1, borderColor: colors.line, backgroundColor: '#fff', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 },
  chipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { fontSize: 14, color: colors.ink },
  listRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.line },
  empty: { alignItems: 'center', justifyContent: 'center', padding: 40 },
  stat: { flex: 1, backgroundColor: colors.card, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: colors.line },
  statValue: { fontSize: 20, fontWeight: '700', color: colors.ink },
});
