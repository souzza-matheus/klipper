// Ordenação e busca das tabelas da versão de computador (sem React: testável no Node).

const norm = (s) => String(s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export function filterRows(rows, q, keys) {
  const t = norm(q).trim();
  if (!t) return rows;
  return rows.filter((r) => keys.some((k) => norm(typeof k === 'function' ? k(r) : r[k]).includes(t)));
}

function value(r, key) {
  return typeof key === 'function' ? key(r) : r[key];
}

// dir: 'asc' | 'desc'. Números (inclusive "12.50" vindos da API) ordenam como número; vazios vão para o fim.
export function sortRows(rows, key, dir = 'asc') {
  if (!key) return rows;
  const sign = dir === 'desc' ? -1 : 1;
  return [...rows].sort((a, b) => {
    const x = value(a, key);
    const y = value(b, key);
    const ex = x === null || x === undefined || x === '';
    const ey = y === null || y === undefined || y === '';
    if (ex || ey) return ex === ey ? 0 : ex ? 1 : -1;
    const nx = Number(x);
    const ny = Number(y);
    if (!Number.isNaN(nx) && !Number.isNaN(ny)) return (nx - ny) * sign;
    return norm(x).localeCompare(norm(y), 'pt-BR') * sign;
  });
}

// Clique no cabeçalho: mesma coluna inverte; outra coluna começa crescente
export function nextSort(cur, key) {
  if (cur.key === key) return { key, dir: cur.dir === 'asc' ? 'desc' : 'asc' };
  return { key, dir: 'asc' };
}
