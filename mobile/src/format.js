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
