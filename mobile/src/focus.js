// useFocusEffect do React Navigation entregue pela casca do app (AppShell.js chama provideFocusEffect ao carregar).
// As telas importam daqui, e não de '@react-navigation/native', para a versão web não precisar da navegação no
// JavaScript das telas nem no pedaço comum que o Expo carrega junto com o login (ver src/shell.web.js). As telas só
// aparecem dentro da casca, então o hook de verdade sempre já está aqui quando elas montam.
let hook = null;

export function provideFocusEffect(useFocusEffect) {
  hook = useFocusEffect;
}

export function useFocusEffect(effect) {
  if (!hook) throw new Error('useFocusEffect usado fora da navegação do app');
  return hook(effect);
}
