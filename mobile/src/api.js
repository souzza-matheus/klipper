import * as SecureStore from 'expo-secure-store';
import { File, Paths } from 'expo-file-system';

let baseUrl = '';
let token = '';
let onUnauthorized = () => {};

export async function loadSession() {
  baseUrl = (await SecureStore.getItemAsync('baseUrl')) || '';
  token = (await SecureStore.getItemAsync('token')) || '';
  const get = async (k) => (await SecureStore.getItemAsync(k)) || '';
  return {
    baseUrl, token, name: await get('userName'), shop: await get('shopName'), email: await get('lastEmail'),
    niche: (await get('niche')) || 'barbershop', themeMode: (await get('themeMode')) || 'auto',
  };
}

export async function saveSession(url, t, name, shop) {
  baseUrl = url;
  token = t;
  // O SecureStore só aceita texto
  await SecureStore.setItemAsync('baseUrl', String(url || ''));
  await SecureStore.setItemAsync('token', String(t || ''));
  await SecureStore.setItemAsync('userName', String(name || ''));
  await SecureStore.setItemAsync('shopName', String(shop || ''));
}

// Segmento e modo do tema do negócio (aplicados já na abertura do app, antes de carregar a API)
export async function saveAppearance(niche, themeMode, shopName) {
  await SecureStore.setItemAsync('niche', String(niche || 'barbershop'));
  await SecureStore.setItemAsync('themeMode', String(themeMode || 'auto'));
  if (shopName) await SecureStore.setItemAsync('shopName', String(shopName));
}

// Endereço e cabeçalho autenticado para imagens servidas pela API (ex.: comprovante do Pix)
export const apiUrl = (path) => baseUrl.replace(/\/$/, '') + '/api' + path;
export const authHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {});

export async function clearSession() {
  token = '';
  await SecureStore.deleteItemAsync('token');
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

export async function request(method, path, body, query) {
  const url = buildUrl(path, query);
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError('Sem conexão com o servidor. Confira o endereço e a internet.');
  }
  if (res.status === 401 && path !== '/auth/login') {
    onUnauthorized();
    throw new ApiError('Sessão expirada. Faça login de novo.');
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
  baseUrl = url.trim().replace(/\/$/, '');
  token = '';
  const r = await request('POST', '/auth/login', { email: email.trim(), password });
  // Outro serviço no endereço (ex.: a porta do Expo responde 200 a qualquer rota) não devolve token
  if (!r || typeof r.token !== 'string' || !r.token) {
    throw new ApiError('Esse endereço não é do servidor SyncServ. Confira o IP e a porta do backend '
      + '(ex.: http://192.168.1.10:8002), não a do Expo.');
  }
  await saveSession(baseUrl, r.token, r.user_name, r.shop_name);
  await saveAppearance(r.niche, r.theme_mode);
  await SecureStore.setItemAsync('lastEmail', email.trim());
  return r;
}

// Renova o token (validade de 7 dias) ao abrir o app: quem usa sempre não precisa logar de novo
export async function refreshSession() {
  if (!token) return null;
  const r = await request('POST', '/auth/refresh', {});
  token = r.token;
  await SecureStore.setItemAsync('token', String(r.token));
  return r;
}

// Baixa um arquivo da API (com o login) para o cache do aparelho e devolve o caminho local
export async function download(path, query, filename) {
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
