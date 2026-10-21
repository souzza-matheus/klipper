import React, { useEffect, useState } from 'react';
import { Loading } from './ui';

// Telas carregadas sob demanda (versão web). O módulo baixado fica guardado por função de carga: tela de um módulo
// já baixado (pelo pré-carregamento ou por outra tela do mesmo arquivo) aparece direto, sem passar pelo esqueleto.
const loaded = new Map();

export function preload(load) {
  return load().then((m) => {
    loaded.set(load, m);
    return m;
  });
}

// Enquanto o pedaço do JavaScript chega, mostra o esqueleto de carregando; se falhar (internet caiu), mostra o erro
// com "Tentar de novo", que pede o arquivo outra vez.
export function lazyScreen(load, name) {
  function Screen(props) {
    const mod = loaded.get(load);
    const [, setTick] = useState(0);
    const [error, setError] = useState(null);
    useEffect(() => {
      if (mod || error) return undefined;
      let alive = true;
      preload(load).then(() => alive && setTick((t) => t + 1), () => alive && setError(
        'Não foi possível abrir esta tela. Confira a internet e tente de novo.'));
      return () => { alive = false; };
    }, [mod, error]);
    if (mod) {
      const Comp = mod[name];
      return <Comp {...props} />;
    }
    return <Loading error={error} onRetry={() => setError(null)} />;
  }
  Screen.displayName = `Lazy(${name})`;
  return Screen;
}
