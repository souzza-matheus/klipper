// Repositório pela API (versão web, e o celular quando o modo offline não está disponível).
// Mesmas funções de repo.local.js; as telas chamam sempre `repo` (src/repo.js).
import { api } from './api';

export const remote = {
  mode: 'online',

  // ------------------------------------------------ leitura
  agendaDay: (day) => api.get('/agenda/day', { day }),
  appointmentsMonth: (year, month, barberId) => api.get('/appointments/month', { year, month, barber_id: barberId }),
  appointmentsOfDay: (day, includeCancelled = false) => api.get('/appointments', { date_from: day,
                                                                                    include_cancelled: includeCancelled }),
  async appointment(id, hint) {
    const day = hint?.start?.slice(0, 10);
    if (!day) return hint;
    const list = await api.get('/appointments', { date_from: day, include_cancelled: true });
    return list.find((x) => x.id === id) || hint;
  },
  availability: (q) => api.get('/availability', q),
  customers: (q) => api.get('/customers', q),
  customer: (id) => api.get(`/customers/${id}`),
  comandas: (q) => api.get('/comandas', q),
  comanda: (id) => api.get(`/comandas/${id}`),
  services: () => api.get('/services'),
  barbers: () => api.get('/barbers'),
  products: (includeInactive = false) => api.get('/products', includeInactive ? { include_inactive: true } : undefined),
  productMovements: (id) => api.get(`/products/${id}/movements`),
  packagePlans: () => api.get('/package-plans'),
  waitlist: (day, includeClosed) => api.get('/waitlist', { day, include_closed: includeClosed }),
  blocks: () => api.get('/blocks'),
  shop: () => api.get('/shop'),

  // ------------------------------------------------ escrita
  createAppointment: (body) => api.post('/appointments', body),
  updateAppointment: (a, body) => api.patch(`/appointments/${a.id}`, body),
  checkIn: (a) => api.post(`/appointments/${a.id}/check-in`),
  reschedule: (a, body) => api.post(`/appointments/${a.id}/reschedule`, body),
  updateCustomer: (c, body) => api.put(`/customers/${c.id}`, body),
  openComanda: (body) => api.post('/comandas', body),
  addComandaItem: (c, body) => api.post(`/comandas/${c.id}/items`, body),
  reverseComandaItem: (c, item) => api.post(`/comandas/${c.id}/items/${item.id}/reverse`),
  addComandaPayment: (c, body) => api.post(`/comandas/${c.id}/payments`, body),
  reverseComandaPayment: (c, p) => api.post(`/comandas/${c.id}/payments/${p.id}/reverse`),
  closeComanda: (c) => api.post(`/comandas/${c.id}/close`),
  cancelComanda: (c) => api.post(`/comandas/${c.id}/cancel`),
  addStockMovement: (p, body) => api.post(`/products/${p.id}/movements`, body),
  joinWaitlist: (body) => api.post('/waitlist', body),
  createBlock: (body) => api.post('/blocks', body),
  deleteBlock: (b) => api.del(`/blocks/${b.id}`),
};
