// O backend envia datas no horário local da barbearia, sem fuso: "2026-10-07T09:00:00".
// Trabalhamos com as strings para não sofrer conversão de fuso no aparelho.

const WEEK = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];
const WEEK_FULL = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];
export const WEEKDAYS_MON_FIRST = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

const pad = (n) => String(n).padStart(2, '0');

export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function addDays(iso, n) {
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.toISOString().slice(0, 10);
}

function weekday(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
}

export function dayLabel(iso) {
  const t = todayISO();
  const base = `${WEEK[weekday(iso)]} ${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  if (iso === t) return `Hoje · ${base}`;
  if (iso === addDays(t, 1)) return `Amanhã · ${base}`;
  if (iso === addDays(t, -1)) return `Ontem · ${base}`;
  return `${WEEK_FULL[weekday(iso)]} · ${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
}

export const hm = (dt) => (dt ? dt.slice(11, 16) : '');
export const dmy = (dt) => (dt ? `${dt.slice(8, 10)}/${dt.slice(5, 7)}/${dt.slice(0, 4)}` : '');
export const dtLabel = (dt) => (dt ? `${dayLabel(dt.slice(0, 10))} às ${hm(dt)}` : '');

export function money(v) {
  const n = Number(v || 0);
  return 'R$ ' + n.toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

export function phoneLabel(p) {
  const d = String(p || '').replace(/\D/g, '');
  const n = d.startsWith('55') ? d.slice(2) : d;
  if (n.length === 11) return `(${n.slice(0, 2)}) ${n.slice(2, 7)}-${n.slice(7)}`;
  if (n.length === 10) return `(${n.slice(0, 2)}) ${n.slice(2, 6)}-${n.slice(6)}`;
  return p || '';
}

// "15/10" ou "15/10/2026" -> "2026-10-15"
export function parseBRDate(s) {
  const m = String(s).trim().match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/);
  if (!m) return null;
  let y = m[3] ? Number(m[3]) : new Date().getFullYear();
  if (y < 100) y += 2000;
  return `${y}-${pad(Number(m[2]))}-${pad(Number(m[1]))}`;
}

export function isHM(s) {
  return /^([01]?\d|2[0-3]):[0-5]\d$/.test(String(s).trim());
}

export const normHM = (s) => {
  const [h, m] = String(s).trim().split(':');
  return `${pad(Number(h))}:${m}`;
};

// Primeiro e último dia do mês atual + offset (-1 = mês passado)
export function monthRange(offset = 0) {
  const d = new Date();
  const first = new Date(Date.UTC(d.getFullYear(), d.getMonth() + offset, 1));
  const last = new Date(Date.UTC(d.getFullYear(), d.getMonth() + offset + 1, 0));
  return [first.toISOString().slice(0, 10), last.toISOString().slice(0, 10)];
}

export const pct = (v) => `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`;

// Valor digitado ("1.234,56", "60" ou "60,5") -> número; null se inválido
export function parseMoney(s) {
  const t = String(s ?? '').trim().replace(/\s|R\$/g, '');
  if (!t) return null;
  const n = Number(t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t);
  return Number.isFinite(n) ? n : null;
}

export const moneyInput = (v) => (v === null || v === undefined ? '' : Number(v).toFixed(2).replace('.', ','));

// "2026-10" <-> ano/mês; navegação de meses
export const monthKey = (y, m) => `${y}-${pad(m)}`;
export function addMonths(key, n) {
  const [y, m] = key.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return monthKey(d.getUTCFullYear(), d.getUTCMonth() + 1);
}
const MONTHS = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro',
  'outubro', 'novembro', 'dezembro'];
export function monthLabel(key) {
  const [y, m] = key.split('-').map(Number);
  const name = MONTHS[m - 1];
  return `${name[0].toUpperCase()}${name.slice(1)} de ${y}`;
}
export function monthBounds(key) {
  const [y, m] = key.split('-').map(Number);
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [`${key}-01`, `${key}-${pad(last)}`];
}
// Dia da semana com segunda = 0 (como no backend)
export const weekdayMonFirst = (iso) => (weekday(iso) + 6) % 7;

// Variação contra o período anterior: "+12,5%" / "-3%"; null quando não há base
export function change(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return `${n > 0 ? '+' : ''}${n.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`;
}

export const PAY_METHODS = [
  { value: 'pix', label: 'Pix' }, { value: 'dinheiro', label: 'Dinheiro' },
  { value: 'debito', label: 'Débito' }, { value: 'credito', label: 'Crédito' },
];
export const payMethodLabel = (v) => PAY_METHODS.find((x) => x.value === v)?.label || 'Não informado';

export const EXPENSE_CATEGORIES = [
  { value: 'aluguel', label: 'Aluguel' }, { value: 'energia', label: 'Energia' }, { value: 'agua', label: 'Água' },
  { value: 'internet', label: 'Internet' }, { value: 'produtos', label: 'Produtos' },
  { value: 'equipamentos', label: 'Equipamentos' }, { value: 'manutencao', label: 'Manutenção' },
  { value: 'marketing', label: 'Marketing' }, { value: 'salarios', label: 'Salários' },
  { value: 'impostos', label: 'Impostos' }, { value: 'outros', label: 'Outros' },
];

// Distância em minutos: 90 -> "1 h 30 min", 240 -> "4 h"
export function gapLabel(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export const ACCESS_OPTIONS = [
  { value: 'normal', label: 'Normal' },
  { value: 'approval', label: 'Precisa de aprovação' },
  { value: 'blocked', label: 'Bloqueado' },
];

// Há quanto tempo (data local sem fuso): "agora", "há 15 min", "há 3 h", "há 2 dias"
export function ago(iso, now = new Date()) {
  if (!iso) return '';
  const min = Math.max(0, Math.round((now - new Date(iso.slice(0, 19))) / 60000));
  if (min < 1) return 'agora';
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 48) return `há ${h} h`;
  return `há ${Math.floor(h / 24)} dias`;
}
