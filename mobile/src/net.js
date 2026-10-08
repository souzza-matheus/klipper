// Está com internet? Celular: NetInfo. Web: eventos online/offline do navegador.
import NetInfo from '@react-native-community/netinfo';
import { IS_WEB } from './storage';

let online = true;
const listeners = new Set();

function set(v) {
  if (v === online) return;
  online = v;
  listeners.forEach((fn) => fn(v));
}

export function startNet() {
  if (IS_WEB) {
    if (typeof window === 'undefined') return () => {};
    online = navigator.onLine !== false;
    const on = () => set(true);
    const off = () => set(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }
  // isInternetReachable null = ainda testando: conta como online até provar o contrário
  return NetInfo.addEventListener((s) => set(!!s.isConnected && s.isInternetReachable !== false));
}

export const isOnline = () => online;

export function onNetChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
