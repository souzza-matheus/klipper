// Capturas e axe das páginas de erro (bloco 2): 404 e 50x da landing, 404 ("Página não encontrada") e 50x do app.
// Uso: node erros.mjs <url da landing> <url do app>   (os dois servidos pelo Caddy: audit/scripts/caddy_local.sh)
import fs from 'node:fs';
import { axe, launch, measure, OUT, saveJson } from './common.mjs';

const [site, app] = process.argv.slice(2);
const DIR = `${OUT}/screenshots/erros`;
fs.mkdirSync(DIR, { recursive: true });
const PAGES = [
  ['landing-404', `${site}/planos/antigos`, 'Página não encontrada'],
  ['landing-50x', `${site}/50x.html`, 'O site está com um problema'],
  ['app-404', `${app}/agenda/antiga`, 'Página não encontrada'],
  ['app-50x', `${app}/50x.html`, 'O SyncServ está com um problema'],
];
const browser = await launch();
const results = [];
for (const width of [375, 1440]) {
  for (const [name, url, title] of PAGES) {
    const ctx = await browser.newContext({ viewport: { width, height: width === 375 ? 812 : 900 } });
    const page = await ctx.newPage();
    const resp = await page.goto(url);
    await page.getByText(title).first().waitFor({ timeout: 20000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${DIR}/${name}-${width}.png` });
    const a = await axe(page, `${name}-${width}`);
    results.push({ ...a, status: resp.status(), medidas: width === 375 ? await measure(page) : undefined });
    await ctx.close();
  }
}
await browser.close();
saveJson('erros-axe', results);
console.log(JSON.stringify(results.map((r) => [r.label, r.status, r.violations.map((v) => `${v.id}(${v.impact})x${v.count}`).join(' ') || '0 violações',
  r.medidas ? `alvos<48: ${r.medidas.smallTargets.length} textos<13: ${Object.keys(r.medidas.smallText).length}` : ""])));
