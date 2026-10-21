import { useCallback, useState } from 'react';
import { useFocusEffect } from './focus';
import { onDataChange } from './offline/manager';

// Fora do ui.js porque depende da navegação (useFocusEffect): o ui.js entra no JavaScript do login na web, e a
// navegação só vem depois (src/shell.web.js)
// Carrega dados sempre que a tela ganha foco; expõe reload para "puxar para atualizar".
export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setData(await fn());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  // Sem o indicador de carregamento: a tela troca os dados quando a sincronização traz novidade
  const quiet = useCallback(() => { Promise.resolve().then(fn).then(setData, () => {}); }, deps); // eslint-disable-line
  useFocusEffect(useCallback(() => {
    load();
    return onDataChange(quiet); // celular com modo offline: recarrega quando os dados do aparelho mudam
  }, [load, quiet]));
  return { data, setData, loading, error, reload: load };
}
