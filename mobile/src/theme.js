export const colors = {
  bg: '#F5F3EF',
  card: '#FFFFFF',
  ink: '#1C1F26',
  muted: '#6B6F78',
  line: '#E4E0D8',
  primary: '#1F2A44',
  accent: '#B8862F',
  good: '#2E7D4F',
  warn: '#B7791F',
  bad: '#B3261E',
  goodBg: '#E5F3EA',
  warnBg: '#FBF0DC',
  badBg: '#FBE4E2',
  infoBg: '#E6EAF2',
  pending: '#6B4FA0',
  pendingBg: '#EEE8F7',
};

export const STATUS = {
  scheduled: { label: 'Agendado', fg: colors.primary, bg: colors.infoBg },
  confirmed: { label: 'Confirmado', fg: colors.good, bg: colors.goodBg },
  completed: { label: 'Atendido', fg: colors.muted, bg: '#EEECE8' },
  cancelled: { label: 'Cancelado', fg: colors.bad, bg: colors.badBg },
  no_show: { label: 'Faltou', fg: colors.bad, bg: colors.badBg },
  pending_approval: { label: 'Aguardando aprovação', fg: colors.pending, bg: colors.pendingBg },
};

// Acesso do cliente ao agendamento pelo bot
export const ACCESS = {
  normal: null,
  approval: { label: 'Precisa de aprovação', fg: colors.warn, bg: colors.warnBg },
  blocked: { label: 'Bloqueado', fg: colors.bad, bg: colors.badBg },
};

export const PAY = {
  none: null,
  pending: { label: 'Pix pendente', fg: colors.warn, bg: colors.warnBg },
  paid: { label: 'Pago', fg: colors.good, bg: colors.goodBg },
  expired: { label: 'Pix expirado', fg: colors.muted, bg: '#EEECE8' },
};
