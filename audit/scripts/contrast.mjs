// Contraste de combinações reais das telas (inclusive as que o tests/contrast.test.mjs não cobre) e da landing
import { allThemes, blend, contrast, STATUS_COLORS, BADGE_ALPHA } from '/home/souzza-matheus/barberbot/mobile/src/theme.js';
import { saveJson } from './common.mjs';

const rows = [];
const add = (scope, theme, what, fg, bg, min) => {
  const r = contrast(fg, bg);
  rows.push({ scope, theme, what, fg, bg, ratio: Number(r.toFixed(2)), min, ok: r >= min });
};
const flat = (hexA) => (hexA.length === 9 ? hexA.slice(0, 7) : hexA);
const alpha = (hexA) => (hexA.length === 9 ? parseInt(hexA.slice(7), 16) / 255 : 1);
const over = (hexA, bg) => blend(flat(hexA), bg, alpha(hexA));

for (const t of allThemes()) {
  const c = t.c;
  const k = t.key;
  // já cobertos pelo teste (confirmação)
  add('app', k, 'texto secundário (textMuted) na superfície', c.textMuted, c.surface, 4.5);
  add('app', k, 'accentText na superfície', c.accentText, c.surface, 4.5);
  // não cobertos
  add('app', k, 'borda de controle (chips, campos) no bottom sheet (surfaceElevated)', c.border, c.surfaceElevated, 3);
  add('app', k, 'placeholder/textMuted dentro de campo no sheet', c.textMuted, c.surface, 4.5);
  add('app', k, 'banner de sincronização com erro: onDanger sobre dangerFill (A10)', c.onDanger, c.dangerFill, 4.5);
  add('app', k, 'banner "pedido para aprovar": accentText sobre accentSoft no fundo', c.accentText, blend(c.accent, c.background, BADGE_ALPHA), 4.5);
  // A08: o bloco "agendado" usa info (o mesmo tom do selo), não a cor do segmento
  const apptBg = blend(STATUS_COLORS.info, c.surface, BADGE_ALPHA);
  add('app', k, 'bloco da agenda (agendado): texto 14px sobre info 15%', c.text, apptBg, 4.5);
  add('app', k, 'bloco da agenda: serviço 13px (textMuted) sobre info 15%', c.textMuted, apptBg, 4.5);
  const okBg = blend(STATUS_COLORS.success, c.surface, BADGE_ALPHA);
  add('app', k, 'bloco da agenda (confirmado): serviço 13px (textMuted) sobre verde 15%', c.textMuted, okBg, 4.5);
  const doneBg = over(c.neutralBg, c.surface);
  add('app', k, 'bloco da agenda (atendido): nome 14px (textMuted) sobre neutralBg', c.textMuted, doneBg, 4.5);
  add('app', k, 'barra lateral do bloco "atendido" (border) sobre neutralBg', c.border, doneBg, 3);
  add('app', k, 'fundo fora do expediente (neutralBg) x expediente (surface)', doneBg, c.surface, 1.2);
  add('app', k, 'hachura de bloqueio (divider) sobre background', c.divider, c.background, 3);
  add('app', k, 'barra de ocupação verde do mês (statusText) sobre a trilha (A26)', c.statusText.success, over(c.neutralBg, c.surface), 3);
  add('app', k, 'barra de ocupação laranja do mês (statusText) sobre a trilha (A26)', c.statusText.warning, over(c.neutralBg, c.surface), 3);
  add('app', k, 'dia fechado do calendário (textMuted, sem opacidade) sobre surface (A26)', c.textMuted, c.surface, 4.5);
  add('app', k, 'borda do toast info (statusText) sobre surfaceElevated', c.statusText.info, c.surfaceElevated, 3);
  add('app', k, 'borda do toast sucesso (statusText) sobre surfaceElevated', c.statusText.success, c.surfaceElevated, 3);
  add('app', k, 'interruptor desligado: trilha (border) x bolinha (surface)', c.border, c.surface, 3);
  add('app', k, 'símbolo do estado vazio (border) sobre background', c.border, c.background, 3);
  add('app', k, 'accent puro como ícone/indicador (BrandSymbol do topo, barra do bloco) sobre surface', c.accent, c.surface, 3);
  add('app', k, 'accent (marca) x warning (Pix pendente): diferença entre as duas cores', c.accent, STATUS_COLORS.warning, 1.5);
  add('app', k, 'divider dos cards sobre background (contorno do card)', c.divider, c.background, 1.5);
}

