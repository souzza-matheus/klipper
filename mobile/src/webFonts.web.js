// Fontes na versão web sem precisar de 'unsafe-inline' no CSP.
//
// O expo-font injeta cada @font-face como TEXTO dentro de um <style>, e o CSP bloqueia isso sem
// 'unsafe-inline'. Aqui as mesmas regras entram pelo CSSOM (insertRule), que o CSP não bloqueia,
// num <style id="expo-generated-fonts"> vazio (liberado pelo hash da string vazia no CSP).
// Como o expo-font procura as regras nesse mesmo elemento, ele vê a fonte já registrada e não injeta nada;
// por isso o download de cada fonte é disparado aqui (senão ela só baixaria no primeiro uso, talvez já sem internet).
// Devolve uma promessa que resolve quando todas baixaram (ou falharam: o texto cai na fonte do sistema).
import { Asset } from 'expo-asset';

const ID = 'expo-generated-fonts';

export function preloadWebFonts(fonts) {
  if (typeof document === 'undefined') return Promise.resolve();
  let el = document.getElementById(ID);
  if (!el) {
    el = document.createElement('style');
    el.id = ID;
    document.head.appendChild(el);
  }
  const sheet = el.sheet;
  if (!sheet) return Promise.resolve();
  const have = new Set([...sheet.cssRules].map((r) => (r.style?.fontFamily || '').replace(/^["']|["']$/g, '')));
  Object.entries(fonts).forEach(([family, mod]) => {
    if (have.has(family)) return;
    const { uri } = Asset.fromModule(mod);
    sheet.insertRule(`@font-face{font-family:${JSON.stringify(family)};src:url(${JSON.stringify(uri)});font-display:auto}`,
      sheet.cssRules.length);
  });
  return Promise.all(Object.keys(fonts).map((family) => document.fonts.load(`16px ${JSON.stringify(family)}`)
    .catch(() => null))).then(() => undefined);
}
