import * as SecureStore from 'expo-secure-store';

let baseUrl = '';
let token = '';
let onUnauthorized = () => {};

export async function loadSession() {
  baseUrl = (await SecureStore.getItemAsync('baseUrl')) || '';
  token = (await SecureStore.getItemAsync('token')) || '';
  const name = (await SecureStore.getItemAsync('userName')) || '';
  const shop = (await SecureStore.getItemAsync('shopName')) || '';
  return { baseUrl, token, name, shop };
}

export async function saveSession(url, t, name, shop) {
  baseUrl = url;
  token = t;
  await SecureStore.setItemAsync('baseUrl', url);
  await SecureStore.setItemAsync('token', t);
  await SecureStore.setItemAsync('userName', name || '');
  await SecureStore.setItemAsync('shopName', shop || '');
}

export async function clearSession() {
  token = '';
  await SecureStore.deleteItemAsync('token');
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export class ApiError extends Error {}

export async function request(method, path, body, query) {
  let url = baseUrl.replace(/\/$/, '') + '/api' + path;
  if (query) {
    const qs = Object.entries(query)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    if (qs) url += '?' + qs;
  }
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
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    let msg = data?.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join('\n');
    throw new ApiError(msg || `Erro ${res.status}`);
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
  await saveSession(baseUrl, r.token, r.user_name, r.shop_name);
  return r;
}
