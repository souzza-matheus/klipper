import React, { useEffect, useState } from 'react';
import { Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Wordmark } from '../brand/Logo';
import { label as keypadLabel, press } from '../keypad';
import { moreItemsFor, ROLE_LABEL, SHORTCUTS, can } from '../roles';
import { filterRows, nextSort, sortRows } from '../table';
import { SPACE, TOUCH } from '../theme';
import { useTheme } from '../ThemeProvider';
import { haptic } from '../ui';

export const SIDEBAR_WIDTH = 260;

// ---------------------------------------------------------------- menu lateral (computador)

function SideItem({ icon, label, focused, onPress, small }) {
  const { c, font } = useTheme();
  const [hover, setHover] = useState(false);
  return (
    <Pressable onPress={onPress} onHoverIn={() => setHover(true)} onHoverOut={() => setHover(false)}
               accessibilityRole="link" accessibilityState={{ selected: focused }} accessibilityLabel={label}
               style={{
                 flexDirection: 'row', alignItems: 'center', gap: SPACE(3), minHeight: small ? 40 : 46,
                 paddingHorizontal: SPACE(3), borderRadius: 10, marginBottom: 2,
                 backgroundColor: focused ? c.accentSoft : hover ? c.neutralBg : 'transparent',
               }}>
      <Ionicons name={icon + (focused || small ? '' : '-outline')} size={small ? 18 : 22}
                color={focused ? c.accentText : c.textMuted} />
      <Text style={{ fontFamily: focused ? font.bold : font.medium, fontSize: small ? 14 : 16,
                     color: focused ? c.accentText : c.text }} numberOfLines={1}>{label}</Text>
    </Pressable>
  );
}

