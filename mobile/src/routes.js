// Telas do app. No celular vêm todas no mesmo pacote (o app abre sem internet); a versão web divide por rota
// (routes.web.js).

export { HomeScreen } from './screens/Home';
export { AgendaScreen, ApprovalsScreen, AppointmentScreen, NewAppointmentScreen } from './screens/Agenda';
export { PaymentsScreen } from './screens/Payments';
export { CustomerScreen, CustomersScreen } from './screens/Customers';
export { BarberEditScreen, BarbersScreen, BlocksScreen, ServiceEditScreen, ServicesScreen } from './screens/Catalog';
export { ReportsScreen, ReviewsScreen } from './screens/Insights';
export { CommissionRuleEditScreen, CommissionRulesScreen, CommissionsScreen, ExpenseEditScreen, ExpensesScreen, FinanceHomeScreen, SettlementsScreen } from './screens/Finance';
export { AboutScreen, MoreScreen, SettingsScreen, WhatsAppScreen } from './screens/Settings';
export { ComandaScreen, ComandasScreen } from './screens/Comandas';
export { ProductEditScreen, ProductsScreen } from './screens/Stock';
export { PackageEditScreen, PackagesScreen, PlanEditScreen, SubscribeScreen, SubscriptionsScreen } from './screens/Plans';
export { WaitlistScreen } from './screens/Waitlist';
export { ChangePasswordScreen, TeamScreen, UserEditScreen } from './screens/Team';

export function prefetchScreens() {}
