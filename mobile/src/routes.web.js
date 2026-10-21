// Versão web: cada arquivo de telas vira um pedaço separado do JavaScript (import() dinâmico), baixado na primeira
// vez que a tela abre. O pacote inicial fica só com o login e a estrutura do app; depois do login, as abas principais
// são baixadas em segundo plano (prefetchScreens). No celular, routes.js importa tudo direto.
import { lazyScreen, preload } from './lazyScreen';

const home = () => import('./screens/Home');
const agenda = () => import('./screens/Agenda');
const payments = () => import('./screens/Payments');
const customers = () => import('./screens/Customers');
const catalog = () => import('./screens/Catalog');
const insights = () => import('./screens/Insights');
const finance = () => import('./screens/Finance');
const settings = () => import('./screens/Settings');
const comandas = () => import('./screens/Comandas');
const stock = () => import('./screens/Stock');
const plans = () => import('./screens/Plans');
const waitlist = () => import('./screens/Waitlist');
const team = () => import('./screens/Team');

export const HomeScreen = lazyScreen(home, 'HomeScreen');
export const AgendaScreen = lazyScreen(agenda, 'AgendaScreen');
export const ApprovalsScreen = lazyScreen(agenda, 'ApprovalsScreen');
export const AppointmentScreen = lazyScreen(agenda, 'AppointmentScreen');
export const NewAppointmentScreen = lazyScreen(agenda, 'NewAppointmentScreen');
export const PaymentsScreen = lazyScreen(payments, 'PaymentsScreen');
export const CustomerScreen = lazyScreen(customers, 'CustomerScreen');
export const CustomersScreen = lazyScreen(customers, 'CustomersScreen');
export const BarberEditScreen = lazyScreen(catalog, 'BarberEditScreen');
export const BarbersScreen = lazyScreen(catalog, 'BarbersScreen');
export const BlocksScreen = lazyScreen(catalog, 'BlocksScreen');
export const ServiceEditScreen = lazyScreen(catalog, 'ServiceEditScreen');
export const ServicesScreen = lazyScreen(catalog, 'ServicesScreen');
export const ReportsScreen = lazyScreen(insights, 'ReportsScreen');
export const ReviewsScreen = lazyScreen(insights, 'ReviewsScreen');
export const CommissionRuleEditScreen = lazyScreen(finance, 'CommissionRuleEditScreen');
export const CommissionRulesScreen = lazyScreen(finance, 'CommissionRulesScreen');
export const CommissionsScreen = lazyScreen(finance, 'CommissionsScreen');
export const ExpenseEditScreen = lazyScreen(finance, 'ExpenseEditScreen');
export const ExpensesScreen = lazyScreen(finance, 'ExpensesScreen');
export const FinanceHomeScreen = lazyScreen(finance, 'FinanceHomeScreen');
export const SettlementsScreen = lazyScreen(finance, 'SettlementsScreen');
export const AboutScreen = lazyScreen(settings, 'AboutScreen');
export const MoreScreen = lazyScreen(settings, 'MoreScreen');
export const SettingsScreen = lazyScreen(settings, 'SettingsScreen');
export const WhatsAppScreen = lazyScreen(settings, 'WhatsAppScreen');
export const ComandaScreen = lazyScreen(comandas, 'ComandaScreen');
export const ComandasScreen = lazyScreen(comandas, 'ComandasScreen');
export const ProductEditScreen = lazyScreen(stock, 'ProductEditScreen');
export const ProductsScreen = lazyScreen(stock, 'ProductsScreen');
export const PackageEditScreen = lazyScreen(plans, 'PackageEditScreen');
export const PackagesScreen = lazyScreen(plans, 'PackagesScreen');
export const PlanEditScreen = lazyScreen(plans, 'PlanEditScreen');
export const SubscribeScreen = lazyScreen(plans, 'SubscribeScreen');
export const SubscriptionsScreen = lazyScreen(plans, 'SubscriptionsScreen');
export const WaitlistScreen = lazyScreen(waitlist, 'WaitlistScreen');
export const ChangePasswordScreen = lazyScreen(team, 'ChangePasswordScreen');
export const TeamScreen = lazyScreen(team, 'TeamScreen');
export const UserEditScreen = lazyScreen(team, 'UserEditScreen');

// Abas principais e telas mais abertas: baixa assim que o navegador estiver livre
export function prefetchScreens() {
  const idle = typeof requestIdleCallback === 'function' ? requestIdleCallback : (fn) => setTimeout(fn, 1500);
  idle(() => [home, agenda, comandas, customers, settings].forEach((load) => preload(load).catch(() => {})));
}
