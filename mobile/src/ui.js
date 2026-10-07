import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from '@react-navigation/native';
import {
  ActivityIndicator, Alert, Animated, Easing, KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl,
  ScrollView, Switch, Text, TextInput, View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Symbol as BrandSymbol } from './brand/Logo';
import { NICHE_INFO, SPACE, TOUCH } from './theme';
import { useTheme } from './ThemeProvider';
import { useWide } from './session';

// ---------------------------------------------------------------- dados e feedback

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

// Feedback tátil nas ações importantes (falha em silêncio onde não há vibração)
export const haptic = {
  tap: () => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {}),
  success: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}),
  warning: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {}),
  error: () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {}),
};

// Toast: avisos curtos de sucesso e erro. Alert fica só para confirmar ações destrutivas.
let toastListener = null;
export function toast(message, kind = 'success') {
  if (kind === 'success') haptic.success();
  else if (kind === 'error') haptic.error();
  if (toastListener) toastListener({ message, kind, id: Date.now() });
  else ask(kind === 'error' ? 'Ops' : 'Pronto', message);
}

// Diálogo com botões. Celular: Alert nativo. Web: modal próprio (o Alert do react-native-web não faz nada).
// buttons: [{ text, style: 'cancel' | 'destructive' | 'default', onPress }]
let dialogListener = null;
export function ask(title, message, buttons = [{ text: 'OK' }]) {
  if (Platform.OS !== 'web' || !dialogListener) {
    Alert.alert(title, message, buttons);
    return;
  }
  dialogListener({ title, message, buttons, id: Date.now() });
}

