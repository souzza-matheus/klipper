import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Platform, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import {
  PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold, useFonts,
} from '@expo-google-fonts/plus-jakarta-sans';
import {
  createNavigationContainerRef, DarkTheme, DefaultTheme, NavigationContainer,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabBar, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { preloadWebFonts } from './src/webFonts';
import { startWebA11y } from './src/webA11y';

import { api, clearSession, loadSession, refreshSession, saveAppearance, setUnauthorizedHandler } from './src/api';
import { LogoVertical } from './src/brand/Logo';
import { OfflineBanner, Sidebar } from './src/components/Layout';
import { AttentionScreen, SyncBanner, SyncScreen } from './src/components/Sync';
import { startNet } from './src/net';
import { setOfflineSession, startOffline, stopOffline } from './src/offline/manager';
import { shortcutFor, tabsFor } from './src/roles';
import { SessionProvider, useWide } from './src/session';
import { BRAND_THEME, TYPE } from './src/theme';
import { ThemeProvider, useTheme } from './src/ThemeProvider';
import { DialogHost, IconButton, ToastHost } from './src/ui';
import Login from './src/screens/Login';
import { HomeScreen } from './src/screens/Home';
import { AgendaScreen, ApprovalsScreen, AppointmentScreen, NewAppointmentScreen } from './src/screens/Agenda';
import { PaymentsScreen } from './src/screens/Payments';
import { CustomerScreen, CustomersScreen } from './src/screens/Customers';
import { BarberEditScreen, BarbersScreen, BlocksScreen, ServiceEditScreen, ServicesScreen } from './src/screens/Catalog';
import { ReportsScreen, ReviewsScreen } from './src/screens/Insights';
import {
  CommissionRuleEditScreen, CommissionRulesScreen, CommissionsScreen, ExpenseEditScreen, ExpensesScreen,
  FinanceHomeScreen, SettlementsScreen,
} from './src/screens/Finance';
import { AboutScreen, MoreScreen, SettingsScreen, WhatsAppScreen } from './src/screens/Settings';
import { ComandaScreen, ComandasScreen } from './src/screens/Comandas';
import { ProductEditScreen, ProductsScreen } from './src/screens/Stock';
import { PackageEditScreen, PackagesScreen, PlanEditScreen, SubscribeScreen, SubscriptionsScreen } from './src/screens/Plans';
import { WaitlistScreen } from './src/screens/Waitlist';
import { ChangePasswordScreen, TeamScreen, UserEditScreen } from './src/screens/Team';

SplashScreen.preventAutoHideAsync().catch(() => {});

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const navRef = createNavigationContainerRef();

// Tema do React Navigation a partir dos tokens
function useNavTheme() {
  const { c, mode, font } = useTheme();
  return useMemo(() => {
    const base = mode === 'dark' ? DarkTheme : DefaultTheme;
    return {
      ...base, dark: mode === 'dark',
      colors: { ...base.colors, primary: c.accentText, background: c.background, card: c.surface, text: c.text,
                border: c.divider, notification: c.status.danger },
      fonts: {
        regular: { fontFamily: font.regular, fontWeight: '400' }, medium: { fontFamily: font.medium, fontWeight: '500' },
        bold: { fontFamily: font.bold, fontWeight: '700' }, heavy: { fontFamily: font.extrabold, fontWeight: '800' },
      },
    };
  }, [c, mode, font]);
}

function useStackOpts() {
  const { c, font } = useTheme();
  return useMemo(() => ({
    headerStyle: { backgroundColor: c.surface },
    headerTintColor: c.accentText,
    headerTitleStyle: { fontFamily: font.bold, fontSize: 18, color: c.text },
    headerBackTitle: 'Voltar',
    headerShadowVisible: false,
    contentStyle: { backgroundColor: c.background },
  }), [c, font]);
}

// Telas de detalhe: disponíveis a partir de qualquer aba (a API decide o que cada papel pode ver)
function details(v) {
  return [
    ['Appointment', AppointmentScreen, 'Agendamento'],
    ['NewAppointment', NewAppointmentScreen, 'Novo agendamento'],
    ['Customer', CustomerScreen, v.Customer],
    ['Approvals', ApprovalsScreen, 'Pedidos para aprovar'],
    ['PixList', PaymentsScreen, 'Pagamentos Pix'],
    ['Comanda', ComandaScreen, 'Comanda'],
    ['Products', ProductsScreen, 'Produtos e estoque'],
    ['ProductEdit', ProductEditScreen, 'Produto'],
    ['Packages', PackagesScreen, 'Pacotes'],
    ['PackageEdit', PackageEditScreen, 'Pacote'],
    ['Subscriptions', SubscriptionsScreen, 'Clube de assinatura'],
    ['PlanEdit', PlanEditScreen, 'Plano'],
    ['Subscribe', SubscribeScreen, 'Nova assinatura'],
    ['Waitlist', WaitlistScreen, 'Lista de espera'],
    ['Team', TeamScreen, 'Equipe e permissões'],
    ['UserEdit', UserEditScreen, 'Pessoa da equipe'],
    ['ChangePassword', ChangePasswordScreen, 'Trocar senha'],
    ['Services', ServicesScreen, 'Serviços'],
    ['ServiceEdit', ServiceEditScreen, 'Serviço'],
    ['Barbers', BarbersScreen, v.Pros],
    ['BarberEdit', BarberEditScreen, v.Pro],
    ['Blocks', BlocksScreen, 'Bloqueios'],
    ['Reviews', ReviewsScreen, 'Avaliações'],
    ['Reports', ReportsScreen, 'Relatórios'],
    ['Settings', SettingsScreen, 'Configurações'],
    ['WhatsApp', WhatsAppScreen, 'Conexão do WhatsApp'],
    ['About', AboutScreen, 'Sobre o SyncServ'],
    ['Sync', SyncScreen, 'Sincronização'],
    ['Attention', AttentionScreen, 'Precisa da sua atenção'],
    ['Expenses', ExpensesScreen, 'Gastos'],
    ['ExpenseEdit', ExpenseEditScreen, 'Gasto'],
    ['Commissions', CommissionsScreen, 'Comissões e repasses'],
    ['CommissionRules', CommissionRulesScreen, 'Regras de repasse'],
    ['CommissionRuleEdit', CommissionRuleEditScreen, 'Regra de repasse'],
    ['Settlements', SettlementsScreen, 'Acertos'],
  ];
}

// Raiz de cada aba: [rota, tela, título; null = sem cabeçalho]
const ROOTS = {
  Hoje: ['HomeMain', HomeScreen, null],
  Agenda: ['AgendaHome', AgendaScreen, 'Agenda'],
  Caixa: ['CaixaHome', ComandasScreen, 'Caixa'],
  Clientes: ['CustomersHome', CustomersScreen, 'Clientes'],
  Financeiro: ['FinanceHome', FinanceHomeScreen, 'Financeiro'],
  Comissoes: ['CommissionsHome', CommissionsScreen, 'Minhas comissões'],
};

// Na web o "Voltar" padrão do cabeçalho tem 30 x 30 px: troca por um botão de 48 px
function webBack(opts, c) {
  if (Platform.OS !== 'web') return opts;
  return ({ navigation }) => ({
    ...opts,
    headerLeft: ({ canGoBack }) => (canGoBack ? (
      <IconButton icon="arrow-back" label="Voltar" color={c.accentText} onPress={() => navigation.goBack()} />
    ) : null),
  });
}

function TabStack({ tab, onLogout, shopName }) {
  const opts = useStackOpts();
  const { v, c } = useTheme();
  const root = ROOTS[tab];
  // role="main": a área de conteúdo é o ponto de referência principal da página (leitor de tela e axe)
  return (
    <View role="main" aria-label="Conteúdo" style={{ flex: 1 }}>
    <Stack.Navigator screenOptions={webBack(opts, c)}>
      {tab === 'Mais' ? (
        <Stack.Screen name="MoreHome" options={{ title: 'Mais' }}>
          {(props) => <MoreScreen {...props} onLogout={onLogout} shopName={shopName} />}
        </Stack.Screen>
      ) : (
        <Stack.Screen name={root[0]} component={root[1]}
                      options={root[2] ? { title: tab === 'Clientes' ? v.Customers : root[2] } : { headerShown: false }} />
      )}
      {details(v).map(([name, comp, title]) => (
        <Stack.Screen key={name} name={name} component={comp} options={{ title }} />
      ))}
    </Stack.Navigator>
    </View>
  );
}

// Atalhos de teclado no computador (web): N novo agendamento, C abrir comanda, B buscar cliente
function useShortcuts(role) {
  useEffect(() => {
    if (Platform.OS !== 'web') return undefined;
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const el = e.target;
      const typing = el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
      if (typing || !navRef.isReady()) return;
      const sc = shortcutFor(role, e.key);
      if (!sc) return;
      e.preventDefault();
      if (sc.key === 'n') navRef.navigate('Agenda', { screen: 'NewAppointment', initial: false });
      if (sc.key === 'c') navRef.navigate('Caixa', { screen: 'CaixaHome', params: { openNew: Date.now() } });
      if (sc.key === 'b') navRef.navigate('Clientes', { screen: 'CustomersHome', params: { focus: Date.now() } });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [role]);
}

function Tabs({ onLogout, session }) {
  const { c, font, v, mode } = useTheme();
  const navTheme = useNavTheme();
  const wide = useWide();
  const tabs = tabsFor(session.role);
  useShortcuts(session.role);
  return (
    <NavigationContainer theme={navTheme} ref={navRef} documentTitle={{ formatter: () => 'SyncServ' }}>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      <OfflineBanner />
      <SyncBanner onOpen={(screen) => navRef.isReady() && navRef.navigate('Mais', { screen })} />
      <Tab.Navigator
        tabBar={wide ? (props) => <Sidebar {...props} role={session.role} shopName={session.shop}
                                             userName={session.name} /> : (props) => (
          <View role="navigation" aria-label="Abas"><BottomTabBar {...props} /></View>
        )}
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarPosition: wide ? 'left' : 'bottom',
          tabBarActiveTintColor: c.accentText,
          tabBarInactiveTintColor: c.textMuted,
          tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.divider, minHeight: 64 },
          // 13 px (piso da escala). O item da aba tem padding fixo de 5 px dos lados (React Navigation) e o texto
          // do react-native-web tem max-width 100%: a margem negativa e o maxWidth devolvem esse espaço ao rótulo,
          // e "Finanças" cabe nas 6 abas de um celular de 375 px
          tabBarLabelStyle: { fontFamily: font.semibold, fontSize: TYPE.caption, marginHorizontal: -4, alignSelf: 'stretch',
                            maxWidth: '120%', textAlign: 'center' },
          tabBarAllowFontScaling: false,
          tabBarItemStyle: { paddingVertical: 4 },
          tabBarIcon: ({ color, focused }) => {
            const t = tabs.find((x) => x.name === route.name);
            return <Ionicons name={t.icon + (focused ? '' : '-outline')} size={24} color={color} />;
          },
        })}>
        {tabs.map((t) => (
          <Tab.Screen key={t.name} name={t.name}
                      options={{ tabBarLabel: t.name === 'Clientes' ? v.Customers : t.label || t.name, sideIcon: t.icon }}>
            {() => <TabStack tab={t.name} onLogout={onLogout} shopName={session.shop} />}
          </Tab.Screen>
        ))}
      </Tab.Navigator>
      <ToastHost />
      <DialogHost />
    </NavigationContainer>
  );
}

// Primeiro acesso de quem foi convidado: troca a senha provisória antes de tudo
function FirstLogin({ onDone }) {
  const { c } = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <View style={{ flex: 1, width: '100%', maxWidth: 560, alignSelf: 'center' }}>
        <ChangePasswordScreen first onDone={onDone} />
      </View>
      <ToastHost />
      <DialogHost />
    </View>
  );
}

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
const webFonts = preloadWebFonts({ ...FONTS, ...Ionicons.font });

export default function App() {
  const [loaded] = useFonts(FONTS);
  const [webFontsReady, setWebFontsReady] = useState(Platform.OS !== 'web');
  useEffect(() => { webFonts.then(() => setWebFontsReady(true)); }, []);
  const fontsLoaded = loaded && webFontsReady;
  const [session, setSession] = useState(null);

  useEffect(() => startWebA11y(), []);
  useEffect(() => {
    const stopNet = startNet();
    loadSession().then(setSession);
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

  // Confere o tema do negócio e o papel na API (podem ter mudado em outro aparelho)
  const token = session?.token;
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
