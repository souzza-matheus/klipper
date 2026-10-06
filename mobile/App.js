import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { clearSession, loadSession, setUnauthorizedHandler } from './src/api';
import { colors } from './src/theme';
import { Loading } from './src/ui';
import Login from './src/screens/Login';
import { AgendaScreen, AppointmentScreen, NewAppointmentScreen } from './src/screens/Agenda';
import { PaymentsScreen } from './src/screens/Payments';
import { CustomerScreen, CustomersScreen } from './src/screens/Customers';
import { BarberEditScreen, BarbersScreen, BlocksScreen, ServiceEditScreen, ServicesScreen } from './src/screens/Catalog';
import { ReportsScreen, ReviewsScreen } from './src/screens/Insights';
import {
  CommissionRuleEditScreen, CommissionRulesScreen, CommissionsScreen, SettlementsScreen,
} from './src/screens/Finance';
import { MoreScreen, SettingsScreen, WhatsAppScreen } from './src/screens/Settings';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

const theme = { ...DefaultTheme, colors: { ...DefaultTheme.colors, background: colors.bg, primary: colors.primary } };
const stackOpts = {
  headerStyle: { backgroundColor: colors.card },
  headerTintColor: colors.primary,
  headerTitleStyle: { fontWeight: '700', color: colors.ink },
  headerBackTitle: 'Voltar',
};

// Telas de detalhe disponíveis a partir de qualquer aba
function shared() {
  return (
    <>
      <Stack.Screen name="Appointment" component={AppointmentScreen} options={{ title: 'Agendamento' }} />
      <Stack.Screen name="NewAppointment" component={NewAppointmentScreen} options={{ title: 'Novo agendamento' }} />
      <Stack.Screen name="Customer" component={CustomerScreen} options={{ title: 'Cliente' }} />
    </>
  );
}

function AgendaStack() {
  return (
    <Stack.Navigator screenOptions={stackOpts}>
      <Stack.Screen name="AgendaHome" component={AgendaScreen} options={{ title: 'Agenda' }} />
      {shared()}
    </Stack.Navigator>
  );
}

function PaymentsStack() {
  return (
    <Stack.Navigator screenOptions={stackOpts}>
      <Stack.Screen name="PaymentsHome" component={PaymentsScreen} options={{ title: 'Pagamentos Pix' }} />
      {shared()}
    </Stack.Navigator>
  );
}

function CustomersStack() {
  return (
    <Stack.Navigator screenOptions={stackOpts}>
      <Stack.Screen name="CustomersHome" component={CustomersScreen} options={{ title: 'Clientes' }} />
      {shared()}
    </Stack.Navigator>
  );
}

function MoreStack({ onLogout, shopName }) {
  return (
    <Stack.Navigator screenOptions={stackOpts}>
      <Stack.Screen name="MoreHome" options={{ title: 'Mais' }}>
        {(props) => <MoreScreen {...props} onLogout={onLogout} shopName={shopName} />}
      </Stack.Screen>
      <Stack.Screen name="Services" component={ServicesScreen} options={{ title: 'Serviços' }} />
      <Stack.Screen name="ServiceEdit" component={ServiceEditScreen} options={{ title: 'Serviço' }} />
      <Stack.Screen name="Barbers" component={BarbersScreen} options={{ title: 'Barbeiros' }} />
      <Stack.Screen name="BarberEdit" component={BarberEditScreen} options={{ title: 'Barbeiro' }} />
      <Stack.Screen name="Blocks" component={BlocksScreen} options={{ title: 'Bloqueios' }} />
      <Stack.Screen name="Reviews" component={ReviewsScreen} options={{ title: 'Avaliações' }} />
      <Stack.Screen name="Reports" component={ReportsScreen} options={{ title: 'Relatórios' }} />
      <Stack.Screen name="Commissions" component={CommissionsScreen} options={{ title: 'Comissões e repasses' }} />
      <Stack.Screen name="CommissionRules" component={CommissionRulesScreen} options={{ title: 'Regras de repasse' }} />
      <Stack.Screen name="CommissionRuleEdit" component={CommissionRuleEditScreen} options={{ title: 'Regra de repasse' }} />
      <Stack.Screen name="Settlements" component={SettlementsScreen} options={{ title: 'Acertos' }} />
      <Stack.Screen name="Settings" component={SettingsScreen} options={{ title: 'Configurações' }} />
      <Stack.Screen name="WhatsApp" component={WhatsAppScreen} options={{ title: 'WhatsApp' }} />
      {shared()}
    </Stack.Navigator>
  );
}

const ICONS = { Agenda: 'calendar', Pix: 'cash', Clientes: 'people', Mais: 'menu' };

export default function App() {
  const [session, setSession] = useState(null);

  useEffect(() => {
    loadSession().then(setSession);
  }, []);

  const logout = async () => {
    await clearSession();
    setSession((s) => ({ ...s, token: '' }));
  };
  useEffect(() => { setUnauthorizedHandler(logout); }, []);

  if (!session) return <Loading />;

  return (
    <SafeAreaProvider>
      <StatusBar style="dark" />
      {!session.token ? (
        <Login initialUrl={session.baseUrl}
               onLogged={(r) => setSession({ ...session, token: r.token, name: r.user_name, shop: r.shop_name })} />
      ) : (
        <NavigationContainer theme={theme}>
          <Tab.Navigator screenOptions={({ route }) => ({
            headerShown: false,
            tabBarActiveTintColor: colors.primary,
            tabBarInactiveTintColor: colors.muted,
            tabBarIcon: ({ color, size, focused }) => (
              <Ionicons name={ICONS[route.name] + (focused ? '' : '-outline')} size={size} color={color} />
            ),
          })}>
            <Tab.Screen name="Agenda" component={AgendaStack} />
            <Tab.Screen name="Pix" component={PaymentsStack} />
            <Tab.Screen name="Clientes" component={CustomersStack} />
            <Tab.Screen name="Mais">
              {() => <MoreStack onLogout={logout} shopName={session.shop} />}
            </Tab.Screen>
          </Tab.Navigator>
        </NavigationContainer>
      )}
    </SafeAreaProvider>
  );
}