export function DialogHost() {
  const { c, s, font, radius } = useTheme();
  const [d, setD] = useState(null);
  useEffect(() => {
    dialogListener = setD;
    return () => { dialogListener = null; };
  }, []);
  useEffect(() => {
    if (!d || Platform.OS !== 'web') return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') {
        const cancel = d.buttons.find((b) => b.style === 'cancel');
        setD(null);
        cancel?.onPress?.();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [d]);
  if (!d) return null;
  const press = (b) => { setD(null); b.onPress?.(); };
  return (
    <Modal transparent visible animationType="fade" onRequestClose={() => setD(null)}>
      <View style={{ flex: 1, backgroundColor: c.overlay, alignItems: 'center', justifyContent: 'center',
                     padding: SPACE(4) }}>
        <View accessibilityRole="alert" style={{
          width: '100%', maxWidth: 440, backgroundColor: c.surfaceElevated, borderRadius: radius.sheet,
          padding: SPACE(5), borderWidth: 1, borderColor: c.divider,
        }}>
          <Text style={[s.heading, { marginBottom: SPACE(2) }]} accessibilityRole="header">{d.title}</Text>
          {d.message ? <Text style={[s.body, { marginBottom: SPACE(4) }]}>{d.message}</Text> : null}
          <View style={{ gap: SPACE(2) }}>
            {d.buttons.map((b) => (
              <Pressable key={b.text} onPress={() => press(b)} accessibilityRole="button"
                         style={({ pressed }) => ({
                           minHeight: 48, borderRadius: radius.input, alignItems: 'center', justifyContent: 'center',
                           paddingHorizontal: SPACE(3), borderWidth: 1.5,
                           borderColor: b.style === 'destructive' ? c.statusText.danger
                             : b.style === 'cancel' ? c.border : c.accentFill,
                           backgroundColor: pressed ? c.neutralBg : b.style === 'default' || !b.style ? c.accentFill
                             : 'transparent',
                         })}>
                <Text style={{
                  fontFamily: font.bold, fontSize: 16,
                  color: b.style === 'destructive' ? c.statusText.danger : b.style === 'cancel' ? c.text : c.onAccent,
                }}>{b.text}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </View>
    </Modal>
  );
}

export function ToastHost() {
  const { c, s, font } = useTheme();
  const insets = useSafeAreaInsets();
  const wide = useWide();
  const [item, setItem] = useState(null);
  const anim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    toastListener = (t) => setItem(t);
    return () => { toastListener = null; };
  }, []);
  useEffect(() => {
    if (!item) return undefined;
    Animated.timing(anim, { toValue: 1, duration: 180, useNativeDriver: true }).start();
    const ms = item.kind === 'error' ? 5000 : 2600;
    const tm = setTimeout(() => {
      Animated.timing(anim, { toValue: 0, duration: 180, useNativeDriver: true }).start(() => setItem(null));
    }, ms);
    return () => clearTimeout(tm);
  }, [item, anim]);
  if (!item) return null;
  const tone = item.kind === 'error' ? 'danger' : item.kind === 'info' ? 'info' : 'success';
  const icon = { danger: 'alert-circle', info: 'information-circle', success: 'checkmark-circle' }[tone];
  return (
    <Animated.View pointerEvents="box-none" style={{
      position: 'absolute', left: wide ? undefined : SPACE(4), right: SPACE(4), width: wide ? 440 : undefined,
      bottom: insets.bottom + (wide ? SPACE(6) : SPACE(20)),
      opacity: anim, transform: [{ translateY: anim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }],
    }}>
      <Pressable accessibilityRole="alert" accessibilityLiveRegion="polite" onPress={() => setItem(null)}
                 style={[s.row, {
                   backgroundColor: c.surfaceElevated, borderRadius: 14, padding: SPACE(4), gap: SPACE(3),
                   borderWidth: 1, borderColor: c.status[tone], minHeight: TOUCH,
                 }]}>
        <Ionicons name={icon} size={24} color={c.statusText[tone]} />
        <Text style={{ flex: 1, color: c.text, fontFamily: font.semibold, fontSize: 15 }}>{item.message}</Text>
      </Pressable>
    </Animated.View>
  );
}

// Executa uma ação da API: sucesso vira Toast (se houver okMsg), erro vira Toast de erro.
export async function run(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(okMsg);
    return r;
  } catch (e) {
    toast(e.message, 'error');
    return undefined;
  }
}

export function confirm(title, msg, onYes, yesLabel = 'Confirmar', destructive = false) {
  if (destructive) haptic.warning();
  ask(title, msg, [
    { text: 'Voltar', style: 'cancel' },
    { text: yesLabel, style: destructive ? 'destructive' : 'default', onPress: onYes },
  ]);
}

// ---------------------------------------------------------------- estrutura

// footer: conteúdo fixo no rodapé (botão principal), que sobe junto com o teclado
// No computador (tela larga) o conteúdo ganha mais respiro e uma largura máxima confortável de leitura.
export function Screen({ children, onRefresh, refreshing, scroll = true, style, footer, maxWidth = 1200 }) {
  const { c, s } = useTheme();
  const insets = useSafeAreaInsets();
  const wide = useWide();
  const wideStyle = wide ? { paddingHorizontal: SPACE(8), paddingTop: SPACE(6), width: '100%', maxWidth,
                             alignSelf: 'center' } : null;
  const body = !scroll ? <View style={[s.screen, wideStyle, style]}>{children}</View> : (
    <ScrollView
      style={s.screenScroll}
      contentContainerStyle={[s.screen, wideStyle, style]}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? (
        <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.accentText}
                        colors={[c.accentText]} progressBackgroundColor={c.surface} />
      ) : undefined}
    >
      {children}
    </ScrollView>
  );
  if (!footer) return body;
  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.background }}
                          behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
      {body}
      <View style={{
        paddingHorizontal: SPACE(4), paddingTop: SPACE(3), paddingBottom: Math.max(insets.bottom, SPACE(3)),
        backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.divider,
      }}>
        {footer}
      </View>
    </KeyboardAvoidingView>
  );
}

export function Card({ children, style, onPress, onLongPress, accessibilityLabel }) {
  const { s, c } = useTheme();
  if (!onPress && !onLongPress) return <View style={[s.card, style]}>{children}</View>;
  return (
    <Pressable onPress={onPress} onLongPress={onLongPress ? () => { haptic.tap(); onLongPress(); } : undefined}
               delayLongPress={350} accessibilityRole="button" accessibilityLabel={accessibilityLabel}
               android_ripple={{ color: c.neutralBg }}
               style={({ pressed }) => [s.card, style, pressed && { opacity: 0.85 }]}>
      {children}
    </Pressable>
  );
}

