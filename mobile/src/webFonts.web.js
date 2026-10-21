// Fontes na versão web sem precisar de 'unsafe-inline' no CSP e sem segurar a primeira tela.
//
// O expo-font injeta cada @font-face como TEXTO dentro de um <style>, e o CSP bloqueia isso sem
// 'unsafe-inline'. Aqui as regras entram pelo CSSOM (insertRule), que o CSP não bloqueia, num
// <style id="expo-generated-fonts"> vazio (liberado pelo hash da string vazia no CSP). O ícone (Ionicons) procura as
// regras nesse mesmo elemento e, achando, não injeta nada.
//
// Arquivos: woff2 do public/fonts (scripts/build-fonts), ~15 KB por peso contra ~95 KB do TTF. A Plus Jakarta Sans
// vem só com o recorte latino; letras de fora (nome de cliente em outro alfabeto) usam o TTF inteiro, que o navegador
// só baixa se a letra aparecer na tela (unicode-range). O Ionicons vem só com os ícones que o código usa.
//
// Enquanto a fonte não chega, o texto aparece na "Jakarta Reserva <peso>": Arial/Liberation Sans ou Roboto com as
// medidas da Plus Jakarta Sans (números do scripts/build-fonts), para o texto não pular na troca. A pilha de fontes
// de cada peso está em theme.js (WEB_FONT_STACK). Os ícones ficam invisíveis até a fonte deles chegar
// (font-display: block), em vez de mostrar quadradinhos.
import { Asset } from 'expo-asset';

const ID = 'expo-generated-fonts';
const LATIN = 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,'
  + 'U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD';
const WOFF2 = {
  PlusJakartaSans_400Regular: 'plus-jakarta-sans-400-latin.woff2',
  PlusJakartaSans_500Medium: 'plus-jakarta-sans-500-latin.woff2',
  PlusJakartaSans_600SemiBold: 'plus-jakarta-sans-600-latin.woff2',
  PlusJakartaSans_700Bold: 'plus-jakarta-sans-700-latin.woff2',
  PlusJakartaSans_800ExtraBold: 'plus-jakarta-sans-800-latin.woff2',
  ionicons: 'ionicons.woff2',
};
// [peso, Arial/Liberation (size, ascent, descent), Roboto (size, ascent, descent)]
const FALLBACK = [
  [400, [103.23, 100.55, 21.5], [105.19, 98.68, 21.11]],
  [500, [104.21, 99.61, 21.3], [106.18, 97.76, 20.91]],
  [600, [99.9, 103.9, 22.22], [105.82, 98.09, 20.98]],
  [700, [100.79, 102.99, 22.03], [106.76, 97.23, 20.79]],
  [800, [101.63, 102.13, 21.84], [107.65, 96.42, 20.62]],
];

const local = (names) => names.map((n) => `local("${n}")`).join(',');
const ARIAL = local(['Arial', 'ArialMT', 'Liberation Sans', 'LiberationSans', 'Helvetica']);
const ARIAL_BOLD = local(['Arial Bold', 'Arial-BoldMT', 'Liberation Sans Bold', 'LiberationSans-Bold', 'Helvetica Bold']);
const ROBOTO = local(['Roboto', 'Roboto-Regular']);
const ROBOTO_BOLD = local(['Roboto Bold', 'Roboto-Bold']);

// Duas faces por peso, cada uma com as medidas da própria fonte: a do Roboto (Android) é testada primeiro e, se o
// aparelho não tiver Roboto, vale a da Arial/Liberation Sans
function fallbackRules() {
  const face = (weight, src, [size, ascent, descent]) => `@font-face{font-family:"Jakarta Reserva ${weight}";`
    + `src:${src};size-adjust:${size}%;ascent-override:${ascent}%;descent-override:${descent}%;line-gap-override:0%}`;
  return FALLBACK.flatMap(([weight, arial, roboto]) => [
    face(weight, weight >= 600 ? ARIAL_BOLD : ARIAL, arial),
    face(weight, weight >= 600 ? ROBOTO_BOLD : ROBOTO, roboto),
  ]);
}

function sheet() {
  let el = document.getElementById(ID);
  if (!el) {
    el = document.createElement('style');
    el.id = ID;
    document.head.appendChild(el);
  }
  return el.sheet;
}

function register(css, fonts) {
  const have = new Set([...css.cssRules].map((r) => (r.style?.fontFamily || '').replace(/^["']|["']$/g, '')));
  const add = (rule) => css.insertRule(rule, css.cssRules.length);
  Object.entries(fonts).forEach(([family, mod]) => {
    if (have.has(family)) return;
    const name = JSON.stringify(family);
    const icon = family === 'ionicons';
    // O TTF inteiro vem antes e só para letras fora do ASCII/Latin-1: com faces iguais, o navegador testa primeiro a
    // última (o woff2 latino), e o TTF só é baixado se aparecer uma letra que o woff2 não tem
    if (!icon) {
      add(`@font-face{font-family:${name};src:url(${JSON.stringify(Asset.fromModule(mod).uri)});font-display:swap;`
        + 'unicode-range:U+0100-FFFF}');
    }
    const file = WOFF2[family];
    const src = file ? `url("/fonts/${file}") format("woff2")` : `url(${JSON.stringify(Asset.fromModule(mod).uri)})`;
    add(`@font-face{font-family:${name};src:${src};font-display:${icon ? 'block' : 'swap'}`
      + `${file && !icon ? `;unicode-range:${LATIN}` : ''}}`);
  });
}

let pending = {};

// Na hora (antes da primeira tela): fonte reserva (local, não baixa nada) e ícones (aparecem já no login)
export function prepareWebFonts(fonts) {
  if (typeof document === 'undefined') return;
  const css = sheet();
  if (!css) return;
  if (![...css.cssRules].some((r) => r.style?.fontFamily === '"Jakarta Reserva 400"')) {
    fallbackRules().forEach((rule) => css.insertRule(rule, css.cssRules.length));
  }
  register(css, Object.fromEntries(Object.entries(fonts).filter(([family]) => family === 'ionicons')));
  pending = Object.fromEntries(Object.entries(fonts).filter(([family]) => family !== 'ionicons'));
}

// Depois que a primeira tela aparece (App chama num efeito): a Plus Jakarta Sans. A tela já está desenhada com a
// reserva de mesmo tamanho e troca em seguida, sem os downloads das fontes disputarem a banda com o JavaScript
// antes de a tela aparecer.
export function loadWebFonts() {
  if (typeof document === 'undefined' || !Object.keys(pending).length) return;
  const text = pending;
  pending = {};
  // rAF + setTimeout: o callback do rAF ainda roda antes da pintura do quadro; o setTimeout cai depois dela
  requestAnimationFrame(() => setTimeout(() => {
    register(sheet(), text);
    Object.keys(text).forEach((family) => document.fonts.load(`16px ${JSON.stringify(family)}`).catch(() => null));
  }, 0));
}
