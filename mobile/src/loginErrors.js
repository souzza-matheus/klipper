// Mensagens de erro do login, abaixo dos campos. Nunca dizem se o e-mail existe: e-mail ou senha errados dão a
// mesma frase (o servidor também responde igual).
export const LOGIN_ERRORS = {
  credentials: 'E-mail ou senha incorretos',
  offline: 'Sem conexão com a internet',
  server: 'Servidor indisponível, tente novamente em instantes',
  email: 'Confira o e-mail digitado.',
};

// e: ApiError (status 0 = o pedido não chegou ao servidor); online: o aparelho tem internet?
export function loginErrorMessage(e, online) {
  const status = e?.status ?? 0;
  if (status === 0) return online ? LOGIN_ERRORS.server : LOGIN_ERRORS.offline;
  if (status === 401) return LOGIN_ERRORS.credentials;
  // Senha certa, mas nenhum negócio ativo: o servidor manda a mensagem ("Seu acesso foi desativado...")
  if (status === 403 && e?.data?.detail?.code === 'access_disabled') return e.message;
  if (status === 422) return LOGIN_ERRORS.email;
  if (status === 429) return e.message; // "Muitas tentativas. Tente de novo em N min."
  return LOGIN_ERRORS.server;
}
