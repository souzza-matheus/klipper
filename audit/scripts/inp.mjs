// INP aproximado (Event Timing) na landing e no app web, com a CPU 4x mais lenta (celular médio).
// Uso: node inp.mjs <url da landing> <url do app> <rótulo>   (app servido pelo Caddy com a API no mesmo endereço)
// INP = a interação mais lenta (com poucas interações, o p98 do Chrome é a maior). Bom: até 200 ms.
import { launch, saveJson } from './common.mjs';

const [landing, app, label = 'medicao'] = process.argv.slice(2);
const OBSERVE = () => {
  window.__inp = new Map();
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.interactionId) continue;
      const t = e.target;
      const name = t ? (t.getAttribute?.('aria-label') || t.textContent || t.tagName).trim().slice(0, 40) : '?';
      const prev = window.__inp.get(e.interactionId);
      if (!prev || e.duration > prev.duration) window.__inp.set(e.interactionId, { duration: e.duration, type: e.name, name });
    }
  }).observe({ type: 'event', durationThreshold: 16, buffered: true });
};

async function page(browser) {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true,
                                         deviceScaleFactor: 2 });
  const p = await ctx.newPage();
  const cdp = await ctx.newCDPSession(p);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  await p.addInitScript(OBSERVE);
  p.setDefaultTimeout(20000);
  return { ctx, p };
}

const summary = async (p) => {
  const all = await p.evaluate(() => [...window.__inp.values()]);
  all.sort((a, b) => b.duration - a.duration);
  return { interacoes: all.length, inp: all[0]?.duration ?? 0, piores: all.slice(0, 4) };
};

const browser = await launch();
const out = {};

// Landing: nichos, calculadora, simulador, perguntas e menu
{
  const { ctx, p } = await page(browser);
  await p.route((u) => !u.href.startsWith(landing), (r) => r.abort());
  await p.goto(landing, { waitUntil: 'load' });
  await p.waitForTimeout(1500);
  for (const n of ['Salão de beleza', 'Pet shop', 'Clínica', 'Estúdio fitness', 'Barbearia']) {
    await p.getByRole('button', { name: n }).first().tap();
    await p.waitForTimeout(300);
  }
  for (let i = 0; i < 4; i++) {
    const plus = p.locator('.calc button, .range button').filter({ hasText: '+' }).first();
    if (await plus.count()) { await plus.tap(); await p.waitForTimeout(200); }
  }
  for (let i = 0; i < 4; i++) {
    const opt = p.locator('.js-sim-options button').first();
    if (await opt.count()) { await opt.tap(); await p.waitForTimeout(1500); }
  }
  const faq = p.locator('details summary');
  for (let i = 0; i < Math.min(3, await faq.count()); i++) { await faq.nth(i).tap(); await p.waitForTimeout(200); }
  await p.getByRole('button', { name: 'Abrir menu' }).tap();
  await p.waitForTimeout(500);
  out.landing = await summary(p);
  await ctx.close();
}

// App web: login, troca de abas, novo agendamento, busca de cliente
{
  const { ctx, p } = await page(browser);
  await p.goto(app, { waitUntil: 'load' });
  await p.getByLabel('E-mail').waitFor();
  await p.getByLabel('E-mail').tap();
  await p.keyboard.type('admin@demo.com', { delay: 30 });
  await p.getByLabel('Senha').tap();
  await p.keyboard.type('demo123', { delay: 30 });
  await p.getByRole('button', { name: 'Entrar' }).tap();
  await p.locator('[role=navigation] >> text="Agenda"').waitFor({ timeout: 30000 });
  await p.waitForTimeout(2500);
  for (const t of ['Agenda', 'Caixa', 'Clientes', 'Hoje', 'Agenda']) {
    await p.locator(`[role=navigation] >> text="${t}"`).first().tap();
    await p.waitForTimeout(1500);
  }
  const search = p.getByPlaceholder(/Buscar/).first();
  await p.locator('[role=navigation] >> text="Clientes"').first().tap();
  await p.waitForTimeout(1500);
  if (await search.count()) { await search.tap(); await p.keyboard.type('ana', { delay: 60 }); await p.waitForTimeout(800); }
  out.app = await summary(p);
  await ctx.close();
}

await browser.close();
saveJson(`inp-${label}`, out);
console.log(JSON.stringify({ landing: { n: out.landing.interacoes, inp: out.landing.inp, pior: out.landing.piores[0] },
  app: { n: out.app.interacoes, inp: out.app.inp, pior: out.app.piores[0] } }));
