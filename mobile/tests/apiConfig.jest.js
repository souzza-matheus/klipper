// Endereço da API embutido no build, endereço antigo apagado, troca de negócio limpando o offline e modo
// desenvolvedor fora do build de produção.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const mockStore = {};
jest.mock('expo-secure-store', () => ({
  getItemAsync: async (k) => (k in mockStore ? mockStore[k] : null),
  setItemAsync: async (k, v) => { mockStore[k] = v; },
  deleteItemAsync: async (k) => { delete mockStore[k]; },
}));
jest.mock('../src/net', () => ({ isOnline: () => true }));

const MOBILE = path.join(__dirname, '..');

function freshApi(env) {
  const old = { ...process.env };
  Object.assign(process.env, env);
  let mod;
  jest.isolateModules(() => { mod = { api: require('../src/api'), config: require('../src/config') }; });
  process.env = old;
  return mod;
}

beforeEach(() => { Object.keys(mockStore).forEach((k) => delete mockStore[k]); });

describe('endereço da API', () => {
  test('vem da variável do perfil do build (EXPO_PUBLIC_API_URL)', async () => {
    const { api, config } = freshApi({ EXPO_PUBLIC_APP_PROFILE: 'preview',
                                       EXPO_PUBLIC_API_URL: 'https://staging.exemplo.com.br/' });
    expect(config.PROFILE).toBe('preview');
    expect(await api.resolveApiUrl()).toBe('https://staging.exemplo.com.br');
  });

  test('web servida em app.<domínio> usa https://api.<domínio>', () => {
    const { config } = freshApi({ EXPO_PUBLIC_API_URL: 'https://api.outro.com' });
    const at = (hostname, origin) => config.buildApiUrl({ hostname, origin }, 'https://api.outro.com', true);
    expect(at('app.exemplo.com.br', 'https://app.exemplo.com.br')).toBe('https://api.exemplo.com.br');
    // Fora de app.<domínio> (teste local): o do build; sem build, o próprio endereço da página
    expect(at('localhost', 'http://localhost:8080')).toBe('https://api.outro.com');
    expect(config.buildApiUrl({ hostname: 'localhost', origin: 'http://localhost:8080' }, '', true))
      .toBe('http://localhost:8080');
  });

  test('o endereço salvo por versões antigas é ignorado e apagado na primeira abertura', async () => {
    mockStore.baseUrl = 'http://192.168.0.99:8000';
    mockStore.token = 'tok';
    const { api } = freshApi({ EXPO_PUBLIC_API_URL: 'https://api.exemplo.com.br' });
    const session = await api.loadSession();
    expect(mockStore.baseUrl).toBeUndefined();
    expect(api.currentApiUrl()).toBe('https://api.exemplo.com.br');
    expect(session.token).toBe('tok'); // a sessão continua
    expect(session).not.toHaveProperty('baseUrl');
  });

  test('modo desenvolvedor: o endereço trocado vale por cima do build e volta ao do build', async () => {
    const { api } = freshApi({ EXPO_PUBLIC_APP_PROFILE: 'development', EXPO_PUBLIC_API_URL: 'https://api.x.com' });
    let dev;
    jest.isolateModules(() => { dev = require('../src/devApi'); });
    await dev.setDevApiUrl('http://192.168.0.10:8002/');
    expect(await api.resolveApiUrl()).toBe('http://192.168.0.10:8002');
    await dev.setDevApiUrl('');
    expect(await api.resolveApiUrl()).toBe('https://api.x.com');
  });
});

describe('troca de negócio', () => {
  test('pede o token novo, apaga o banco offline do anterior e só então carrega o novo', async () => {
    const calls = [];
    let promise;
    jest.isolateModules(() => {
      jest.doMock('../src/api', () => ({
        switchBusiness: async (id) => { calls.push(['switch', id]); return { token: 't2', shop_id: id }; },
      }));
      jest.doMock('../src/offline/manager', () => ({
        stopOffline: async (opts) => { calls.push(['stopOffline', opts]); },
        offlineState: () => ({ pending: 0 }), syncNow: async () => ({}),
      }));
      const { changeBusiness } = require('../src/businessSwitch');
      promise = changeBusiness(7, async (r) => { calls.push(['apply', r.shop_id]); });
    });
    await promise;
    expect(calls).toEqual([['switch', 7], ['stopOffline', { wipe: true }], ['apply', 7]]);
  });

  test('se o pedido falhar (sem internet), nada é apagado', async () => {
    const stop = jest.fn();
    let promise;
    jest.isolateModules(() => {
      jest.doMock('../src/api', () => ({ switchBusiness: async () => { throw new Error('sem conexão'); } }));
      jest.doMock('../src/offline/manager', () => ({ stopOffline: stop, offlineState: () => ({ pending: 0 }),
                                                     syncNow: async () => ({}) }));
      const { changeBusiness } = require('../src/businessSwitch');
      promise = changeBusiness(7, jest.fn());
    });
    await expect(promise).rejects.toThrow('sem conexão');
    expect(stop).not.toHaveBeenCalled();
  });
});

describe('modo desenvolvedor no build', () => {
  // Gera o JavaScript de verdade (expo export) e procura o texto da tela do modo desenvolvedor. --clear: o cache do
  // Metro não considera as variáveis EXPO_PUBLIC_* e reaproveitaria o código de outro perfil
  const MARK = 'Modo desenvolvedor';
  const bundle = (profile) => {
    const out = fs.mkdtempSync(path.join(os.tmpdir(), `syncserv-${profile}-`));
    execFileSync('npx', ['expo', 'export', '--platform', 'android', '--no-bytecode', '--clear', '--output-dir', out], {
      cwd: MOBILE, stdio: 'ignore',
      env: { ...process.env, EXPO_PUBLIC_APP_PROFILE: profile, EXPO_PUBLIC_API_URL: 'https://api.exemplo.com.br' },
    });
    const dir = path.join(out, '_expo', 'static', 'js', 'android');
    const text = fs.readdirSync(dir).map((f) => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n');
    fs.rmSync(out, { recursive: true, force: true });
    return text;
  };

  test('não existe no build de produção (e existe no de preview)', () => {
    const production = bundle('production');
    expect(production).toContain('https://api.exemplo.com.br');
    expect(production).not.toContain(MARK);
    expect(production).not.toContain('devApiUrl');
    expect(bundle('preview')).toContain(MARK);
  }, 600000);
});
