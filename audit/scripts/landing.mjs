// Capturas e medições da landing em 375, 768 e 1440 px
import { axe, launch, measure, OUT, saveJson } from './common.mjs';

const URL = 'http://127.0.0.1:8101/';
const DIR = `${OUT}/screenshots/landing`;
const WIDTHS = [375, 768, 1440];
const SECTIONS = [
  ['01-topo', '.topbar'], ['02-hero', '#topo'], ['03-demo', '#demo'], ['04-como-funciona', '#como-funciona'],
  ['05-recursos', '#recursos'], ['06-gestao', '#gestao'], ['07-comparativo', 'section[aria-labelledby=compare-title]'],
  ['08-calculadora', '#calculadora'], ['09-precos', '#precos'], ['10-faq', '#duvidas'], ['11-chamada-final', '.final'],
  ['12-rodape', '.footer'],
];
const NICHES = ['barbershop', 'beauty', 'petshop', 'clinic', 'fitness'];

const results = { axe: [], measure: {}, console: [], cta: {}, firstScreen: {} };
const browser = await launch();
for (const w of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w === 375 ? 812 : w === 768 ? 1024 : 900 },
                                         deviceScaleFactor: 1, reducedMotion: 'reduce', isMobile: w === 375, hasTouch: w !== 1440 });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') results.console.push(`${w}: ${m.text()}`); });
  page.on('pageerror', (e) => results.console.push(`${w}: ${e.message}`));
  await page.goto(URL, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  // primeira dobra
  await page.screenshot({ path: `${DIR}/landing-${w}-primeira-dobra.png` });
  results.firstScreen[w] = await page.evaluate(() => {
    const vh = innerHeight;
    const inView = (sel) => [...document.querySelectorAll(sel)].some((e) => { const r = e.getBoundingClientRect(); return r.height && r.top < vh && r.bottom > 0 && getComputedStyle(e).display !== 'none'; });
    const cta = document.querySelector('.hero .btn--cta').getBoundingClientRect();
    return { heroCtaTop: Math.round(cta.top), heroCtaBottom: Math.round(cta.bottom), vh, ctaVisible: cta.bottom <= vh,
             headerCtaVisible: inView('.topbar .btn--cta'), h1: document.querySelector('h1').innerText,
             phonesTop: Math.round(document.querySelector('.phones').getBoundingClientRect().top) };
  });
  results.cta[w] = await page.$$eval('.js-cta', (as) => as.map((a) => ({ text: a.innerText.trim(), href: a.href.slice(0, 140), target: a.target })));
  await page.screenshot({ path: `${DIR}/landing-${w}-pagina-inteira.png`, fullPage: true });
  for (const [name, sel] of SECTIONS) {
    const el = page.locator(sel).first();
    await el.scrollIntoViewIfNeeded();
    await el.screenshot({ path: `${DIR}/landing-${w}-${name}.png` });
  }
  // menu do celular aberto
  if (w < 900) {
    await page.evaluate(() => scrollTo(0, 0));
    await page.click('.menu-btn');
    await page.screenshot({ path: `${DIR}/landing-${w}-menu-aberto.png` });
    await page.click('.menu-btn');
  }
  results.axe.push(await axe(page, `landing ${w}px`));
  results.measure[w] = await measure(page);
  // seletor de nicho: hero em cada segmento
  for (const n of NICHES) {
    await page.click(`.niche[data-niche=${n}]`);
    await page.waitForTimeout(150);
    await page.locator('#topo').screenshot({ path: `${DIR}/landing-${w}-nicho-${n}-hero.png` });
    if (w === 375 || w === 1440) await page.locator('#gestao .showcase').screenshot({ path: `${DIR}/landing-${w}-nicho-${n}-gestao.png` });
  }
  await page.click('.niche[data-niche=barbershop]');
  // simulador em 3 etapas
  const sim = page.locator('.sim');
  const pick = async (re) => { const b = page.locator('.sim__options button.opt', { hasText: re }).first(); await b.waitFor(); await b.click(); };
  await sim.scrollIntoViewIfNeeded();
  await pick(/^Oi$/);
  await page.locator('.sim__options .opt', { hasText: 'Agendar' }).first().waitFor();
  await page.waitForTimeout(200);
  await sim.screenshot({ path: `${DIR}/landing-${w}-simulador-1-menu.png` });
  await pick(/1 - Agendar/); await pick(/^1 - /); await pick(/^1 - /); await pick(/^2 - /);
  await page.locator('.sim__options .opt', { hasText: '10:30' }).first().waitFor();
  await page.waitForTimeout(200);
  await sim.screenshot({ path: `${DIR}/landing-${w}-simulador-2-horarios.png` });
  await pick(/10:30/); await pick(/1 - Confirmar/); await pick(/Pix/); await pick(/paguei/);
  await pick(/Ver o lembrete/); await pick(/Confirmo/);
  await page.locator('.sim__options .btn--cta').waitFor();
  await page.waitForTimeout(200);
  await sim.screenshot({ path: `${DIR}/landing-${w}-simulador-3-fim.png` });
  results.axe.push(await axe(page, `simulador no fim ${w}px`, '.sim'));
  // calculadora ajustada
  const calc = page.locator('#calculadora');
  await page.fill('#c-appts', '20');
  await page.locator('#c-appts').dispatchEvent('input');
  await calc.screenshot({ path: `${DIR}/landing-${w}-calculadora-ajustada.png` });
  // FAQ aberto
  await page.$$eval('#duvidas details', (ds) => ds.forEach((d) => { d.open = true; }));
  await page.locator('#duvidas').screenshot({ path: `${DIR}/landing-${w}-faq-aberto.png` });
  if (w === 375) {
    await page.$$eval('#duvidas details', (ds) => ds.forEach((d, i) => { d.open = i === 5; }));
    await page.locator('#duvidas details').nth(5).screenshot({ path: `${DIR}/landing-375-faq-uma-aberta.png` });
  }
  await ctx.close();
}
await browser.close();
saveJson('landing', results);
console.log(JSON.stringify({ console: results.console, firstScreen: results.firstScreen,
  axe: results.axe.map((a) => [a.label, a.violations.map((v) => `${v.id}(${v.impact}) x${v.count}`)]),
  measure: Object.fromEntries(Object.entries(results.measure).map(([k, v]) => [k, { targets: v.smallTargets.length, text: Object.fromEntries(Object.entries(v.smallText).map(([f, x]) => [f, x.count])), hscroll: v.horizontalScroll }])) }, null, 1));
