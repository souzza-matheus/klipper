import { File, Paths } from 'expo-file-system';
import { getItem, IS_WEB, removeItem, setItem } from './storage';

let baseUrl = '';
let token = '';
let refreshToken = ''; // só na versão web
let refreshTimer = null;
let onUnauthorized = () => {};

// Na versão web publicada (app.dominio), a API fica no mesmo endereço (o Caddy encaminha /api)
const webOrigin = () => (IS_WEB && typeof window !== 'undefined' ? window.location.origin : '');

export async function loadSession() {
  baseUrl = (await getItem('baseUrl')) || webOrigin();
  token = await getItem('token');
  refreshToken = IS_WEB ? await getItem('refreshToken') : '';
  const session = {
    baseUrl, token, name: await getItem('userName'), shop: await getItem('shopName'),
    email: await getItem('lastEmail'), niche: (await getItem('niche')) || 'barbershop',
    themeMode: (await getItem('themeMode')) || 'auto', role: (await getItem('role')) || 'owner',
    barberId: Number(await getItem('barberId')) || null,
  };
  if (IS_WEB && !token && refreshToken) {
    // Aba recarregada: o token de acesso estava só na memória; o refresh token da aba gera um novo
    try {
      await useRefreshToken();
      session.token = token;
    } catch (e) {
      await clearSession();
    }
  }
  return session;
}

async function keep(r) {
  token = r.token;
  await setItem('token', r.token);
  if (IS_WEB && r.refresh_token) {
    refreshToken = r.refresh_token;
    await setItem('refreshToken', r.refresh_token);
    scheduleRefresh(r.expires_in);
  }
}

// Web: renova o token de acesso um pouco antes de vencer, enquanto a aba está aberta
function scheduleRefresh(seconds) {
  if (refreshTimer) clearTimeout(refreshTimer);
  if (!seconds) return;
  refreshTimer = setTimeout(() => { useRefreshToken().catch(() => onUnauthorized()); },
    Math.max(30, seconds - 60) * 1000);
}

async function useRefreshToken() {
  const res = await fetch(baseUrl.replace(/\/$/, '') + '/api/auth/token', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new ApiError('Sessão expirada. Faça login de novo.', res.status);
  const r = await res.json();
  await keep(r);
  return r;
}

async function saveSession(url, r) {
  baseUrl = url;
  await setItem('baseUrl', url);
  await keep(r);
  await setItem('userName', r.user_name);
  await setItem('shopName', r.shop_name);
  await setItem('role', r.role || 'owner');
  await setItem('barberId', r.barber_id || '');
}

// Segmento e modo do tema do negócio (aplicados já na abertura do app, antes de carregar a API)
export async function saveAppearance(niche, themeMode, shopName) {
  await setItem('niche', niche || 'barbershop');
  await setItem('themeMode', themeMode || 'auto');
  if (shopName) await setItem('shopName', shopName);
}

// Endereço e cabeçalho autenticado para arquivos servidos pela API (ex.: comprovante do Pix)
export const apiUrl = (path) => baseUrl.replace(/\/$/, '') + '/api' + path;
export const authHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {});

