// Endereço da API trocado no modo desenvolvedor (development e preview). No build de produção este arquivo nem
// entra no pacote: quem importa usa process.env.EXPO_PUBLIC_APP_PROFILE !== 'production' ? require(...) : null.
import { getItem, removeItem, setItem } from './storage';

const KEY = 'devApiUrl';

export const getDevApiUrl = () => getItem(KEY);

export async function setDevApiUrl(url) {
  const v = (url || '').trim().replace(/\/+$/, '');
  if (v) await setItem(KEY, v);
  else await removeItem(KEY);
  return v;
}
