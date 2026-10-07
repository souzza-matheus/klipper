import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

// Onde a sessão fica guardada.
// - Celular: SecureStore (Keychain / Keystore), criptografado pelo sistema.
// - Web: o token de acesso fica SÓ em memória (some ao fechar a aba); o refresh token e as preferências da sessão
//   ficam no sessionStorage, que é da aba e é apagado ao fechá-la. Nada vai para armazenamento permanente do
//   navegador.
export const IS_WEB = Platform.OS === 'web';

const PREFIX = 'syncserv:';
const memory = {};

function tabStore() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch (e) {
    return null; // navegador bloqueando armazenamento: fica só em memória
  }
}

// Chaves que no web nunca saem da memória
const MEMORY_ONLY = new Set(['token']);

export async function getItem(key) {
  if (!IS_WEB) return (await SecureStore.getItemAsync(key)) || '';
  if (key in memory) return memory[key];
  if (MEMORY_ONLY.has(key)) return '';
  return tabStore()?.getItem(PREFIX + key) || '';
}

export async function setItem(key, value) {
  const v = String(value ?? '');
  if (!IS_WEB) {
    await SecureStore.setItemAsync(key, v); // o SecureStore só aceita texto
    return;
  }
  memory[key] = v;
  if (!MEMORY_ONLY.has(key)) tabStore()?.setItem(PREFIX + key, v);
}

export async function removeItem(key) {
  if (!IS_WEB) {
    await SecureStore.deleteItemAsync(key);
    return;
  }
  delete memory[key];
  tabStore()?.removeItem(PREFIX + key);
}
