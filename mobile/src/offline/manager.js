// Liga o modo offline no celular: abre o banco criptografado, sincroniza e avisa as telas.
//
// Quando sincroniza: ao abrir o app, ao voltar para ele (foreground), quando a internet volta, a cada 2 minutos
// com o app aberto, logo depois de cada alteração e em segundo plano (expo-background-task, a cada ~15 min, quando
// o sistema deixar). Falhas de rede esperam cada vez mais antes da próxima tentativa (engine.js).
//
// Quando apaga: sair da conta, outra pessoa (ou outro papel) entrar no aparelho, ou o servidor recusar o token.
import { AppState } from 'react-native';
import * as BackgroundTask from 'expo-background-task';
import * as Crypto from 'expo-crypto';
import * as TaskManager from 'expo-task-manager';
import { api, loadSession, setWriteHook } from '../api';
import { isOnline, onNetChange } from '../net';
import { getItem, IS_WEB, setItem } from '../storage';
import { destroyOfflineDb, openOfflineDb } from './db';
import { createEngine } from './engine';
import { createStore } from './store';

const INTERVAL_MS = 2 * 60000;
const TASK = 'syncserv-sync';

let db = null;
let store = null;
let engine = null;
let identity = '';
let session = { role: 'owner', barberId: null };
let version = 0;
let cleanup = [];
let starting = null;
let state = { available: false, reason: IS_WEB ? 'web' : 'starting', encrypted: false };
let status = { pending: 0, attention: 0, lastSync: null, running: false, lastError: '', online: true };
const subs = new Set();
const dataSubs = new Set();

// Só eventos e contagens: nunca dados de clientes
const log = (event, info) => { if (__DEV__) console.log(`[sync] ${event}`, JSON.stringify(info || {})); };

function publish() {
  const snap = { ...state, ...status, online: isOnline() };
  subs.forEach((fn) => fn(snap));
}

async function refreshStatus() {
  if (!engine) return publish();
  try {
    status = { ...status, ...(await engine.status()) };
  } catch (e) { /* banco fechando */ }
  return publish();
}

export const ctx = {
  store: () => store,
  engine: () => engine,
  session: () => session,
  version: () => version,
  bump() {
    version += 1;
    dataSubs.forEach((fn) => fn(version));
    refreshStatus();
  },
};

export const offlineReady = () => !!engine;
export const offlineState = () => ({ ...state, ...status, online: isOnline() });

export function onSyncStatus(fn) {
  subs.add(fn);
  fn(offlineState());
  return () => subs.delete(fn);
}

// Dados mudaram (pull trouxe novidade ou houve alteração local): as telas abertas recarregam
export function onDataChange(fn) {
  dataSubs.add(fn);
  return () => dataSubs.delete(fn);
}

export function setOfflineSession(s) {
  session = { role: s.role || 'owner', barberId: s.barberId || null };
}

const transport = {
  pull: (cursor) => api.get('/sync/pull', { cursor }),
  push: (operations) => api.post('/sync/push', { operations }),
};

export function syncNow(reason = 'manual') {
  if (!engine) return Promise.resolve({ ok: false });
  return engine.sync(reason).then((r) => { refreshStatus(); return r; }).catch(async (e) => {
    // Token recusado pelo servidor: apaga os dados do aparelho (o app também volta para o login)
    if (e && e.status === 401) await stopOffline({ wipe: true });
    refreshStatus();
    return { ok: false, error: e };
  });
}

async function open() {
  const r = await openOfflineDb();
  if (!r.db) return r;
  db = r.db;
  store = createStore(db);
  await store.init();
  return r;
}

// identity = loja:usuário:papel. Outro dono no banco: apaga o arquivo e a chave antes de usar.
export async function startOffline(id) {
  if (IS_WEB) return;
  if (starting) await starting;
  if (engine && identity === id) return;
  starting = (async () => {
    if (engine) await stopOffline({ wipe: true });
    let r = await open();
    if (!r.db) {
      state = { available: false, reason: r.reason, encrypted: false };
      publish();
      return;
    }
    const owner = await store.getMeta('owner');
    if (owner && owner !== id) {
      await destroyOfflineDb(db);
      r = await open();
    }
    engine = createEngine({ store, transport, uuid: Crypto.randomUUID, log });
    await engine.ensureOwner(id);
    identity = id;
    await setItem('offlineOwner', id); // para a sincronização em segundo plano saber de quem é o banco
    state = { available: true, reason: '', encrypted: r.encrypted };
    engine.onChange((changed) => (changed ? ctx.bump() : refreshStatus()));

    const timer = setInterval(() => { if (AppState.currentState === 'active') syncNow('interval'); }, INTERVAL_MS);
    const app = AppState.addEventListener('change', (s) => { if (s === 'active') syncNow('foreground'); });
    const net = onNetChange((on) => { publish(); if (on) syncNow('network'); });
    setWriteHook(() => syncNow('write')); // alteração feita direto pela API: traz para o aparelho
    cleanup = [() => clearInterval(timer), () => app.remove(), net, () => setWriteHook(null)];
    registerBackgroundSync();
    ctx.bump();
    syncNow('open');
  })();
  try {
    await starting;
  } finally {
    starting = null;
  }
}

// Sair da conta ou token recusado: apaga tudo (arquivo e chave)
export async function stopOffline({ wipe = true } = {}) {
  cleanup.forEach((fn) => { try { fn(); } catch (e) { /* já removido */ } });
  cleanup = [];
  engine = null;
  identity = '';
  const old = db;
  db = null;
  store = null;
  if (wipe) {
    await destroyOfflineDb(old);
    await setItem('offlineOwner', '');
    BackgroundTask.unregisterTaskAsync(TASK).catch(() => {});
  } else if (old) {
    await old.closeAsync().catch(() => {});
  }
  status = { pending: 0, attention: 0, lastSync: null, running: false, lastError: '', online: isOnline() };
  state = { available: false, reason: IS_WEB ? 'web' : 'stopped', encrypted: false };
  ctx.bump();
}

// ---------------------------------------------------------------- segundo plano

if (!IS_WEB) {
  // Precisa ficar no escopo do módulo: o sistema pode abrir o app só para rodar a tarefa
  TaskManager.defineTask(TASK, async () => {
    try {
      if (!engine) {
        const s = await loadSession();
        const owner = await getItem('offlineOwner');
        if (!s.token || !owner) return BackgroundTask.BackgroundTaskResult.Success;
        setOfflineSession(s);
        await startOffline(owner);
      }
      const r = await syncNow('background');
      return r.ok === false ? BackgroundTask.BackgroundTaskResult.Failed : BackgroundTask.BackgroundTaskResult.Success;
    } catch (e) {
      return BackgroundTask.BackgroundTaskResult.Failed;
    }
  });
}

async function registerBackgroundSync() {
  try {
    const st = await BackgroundTask.getStatusAsync();
    if (st === BackgroundTask.BackgroundTaskStatus.Available) {
      await BackgroundTask.registerTaskAsync(TASK, { minimumInterval: 15 });
    }
  } catch (e) { /* Expo Go ou sistema sem suporte: fica só a sincronização com o app aberto */ }
}

// Telas de atenção
export async function attentionList() {
  return store ? store.attention() : [];
}
export async function dismissAttention(id) {
  if (!store) return;
  await store.dismiss(id);
  refreshStatus();
}
export async function pendingList() {
  return store ? store.ops(200) : [];
}
