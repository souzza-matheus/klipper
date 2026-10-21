// Versão web: a parte de depois do login (React Navigation, abas, menu lateral) vem num pedaço separado do
// JavaScript, para a tela de login abrir mais rápido. prefetchShell baixa esse pedaço em segundo plano assim que a
// pessoa começa a usar o login (foco, toque ou tecla), enquanto digita a senha; já logada, baixa as telas das abas
// principais.
import { lazyScreen, preload } from './lazyScreen';

const shell = () => import('./AppShell');
const routes = () => import('./routes');

export const Tabs = lazyScreen(shell, 'Tabs');
export const FirstLogin = lazyScreen(shell, 'FirstLogin');

const EVENTS = ['focusin', 'pointerdown', 'keydown'];

export function prefetchShell(loggedIn) {
  if (loggedIn) {
    const idle = typeof requestIdleCallback === 'function' ? requestIdleCallback : (fn) => setTimeout(fn, 1500);
    idle(() => routes().then((m) => m.prefetchScreens()).catch(() => {}));
    return;
  }
  const start = () => {
    EVENTS.forEach((e) => window.removeEventListener(e, start, true));
    preload(shell).catch(() => {});
  };
  EVENTS.forEach((e) => window.addEventListener(e, start, true));
}