// tabBar do navegador de abas quando a tela é larga: logo, abas, "Gestão" (itens do Mais) e atalhos
export function Sidebar({ state, navigation, descriptors, role, shopName, userName }) {
  const { c, font, v, mode } = useTheme();
  const more = moreItemsFor(role, v, Platform.OS === 'web').filter((m) => !['About', 'ChangePassword'].includes(m.route));
  const current = state.routes[state.index];
  const nested = current.state ? current.state.routes[current.state.index]?.name : null;
  const shortcuts = Platform.OS === 'web' ? SHORTCUTS.filter((s) => can(role, s.feature)) : [];
  return (
    <View style={{ width: SIDEBAR_WIDTH, backgroundColor: c.surface, borderRightWidth: 1, borderRightColor: c.divider }}>
      <ScrollView contentContainerStyle={{ padding: SPACE(4), paddingBottom: SPACE(6) }}>
        <View style={{ marginBottom: SPACE(2), marginTop: SPACE(1) }}>
          <Wordmark height={30} variant={mode === 'light' ? 'light' : 'dark'} />
        </View>
        <Text style={{ fontFamily: font.bold, fontSize: 15, color: c.text, marginTop: SPACE(3) }} numberOfLines={2}>
          {shopName}
        </Text>
        <Text style={{ fontFamily: font.medium, fontSize: 13, color: c.textMuted, marginBottom: SPACE(5) }}
              numberOfLines={1}>
          {userName} · {ROLE_LABEL[role]}
        </Text>
        {state.routes.filter((r) => r.name !== 'Mais').map((r) => {
          const i = state.routes.indexOf(r);
          const opts = descriptors[r.key].options;
          return (
            <SideItem key={r.key} icon={opts.sideIcon} label={opts.tabBarLabel || r.name} focused={state.index === i}
                      onPress={() => navigation.navigate(r.name)} />
          );
        })}
        <Text style={{ fontFamily: font.bold, fontSize: 12, color: c.textMuted, textTransform: 'uppercase',
                       letterSpacing: 0.6, marginTop: SPACE(5), marginBottom: SPACE(2), paddingHorizontal: SPACE(3) }}>
          Gestão
        </Text>
        {more.map((m) => (
          <SideItem key={m.route} small icon={m.icon.replace('-outline', '')} label={m.label}
                    focused={current.name === 'Mais' && nested === m.route}
                    onPress={() => navigation.navigate('Mais', { screen: m.route, initial: false })} />
        ))}
        <SideItem small icon="ellipsis-horizontal" label="Mais opções" focused={current.name === 'Mais' && nested === 'MoreHome'}
                  onPress={() => navigation.navigate('Mais', { screen: 'MoreHome' })} />
        {shortcuts.length ? (
          <View style={{ marginTop: SPACE(5), paddingHorizontal: SPACE(3) }}>
            <Text style={{ fontFamily: font.bold, fontSize: 12, color: c.textMuted, textTransform: 'uppercase',
                           letterSpacing: 0.6, marginBottom: SPACE(2) }}>Atalhos</Text>
            {shortcuts.map((s) => (
              <View key={s.key} style={{ flexDirection: 'row', alignItems: 'center', gap: SPACE(2), marginBottom: 6 }}>
                <View style={{ borderWidth: 1, borderColor: c.border, borderRadius: 6, minWidth: 24, alignItems: 'center',
                               paddingHorizontal: 6, paddingVertical: 1 }}>
                  <Text style={{ fontFamily: font.bold, fontSize: 12, color: c.text }}>{s.key.toUpperCase()}</Text>
                </View>
                <Text style={{ fontFamily: font.medium, fontSize: 13, color: c.textMuted }}>{s.label}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

// ---------------------------------------------------------------- sem conexão

// Web: funciona só online; sem internet, avisa e as alterações ficam bloqueadas (a API recusa no api.js)
// Navegador: segue os eventos online/offline (o app nativo ganha o modo offline completo na Etapa 3)
export function useBrowserOnline() {
  const get = () => (typeof navigator === 'undefined' ? true : navigator.onLine !== false);
  const [online, setOnline] = useState(get);
  useEffect(() => {
    if (Platform.OS !== 'web') return undefined;
    const update = () => setOnline(get());
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); };
  }, []);
  return online;
}

export function OfflineBanner() {
  const { c, font } = useTheme();
  const online = useBrowserOnline();
  if (Platform.OS !== 'web' || online) return null;
  return (
    <View accessibilityRole="alert" style={{
      flexDirection: 'row', alignItems: 'center', gap: SPACE(2), paddingHorizontal: SPACE(4), paddingVertical: SPACE(2.5),
      backgroundColor: c.status.warning,
    }}>
      <Ionicons name="cloud-offline-outline" size={20} color={c.onWarning} />
      <Text style={{ flex: 1, color: c.onWarning, fontFamily: font.bold, fontSize: 15 }}>
        Sem conexão. A versão web funciona só com internet: alterações estão bloqueadas até a conexão voltar.
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------- tabela (computador)

// columns: [{ key, label, width?, flex?, align?, render?(row), sortValue? }]
export function DataTable({ columns, rows, searchKeys, onRowPress, placeholder = 'Buscar', empty, initialSort }) {
  const { c, s, font } = useTheme();
  const [q, setQ] = useState('');
  const [sort, setSort] = useState(initialSort || { key: null, dir: 'asc' });
  const col = columns.find((x) => x.key === sort.key);
  const shown = sortRows(filterRows(rows, q, searchKeys || columns.map((x) => x.key)),
    col ? (col.sortValue || col.key) : null, sort.dir);
  return (
    <View>
      <View style={[s.row, s.input, { marginBottom: SPACE(3), gap: SPACE(2) }]}>
        <Ionicons name="search" size={18} color={c.textMuted} />
        <TextInput value={q} onChangeText={setQ} placeholder={placeholder} placeholderTextColor={c.textMuted}
                   accessibilityLabel={placeholder}
                   style={{ flex: 1, fontSize: 16, fontFamily: font.regular, color: c.text, minHeight: 32 }} />
      </View>
      <View style={{ borderWidth: 1, borderColor: c.divider, borderRadius: 14, overflow: 'hidden' }}>
        <View style={[s.row, { backgroundColor: c.surfaceElevated, paddingHorizontal: SPACE(3), minHeight: 44 }]}>
          {columns.map((x) => (
            <Pressable key={x.key} onPress={() => setSort(nextSort(sort, x.key))} accessibilityRole="button"
                       accessibilityLabel={`Ordenar por ${x.label}`}
                       style={{ flex: x.width ? undefined : (x.flex || 1), width: x.width, flexDirection: 'row',
                                alignItems: 'center', gap: 4, paddingVertical: SPACE(2), paddingRight: SPACE(2),
                                justifyContent: x.align === 'right' ? 'flex-end' : 'flex-start' }}>
              <Text style={[s.caption, { fontFamily: font.bold }]}>{x.label}</Text>
              {sort.key === x.key ? (
                <Ionicons name={sort.dir === 'asc' ? 'arrow-up' : 'arrow-down'} size={13} color={c.textMuted} />
              ) : null}
            </Pressable>
          ))}
        </View>
        {shown.map((r, i) => (
          <Pressable key={r.id ?? i} onPress={onRowPress ? () => onRowPress(r) : undefined} disabled={!onRowPress}
                     accessibilityRole={onRowPress ? 'button' : undefined}
                     style={({ hovered, pressed }) => [s.row, {
                       paddingHorizontal: SPACE(3), minHeight: 52, borderTopWidth: 1, borderTopColor: c.divider,
                       backgroundColor: pressed || hovered ? c.neutralBg : c.surface,
                     }]}>
            {columns.map((x) => (
              <View key={x.key} style={{ flex: x.width ? undefined : (x.flex || 1), width: x.width,
                                         paddingVertical: SPACE(2), paddingRight: SPACE(2),
                                         alignItems: x.align === 'right' ? 'flex-end' : 'flex-start' }}>
                {x.render ? x.render(r) : <Text style={s.body} numberOfLines={1}>{String(r[x.key] ?? '')}</Text>}
              </View>
            ))}
          </Pressable>
        ))}
        {!shown.length ? (
          <Text style={[s.muted, { padding: SPACE(4), textAlign: 'center' }]}>{empty || 'Nada encontrado.'}</Text>
        ) : null}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------- teclado numérico (comanda)

const KEYS = [['1', '2', '3'], ['4', '5', '6'], ['7', '8', '9'], ['00', '0', 'back']];

export function Keypad({ value, onChange }) {
  const { c, font, radius } = useTheme();
  return (
    <View>
      <View style={{ alignItems: 'flex-end', paddingVertical: SPACE(3), paddingHorizontal: SPACE(4), marginBottom: SPACE(3),
                     backgroundColor: c.surface, borderRadius: radius.input, borderWidth: 1, borderColor: c.border }}>
        <Text accessibilityLabel={`Valor ${keypadLabel(value)} reais`}
              style={{ fontFamily: font.extrabold, fontSize: 34, color: c.text }}>R$ {keypadLabel(value)}</Text>
      </View>
      {KEYS.map((row) => (
        <View key={row.join()} style={{ flexDirection: 'row', gap: SPACE(2), marginBottom: SPACE(2) }}>
          {row.map((k) => (
            <Pressable key={k} onPress={() => { haptic.tap(); onChange(press(value, k)); }}
                       onLongPress={k === 'back' ? () => onChange(press(value, 'clear')) : undefined}
                       accessibilityRole="button" accessibilityLabel={k === 'back' ? 'Apagar' : k}
                       style={({ pressed }) => ({
                         flex: 1, minHeight: 60, borderRadius: radius.input, alignItems: 'center', justifyContent: 'center',
                         backgroundColor: pressed ? c.accentSoft : c.surfaceElevated, borderWidth: 1, borderColor: c.divider,
                       })}>
              {k === 'back' ? <Ionicons name="backspace-outline" size={26} color={c.text} />
                : <Text style={{ fontFamily: font.bold, fontSize: 24, color: c.text }}>{k}</Text>}
            </Pressable>
          ))}
        </View>
      ))}
    </View>
  );
}

// Botões grandes (comanda): ícone + texto, em grade
export function BigButton({ icon, label, onPress, tone, selected, disabled }) {
  const { c, font, radius } = useTheme();
  const on = selected;
  return (
    <Pressable onPress={() => { haptic.tap(); onPress(); }} disabled={disabled} accessibilityRole="button"
               accessibilityLabel={label} accessibilityState={{ selected: !!on, disabled: !!disabled }}
               style={({ pressed }) => ({
                 flexBasis: '30%', flexGrow: 1, minHeight: 76, minWidth: TOUCH * 2, borderRadius: radius.card,
                 alignItems: 'center', justifyContent: 'center', gap: 6, padding: SPACE(2),
                 opacity: disabled ? 0.45 : 1, borderWidth: on ? 2 : 1,
                 borderColor: on ? c.accentText : tone === 'danger' ? c.statusText.danger : c.divider,
                 backgroundColor: on ? c.accentSoft : pressed ? c.neutralBg : c.surface,
               })}>
      <Ionicons name={icon} size={26} color={tone === 'danger' ? c.statusText.danger : c.accentText} />
      <Text style={{ fontFamily: font.bold, fontSize: 15, color: c.text, textAlign: 'center' }} numberOfLines={2}>
        {label}
      </Text>
    </Pressable>
  );
}
