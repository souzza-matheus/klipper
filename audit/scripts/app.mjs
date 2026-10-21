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
// A01 corrigido no bloco 1: o app calcula a posição do clique sem locationY. O ajuste antigo (que completava o
// locationY só no navegador de teste) fica disponível com SHIM=1, para reproduzir as capturas da auditoria.
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
  const NOSHOT = process.env.NOSHOT === '1';
  if (!NOSHOT) await page.screenshot({ path: name(n) });
  if (tall || NOSHOT) {
    // tela longa: aumenta a altura da janela para mostrar o conteúdo inteiro de uma vez
    const full = await page.evaluate(() => Math.max(...[...document.querySelectorAll('div')].map((d) => d.scrollHeight)));
    await page.setViewportSize({ width: W, height: Math.min(Math.max(H, full + 120), 6000) });
    await settle();
    if (!NOSHOT && tall) await page.screenshot({ path: name(`${n}-inteira`) });
    if (a11y && W <= 768) results.measure[n] = await measure(page, { topOnly: true });
    await page.setViewportSize({ width: W, height: H });
    await wait(300);
  } else if (a11y && W <= 768) results.measure[n] = await measure(page, { topOnly: true });
  if (a11y && process.env.NOAXE !== '1') results.axe.push(await axe(page, n));
  log.push(n);
}
async function step(label, fn) {
  try { await fn(); } catch (e) { results.errors.push(`${label}: ${e.message.split('\n')[0]}`); }
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
if (!mainOnly) await shot('01-login');
await page.getByLabel('E-mail').fill('admin@demo.com');
await page.getByLabel('Senha').fill('errada');
if (await page.getByLabel('Endereço do servidor').count() === 0) await page.getByRole('button', { name: /Configuração avançada/ }).click();
await page.getByLabel('Endereço do servidor').fill(API);
if (!mainOnly) {
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

// ---------------------------------------------------------------- Hoje
await shot('03-hoje', { tall: true });
await step('agendamento', async () => {
  await page.locator('[role=button] >> visible=true').filter({ hasText: /até \d\d:\d\d/ }).first().click();
  await shot('04-agendamento-detalhe', { tall: true });
  await tab('Hoje');
});
await step('acoes rapidas', async () => {
  const card = page.locator('[role=button] >> visible=true').filter({ hasText: /até \d\d:\d\d/ }).first();
  const b = await card.boundingBox();
  await page.mouse.move(b.x + 40, b.y + 30);
  await page.mouse.down();
  await wait(700);
  await page.mouse.up();
  await wait(600);
  await shot('05-acoes-rapidas', { a11y: false });
  await page.keyboard.press('Escape');
  await page.locator('[aria-label="Fechar"] >> visible=true').last().click().catch(() => {});
  await wait(500);
});

// ---------------------------------------------------------------- Agenda
await step('agenda timeline', async () => {
  await tab('Agenda');
  await page.locator('[role=tab][aria-label="Timeline"] >> visible=true').click();
  await shot('06-agenda-timeline');
});
await step('quickbook', async () => {
  await tapFree();
  await shot('07-agendamento-rapido');
  await page.locator('[placeholder=\"Nome ou telefone\"] >> visible=true').first().fill('Lu');
  await wait(1200);
  await shot('08-agendamento-rapido-busca', { a11y: false });
  await page.locator('[aria-label="Fechar"] >> visible=true').last().click();
  await wait(500);
});
await step('agenda pros', async () => {
  await page.locator('[role=tab] >> visible=true').nth(1).click();
  await shot('09-agenda-profissionais');
});
await step('agenda mes', async () => {
  await page.locator('[role=tab][aria-label="Mês"] >> visible=true').click();
  await shot('10-agenda-mes', { tall: true });
  await page.locator('[role=tab][aria-label="Timeline"] >> visible=true').click();
  await wait(500);
});
if (!mainOnly) {
  await step('conflito', async () => {
    // 23/10: Alexandre tem horário; tentar agendar Renato (par incompatível) no mesmo dia
    for (let i = 0; i < 3; i++) { await page.locator('[aria-label="Próximo dia"] >> visible=true').click(); await wait(500); }
    await settle();
    await tapFree();
    await page.locator('[placeholder=\"Nome ou telefone\"] >> visible=true').first().fill('Renato');
    await wait(1200);
    await text('Renato Vasconcelos').click();
    await wait(1500);
    await shot('11-agendamento-rapido-conflito', { a11y: false });
    await page.locator('[aria-label="Fechar"] >> visible=true').last().click();
    await wait(400);
  });
  await step('novo agendamento', async () => {
    await clickTop('[aria-label="Novo agendamento"]');
    await shot('12-novo-agendamento', { tall: true });
    await tab('Agenda');
  });
}

// ---------------------------------------------------------------- Caixa e comanda
await step('caixa', async () => {
  await tab('Caixa');
  await shot('13-caixa', { tall: true });
});
await step('comanda', async () => {
  const open = page.getByRole('button', { name: 'Abrir comanda' }).filter({ visible: true }).first();
  if (await open.count()) await open.click();
  else {
    await page.getByRole('button', { name: 'Nova comanda' }).filter({ visible: true }).click();
    await page.getByRole('button', { name: /venda avulsa/ }).filter({ visible: true }).click();
  }
  await wait(1500);
  await shot('14-comanda', { tall: true });
  await step('lancar', async () => {
    const add = page.getByRole('button', { name: /Produto/ }).filter({ visible: true }).first();
    if (await add.count()) { await add.click(); await wait(800); await shot('15-comanda-lancar-produto', { a11y: false }); await page.locator('[aria-label="Fechar"] >> visible=true').last().click(); }
  });
});

// ---------------------------------------------------------------- Pix
await step('pix', async () => {
  await more('Pagamentos Pix');
  await shot('16-pix-pendentes', { tall: true });
  const img = page.locator('[aria-label="Ver comprovante"] >> visible=true').first();
  if (await img.count()) {
    await img.scrollIntoViewIfNeeded();
    await shot('17-pix-com-comprovante', { a11y: false });
    await img.click();
    await wait(800);
    await shot('18-pix-comprovante-aberto', { a11y: false });
    await page.locator('[aria-label^="Fechar"] >> visible=true').last().click();
  }
});

// ---------------------------------------------------------------- Clientes
await step('clientes', async () => {
  await tab(theme === 'barber' ? 'Clientes' : 'Clientes');
  await shot('19-clientes');
});
await step('ficha', async () => {
  await page.getByText('Marcos Teixeira').first().click().catch(async () => {
    await page.locator('[role=button] >> visible=true').filter({ hasText: /\(\d\d\)/ }).first().click();
  });
  await shot('20-ficha-cliente', { tall: true });
});
if (!mainOnly) {
  await step('clientes vazio', async () => {
    await tab('Clientes');
    await page.locator('[placeholder=\"Buscar por nome ou telefone\"] >> visible=true').first().fill('zzzzqq');
    await wait(1500);
    await shot('21-clientes-busca-vazia', { a11y: false });
    await page.locator('[placeholder=\"Buscar por nome ou telefone\"] >> visible=true').first().fill('');
  });
}

// ---------------------------------------------------------------- Gestão
const gestao = mainOnly ? [] : [
  ['22-produtos-estoque', 'Produtos e estoque'], ['24-pacotes', 'Pacotes'], ['25-assinaturas', 'Clube de assinatura'],
  ['26-lista-espera', 'Lista de espera'], ['27-relatorios', 'Relatórios'], ['28-avaliacoes', 'Avaliações'],
  ['29-equipe', 'Equipe e permissões'], ['30-servicos', 'Serviços e preços'], ['31-bloqueios', 'Bloqueios de agenda'],
];
for (const [n, label] of gestao) {
  await step(n, async () => {
    await more(label);
    await shot(n, { tall: true });
    if (n === '22-produtos-estoque') {
      await page.locator('[role=button] >> visible=true').filter({ hasText: /estoque|un\./i }).first().click();
      await shot('23-produto-detalhe', { tall: true });
    }
  });
}

// ---------------------------------------------------------------- Financeiro e configurações
await step('financeiro', async () => {
  await tab('Finanças');
  await shot('32-financeiro', { tall: true });
});
await step('configuracoes', async () => {
  await more('Configurações e aparência');
  await shot('33-configuracoes', { tall: true });
});
if (!mainOnly) {
  await step('whatsapp', async () => {
    await more('Conexão do WhatsApp');
    await shot('34-whatsapp', { tall: true });
  });
  await step('mais', async () => {
    if (!wide) { await tab('Mais'); await shot('35-mais', { tall: true }); }
  });
}

if (process.env.NOSHOT !== '1') {
// ---------------------------------------------------------------- carregando, erro e offline
await step('carregando', async () => {
  await page.route('**/payments**', async (r) => { await new Promise((x) => setTimeout(x, 8000)); await r.continue().catch(() => {}); });
  if (wide) await page.locator('[aria-label="Pagamentos Pix"]').first().click();
  else { await tab('Mais'); await text('Pagamentos Pix').click(); }
  await wait(900);
  await page.screenshot({ path: name('36-carregando') });
  await page.unroute('**/payments**');
  await wait(8500);
});
await step('erro', async () => {
  await page.route('**/payments**', (r) => r.abort('failed'));
  await page.locator('[role=tab] >> visible=true').nth(1).click().catch(() => {});
  await wait(1500);
  await page.screenshot({ path: name('37-erro') });
  await page.unroute('**/payments**');
});
await step('offline', async () => {
  await tab('Hoje');
  await ctx.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  await wait(1200);
  await page.screenshot({ path: name('38-offline') });
  await tab('Caixa');
  await page.getByRole('button', { name: 'Nova comanda' }).filter({ visible: true }).click();
  await page.getByRole('button', { name: /venda avulsa/ }).filter({ visible: true }).click();
  await wait(1200);
  await page.screenshot({ path: name('39-offline-acao-bloqueada') });
  await ctx.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
});

}
await browser.close();
saveJson(process.env.OUTNAME || `app-${theme}-${W}`, results);
console.log(JSON.stringify({ shots: log, errors: results.errors, console: results.console.slice(0, 10),
  axe: results.axe.map((a) => [a.label, a.violations.map((v) => `${v.id}(${v.impact})x${v.count}`).join(' ')]) }, null, 1));