export function T({ variant = 'body', style, children, ...props }) {
  const { s } = useTheme();
  return <Text style={[s[variant], style]} maxFontSizeMultiplier={1.6} {...props}>{children}</Text>;
}
export const Title = ({ children, style }) => <T variant="title" style={style}>{children}</T>;
export const Label = ({ children, style }) => <T variant="label" style={style}>{children}</T>;
export const Muted = ({ children, style, numberOfLines }) => (
  <T variant="muted" style={style} numberOfLines={numberOfLines}>{children}</T>
);

export function Section({ title, children, right }) {
  const { s } = useTheme();
  return (
    <View style={{ marginBottom: SPACE(5) }}>
      <View style={[s.row, { marginBottom: SPACE(2), minHeight: 32 }]}>
        <Text style={[s.section, { flex: 1 }]} accessibilityRole="header">{title}</Text>
        {right}
      </View>
      {children}
    </View>
  );
}

export function Stat({ label, value, icon, tone }) {
  const { s, c } = useTheme();
  return (
    <View style={s.stat}>
      <View style={[s.row, { gap: SPACE(1.5), marginBottom: SPACE(1) }]}>
        {icon ? <Ionicons name={icon} size={16} color={tone ? c.statusText[tone] : c.accentText} /> : null}
        <Text style={[s.caption, { flexShrink: 1 }]} numberOfLines={2}>{label}</Text>
      </View>
      <Text style={s.statValue} numberOfLines={1} adjustsFontSizeToFit maxFontSizeMultiplier={1.3}>{value}</Text>
    </View>
  );
}

// ---------------------------------------------------------------- botões e ações

export function Button({
  title, onPress, kind = 'primary', icon, disabled, loading, style, haptics = true, accessibilityLabel, compact,
}) {
  const { c, font, radius } = useTheme();
  const k = kind === 'accent' ? 'secondary' : kind;
  const look = {
    primary: { bg: c.accentFill, pressed: c.accentPressed, fg: c.onAccent, border: c.accentFill },
    secondary: { bg: c.accentSoft, pressed: c.accentSoft, fg: c.accentText, border: c.accentText },
    ghost: { bg: 'transparent', pressed: c.neutralBg, fg: c.text, border: c.border },
    danger: { bg: c.statusBg.danger, pressed: c.statusBg.danger, fg: c.statusText.danger, border: c.statusText.danger },
  }[k];
  const off = disabled || loading;
  return (
    <Pressable
      onPress={() => { if (haptics && k !== 'ghost') haptic.tap(); onPress && onPress(); }}
      disabled={off} accessibilityRole="button" accessibilityLabel={accessibilityLabel || title}
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      style={({ pressed }) => [{
        flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACE(2),
        borderRadius: radius.input + 2, minHeight: compact ? 40 : 52, paddingHorizontal: SPACE(compact ? 3 : 4),
        paddingVertical: SPACE(compact ? 2 : 3), marginBottom: compact ? 0 : SPACE(2.5), borderWidth: 1.5,
        backgroundColor: pressed ? look.pressed : look.bg, borderColor: look.border, opacity: off && !loading ? 0.45 : 1,
      }, style]}>
      {loading ? <ActivityIndicator color={look.fg} /> : icon ? <Ionicons name={icon} size={20} color={look.fg} /> : null}
      <Text style={{ color: look.fg, fontFamily: font.bold, fontSize: compact ? 15 : 17, flexShrink: 1, textAlign: 'center' }}
            maxFontSizeMultiplier={1.4}>
        {title}
      </Text>
    </Pressable>
  );
}

