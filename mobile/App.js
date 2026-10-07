import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import {
  PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold, useFonts,
} from '@expo-google-fonts/plus-jakarta-sans';
import { DarkTheme, DefaultTheme, NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { api, clearSession, loadSession, saveAppearance, setUnauthorizedHandler } from './src/api';
import { LogoVertical } from './src/brand/Logo';
import { BRAND_THEME } from './src/theme';
import { ThemeProvider, useTheme } from './src/ThemeProvider';
import { ToastHost } from './src/ui';
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

SplashScreen.preventAutoHideAsync().catch(() => {});

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

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

// Telas de detalhe disponíveis a partir de qualquer aba
function shared(v) {
  return (
    <>
      <Stack.Screen name="Appointment" component={AppointmentScreen} options={{ title: 'Agendamento' }} />
      <Stack.Screen name="NewAppointment" component={NewAppointmentScreen} options={{ title: 'Novo agendamento' }} />
      <Stack.Screen name="Customer" component={CustomerScreen} options={{ title: v.Customer }} />
      <Stack.Screen name="Approvals" component={ApprovalsScreen} options={{ title: 'Pedidos para aprovar' }} />
      <Stack.Screen name="PixList" component={PaymentsScreen} options={{ title: 'Pagamentos Pix' }} />
    </>
  );
}

function HomeStack() {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="HomeMain" component={HomeScreen} options={{ headerShown: false }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

function AgendaStack() {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="AgendaHome" component={AgendaScreen} options={{ title: 'Agenda' }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

function PaymentsStack() {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="PaymentsHome" component={PaymentsScreen} options={{ title: 'Pagamentos Pix' }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

function FinanceStack() {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="FinanceHome" component={FinanceHomeScreen} options={{ title: 'Financeiro' }} />
      <Stack.Screen name="Expenses" component={ExpensesScreen} options={{ title: 'Gastos' }} />
      <Stack.Screen name="ExpenseEdit" component={ExpenseEditScreen} options={{ title: 'Gasto' }} />
      <Stack.Screen name="Commissions" component={CommissionsScreen} options={{ title: 'Comissões e repasses' }} />
      <Stack.Screen name="CommissionRules" component={CommissionRulesScreen} options={{ title: 'Regras de repasse' }} />
      <Stack.Screen name="CommissionRuleEdit" component={CommissionRuleEditScreen} options={{ title: 'Regra de repasse' }} />
      <Stack.Screen name="Settlements" component={SettlementsScreen} options={{ title: 'Acertos' }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

function CustomersStack() {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="CustomersHome" component={CustomersScreen} options={{ title: v.Customers }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

function MoreStack({ onLogout, shopName }) {
  const opts = useStackOpts();
  const { v } = useTheme();
  return (
    <Stack.Navigator screenOptions={opts}>
      <Stack.Screen name="MoreHome" options={{ title: 'Mais' }}>
        {(props) => <MoreScreen {...props} onLogout={onLogout} shopName={shopName} />}
      </Stack.Screen>
      <Stack.Screen name="Services" component={ServicesScreen} options={{ title: 'Serviços' }} />
      <Stack.Screen name="ServiceEdit" component={ServiceEditScreen} options={{ title: 'Serviço' }} />
      <Stack.Screen name="Barbers" component={BarbersScreen} options={{ title: v.Pros }} />
      <Stack.Screen name="BarberEdit" component={BarberEditScreen} options={{ title: v.Pro }} />
      <Stack.Screen name="Blocks" component={BlocksScreen} options={{ title: 'Bloqueios' }} />
      <Stack.Screen name="Reviews" component={ReviewsScreen} options={{ title: 'Avaliações' }} />
      <Stack.Screen name="Reports" component={ReportsScreen} options={{ title: 'Relatórios' }} />
      {/* aberta pela seção "Comissões" do profissional */}
      <Stack.Screen name="CommissionRuleEdit" component={CommissionRuleEditScreen} options={{ title: 'Regra de repasse' }} />
      <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Configurações' }} />
      <Stack.Screen name="WhatsApp" component={WhatsAppScreen} options={{ title: 'Conexão do WhatsApp' }} />
      <Stack.Screen name="About" component={AboutScreen} options={{ title: 'Sobre o SyncServ' }} />
      {shared(v)}
    </Stack.Navigator>
  );
}

const ICONS = { Hoje: 'today', Agenda: 'calendar', Pix: 'cash', Financeiro: 'wallet', Clientes: 'people', Mais: 'menu' };

function Tabs({ onLogout, shopName }) {
  const { c, font, v, mode } = useTheme();
  const navTheme = useNavTheme();
  return (
    <NavigationContainer theme={navTheme}>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      <Tab.Navigator screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: c.accentText,
        tabBarInactiveTintColor: c.textMuted,
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.divider, minHeight: 64 },
        tabBarLabelStyle: { fontFamily: font.semibold, fontSize: 12 },
        tabBarAllowFontScaling: false,
        tabBarItemStyle: { paddingVertical: 4 },
        tabBarIcon: ({ color, focused }) => (
          <Ionicons name={ICONS[route.name] + (focused ? '' : '-outline')} size={24} color={color} />
        ),
      })}>
        <Tab.Screen name="Hoje" component={HomeStack} />
        <Tab.Screen name="Agenda" component={AgendaStack} />
        <Tab.Screen name="Pix" component={PaymentsStack} />
        <Tab.Screen name="Financeiro" component={FinanceStack} options={{ tabBarLabel: 'Finanças' }} />
        <Tab.Screen name="Clientes" component={CustomersStack} options={{ tabBarLabel: v.Customers }} />
        <Tab.Screen name="Mais">
          {() => <MoreStack onLogout={onLogout} shopName={shopName} />}
        </Tab.Screen>
      </Tab.Navigator>
      <ToastHost />
    </NavigationContainer>
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

export default function App() {
  const [fontsLoaded] = useFonts({
    PlusJakartaSans_400Regular, PlusJakartaSans_500Medium, PlusJakartaSans_600SemiBold, PlusJakartaSans_700Bold,
    PlusJakartaSans_800ExtraBold,
  });
  const [session, setSession] = useState(null);

  useEffect(() => {
    loadSession().then(setSession);
  }, []);
  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded]);

  const logout = useCallback(async () => {
    await clearSession();
    setSession((s) => ({ ...s, token: '' }));
  }, []);
  useEffect(() => { setUnauthorizedHandler(logout); }, [logout]);

  // Troca de segmento ou modo nas Configurações: aplica na hora e guarda para a próxima abertura
  const setAppearance = useCallback((niche, themeMode, shopName) => {
    setSession((s) => ({ ...s, niche, themeMode, shop: shopName || s.shop }));
    saveAppearance(niche, themeMode, shopName);
  }, []);

  // Confere o tema do negócio na API (pode ter mudado em outro aparelho)
  const token = session?.token;
  useEffect(() => {
    if (!token) return;
    api.get('/me').then((me) => setAppearance(me.niche, me.theme_mode, me.shop_name)).catch(() => {});
  }, [token, setAppearance]);

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
                   themeMode: r.theme_mode,
                 })} />
          <ToastHost />
        </ThemeProvider>
      ) : (
        <ThemeProvider niche={session.niche} themeMode={session.themeMode} setAppearance={setAppearance}>
          <Tabs onLogout={logout} shopName={session.shop} />
        </ThemeProvider>
      )}
    </SafeAreaProvider>
  );
}
