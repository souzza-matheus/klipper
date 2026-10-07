// Rótulo, tom (cor do tema) e ícone de cada status. O ícone dá um sinal além da cor.

export const STATUS = {
  scheduled: { label: 'Agendado', tone: 'info', icon: 'time-outline' },
  confirmed: { label: 'Confirmado', tone: 'success', icon: 'checkmark-circle-outline' },
  completed: { label: 'Atendido', tone: 'neutral', icon: 'checkmark-done' },
  cancelled: { label: 'Cancelado', tone: 'danger', icon: 'close-circle-outline' },
  no_show: { label: 'Faltou', tone: 'danger', icon: 'alert-circle-outline' },
  pending_approval: { label: 'Aguardando aprovação', tone: 'accent', icon: 'hourglass-outline' },
  awaiting_deposit: { label: 'Aguardando sinal', tone: 'warning', icon: 'cash-outline' },
  held: { label: 'Reservado (lista de espera)', tone: 'accent', icon: 'hourglass-outline' },
};

// Sinal (Pix antecipado que garante o horário)
export const DEPOSIT = {
  none: null,
  pending: { label: 'Sinal pendente', tone: 'warning', icon: 'time-outline' },
  paid: { label: 'Sinal pago', tone: 'success', icon: 'checkmark-circle' },
  refund_due: { label: 'Devolver sinal', tone: 'danger', icon: 'return-down-back-outline' },
  refunded: { label: 'Sinal devolvido', tone: 'neutral', icon: 'checkmark-done' },
  forfeited: { label: 'Sinal retido', tone: 'neutral', icon: 'lock-closed-outline' },
};

// Acesso do cliente ao agendamento pelo bot
export const ACCESS = {
  normal: null,
  approval: { label: 'Precisa de aprovação', tone: 'info', icon: 'shield-checkmark-outline' },
  blocked: { label: 'Bloqueado', tone: 'danger', icon: 'ban-outline' },
};

export const PAY = {
  none: null,
  pending: { label: 'Pix pendente', tone: 'warning', icon: 'time-outline' },
  paid: { label: 'Pix pago', tone: 'success', icon: 'checkmark-circle' },
  expired: { label: 'Pix expirado', tone: 'neutral', icon: 'close-circle-outline' },
};

export const PAY_LIST = {
  pending: { label: 'Pendente', tone: 'warning', icon: 'time-outline' },
  paid: { label: 'Pago', tone: 'success', icon: 'checkmark-circle' },
  expired: { label: 'Expirado', tone: 'neutral', icon: 'close-circle-outline' },
};
