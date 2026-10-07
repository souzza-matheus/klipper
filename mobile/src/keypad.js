// Lógica do teclado numérico da comanda: o valor é digitado em centavos, da direita para a esquerda
// ("4" -> 0,04; "4","0","0","0" -> 40,00), como na maquininha. Guardado como texto só de dígitos.

const MAX_DIGITS = 9; // até 9.999.999,99

export function press(digits, key) {
  const d = String(digits || '');
  if (key === 'back') return d.slice(0, -1);
  if (key === 'clear') return '';
  if (key === '00') return press(press(d, '0'), '0');
  if (!/^\d$/.test(key)) return d;
  if (!d && key === '0') return d; // zero à esquerda não conta
  return d.length >= MAX_DIGITS ? d : d + key;
}

export function toNumber(digits) {
  return Number(digits || 0) / 100;
}

// Texto para a API: "40.00"
export function toApi(digits) {
  return toNumber(digits).toFixed(2);
}

// Texto na tela: "40,00" / "1.234,56"
export function label(digits) {
  const cents = String(Number(digits || 0)).padStart(3, '0');
  const int = cents.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${int},${cents.slice(-2)}`;
}

// De um valor em reais (ex.: saldo "36.5") para os dígitos do teclado ("3650")
export function fromValue(v) {
  const n = Math.round(Math.max(0, Number(v) || 0) * 100);
  return n ? String(n) : '';
}
