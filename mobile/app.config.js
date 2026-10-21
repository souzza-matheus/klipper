// Configuração do Expo (era o app.json). Os perfis de build (development, preview, production) ficam no eas.json, que
// define EXPO_PUBLIC_APP_PROFILE e EXPO_PUBLIC_API_URL de cada um. No desenvolvimento local (npx expo start), as duas
// vêm do mobile/.env.local (modelo em .env.example). O JavaScript lê as variáveis direto (src/config.js); aqui elas só
// vão para o extra, para conferência (Constants.expoConfig.extra).
const profile = process.env.EXPO_PUBLIC_APP_PROFILE || 'development';
const apiUrl = process.env.EXPO_PUBLIC_API_URL || '';

if (profile === 'production' && !/^https:\/\//.test(apiUrl)) {
  // Não para o build (o marcador [DOMINIO] fica até o domínio ser definido), mas avisa
  console.warn(`[app.config] perfil production sem endereço https da API (EXPO_PUBLIC_API_URL=${apiUrl || 'vazio'})`);
}

module.exports = {
  expo: {
    name: 'SyncServ',
    slug: 'syncserv',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    userInterfaceStyle: 'automatic',
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'br.com.barberbot.admin'
    },
    android: {
      adaptiveIcon: {
        foregroundImage: './assets/adaptive-icon.png',
        backgroundColor: '#0F172A'
      },
      package: 'br.com.barberbot.admin'
    },
    web: {
      favicon: './public/favicon.ico',
      name: 'SyncServ',
      shortName: 'SyncServ',
      lang: 'pt-BR',
      themeColor: '#0F172A',
      backgroundColor: '#0F172A',
      bundler: 'metro',
      output: 'single'
    },
    plugins: [
      'expo-secure-store',
      'expo-sharing',
      'expo-font',
      [
        'expo-splash-screen',
        {
          image: './assets/splash-icon.png',
          imageWidth: 200,
          resizeMode: 'contain',
          backgroundColor: '#0F172A',
          dark: {
            image: './assets/splash-icon.png',
            backgroundColor: '#0F172A'
          }
        }
      ],
      'expo-asset',
      'expo-background-task',
      [
        'expo-sqlite',
        {
          useSQLCipher: true
        }
      ]
    ],
    extra: { profile, apiUrl },
  },
};
