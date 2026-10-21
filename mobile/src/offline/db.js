// Banco local criptografado (só no celular).
//
// expo-sqlite com SQLCipher (plugin "expo-sqlite" com useSQLCipher: true no app.config.js): o arquivo inteiro é
// criptografado com uma chave aleatória de 256 bits gerada no aparelho e guardada no SecureStore
// (Keychain/Keystore), que só abre neste aparelho. Sem a chave, o arquivo é ilegível.
//
// O Expo Go não traz o SQLCipher: lá o modo offline fica desligado (o app funciona online, como a versão web),
// a não ser em desenvolvimento com EXPO_PUBLIC_OFFLINE_PLAINTEXT=1, só com dados fictícios.
import * as SQLite from 'expo-sqlite';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';

const NAME = 'syncserv-offline.db';
const KEY = 'offlineDbKey';
const KEY_OPTS = { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY };

const hex = (bytes) => Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');

async function dbKey() {
  let key = await SecureStore.getItemAsync(KEY, KEY_OPTS);
  if (!key) {
    key = hex(await Crypto.getRandomBytesAsync(32));
    await SecureStore.setItemAsync(KEY, key, KEY_OPTS);
  }
  return key;
}

const plaintextAllowed = () => __DEV__ && process.env.EXPO_PUBLIC_OFFLINE_PLAINTEXT === '1';

// { db, encrypted } ou { db: null, reason } quando o modo offline não pode ser usado neste build
export async function openOfflineDb() {
  const key = await dbKey();
  let db = await SQLite.openDatabaseAsync(NAME);
  // A chave tem de ser o primeiro comando da conexão. No SQLite comum, PRAGMA key é ignorado.
  await db.execAsync(`PRAGMA key = "x'${key}'"`);
  const cipher = await db.getFirstAsync('PRAGMA cipher_version');
  const encrypted = !!cipher?.cipher_version;
  if (!encrypted && !plaintextAllowed()) {
    await db.closeAsync();
    await SQLite.deleteDatabaseAsync(NAME).catch(() => {});
    return { db: null, reason: 'no-cipher' };
  }
  try {
    await db.getFirstAsync('SELECT count(*) AS n FROM sqlite_master');
  } catch (e) {
    // Arquivo de outra chave (ex.: o app foi reinstalado e a chave sumiu): não dá para ler, começa do zero
    await db.closeAsync().catch(() => {});
    await SQLite.deleteDatabaseAsync(NAME).catch(() => {});
    db = await SQLite.openDatabaseAsync(NAME);
    await db.execAsync(`PRAGMA key = "x'${key}'"`);
  }
  await db.execAsync('PRAGMA journal_mode = DELETE; PRAGMA foreign_keys = OFF;');
  return { db, encrypted };
}

// Sair da conta, trocar de usuário ou token recusado: apaga o arquivo e a chave
export async function destroyOfflineDb(db) {
  if (db) await db.closeAsync().catch(() => {});
  await SQLite.deleteDatabaseAsync(NAME).catch(() => {});
  await SecureStore.deleteItemAsync(KEY, KEY_OPTS).catch(() => {});
}
