// Endereço da API, embutido no build: ninguém digita servidor no app.
//
// - Perfil do build (eas.json): EXPO_PUBLIC_APP_PROFILE = development, preview ou production, e EXPO_PUBLIC_API_URL
//   (preview: https://staging.[DOMINIO]; production: https://api.[DOMINIO]). Desenvolvimento local: mobile/.env.local.
// - Web publicada em app.<domínio>: usa https://api.<domínio> sozinha, qualquer que seja o build.
// - Modo desenvolvedor (só development e preview): o endereço trocado nos 7 toques do logo (src/devApi.js) vale
//   por cima destes.
//
// As variáveis EXPO_PUBLIC_* são trocadas pelo valor na hora do build: process.env.EXPO_PUBLIC_X precisa aparecer
// escrito assim, por inteiro, no código.
import { Platform } from 'react-native';

export const PROFILE = process.env.EXPO_PUBLIC_APP_PROFILE || 'development';
const BUILD_URL = process.env.EXPO_PUBLIC_API_URL || '';

const clean = (url) => (url || '').trim().replace(/\/+$/, '');

// location: só para os testes (no navegador é window.location)
export function buildApiUrl(location = typeof window !== 'undefined' ? window.location : null, buildUrl = BUILD_URL,
  web = Platform.OS === 'web') {
  if (web && location?.hostname) {
    const m = /^app\.(.+)$/.exec(location.hostname);
    if (m) return `https://api.${m[1]}`;
  }
  if (clean(buildUrl)) return clean(buildUrl);
  // Web local (export servido pelo Caddy de teste ou expo start --web): a API no mesmo endereço
  if (web && location?.origin) return location.origin;
  return '';
}
