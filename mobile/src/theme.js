// Design system SyncServ: marca-base + um tema por segmento do negócio.
// Arquivo sem dependências do React Native: o teste de contraste (tests/contrast.test.mjs) roda no Node.
//
// Tokens de cor de cada tema:
//   background, surface, surfaceElevated  fundos (tela, cards, sheet/menus)
//   border        contorno de controles (inputs, chips, botões secundários): 3:1 contra background, surface e
//                 surfaceElevated (fundo dos bottom sheets)
//   divider       separadores e contornos decorativos (pode ter contraste baixo, nunca é o único sinal)
//   text, textMuted   texto principal e secundário: 4.5:1 contra background, surface e surfaceElevated
//   accent        cor do segmento como preenchimento: barras, indicadores e o símbolo do header (logo é isento
//                 de contraste). Ícones, contornos de seleção e textos em destaque usam accentText.
//   accentPressed accent pressionado
//   accentFill    fundo dos botões principais: igual ao accent, exceto quando nenhum texto alcança 4.5:1 sobre
//                 ele (azul #0284C7 da clínica e da marca-base: usa #0369A1)
//   onAccent      texto sobre accentFill (4.5:1)
//   accentText    accent usado como TEXTO sobre o fundo (versão mais escura nos temas claros)

export const NICHES = ['barbershop', 'beauty', 'petshop', 'clinic', 'fitness'];
export const THEME_MODES = ['auto', 'dark', 'light'];

export const NICHE_INFO = {
  barbershop: { label: 'Barbearia', icon: 'cut', mode: 'dark', accent: '#F59E0B' },
  beauty: { label: 'Salão de beleza e estética', icon: 'flower', mode: 'light', accent: '#EC4899' },
  petshop: { label: 'Pet shop', icon: 'paw', mode: 'light', accent: '#06B6D4' },
  clinic: { label: 'Clínica e consultório', icon: 'medkit', mode: 'light', accent: '#0284C7' },
  fitness: { label: 'Estúdio fitness', icon: 'barbell', mode: 'dark', accent: '#84CC16' },
};

// Cores de status: as mesmas em todos os temas (o profissional não precisa reaprender).
export const STATUS_COLORS = {
  success: '#22C55E', // Pix confirmado, pago, confirmado
  warning: '#F97316', // Pix pendente
  danger: '#EF4444', // erro, cancelado, faltou, bloqueado
  info: '#0284C7', // informação, agendado
};
// Texto e ícones de status (badge = cor cheia a 15% de fundo): a cor cheia não passa 4.5:1 em todos os fundos,
// então o texto usa um tom mais claro da mesma família no escuro e mais escuro no claro.
const STATUS_TEXT = {
  dark: { success: '#4ADE80', warning: '#FDBA74', danger: '#FCA5A5', info: '#7DD3FC', neutral: '#CBD5E1' },
  light: { success: '#166534', warning: '#9A3412', danger: '#B91C1C', info: '#0369A1', neutral: '#334155' },
};
// Texto sobre a cor cheia de aviso (banner laranja de Pix pendente)
const ON_WARNING = '#1C1917';
// Faixa cheia de erro: o vermelho de status (#EF4444) com texto branco dá 3,76:1; o fundo cheio usa um tom mais escuro
const DANGER_FILL = '#B91C1C';
const ON_DANGER = '#FFFFFF';
export const BADGE_ALPHA = 0.15;

// Superfícies de cada segmento no modo dele (tabela da marca) e as derivadas para o modo oposto
const NATIVE = {
  barbershop: {
    background: '#121212', surface: '#1E1E1E', surfaceElevated: '#2A2A2A', border: '#747474', divider: '#2E2E2E',
    text: '#F5F5F5', textMuted: '#A3A3A3',
  },
  fitness: {
    background: '#18181B', surface: '#27272A', surfaceElevated: '#3F3F46', border: '#8B8B92', divider: '#3F3F46',
    text: '#FAFAFA', textMuted: '#B4B4BC',
  },
  beauty: {
    background: '#FAF5F5', surface: '#FFFFFF', surfaceElevated: '#FFFFFF', border: '#877F83', divider: '#EFE4E6',
    text: '#1F1A1C', textMuted: '#6B5F63',
  },
  petshop: {
    background: '#F8FAFC', surface: '#FFFFFF', surfaceElevated: '#FFFFFF', border: '#7C8794', divider: '#E2E8F0',
    text: '#0F172A', textMuted: '#556170',
  },
  clinic: {
    background: '#F0FDFA', surface: '#FFFFFF', surfaceElevated: '#FFFFFF', border: '#7A8896', divider: '#D5EFEA',
    text: '#0F2A2E', textMuted: '#4F6463',
  },
};
const DERIVED_DARK = {
  background: '#111214', surface: '#1C1D21', surfaceElevated: '#26282D', border: '#6F727A', divider: '#2C2E33',
  text: '#F5F5F7', textMuted: '#A4A7AE',
};
const DERIVED_LIGHT = {
  background: '#F7F7F5', surface: '#FFFFFF', surfaceElevated: '#FFFFFF', border: '#858585', divider: '#E7E5E0',
  text: '#171717', textMuted: '#5F5F5F',
};

