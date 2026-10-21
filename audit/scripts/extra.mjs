// Capturas e medições do app (export web do Expo). Uso: node app.mjs <tema: barber|beauty> <largura> [só-principais]
import fs from 'node:fs';
import { axe, launch, measure, OUT, saveJson } from './common.mjs';

const [theme = 'barber', widthArg = '375', mainOnly] = process.argv.slice(2);
const W = Number(widthArg);
const H = W === 375 ? 812 : W === 768 ? 1024 : 900;
const API = theme === 'barber' ? 'http://127.0.0.1:8011' : 'http://127.0.0.1:8012';
const WEB = 'http://127.0.0.1:8100';
const T = theme === 'barber' ? 'barbearia' : 'salao';
const DIR = `${OUT}/screenshots/app`;
fs.mkdirSync(DIR, { recursive: true });
const wide = W >= 900;
const log = [];
const results = { theme, width: W, axe: [], measure: {}, errors: [], console: [] };

const browser = await launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1, bypassCSP: true,
                                       isMobile: W === 375, hasTouch: W !== 1440 });
const page = await ctx.newPage();
page.setDefaultTimeout(6000);
// A01 corrigido no bloco 1; o ajuste antigo do locationY só com SHIM=1 (para reproduzir as capturas da auditoria)
if (process.env.SHIM === '1') await page.addInitScript(() => {
  window.addEventListener('click', (e) => {
    if (e.locationY === undefined && e.target && e.target.getBoundingClientRect) {
      const r = e.target.getBoundingClientRect();
      Object.defineProperty(e, 'locationY', { get: () => e.clientY - r.top });
      Object.defineProperty(e, 'locationX', { get: () => e.clientX - r.left });
    }
  }, true);
});
page.on('console', (m) => { if (m.type() === 'error') results.console.push(m.text().slice(0, 200)); });
page.on('pageerror', (e) => results.console.push(e.message.slice(0, 200)));

const wait = (ms = 900) => page.waitForTimeout(ms);
async function settle() {
  await wait(500);
  for (let i = 0; i < 20; i++) {
    const busy = await page.locator('[aria-label="Carregando"] >> visible=true').count();
    if (!busy) break;
    await wait(300);
  }
  await wait(400);
}
const name = (n) => `${DIR}/${T}-${W}-${n}.png`;
async function shot(n, { tall = false, a11y = true } = {}) {
  await settle();
  await page.screenshot({ path: name(n) });
  if (tall) {
    // tela longa: aumenta a altura da janela para mostrar o conteúdo inteiro de uma vez
    const full = await page.evaluate(() => Math.max(...[...document.querySelectorAll('div')].map((d) => d.scrollHeight)));
    await page.setViewportSize({ width: W, height: Math.min(Math.max(H, full + 120), 6000) });
    await settle();
    await page.screenshot({ path: name(`${n}-inteira`) });
    await page.setViewportSize({ width: W, height: H });
    await wait(300);
  }
  if (a11y) {
    results.axe.push(await axe(page, n));
    if (W === 375) results.measure[n] = await measure(page);
  }
  log.push(n);
}
async function step(label, fn) {
  try { await fn(); } catch (e) {
    results.errors.push(`${label}: ${e.message.split('\n')[0]}`);
    if (process.env.DEBUG_SHOTS) await page.screenshot({ path: `${process.env.DEBUG_SHOTS}/falha-${label.replace(/\W+/g, '-')}.png` }).catch(() => {});
  }
}
const text = (t) => page.locator(`text="${t}" >> visible=true`).first();

// Toca num horário vago: só pontos em que o elemento por baixo é a própria coluna (não um agendamento ou bloqueio)
async function tapFree() {
  const pts = await page.evaluate((H) => {
    const out = [];
    for (const col of document.querySelectorAll('[aria-label^="Horários de"]')) {
      const r = col.getBoundingClientRect();
      for (let y = Math.max(r.top + 10, 120); y < Math.min(r.bottom, H - 90); y += 19) {
        const x = r.left + r.width / 2;
        const el = document.elementFromPoint(x, y);
        if (el && el.closest('[aria-label^="Horários de"]') === col && !el.closest('[aria-label*=" a "]')) out.push([x, y]);
      }
    }
    return out;
  }, H);
  for (const [x, y] of pts) {
    await page.mouse.click(x, y);
    await wait(600);
    if (await page.locator('text=/livre até/ >> visible=true').count()) return;
  }
  throw new Error('nenhum horário vago visível');
}

