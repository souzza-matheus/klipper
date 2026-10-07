import React, { createContext, useContext, useMemo } from 'react';
import { useWindowDimensions } from 'react-native';
import { can, isWide } from './roles';

// Quem está logado (papel e profissional vinculado) e se a tela é de computador
const Ctx = createContext({ role: 'owner', barberId: null });

export function SessionProvider({ value, children }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSession() {
  const s = useContext(Ctx);
  const { width } = useWindowDimensions();
  return useMemo(() => ({
    ...s, wide: isWide(width), can: (feature) => can(s.role, feature),
    isOwner: s.role === 'owner', isPro: s.role === 'professional',
  }), [s, width]);
}

export function useWide() {
  return isWide(useWindowDimensions().width);
}
