import React, { startTransition, useCallback, useEffect, useMemo, useState } from 'react';
import { Platform, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import {
  PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold, useFonts,
} from '@expo-google-fonts/plus-jakarta-sans';
import { SafeAreaProvider } from 'react-native-safe-area-context';
// Só o Ionicons: o índice do @expo/vector-icons traz o mapa de glifos de todas as famílias (~400 KB na web)
import Ionicons from '@expo/vector-icons/Ionicons';
import { loadWebFonts, prepareWebFonts } from './src/webFonts';
import { startWebA11y } from './src/webA11y';

import { api, clearSession, loadSession, refreshSession, saveAppearance, setUnauthorizedHandler } from './src/api';
import { LogoVertical } from './src/brand/Logo';
import { startNet } from './src/net';
import { setOfflineSession, startOffline, stopOffline } from './src/offline/manager';
import { SessionProvider } from './src/session';
import { BRAND_THEME } from './src/theme';
import { ThemeProvider } from './src/ThemeProvider';
import { DialogHost, ToastHost } from './src/ui';
import Login from './src/screens/Login';
import NotFound, { unknownWebPath } from './src/screens/NotFound';
// Depois do login: abas, pilhas e telas. Na web vem num pedaço separado do JavaScript (src/shell.web.js)
import { FirstLogin, prefetchShell, Tabs } from './src/shell';

SplashScreen.preventAutoHideAsync().catch(() => {});

// Splash interna (depois da nativa, enquanto lê a sessão salva)
function BrandSplash() {
  return (
    <View style={{ flex: 1, backgroundColor: BRAND_THEME.c.background, alignItems: 'center', justifyContent: 'center' }}>
      <LogoVertical width={180} variant="dark" />
    </View>
  );
}

const FONTS = {
  PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold,
};
// Web: as fontes entram pelo src/webFonts.web.js (woff2 com fonte reserva do mesmo tamanho) e a primeira tela não
// espera por elas (a Plus Jakarta Sans é pedida logo depois de a tela aparecer); no celular, o expo-font carrega os
// TTF e a splash nativa fica até terminar
const IS_WEB = Platform.OS === 'web';
prepareWebFonts({ ...FONTS, ...Ionicons.font });
const NOT_FOUND = IS_WEB && unknownWebPath();

export default function App() {
  const [fontsLoaded] = useFonts(IS_WEB ? {} : FONTS);
  const [session, setSession] = useState(null);

  useEffect(() => startWebA11y(), []);
  useEffect(() => {
    const stopNet = startNet();
    // startTransition: a primeira tela de verdade (login ou abas) é desenhada em fatias, sem travar a página
    loadSession().then((s) => startTransition(() => setSession(s)));
    return stopNet;
  }, []);
  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded]);

  const logout = useCallback(async () => {
    await stopOffline({ wipe: true }); // LGPD: nada de clientes fica no aparelho depois de sair
    await clearSession();
    setSession((s) => ({ ...s, token: '', firstLogin: false }));
  }, []);
  useEffect(() => { setUnauthorizedHandler(logout); }, [logout]);

  // Troca de segmento ou modo nas Configurações: aplica na hora e guarda para a próxima abertura
  const setAppearance = useCallback((niche, themeMode, shopName) => {
    setSession((s) => ({ ...s, niche, themeMode, shop: shopName || s.shop }));
    saveAppearance(niche, themeMode, shopName);
  }, []);

  // Web: enquanto a pessoa digita a senha, baixa em segundo plano a parte do app que vem depois do login; logada, as
  // telas das abas principais
  const token = session?.token;
  const sessionRead = session !== null;
  useEffect(() => { if (sessionRead) loadWebFonts(); }, [sessionRead]);
  useEffect(() => { if (sessionRead) prefetchShell(!!token); }, [sessionRead, token]);

  // Confere o tema do negócio e o papel na API (podem ter mudado em outro aparelho)
  useEffect(() => {
    if (!token) return;
    refreshSession().catch(() => {}); // renova a validade do token
    api.get('/me').then((me) => {
      setAppearance(me.niche, me.theme_mode, me.shop_name);
      setSession((s) => ({ ...s, role: me.role, barberId: me.barber_id, name: me.name, firstLogin: me.first_login,
                           userId: me.user_id, shopId: me.shop_id }));
    }).catch(() => {});
  }, [token, setAppearance]);

  // Modo offline (celular): banco da pessoa logada. Outra pessoa ou outro papel no aparelho = banco apagado.
  const { userId, shopId, role, barberId, firstLogin } = session || {};
  useEffect(() => {
    if (!token || !userId || !shopId || firstLogin) return;
    setOfflineSession({ role, barberId });
    startOffline(`${shopId}:${userId}:${role}`);
  }, [token, userId, shopId, role, barberId, firstLogin]);

  const sessionValue = useMemo(() => ({
    role: session?.role || 'owner', barberId: session?.barberId || null, userName: session?.name || '',
    shopName: session?.shop || '',
  }), [session?.role, session?.barberId, session?.name, session?.shop]);

  if (!fontsLoaded) return null; // a splash nativa continua na tela
  if (NOT_FOUND) {
    return <SafeAreaProvider><ThemeProvider brand><StatusBar style="light" /><NotFound /></ThemeProvider></SafeAreaProvider>;
  }
  if (!session) {
    return <SafeAreaProvider><StatusBar style="light" /><BrandSplash /></SafeAreaProvider>;
  }

  return (
    <SafeAreaProvider>
      {!session.token ? (
        <ThemeProvider brand>
          <StatusBar style="light" />
          <Login initialUrl={session.baseUrl} initialEmail={session.email}
                 onLogged={(r) => setSession({
                   ...session, token: r.token, name: r.user_name, shop: r.shop_name, niche: r.niche,
                   themeMode: r.theme_mode, role: r.role, barberId: r.barber_id, firstLogin: r.first_login,
                   userId: r.user_id, shopId: r.shop_id,
                 })} />
          <ToastHost />
          <DialogHost />
        </ThemeProvider>
      ) : (
        <ThemeProvider niche={session.niche} themeMode={session.themeMode} setAppearance={setAppearance}>
          <SessionProvider value={sessionValue}>
            {session.firstLogin ? (
              <FirstLogin onDone={(r) => setSession((s) => ({ ...s, token: r.token, firstLogin: false }))} />
            ) : (
              <Tabs onLogout={logout} session={session} />
            )}
          </SessionProvider>
        </ThemeProvider>
      )}
    </SafeAreaProvider>
  );
}
