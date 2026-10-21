// Utilidades comuns: Playwright do mobile/node_modules, Chromium do cache local, axe e medições no navegador.
import { createRequire } from 'node:module';
import fs from 'node:fs';
const require = createRequire('/home/souzza-matheus/barberbot/mobile/package.json');
export const { chromium } = require('playwright');
export const AxeBuilder = require('@axe-core/playwright').default;
export const CHROME = `${process.env.HOME}/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`;
export const OUT = '/home/souzza-matheus/barberbot/audit';

export const launch = () => chromium.launch({ executablePath: CHROME });

export function saveJson(name, data) {
  fs.mkdirSync(`${OUT}/data`, { recursive: true });
  fs.writeFileSync(`${OUT}/data/${name}.json`, JSON.stringify(data, null, 2));
}

export async function axe(page, label, include) {
  let b = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']);
  if (include) b = b.include(include);
  const r = await b.analyze();
  return {
    label,
    violations: r.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
      nodes: v.nodes.slice(0, 8).map((n) => ({ target: n.target.join(' '), summary: (n.failureSummary || '').slice(0, 300),
                                             html: n.html.slice(0, 160) })),
    })),
    passes: r.passes.length, incomplete: r.incomplete.map((v) => ({ id: v.id, count: v.nodes.length })),
  };
}

// Alvos de toque < min px e textos < minFont px, só os visíveis na viewport inteira da página
export async function measure(page, { min = 48, minFont = 13, topOnly = false } = {}) {
  return page.evaluate(({ min, minFont, topOnly }) => {
    const vis = (el) => {
      const s = getComputedStyle(el);
      if (s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) === 0) return false;
      const r = el.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0)) return false;
      if (!topOnly) return true;
      // só o que está por cima na janela (as telas de baixo da pilha continuam no DOM)
      const x = Math.min(Math.max(r.left + Math.min(r.width / 2, 8), 0), innerWidth - 1);
      const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
      const hit = document.elementFromPoint(x, y);
      return !!hit && (hit === el || el.contains(hit) || hit.contains(el));
    };
    const desc = (el) => {
      const t = (el.getAttribute('aria-label') || el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 50);
      const cls = typeof el.className === 'string' ? el.className.split(' ').filter((x) => x && !/^css-|^r-/.test(x)).slice(0, 2).join('.') : '';
      return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''} "${t}"`;
    };
    const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=tab], [role=switch], [role=checkbox], [role=radio], [tabindex="0"]';
    const small = [];
    const seen = new Set();
    for (const el of document.querySelectorAll(sel)) {
      if (!vis(el)) continue;
      // ignora o que está dentro de outro alvo já contado (ex.: texto dentro do botão)
      if (el.parentElement && el.parentElement.closest(sel)) continue;
      const r = el.getBoundingClientRect();
      const inline = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
      if (r.width < min || r.height < min) {
        const k = desc(el) + Math.round(r.width) + 'x' + Math.round(r.height);
        if (seen.has(k)) continue;
        seen.add(k);
        small.push({ el: desc(el), w: Math.round(r.width), h: Math.round(r.height), inline });
      }
    }
    const fonts = {};
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const txt = n.textContent.trim();
      if (!txt || !n.parentElement || !vis(n.parentElement)) continue;
      const fs = parseFloat(getComputedStyle(n.parentElement).fontSize);
      if (fs < minFont) {
        const key = `${fs}px`;
        fonts[key] = fonts[key] || { count: 0, samples: [] };
        fonts[key].count += 1;
        if (fonts[key].samples.length < 8 && !fonts[key].samples.includes(txt.slice(0, 40))) fonts[key].samples.push(txt.slice(0, 40));
      }
    }
    const scrollX = document.documentElement.scrollWidth > window.innerWidth + 1;
    return { smallTargets: small, smallText: fonts, horizontalScroll: scrollX, scrollWidth: document.documentElement.scrollWidth };
  }, { min, minFont, topOnly });
}
