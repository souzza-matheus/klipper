// Versão web: só online (sem banco local). Mesmas funções de manager.js, sem efeito.
const state = { available: false, reason: 'web', encrypted: false, pending: 0, attention: 0, lastSync: null,
                running: false, lastError: '', online: true };
export const ctx = {};
export const offlineReady = () => false;
export const offlineState = () => state;
export const onSyncStatus = (fn) => { fn(state); return () => {}; };
export const onDataChange = () => () => {};
export const setOfflineSession = () => {};
export const syncNow = () => Promise.resolve({ ok: false });
export const startOffline = async () => {};
export const stopOffline = async () => {};
export const attentionList = async () => [];
export const dismissAttention = async () => {};
export const pendingList = async () => [];
