// Contraste de todos os temas: 4.5:1 para texto e 3:1 para bordas e ícones (WCAG AA).
// Rodar com: npm test   (node --test)
import assert from 'node:assert/strict';
import test from 'node:test';
import { allThemes, blend, BADGE_ALPHA, contrast, STATUS_COLORS } from '../src/theme.js';

const TEXT = 4.5;
const UI = 3;

function check(theme, label, fg, bg, min) {
  const r = contrast(fg, bg);
  assert.ok(r >= min, `${theme.key}: ${label} ${fg} sobre ${bg} = ${r.toFixed(2)}:1 (mínimo ${min}:1)`);
}

for (const t of allThemes()) {
  const c = t.c;
  const grounds = { background: c.background, surface: c.surface, surfaceElevated: c.surfaceElevated };

  test(`${t.key}: textos`, () => {
    for (const [name, bg] of Object.entries(grounds)) {
      check(t, `text/${name}`, c.text, bg, TEXT);
      check(t, `textMuted/${name}`, c.textMuted, bg, TEXT);
      check(t, `accentText/${name}`, c.accentText, bg, TEXT);
    }
  });

  test(`${t.key}: botão principal`, () => {
    check(t, 'onAccent/accentFill', c.onAccent, c.accentFill, TEXT);
    check(t, 'onAccent/accentPressed', c.onAccent, c.accentPressed, TEXT);
  });

  test(`${t.key}: bordas, ícones e seleção`, () => {
    // surfaceElevated: chips e campos dentro dos bottom sheets
    for (const [name, bg] of Object.entries(grounds)) {
      check(t, `border/${name}`, c.border, bg, UI);
      // Ícones e contornos de seleção usam accentText (o accent puro é preenchimento e logo)
      check(t, `ícone accentText/${name}`, c.accentText, bg, UI);
    }
    // Chip selecionado: fundo accent a 15% com texto accentText
    check(t, 'accentText/accentSoft', c.accentText, blend(c.accent, c.surface, BADGE_ALPHA), TEXT);
  });

  test(`${t.key}: badges de status`, () => {
    for (const [k, color] of Object.entries(STATUS_COLORS)) {
      for (const [name, bg] of Object.entries(grounds)) {
        check(t, `badge ${k}/${name}`, c.statusText[k], blend(color, bg, BADGE_ALPHA), TEXT);
        check(t, `status ${k} como texto/${name}`, c.statusText[k], bg, TEXT);
      }
    }
    check(t, 'badge neutro/surface', c.statusText.neutral, c.surface, TEXT);
  });

  test(`${t.key}: banner de Pix pendente`, () => {
    check(t, 'onWarning/warning', c.onWarning, STATUS_COLORS.warning, TEXT);
  });

  test(`${t.key}: barras de ocupação do mês sobre a trilha`, () => {
    // trilha = neutralBg (#FFFFFF a 10% no escuro, #0F172A a 7% no claro) sobre o card
    const track = blend(t.mode === 'dark' ? '#FFFFFF' : '#0F172A', c.surface, t.mode === 'dark' ? 0.1 : 0.07);
    for (const k of ['success', 'warning', 'danger']) check(t, `ocupação ${k}/trilha`, c.statusText[k], track, UI);
  });

  test(`${t.key}: faixa cheia de erro (sincronização)`, () => {
    check(t, 'onDanger/dangerFill', c.onDanger, c.dangerFill, TEXT);
  });

  test(`${t.key}: contorno dos avisos (toast)`, () => {
    for (const k of ['success', 'info', 'danger']) check(t, `toast ${k}/surfaceElevated`, c.statusText[k], c.surfaceElevated, UI);
  });
}