// Landing (styles.css)
const L = [
  ['texto de destaque do h1 (.hl #0284C7, texto grande) sobre o fundo', '#0284C7', '#0F172A', 3],
  ['número dos passos (.steps__n #0284C7, 36px) sobre #0F172A', '#0284C7', '#0F172A', 3],
  ['borda dos botões de nicho (--control #64748B) sobre o fundo (L09)', '#64748B', '#0F172A', 3],
  ['borda do botão "Ver como funciona" (.btn--ghost --control #64748B) (L09)', '#64748B', '#0F172A', 3],
  ['borda do botão de menu (--control #64748B) (L09)', '#64748B', '#0F172A', 3],
  ['texto secundário (#94A3B8) sobre #1E293B (seções alternadas)', '#94A3B8', '#1E293B', 4.5],
  ['texto secundário (#94A3B8) sobre #0F172A', '#94A3B8', '#0F172A', 4.5],
  ['CTA verde: #0F172A sobre #22C55E', '#0F172A', '#22C55E', 4.5],
  ['valor da calculadora (#22C55E) sobre #1E293B', '#22C55E', '#1E293B', 3],
  ['bolha do robô (#E9EDEF sobre #202C33)', '#E9EDEF', '#202C33', 4.5],
  ['nota do simulador (#AEBAC1 sobre #1F2C34, 12px)', '#AEBAC1', '#1F2C34', 4.5],
  ['opção do simulador: borda accent-text barbearia (#F59E0B) sobre #111B21', '#F59E0B', '#111B21', 3],
  ['mockup: texto cinza (#9CA3AF) sobre card #1E293B', '#9CA3AF', '#1E293B', 4.5],
  ['mockup: selo "Sinal pago" (#4ADE80) sobre verde 15% em #1E293B', '#4ADE80', blend('#22C55E', '#1E293B', 0.15), 4.5],
  ['mockup: selo "Aguardando sinal" (#FDBA74) sobre laranja 15%', '#FDBA74', blend('#F97316', '#1E293B', 0.15), 4.5],
  ['mockup: faixa offline (#422006 sobre #FDE68A)', '#422006', '#FDE68A', 4.5],
  ['mockup web: grupo "Gestão" (#94A3B8 sobre #0F172A, 11px) (L17)', '#94A3B8', '#0F172A', 4.5],
  ['plano em destaque: borda #0284C7 sobre #1E293B', '#0284C7', '#1E293B', 3],
  ['badge do topo (#38BDF8 sobre azul 15% em #0F172A)', '#38BDF8', blend('#0284C7', '#0F172A', 0.15), 4.5],
  ['link do rodapé (#F8FAFC sobre #0F172A)', '#F8FAFC', '#0F172A', 4.5],
  ['aviso das páginas legais (#FED7AA sobre laranja 12%)', '#FED7AA', blend('#F97316', '#0F172A', 0.12), 4.5],
];
for (const [what, fg, bg, min] of L) add('landing', 'landing', what, fg, bg, min);

saveJson('contraste', rows);
const fails = rows.filter((r) => !r.ok);
console.log(`total ${rows.length}, abaixo do mínimo ${fails.length}`);
const by = {};
for (const f of fails) (by[f.what] = by[f.what] || []).push(`${f.theme} ${f.ratio}`);
for (const [w, l] of Object.entries(by)) console.log(`- ${w}: ${l.join(', ')}`);
