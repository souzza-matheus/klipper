// Papéis e o que cada um vê no app. Espelha as permissões da API (backend/app/permissions.py): esconder um botão
// aqui é só conforto; quem garante é a API, que responde 403 fora do papel.

export const ROLES = ['owner', 'reception', 'professional'];
export const ROLE_LABEL = { owner: 'Dono', reception: 'Recepção', professional: 'Profissional' };

const ALL = ROLES;
const STAFF = ['owner', 'reception'];
const OWNER = ['owner'];

export const FEATURES = {
  home: STAFF,
  agenda: ALL,
  newAppointment: STAFF,
  reschedule: STAFF,
  cancelAppointment: STAFF,
  changePrice: STAFF,
  sendPix: STAFF,
  checkIn: ALL,
  approvals: STAFF,
  comandas: STAFF,
  reverseClosed: OWNER, // estorno em comanda já fechada
  pix: STAFF,
  customers: ALL,
  customerEdit: STAFF,
  customerAccess: OWNER, // bloqueio, aprovação e clientes incompatíveis
  customerBalance: STAFF,
  finance: OWNER,
  commissions: ['owner', 'professional'],
  products: STAFF,
  productCost: OWNER,
  productEdit: OWNER,
  stockPurchase: OWNER, // entrada e ajuste; uso interno é STAFF
  packages: STAFF,
  packageEdit: OWNER,
  subscriptions: STAFF,
  planEdit: OWNER,
  mrr: OWNER,
  chargeCancel: OWNER,
  waitlist: STAFF,
  team: OWNER,
  services: OWNER,
  barbers: OWNER,
  blocks: STAFF,
  reviews: ALL,
  reports: OWNER,
  settings: OWNER,
  whatsapp: OWNER,
};

export function can(role, feature) {
  const allowed = FEATURES[feature];
  if (!allowed) throw new Error(`Permissão desconhecida: ${feature}`);
  return allowed.includes(role || 'owner');
}

// Abas principais (rodapé no celular, menu lateral no computador)
const TABS = [
  { name: 'Hoje', icon: 'today', feature: 'home' },
  { name: 'Agenda', icon: 'calendar', feature: 'agenda' },
  { name: 'Caixa', icon: 'receipt', feature: 'comandas' },
  { name: 'Clientes', icon: 'people', feature: 'customers' },
  { name: 'Financeiro', icon: 'wallet', feature: 'finance', label: 'Finanças' },
  { name: 'Comissoes', icon: 'cash', feature: 'commissions', label: 'Comissões', onlyRole: 'professional' },
  { name: 'Mais', icon: 'menu' },
];

export function tabsFor(role) {
  return TABS.filter((t) => (!t.feature || can(role, t.feature)) && (!t.onlyRole || t.onlyRole === role));
}

// Itens da aba Mais (e da seção "Gestão" do menu lateral). label pode usar o vocabulário do segmento (v).
const MORE = [
  { route: 'PixList', icon: 'qr-code-outline', label: () => 'Pagamentos Pix', feature: 'pix' },
  { route: 'Products', icon: 'cube-outline', label: () => 'Produtos e estoque', feature: 'products' },
  { route: 'Packages', icon: 'albums-outline', label: () => 'Pacotes', feature: 'packages' },
  { route: 'Subscriptions', icon: 'repeat-outline', label: () => 'Clube de assinatura', feature: 'subscriptions' },
  { route: 'Waitlist', icon: 'list-outline', label: () => 'Lista de espera', feature: 'waitlist' },
  { route: 'Team', icon: 'id-card-outline', label: () => 'Equipe e permissões', feature: 'team' },
  { route: 'Services', icon: 'pricetags-outline', label: () => 'Serviços e preços', feature: 'services' },
  { route: 'Barbers', icon: 'people-outline', label: (v) => `${v.Pros} e expediente`, feature: 'barbers' },
  { route: 'Blocks', icon: 'lock-closed-outline', label: () => 'Bloqueios de agenda', feature: 'blocks' },
  { route: 'Reviews', icon: 'star-outline', label: () => 'Avaliações', feature: 'reviews' },
  { route: 'Reports', icon: 'bar-chart-outline', label: () => 'Relatórios', feature: 'reports' },
  { route: 'Settings', icon: 'settings-outline', label: () => 'Configurações e aparência', feature: 'settings' },
  { route: 'WhatsApp', icon: 'logo-whatsapp', label: () => 'Conexão do WhatsApp', feature: 'whatsapp' },
  { route: 'Sync', icon: 'sync-outline', label: () => 'Sincronização e modo offline', appOnly: true },
  { route: 'ChangePassword', icon: 'key-outline', label: () => 'Trocar senha' },
  { route: 'About', icon: 'information-circle-outline', label: () => 'Sobre o SyncServ' },
];

// web=true: sem os itens que só existem no app do celular (modo offline)
export function moreItemsFor(role, v = { Pros: 'Profissionais' }, web = false) {
  return MORE.filter((m) => (!m.feature || can(role, m.feature)) && !(web && m.appOnly))
    .map((m) => ({ ...m, label: m.label(v) }));
}

// Atalhos de teclado da versão web (computador). Só com o foco fora de campos de texto.
export const SHORTCUTS = [
  { key: 'n', label: 'Novo agendamento', feature: 'newAppointment' },
  { key: 'c', label: 'Abrir comanda', feature: 'comandas' },
  { key: 'b', label: 'Buscar cliente', feature: 'customers' },
];

export function shortcutFor(role, key) {
  const k = String(key || '').toLowerCase();
  return SHORTCUTS.find((s) => s.key === k && can(role, s.feature)) || null;
}

// Largura a partir da qual o app vira "computador": menu lateral fixo e conteúdo mais largo
export const WIDE = 900;
export const isWide = (width) => width >= WIDE;