// Botão só com ícone: sempre com accessibilityLabel e área de toque de 48 px
export function IconButton({ icon, onPress, label, color, size = 26, style }) {
  const { c } = useTheme();
  return (
    <Pressable onPress={() => { haptic.tap(); onPress(); }} accessibilityRole="button" accessibilityLabel={label}
               hitSlop={4} style={({ pressed }) => [{
                 width: TOUCH, height: TOUCH, alignItems: 'center', justifyContent: 'center', borderRadius: TOUCH / 2,
                 backgroundColor: pressed ? c.neutralBg : 'transparent',
               }, style]}>
      <Ionicons name={icon} size={size} color={color || c.accentText} />
    </Pressable>
  );
}

// ---------------------------------------------------------------- formulários

const onlyDigits = (v) => String(v || '').replace(/\D/g, '');

// (31) 99999-8888 enquanto digita (aceita colar com +55)
export function maskPhone(v) {
  let d = onlyDigits(v);
  if (d.length > 11 && d.startsWith('55')) d = d.slice(2);
  d = d.slice(0, 11);
  if (d.length <= 2) return d ? `(${d}` : '';
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
}

// Dinheiro digitado da direita para a esquerda: "4", "40", "4000" -> "40,00"; com milhar: "1.234,56"
export function maskMoney(v) {
  const raw = onlyDigits(v);
  if (!raw) return '';
  const d = raw.replace(/^0+/, '').slice(0, 9) || '0';
  const cents = d.padStart(3, '0');
  const int = cents.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${int},${cents.slice(-2)}`;
}

const MASKS = {
  phone: { fn: maskPhone, keyboardType: 'phone-pad', placeholder: '(31) 99999-8888' },
  money: { fn: maskMoney, keyboardType: 'number-pad', placeholder: '0,00' },
};

export function Field({ label, hint, error, mask, onChangeText, value, prefix, style, ...props }) {
  const { c, s, font } = useTheme();
  const [focus, setFocus] = useState(false);
  const m = MASKS[mask];
  const shown = m && value ? m.fn(value) : value;
  return (
    <View style={[{ marginBottom: SPACE(4) }, style]}>
      {label ? <Text style={s.label}>{label}</Text> : null}
      <View style={[s.row, s.input, { paddingVertical: 0 },
                    focus && { borderColor: c.accentText, borderWidth: 2 }, error && { borderColor: c.statusText.danger }]}>
        {prefix || (mask === 'money' ? <Text style={[s.body, { color: c.textMuted, marginRight: SPACE(1) }]}>R$</Text> : null)}
        <TextInput
          placeholderTextColor={c.textMuted} accessibilityLabel={label || props.placeholder}
          keyboardType={m?.keyboardType} placeholder={m?.placeholder}
          {...props}
          value={shown}
          onChangeText={(t) => onChangeText && onChangeText(m ? m.fn(t) : t)}
          onFocus={(e) => { setFocus(true); props.onFocus && props.onFocus(e); }}
          onBlur={(e) => { setFocus(false); props.onBlur && props.onBlur(e); }}
          style={[{ flex: 1, minHeight: 46, fontSize: 17, fontFamily: font.regular, color: c.text, paddingVertical: SPACE(2.5) },
                  props.multiline && { minHeight: 88, textAlignVertical: 'top' }]}
          maxFontSizeMultiplier={1.5}
        />
      </View>
      {error ? <Text style={[s.caption, { color: c.statusText.danger, marginTop: SPACE(1) }]}>{error}</Text> : null}
      {hint && !error ? <Text style={[s.caption, { marginTop: SPACE(1) }]}>{hint}</Text> : null}
    </View>
  );
}

export function Toggle({ label, value, onValueChange, hint, disabled }) {
  const { c, s } = useTheme();
  return (
    <Pressable onPress={() => !disabled && onValueChange(!value)} accessibilityRole="switch"
               accessibilityState={{ checked: !!value, disabled: !!disabled }} accessibilityLabel={label}
               style={{ marginBottom: SPACE(3), opacity: disabled ? 0.5 : 1 }}>
      <View style={[s.row, { minHeight: TOUCH, gap: SPACE(3) }]}>
        <Text style={[s.body, { flex: 1 }]}>{label}</Text>
        <Switch value={!!value} onValueChange={onValueChange} disabled={disabled}
                trackColor={{ true: c.accentFill, false: c.border }} thumbColor={value ? c.onAccent : c.surface}
                ios_backgroundColor={c.border} />
      </View>
      {hint ? <Text style={s.caption}>{hint}</Text> : null}
    </Pressable>
  );
}

export function Chips({ options, value, onChange, multi = false }) {
  const { c, font } = useTheme();
  const isOn = (v) => (multi ? (value || []).includes(v) : value === v);
  const toggle = (v) => {
    haptic.tap();
    if (!multi) return onChange(v);
    const cur = value || [];
    return onChange(cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]);
  };
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: SPACE(2), marginBottom: SPACE(4) }}>
      {options.map((o) => {
        const on = isOn(o.value);
        return (
          <Pressable key={String(o.value)} onPress={() => toggle(o.value)} hitSlop={4}
                     accessibilityRole={multi ? 'checkbox' : 'radio'} accessibilityState={{ checked: on }}
                     style={{
                       flexDirection: 'row', alignItems: 'center', gap: SPACE(1.5), minHeight: 44,
                       borderWidth: on ? 2 : 1, borderColor: on ? c.accentText : c.border, borderRadius: 999,
                       paddingHorizontal: SPACE(4), backgroundColor: on ? c.accentSoft : c.surface,
                     }}>
            {on ? <Ionicons name="checkmark" size={16} color={c.accentText} /> : null}
            <Text style={{ fontSize: 15, fontFamily: on ? font.bold : font.medium, color: on ? c.accentText : c.text }}
                  maxFontSizeMultiplier={1.4}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function SegmentedControl({ options, value, onChange, style }) {
  const { c, font, radius } = useTheme();
  return (
    <View accessibilityRole="tablist" style={[{
      flexDirection: 'row', backgroundColor: c.surface, borderRadius: radius.input + 2, padding: 4,
      borderWidth: 1, borderColor: c.border, marginBottom: SPACE(3),
    }, style]}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable key={o.value} onPress={() => { haptic.tap(); onChange(o.value); }} accessibilityRole="tab"
                     accessibilityState={{ selected: on }} accessibilityLabel={o.label}
                     style={{
                       flex: 1, minHeight: 44, borderRadius: radius.input, alignItems: 'center', justifyContent: 'center',
                       flexDirection: 'row', gap: SPACE(1.5), backgroundColor: on ? c.accentFill : 'transparent',
                     }}>
            {o.icon ? <Ionicons name={o.icon} size={16} color={on ? c.onAccent : c.textMuted} /> : null}
            <Text style={{ fontFamily: font.bold, fontSize: 15, color: on ? c.onAccent : c.textMuted }}
                  numberOfLines={1} maxFontSizeMultiplier={1.3}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function ListRow({ icon, title, subtitle, right, onPress, first, last }) {
  const { c, s } = useTheme();
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : undefined}
               android_ripple={{ color: c.neutralBg }}
               style={({ pressed }) => [s.row, {
                 minHeight: 60, paddingVertical: SPACE(3), paddingHorizontal: SPACE(4), backgroundColor: c.surface,
                 borderBottomWidth: last ? 0 : 1, borderBottomColor: c.divider, gap: SPACE(3.5),
                 borderTopLeftRadius: first ? 14 : 0, borderTopRightRadius: first ? 14 : 0,
               }, pressed && { backgroundColor: c.surfaceElevated }]}>
      {icon ? <Ionicons name={icon} size={24} color={c.accentText} /> : null}
      <View style={{ flex: 1 }}>
        <Text style={s.body}>{title}</Text>
        {subtitle ? <Text style={[s.muted, { marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right ?? (onPress ? <Ionicons name="chevron-forward" size={20} color={c.textMuted} /> : null)}
    </Pressable>
  );
}

// Lista agrupada (cantos arredondados) para ListRow
export function Group({ children, style }) {
  const { c } = useTheme();
  return (
    <View style={[{ borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: c.divider,
                    marginBottom: SPACE(4) }, style]}>
      {children}
    </View>
  );
}

// ---------------------------------------------------------------- status

// info: { label, tone: success|warning|danger|info|neutral|accent, icon? }
export function Badge({ info, large }) {
  const { c, font } = useTheme();
  if (!info) return null;
  const tone = info.tone || 'neutral';
  const fg = tone === 'accent' ? c.accentText : c.statusText[tone];
  const bg = tone === 'accent' ? c.accentSoft : tone === 'neutral' ? c.neutralBg : c.statusBg[tone];
  return (
    <View style={{
      flexDirection: 'row', alignItems: 'center', gap: 4, borderRadius: 999, backgroundColor: bg,
      paddingHorizontal: SPACE(2.5), paddingVertical: large ? 6 : 3, alignSelf: 'flex-start',
    }}>
      {info.icon ? <Ionicons name={info.icon} size={large ? 15 : 13} color={fg} /> : null}
      <Text style={{ fontSize: large ? 15 : 13, fontFamily: font.semibold, color: fg }} maxFontSizeMultiplier={1.4}>
        {info.label}
      </Text>
    </View>
  );
}

// Faixa de aviso. tone "warning" = laranja cheio (Pix pendente); os demais usam fundo suave.
export function Banner({ tone = 'info', icon, title, text, onPress, accessibilityLabel }) {
  const { c, s, font } = useTheme();
  const solid = tone === 'warning';
  const fg = solid ? c.onWarning : tone === 'accent' ? c.accentText : c.statusText[tone];
  const bg = solid ? c.status.warning : tone === 'accent' ? c.accentSoft : c.statusBg[tone];
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole={onPress ? 'button' : 'text'}
               accessibilityLabel={accessibilityLabel || [title, text].filter(Boolean).join('. ')}
               style={({ pressed }) => [s.row, {
                 backgroundColor: bg, borderRadius: 14, padding: SPACE(4), marginBottom: SPACE(3), gap: SPACE(3),
                 minHeight: 56, opacity: pressed ? 0.85 : 1,
               }]}>
      {icon ? <Ionicons name={icon} size={24} color={fg} /> : null}
      <View style={{ flex: 1 }}>
        {title ? <Text style={{ color: fg, fontFamily: font.bold, fontSize: 17 }}>{title}</Text> : null}
        {text ? <Text style={{ color: fg, fontFamily: font.medium, fontSize: 15, marginTop: title ? 2 : 0 }}>{text}</Text> : null}
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={22} color={fg} /> : null}
    </Pressable>
  );
}

// ---------------------------------------------------------------- carregamento e vazio

export function Skeleton({ height = 16, width = '100%', radius = 8, style }) {
  const { c } = useTheme();
  const v = useRef(new Animated.Value(0.4)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(v, { toValue: 1, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      Animated.timing(v, { toValue: 0.4, duration: 700, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [v]);
  return <Animated.View style={[{ height, width, borderRadius: radius, backgroundColor: c.surfaceElevated, opacity: v }, style]} />;
}

// Cards de esqueleto no lugar da lista enquanto carrega
export function SkeletonList({ rows = 4, height = 72 }) {
  const { s } = useTheme();
  return (
    <View accessibilityLabel="Carregando" accessibilityRole="progressbar">
      {Array.from({ length: rows }, (_, i) => (
        <View key={i} style={[s.card, s.row, { gap: SPACE(3) }]}>
          <Skeleton width={56} height={height - 32} />
          <View style={{ flex: 1, gap: SPACE(2) }}>
            <Skeleton width="70%" />
            <Skeleton width="45%" height={12} />
          </View>
        </View>
      ))}
    </View>
  );
}

// Estado vazio: símbolo SyncServ neutro com o ícone do segmento, frase curta e uma ação
export function Empty({ text, icon, action }) {
  const { c, s, niche } = useTheme();
  const nicheIcon = icon || NICHE_INFO[niche]?.icon || 'calendar';
  return (
    <View style={s.empty}>
      <View style={{ width: 72, height: 72, alignItems: 'center', justifyContent: 'center' }}>
        <BrandSymbol size={64} color={c.border} />
        <View style={{
          position: 'absolute', right: -6, bottom: -6, width: 34, height: 34, borderRadius: 17,
          backgroundColor: c.accentSoft, alignItems: 'center', justifyContent: 'center',
        }}>
          <Ionicons name={nicheIcon} size={18} color={c.accentText} />
        </View>
      </View>
      <Text style={[s.muted, { marginTop: SPACE(4), textAlign: 'center', fontSize: 16 }]}>{text}</Text>
      {action ? (
        <Button title={action.title} icon={action.icon} kind="secondary" onPress={action.onPress}
                style={{ marginTop: SPACE(4), alignSelf: 'stretch' }} />
      ) : null}
    </View>
  );
}

export function Loading({ error, onRetry, rows = 3 }) {
  const { s, c } = useTheme();
  if (!error) return <View style={{ padding: SPACE(4) }}><SkeletonList rows={rows} /></View>;
  return (
    <View style={s.empty}>
      <Ionicons name="cloud-offline-outline" size={40} color={c.textMuted} />
      <Text style={[s.muted, { textAlign: 'center', marginVertical: SPACE(3) }]}>{error}</Text>
      {onRetry ? <Button title="Tentar de novo" kind="ghost" icon="refresh" onPress={onRetry} /> : null}
    </View>
  );
}

// ---------------------------------------------------------------- bottom sheet

// Modal que sobe de baixo, com fundo escurecido, alça e fechar ao tocar fora
export function BottomSheet({ visible, onClose, title, children, footer, scroll = true }) {
  const { c, s, radius } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  const y = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(y, { toValue: 1, duration: 240, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start();
    } else if (mounted) {
      Animated.timing(y, { toValue: 0, duration: 180, easing: Easing.in(Easing.cubic), useNativeDriver: true })
        .start(() => setMounted(false));
    }
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!mounted) return null;
  const Body = scroll ? ScrollView : View;
  return (
    <Modal transparent visible animationType="none" onRequestClose={onClose} statusBarTranslucent navigationBarTranslucent>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <Animated.View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: c.overlay, opacity: y }}>
          <Pressable style={{ flex: 1 }} onPress={onClose} accessibilityRole="button" accessibilityLabel="Fechar" />
        </Animated.View>
        <View style={{ flex: 1 }} pointerEvents="box-none" />
        <Animated.View style={{
          backgroundColor: c.surfaceElevated, borderTopLeftRadius: radius.sheet, borderTopRightRadius: radius.sheet,
          maxHeight: '88%', paddingBottom: footer ? 0 : insets.bottom + SPACE(2),
          transform: [{ translateY: y.interpolate({ inputRange: [0, 1], outputRange: [600, 0] }) }],
        }}>
          <View style={{ alignItems: 'center', paddingTop: SPACE(2.5) }}>
            <View style={{ width: 40, height: 5, borderRadius: 3, backgroundColor: c.border }} />
          </View>
          <View style={[s.row, { paddingHorizontal: SPACE(4), paddingTop: SPACE(2), minHeight: TOUCH }]}>
            <Text style={[s.heading, { flex: 1 }]} accessibilityRole="header">{title}</Text>
            <IconButton icon="close" label="Fechar" color={c.textMuted} onPress={onClose} />
          </View>
          <Body style={{ flexGrow: 0 }} contentContainerStyle={{ padding: SPACE(4), paddingTop: SPACE(2) }}
                keyboardShouldPersistTaps="handled">
            {children}
          </Body>
          {footer ? (
            <View style={{
              paddingHorizontal: SPACE(4), paddingTop: SPACE(3), paddingBottom: insets.bottom + SPACE(3),
              borderTopWidth: 1, borderTopColor: c.divider,
            }}>
              {footer}
            </View>
          ) : null}
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
