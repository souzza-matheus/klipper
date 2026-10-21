// Versão web: as telas que ficam por baixo na pilha (e qualquer outra parte escondida com aria-hidden) continuavam
// recebendo foco pelo Tab (axe: aria-hidden-focus, 67 ocorrências em 1440 px). Aqui todo elemento com
// aria-hidden="true" ganha o atributo inert, que tira o foco e o clique, e perde quando volta a aparecer.
// Só mexe no inert que ele mesmo colocou (marcado em data-auto-inert).
const MARK = 'data-auto-inert';

function sync(el) {
  if (!(el instanceof HTMLElement)) return;
  const hidden = el.getAttribute('aria-hidden') === 'true';
  if (hidden && !el.inert) {
    el.inert = true;
    el.setAttribute(MARK, '');
  } else if (!hidden && el.hasAttribute(MARK)) {
    el.inert = false;
    el.removeAttribute(MARK);
  }
}

export function startWebA11y(root = document.body) {
  if (typeof MutationObserver === 'undefined' || !root) return () => {};
  root.querySelectorAll('[aria-hidden]').forEach(sync);
  const obs = new MutationObserver((list) => {
    for (const m of list) {
      if (m.type === 'attributes') sync(m.target);
      else m.addedNodes.forEach((n) => {
        if (n instanceof HTMLElement) {
          sync(n);
          n.querySelectorAll('[aria-hidden]').forEach(sync);
        }
      });
    }
  });
  obs.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-hidden'] });
  return () => obs.disconnect();
}