// Variações do accent por segmento e modo
const ACCENTS = {
  barbershop: {
    dark: { accent: '#F59E0B', accentPressed: '#D97706', accentFill: '#F59E0B', onAccent: '#121212', accentText: '#F59E0B' },
    light: { accent: '#F59E0B', accentPressed: '#D97706', accentFill: '#F59E0B', onAccent: '#1C1917', accentText: '#92400E' },
  },
  beauty: {
    dark: { accent: '#EC4899', accentPressed: '#F472B6', accentFill: '#EC4899', onAccent: '#1F1A1C', accentText: '#F472B6' },
    light: { accent: '#EC4899', accentPressed: '#F472B6', accentFill: '#EC4899', onAccent: '#1F1A1C', accentText: '#BE185D' },
  },
  petshop: {
    dark: { accent: '#06B6D4', accentPressed: '#0891B2', accentFill: '#06B6D4', onAccent: '#0F172A', accentText: '#22D3EE' },
    light: { accent: '#06B6D4', accentPressed: '#0891B2', accentFill: '#06B6D4', onAccent: '#0F172A', accentText: '#0E7490' },
  },
  clinic: {
    dark: { accent: '#0284C7', accentPressed: '#075985', accentFill: '#0369A1', onAccent: '#FFFFFF', accentText: '#38BDF8' },
    light: { accent: '#0284C7', accentPressed: '#075985', accentFill: '#0369A1', onAccent: '#FFFFFF', accentText: '#0369A1' },
  },
  fitness: {
    dark: { accent: '#84CC16', accentPressed: '#65A30D', accentFill: '#84CC16', onAccent: '#18181B', accentText: '#84CC16' },
    light: { accent: '#84CC16', accentPressed: '#65A30D', accentFill: '#84CC16', onAccent: '#1A2E05', accentText: '#4D7C0F' },
  },
};

// Marca-base SyncServ (login e telas sem negócio carregado). A "borda" #334155 da marca é o divider;
// controles usam #707F94 para chegar a 3:1 também sobre surfaceElevated.
const BRAND_COLORS = {
  background: '#0F172A', surface: '#1E293B', surfaceElevated: '#273449', border: '#707F94', divider: '#334155',
  text: '#F8FAFC', textMuted: '#94A3B8',
  accent: '#0284C7', accentPressed: '#075985', accentFill: '#0369A1', onAccent: '#FFFFFF', accentText: '#38BDF8',
  secondary: '#22C55E',
};

// Na web, cada peso ganha uma fonte reserva com as mesmas medidas (src/webFonts.web.js) e a do sistema: a primeira
// tela aparece antes de a Plus Jakarta Sans chegar, sem o texto pular na troca
const WEB = typeof document !== 'undefined';
const face = (family, weight) => (WEB ? `${family}, "Jakarta Reserva ${weight}", System` : family);
export const FONTS = {
  regular: face('PlusJakartaSans_400Regular', 400),
  medium: face('PlusJakartaSans_500Medium', 500),
  semibold: face('PlusJakartaSans_600SemiBold', 600),
  bold: face('PlusJakartaSans_700Bold', 700),
  extrabold: face('PlusJakartaSans_800ExtraBold', 800),
};
// Escala tipográfica 32/24/20/17/15/13
export const TYPE = { display: 32, title: 24, heading: 20, body: 17, label: 15, caption: 13 };
export const SPACE = (n) => n * 4; // múltiplos de 4
export const RADIUS = { input: 10, card: 14, sheet: 20, pill: 999 };
export const TOUCH = 48; // alvo de toque mínimo

// "#RRGGBB" + alpha (0..1) -> "#RRGGBBAA"
export function withAlpha(hex, a) {
  return hex + Math.round(a * 255).toString(16).padStart(2, '0').toUpperCase();
}

// Mistura fg sobre bg com opacidade a (para medir o contraste de fundos translúcidos)
export function blend(fg, bg, a) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const f = p(fg);
  const b = p(bg);
  return '#' + f.map((x, i) => Math.round(x * a + b[i] * (1 - a)).toString(16).padStart(2, '0')).join('').toUpperCase();
}

function luminance(hex) {
  const ch = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}

function finish(key, niche, mode, colors) {
  const statusText = STATUS_TEXT[mode];
  const c = {
    ...colors,
    accentSoft: withAlpha(colors.accent, BADGE_ALPHA),
    overlay: mode === 'dark' ? 'rgba(0,0,0,0.6)' : 'rgba(15,23,42,0.45)',
    status: STATUS_COLORS,
    statusText,
    statusBg: Object.fromEntries(Object.entries(STATUS_COLORS).map(([k, v]) => [k, withAlpha(v, BADGE_ALPHA)])),
    neutralBg: mode === 'dark' ? '#FFFFFF1A' : '#0F172A12',
    onWarning: ON_WARNING,
    dangerFill: DANGER_FILL,
    onDanger: ON_DANGER,
    qrBackground: '#FFFFFF', // o QR Code precisa de fundo branco para ser lido, em qualquer tema
  };
  return { key, niche, mode, c, font: FONTS, type: TYPE, radius: RADIUS };
}

export const BRAND_THEME = finish('brand', null, 'dark', BRAND_COLORS);

// Tema do negócio: segmento + theme_mode ("auto" usa o modo do segmento)
export function buildTheme(niche, themeMode = 'auto') {
  const n = NICHE_INFO[niche] ? niche : 'barbershop';
  const native = NICHE_INFO[n].mode;
  const mode = themeMode === 'dark' || themeMode === 'light' ? themeMode : native;
  const surfaces = mode === native ? NATIVE[n] : mode === 'dark' ? DERIVED_DARK : DERIVED_LIGHT;
  return finish(`${n}-${mode}`, n, mode, { ...surfaces, ...ACCENTS[n][mode] });
}

// Todas as combinações (para o teste de contraste e a tela de Aparência)
export function allThemes() {
  return [BRAND_THEME, ...NICHES.flatMap((n) => ['dark', 'light'].map((m) => buildTheme(n, m)))];
}