// Clica no elemento que está de fato por cima (as telas de baixo da pilha continuam no DOM)
async function clickTop(sel) {
  const ok = await page.evaluate((sel) => {
    for (const e of document.querySelectorAll(sel)) {
      const r = e.getBoundingClientRect();
      if (!r.width) continue;
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (hit && (hit === e || e.contains(hit))) { e.click(); return true; }
    }
    return false;
  }, sel);
  if (!ok) throw new Error(`nada clicável em ${sel}`);
}
async function tab(t) {
  await page.keyboard.press('Escape').catch(() => {});
  // dentro da barra de abas ou do menu lateral (o título da tela com o mesmo nome pode estar por trás)
  await page.locator(`[role=navigation] >> text="${t}" >> visible=true`).first().click();
  await wait(500);
  // volta ao topo da pilha da aba (no menu lateral, tocar de novo não volta sozinho)
  for (let i = 0; i < 6; i++) {
    // só o "Voltar" que está por cima (o das outras abas fica atrás, inert)
    const clicked = await page.evaluate(() => {
      for (const e of document.querySelectorAll('[aria-label^="Voltar"]')) {
        const r = e.getBoundingClientRect();
        if (!r.width || e.closest('[inert]')) continue;
        const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        if (hit && e.contains(hit)) { e.click(); return true; }
      }
      return false;
    });
    if (!clicked) break;
    await wait(500);
  }
  await settle();
}
async function more(label) {
  if (wide) await page.locator(`[aria-label="${label}"]`).first().click();
  else { await tab('Mais'); await text(label).click(); }
  await settle();
}

// ---------------------------------------------------------------- login
await page.goto(`${WEB}/`);
await page.getByLabel('E-mail').waitFor({ timeout: 30000 });
await wait(800);

await page.getByLabel('E-mail').fill('admin@demo.com');
await page.getByLabel('Senha').fill('errada');
if (await page.getByLabel('Endereço do servidor').count() === 0) await page.getByRole('button', { name: /Configuração avançada/ }).click();
await page.getByLabel('Endereço do servidor').fill(API);
if (false) {
  await step('login erro', async () => {
    await page.getByRole('button', { name: 'Entrar' }).filter({ visible: true }).click();
    await wait(1500);
    await shot('02-login-erro', { a11y: false });
  });
}
await page.getByLabel('Senha').fill('demo123');
await page.getByRole('button', { name: 'Entrar' }).filter({ visible: true }).click();
await text('Agenda').waitFor({ timeout: 20000 });
await settle();


// ---------------------------------------------------------------- extras: Pix com comprovante, erro, offline, novo agendamento
await step('aria', async () => {
  await tab('Agenda');
  results.aria = await page.evaluate(() => [...document.querySelectorAll('[role=tab],[role=radio],[role=checkbox],[role=switch]')]
    .filter((e) => e.getBoundingClientRect().width).slice(0, 12)
    .map((e) => e.outerHTML.slice(0, e.outerHTML.indexOf('>') + 1).replace(/class="[^"]*"/, '').replace(/style="[^"]*"/, '')));
});
await step('pix comprovante', async () => {
  await more('Pagamentos Pix');
  await settle();
  const img = page.locator('[aria-label^="Ver comprovante"] >> visible=true').first();
  await img.waitFor({ timeout: 8000 });
  const card = page.locator('text="Arthur Lima" >> visible=true').first();
  await card.scrollIntoViewIfNeeded();
  await page.evaluate(() => { const e = [...document.querySelectorAll('[aria-label^="Ver comprovante"]')].pop(); e.scrollIntoView({ block: 'center' }); });
  await wait(500);
  await shot('17-pix-com-comprovante');
  await shot('16-pix-pendentes', { tall: true, a11y: false });
  await img.click();
  await wait(900);
  await shot('18-pix-comprovante-aberto', { a11y: false });
  await page.locator('[aria-label^="Fechar"] >> visible=true').last().click();
});
await step('novo agendamento', async () => {
  await tab('Agenda');
  await clickTop('[aria-label="Novo agendamento"]');
  await shot('12-novo-agendamento', { tall: true });
});
await step('erro', async () => {
  await page.route('**/api/products**', (r) => r.abort('failed'));
  await more('Produtos e estoque');
  await wait(1500);
  await shot('37-erro', { a11y: false });
  await page.unroute('**/api/products**');
});
await step('offline toast', async () => {
  await tab('Caixa');
  await ctx.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await wait(800);
  await page.getByRole('button', { name: 'Nova comanda' }).filter({ visible: true }).click();
  await page.getByRole('button', { name: /venda avulsa/ }).filter({ visible: true }).click();
  await wait(700);
  await page.screenshot({ path: name('39-offline-acao-bloqueada') }); log.push('39');
  await wait(1500); await page.locator('[aria-label="Fechar"] >> visible=true').last().click().catch(() => {}); await wait(600); await page.screenshot({ path: name('40-offline-depois-de-fechar') }); log.push('40');
  await ctx.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
});
await browser.close();
saveJson(`app-extra-${theme}-${W}`, results);
console.log(JSON.stringify({ shots: log, errors: results.errors, console: results.console.slice(0, 10),
  axe: results.axe.map((a) => [a.label, a.violations.map((v) => `${v.id}(${v.impact})x${v.count}`).join(' ')]) }, null, 1));
