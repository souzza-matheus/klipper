// Parte do app que só aparece depois do login: navegação por abas e pilhas, menu lateral, atalhos e o primeiro
// acesso. Fica num arquivo próprio para a versão web baixar este pedaço (React Navigation incluído) só depois do
// JavaScript do login (src/shell.web.js); no celular entra direto (src/shell.js).
import React, { useEffect, useMemo } from 'react';
import { Platform, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import {
  createNavigationContainerRef, DarkTheme, DefaultTheme, NavigationContainer, useFocusEffect,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { BottomTabBar, createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import Ionicons from '@expo/vector-icons/Ionicons';
import { OfflineBanner, Sidebar } from './components/Layout';
import { provideFocusEffect } from './focus';
import { AttentionScreen, SyncBanner, SyncScreen } from './components/Sync';
import { shortcutFor, tabsFor } from './roles';
import { useWide } from './session';
import { TYPE } from './theme';
import { useTheme } from './ThemeProvider';
import { DialogHost, IconButton, ToastHost } from './ui';
// Na web cada grupo de telas é baixado sob demanda (routes.web.js); no celular vem tudo junto (routes.js)
import {
  AboutScreen, AgendaScreen, AppointmentScreen, ApprovalsScreen, BarberEditScreen, BarbersScreen, BlocksScreen,
  ChangePasswordScreen, ComandaScreen, ComandasScreen, CommissionRuleEditScreen, CommissionRulesScreen,
  CommissionsScreen, CustomerScreen, CustomersScreen, ExpenseEditScreen, ExpensesScreen, FinanceHomeScreen,
  HomeScreen, MoreScreen, NewAppointmentScreen, PackageEditScreen, PackagesScreen, PaymentsScreen, PlanEditScreen,
  ProductEditScreen, ProductsScreen, ReportsScreen, ReviewsScreen, ServiceEditScreen, ServicesScreen,
  SettingsScreen, SettlementsScreen, SubscribeScreen, SubscriptionsScreen, SwitchBusinessScreen, TeamScreen,
  UserEditScreen, WaitlistScreen, WhatsAppScreen,
} from './routes';

provideFocusEffect(useFocusEffect);

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
    ['SwitchBusiness', SwitchBusinessScreen, 'Trocar de negócio'],
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

export function Tabs({ onLogout, session }) {
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
export function FirstLogin({ onDone }) {
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