export async function clearSession() {
  token = '';
  refreshToken = '';
  if (refreshTimer) clearTimeout(refreshTimer);
  await removeItem('token');
  await removeItem('refreshToken');
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

// status e data permitem tratar respostas específicas (ex.: 409 de conflito entre clientes)
export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export const OFFLINE_WEB = 'Sem conexão. Na versão web as alterações só podem ser feitas com internet.';

// A versão web funciona só online: sem internet, nenhuma alteração é enviada
export function webOffline() {
  return IS_WEB && typeof navigator !== 'undefined' && navigator.onLine === false;
}

function buildUrl(path, query) {
  let url = baseUrl.replace(/\/$/, '') + '/api' + path;
  if (query) {
    const qs = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    if (qs) url += '?' + qs;
  }
  return url;
}

export async function request(method, path, body, query, retried = false) {
  if (method !== 'GET' && webOffline()) throw new ApiError(OFFLINE_WEB, 0);
  const url = buildUrl(path, query);
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(IS_WEB && webOffline() ? OFFLINE_WEB : 'Sem conexão com o servidor. Confira o endereço e a internet.');
  }
  if (res.status === 401 && path !== '/auth/login' && path !== '/auth/change-password') {
    if (IS_WEB && refreshToken && !retried) {
      try {
        await useRefreshToken();
        return request(method, path, body, query, true);
      } catch (e) { /* refresh vencido: login de novo */ }
    }
    onUnauthorized();
    throw new ApiError('Sessão expirada. Faça login de novo.', 401);
  }
  const text = await res.text();
  // Erro 500 do servidor ou endereço errado (proxy, página HTML) não vem em JSON
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      throw new ApiError(res.ok ? 'Resposta inválida do servidor. Confira o endereço.'
        : `Erro ${res.status} no servidor: ${text.slice(0, 120)}`, res.status, null);
    }
  }
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join('\n');
    else if (msg && typeof msg === 'object') msg = msg.message;
    throw new ApiError(msg || `Erro ${res.status}`, res.status, data);
  }
  return data;
}

export const api = {
  get: (p, q) => request('GET', p, null, q),
  post: (p, b) => request('POST', p, b || {}),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
};

export async function login(url, email, password) {
  baseUrl = (url || webOrigin()).trim().replace(/\/$/, '');
  token = '';
  const r = await request('POST', '/auth/login', { email: email.trim(), password, client: IS_WEB ? 'web' : 'app' });
  // Outro serviço no endereço (ex.: a porta do Expo responde 200 a qualquer rota) não devolve token
  if (!r || typeof r.token !== 'string' || !r.token) {
    throw new ApiError('Esse endereço não é do servidor SyncServ. Confira o IP e a porta do backend '
      + '(ex.: http://192.168.1.10:8002), não a do Expo.');
  }
  await saveSession(baseUrl, r);
  await saveAppearance(r.niche, r.theme_mode);
  await setItem('lastEmail', email.trim());
  return r;
}

// Troca a senha provisória (primeiro acesso) ou a própria senha; devolve o token novo
export async function changePassword(current, next) {
  const r = await request('POST', '/auth/change-password', { current_password: current, new_password: next });
  await keep(r);
  return r;
}

// Renova o token ao abrir o app: quem usa sempre não precisa logar de novo
export async function refreshSession() {
  if (!token) return null;
  const r = await request('POST', '/auth/refresh', {});
  await keep(r);
  return r;
}

// Baixa um arquivo da API (com o login). Celular: salva no cache e devolve o caminho local.
// Web: devolve um endereço blob: para abrir ou baixar no navegador.
export async function download(path, query, filename) {
  if (IS_WEB) {
    const res = await fetch(buildUrl(path, query), { headers: authHeaders() });
    if (!res.ok) throw new ApiError(res.status === 401 ? 'Sessão expirada. Faça login de novo.'
      : 'Não foi possível baixar o arquivo.', res.status);
    return URL.createObjectURL(await res.blob());
  }
  const dest = new File(Paths.cache, filename);
  try {
    const file = await File.downloadFileAsync(buildUrl(path, query), dest, {
      headers: token ? { Authorization: `Bearer ${token}` } : {}, idempotent: true,
    });
    return file.uri;
  } catch (e) {
    throw new ApiError(/401/.test(String(e?.message)) ? 'Sessão expirada. Faça login de novo.'
      : 'Não foi possível baixar o arquivo. Confira a conexão com o servidor.');
  }
}

// Exporta/compartilha um arquivo da API: celular abre o compartilhar; web baixa com o nome certo
export async function saveFile(path, query, filename, mimeType) {
  const uri = await download(path, query, filename);
  if (IS_WEB) {
    const a = document.createElement('a');
    a.href = uri;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(uri), 10000);
    return;
  }
  const Sharing = await import('expo-sharing');
  if (!(await Sharing.isAvailableAsync())) throw new Error('Compartilhamento indisponível neste aparelho.');
  await Sharing.shareAsync(uri, { mimeType, dialogTitle: 'Exportar', UTI: mimeType === 'text/csv'
    ? 'public.comma-separated-values-text' : undefined });
}
