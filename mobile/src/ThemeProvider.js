import React, { createContext, useContext, useMemo } from 'react';
import { StyleSheet } from 'react-native';
import { BRAND_THEME, buildTheme, SPACE } from './theme';
import { NEUTRAL, vocab } from './vocab';

// Estilos base de cada tema (cores, fonte e escala vêm dos tokens; nenhuma cor fixa nas telas)
export function makeStyles(t) {
  const { c, font, type, radius } = t;
  return StyleSheet.create({
    screenScroll: { flex: 1, backgroundColor: c.background },
    screen: { padding: SPACE(4), paddingBottom: SPACE(12), backgroundColor: c.background, flexGrow: 1 },
    card: {
      backgroundColor: c.surface, borderRadius: radius.card, padding: SPACE(4), marginBottom: SPACE(3),
      borderWidth: 1, borderColor: c.divider,
    },
    display: { fontFamily: font.extrabold, fontSize: type.display, color: c.text },
    title: { fontFamily: font.bold, fontSize: type.title, color: c.text, marginBottom: SPACE(2) },
    heading: { fontFamily: font.bold, fontSize: type.heading, color: c.text },
    section: {
      fontFamily: font.bold, fontSize: type.caption, color: c.textMuted, textTransform: 'uppercase', letterSpacing: 0.6,
    },
    label: { fontFamily: font.semibold, fontSize: type.label, color: c.text, marginBottom: SPACE(1.5) },
    body: { fontFamily: font.regular, fontSize: type.body, color: c.text },
    bodyBold: { fontFamily: font.bold, fontSize: type.body, color: c.text },
    strong: { fontFamily: font.bold },
    muted: { fontFamily: font.regular, fontSize: type.label, color: c.textMuted },
    caption: { fontFamily: font.medium, fontSize: type.caption, color: c.textMuted },
    accentText: { color: c.accentText },
    row: { flexDirection: 'row', alignItems: 'center' },
    input: {
      backgroundColor: c.surface, borderWidth: 1, borderColor: c.border, borderRadius: radius.input,
      paddingHorizontal: SPACE(3), paddingVertical: SPACE(3), minHeight: 48, fontSize: type.body,
      fontFamily: font.regular, color: c.text,
    },
    stat: {
      flex: 1, backgroundColor: c.surface, borderRadius: radius.card, padding: SPACE(3), borderWidth: 1,
      borderColor: c.divider, minHeight: 72, minWidth: 136, // 3 cards num celular de 375 px viram 2 + 1
    },
    statValue: { fontFamily: font.extrabold, fontSize: type.heading, color: c.text },
    empty: { alignItems: 'center', justifyContent: 'center', padding: SPACE(10) },
  });
}

const Ctx = createContext(null);

// niche e themeMode vêm do negócio logado; brand=true usa a marca-base (login)
export function ThemeProvider({ niche, themeMode, brand = false, setAppearance, children }) {
  const value = useMemo(() => {
    const t = brand ? BRAND_THEME : buildTheme(niche, themeMode);
    return {
      ...t, s: makeStyles(t), v: brand ? NEUTRAL : vocab(t.niche),
      themeMode: themeMode || 'auto', setAppearance: setAppearance || (() => {}),
    };
  }, [niche, themeMode, brand, setAppearance]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const t = useContext(Ctx);
  if (!t) throw new Error('useTheme precisa estar dentro do ThemeProvider');
  return t;
}
