import { buildApiUrl } from './config';
import { isOnline } from './net';
import { getItem, IS_WEB, removeItem, setItem } from './storage';

// Modo desenvolvedor (development e preview): endereço trocado nos 7 toques do logo. Em produção a condição vira
// false na hora do build e o devApi.js não entra no pacote.
const devApi = process.env.EXPO_PUBLIC_APP_PROFILE !== 'production' ? require('./devApi') : null;

let baseUrl = buildApiUrl();
let token = '';
let refreshToken = ''; // só na versão web
let refreshTimer = null;
let onUnauthorized = () => {};
let onWrite = null; // celular: depois de uma alteração feita direto na API, sincroniza o banco local

const CLIENT = IS_WEB ? 'web' : 'app';

// Endereço da API em uso: o do build (src/config.js) ou, no modo desenvolvedor, o trocado à mão
export async function resolveApiUrl() {
  const override = devApi ? await devApi.getDevApiUrl() : '';
  baseUrl = override || buildApiUrl();
  return baseUrl;
}
export const currentApiUrl = () => baseUrl;

// Versões antigas guardavam o endereço digitado no login: não vale mais (o endereço vem do build) e é apagado
export async function forgetLegacyServer() {
  if (await getItem('baseUrl')) await removeItem('baseUrl');
}

export async function loadSession() {
  await forgetLegacyServer();
  await resolveApiUrl();
  token = await getItem('token');
  refreshToken = IS_WEB ? await getItem('refreshToken') : '';
  const session = {
    token, name: await getItem('userName'), shop: await getItem('shopName'),
    email: await getItem('lastEmail'), niche: (await getItem('niche')) || 'barbershop',
    themeMode: (await getItem('themeMode')) || 'auto', role: (await getItem('role')) || 'owner',
    barberId: Number(await getItem('barberId')) || null,
    userId: Number(await getItem('userId')) || null, shopId: Number(await getItem('shopId')) || null,
    businessesCount: Number(await getItem('businessesCount')) || 1,
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

async function saveSession(r) {
  await keep(r);
  await setItem('userName', r.user_name);
  await setItem('shopName', r.shop_name);
  await setItem('role', r.role || 'owner');
  await setItem('barberId', r.barber_id || '');
  await setItem('userId', r.user_id || '');
  await setItem('shopId', r.shop_id || '');
  await setItem('businessesCount', r.businesses_count || 1);
  await setItem('lastShopId', r.shop_id || ''); // o próximo login abre direto neste negócio
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

// status e data permitem tratar respostas específicas (ex.: 409 de conflito entre clientes). status 0 = o pedido
// nem chegou ao servidor (sem internet ou servidor fora do ar).
export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export const OFFLINE_WEB = 'Sem conexão. Na versão web as alterações só podem ser feitas com internet.';
export const OFFLINE_APP = 'Sem conexão. Essa ação precisa de internet; as de agenda, comanda e estoque funcionam '
  + 'offline.';

// A versão web funciona só online: sem internet, nenhuma alteração é enviada
export function webOffline() {
  return IS_WEB && typeof navigator !== 'undefined' && navigator.onLine === false;
}

export function setWriteHook(fn) {
  onWrite = fn;
}

const NO_HOOK = /^\/(sync|auth)\//;

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
  // Celular sem internet: o que funciona offline passa pelo repositório local (src/repo.local.js), não por aqui
  if (method !== 'GET' && !IS_WEB && !isOnline() && !path.startsWith('/auth/')) throw new ApiError(OFFLINE_APP, 0);
  const url = buildUrl(path, query);
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(IS_WEB && webOffline() ? OFFLINE_WEB : 'Sem conexão com o servidor. Confira a internet.');
  }
  if (res.status === 401 && !['/auth/login', '/auth/select', '/auth/change-password'].includes(path)) {
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
      throw new ApiError(res.ok ? 'Resposta inválida do servidor.'
        : `Erro ${res.status} no servidor: ${text.slice(0, 120)}`, res.status, null);
    }
  }
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join('\n');
    else if (msg && typeof msg === 'object') msg = msg.message;
    throw new ApiError(msg || `Erro ${res.status}`, res.status, data);
  }
  if (method !== 'GET' && onWrite && !NO_HOOK.test(path)) onWrite();
  return data;
}

export const api = {
  get: (p, q) => request('GET', p, null, q),
  post: (p, b) => request('POST', p, b || {}),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
};

// Login só com e-mail e senha: o servidor descobre o negócio. Quem tem mais de um recebe { choose, businesses,
// selection_token } (a tela "Escolha o negócio" chama selectBusiness), a não ser que o último negócio escolhido
// neste aparelho ainda esteja na lista: aí entra direto nele.
export async function login(email, password) {
  token = '';
  const lastShop = Number(await getItem('lastShopId')) || undefined;
  const r = await request('POST', '/auth/login', { email: email.trim(), password, client: CLIENT, shop_id: lastShop });
  await setItem('lastEmail', email.trim());
  if (r && r.choose) return r;
  return applyLogin(r);
}

async function applyLogin(r) {
  if (!r || typeof r.token !== 'string' || !r.token) throw new ApiError('Resposta inválida do servidor.', 502);
  await saveSession(r);
  await saveAppearance(r.niche, r.theme_mode, r.shop_name);
  return r;
}

export async function selectBusiness(selectionToken, shopId) {
  return applyLogin(await request('POST', '/auth/select', { selection_token: selectionToken, shop_id: shopId,
                                                             client: CLIENT }));
}

// Trocar de negócio sem sair: token novo, só do negócio escolhido (quem chama apaga antes o offline do anterior;
// ver src/businessSwitch.js)
export async function switchBusiness(shopId) {
  return applyLogin(await request('POST', '/auth/switch', { shop_id: shopId }));
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
  // Só no celular: import sob demanda, para o expo-file-system não entrar no JavaScript inicial da web
  const { File, Paths } = await import('expo-file-system');
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
