import React, { useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { api, changePassword } from '../api';
import { DataTable } from '../components/Layout';

import { ROLE_LABEL } from '../roles';
import { useSession } from '../session';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import {
  Badge, Banner, BottomSheet, Button, Card, Chips, confirm, Empty, Field, IconButton, Loading, Screen, Section, Toggle,
  run, toast, useLoad,
} from '../ui';

const ROLE_HELP = {
  owner: 'Tudo: financeiro, equipe, configurações, WhatsApp e IA.',
  reception: 'Agenda, check-in, clientes, comandas, Pix, assinaturas e lista de espera. Sem financeiro completo.',
  professional: 'Só a própria agenda, os clientes que atendeu e as próprias comissões.',
};
const ROLE_BADGE = { owner: { label: 'Dono', tone: 'accent' }, reception: { label: 'Recepção', tone: 'info' },
                     professional: { label: 'Profissional', tone: 'neutral' } };

// A senha provisória aparece uma vez: o dono copia e repassa à pessoa
function PasswordSheet({ data, onClose }) {
  const { s, font } = useTheme();
  return (
    <BottomSheet visible={!!data} onClose={onClose} title="Senha provisória">
      {data ? (
        <>
          <Text style={[s.body, { marginBottom: SPACE(3) }]}>
            Passe para {data.user.name} o e-mail <Text style={s.strong}>{data.user.email}</Text> e a senha abaixo. No
            primeiro acesso, o app pede uma senha nova.
          </Text>
          <Card>
            <Text selectable style={{ fontFamily: font.extrabold, fontSize: 26, textAlign: 'center', letterSpacing: 1 }}>
              {data.provisional_password}
            </Text>
          </Card>
          <Button title="Copiar senha" icon="copy-outline" onPress={() => Clipboard.setStringAsync(data.provisional_password)
            .then(() => toast('Senha copiada.'))} />
          <Text style={s.caption}>Ela não aparece de novo. Se perder, gere outra em "Nova senha provisória".</Text>
        </>
      ) : null}
    </BottomSheet>
  );
}

export function TeamScreen({ navigation }) {
  const { s, v } = useTheme();
  const { wide } = useSession();
  const list = useLoad(() => api.get('/users'), []);
  useLayoutEffect(() => {
    navigation.setOptions({ headerRight: () => (
      <IconButton icon="person-add" size={28} label="Convidar pessoa" onPress={() => navigation.navigate('UserEdit', {})} />
    ) });
  }, [navigation]);
  const items = list.data || [];
  const open = (u) => navigation.navigate('UserEdit', { item: u });
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {Object.entries(ROLE_HELP).map(([r, t]) => (
        <View key={r} style={[s.row, { gap: SPACE(2), marginBottom: SPACE(2), alignItems: 'flex-start' }]}>
          <Badge info={ROLE_BADGE[r]} />
          <Text style={[s.caption, { flex: 1 }]}>{t}</Text>
        </View>
      ))}
      <View style={{ height: SPACE(3) }} />
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? <Empty icon="people-outline" text="Ninguém na equipe ainda." /> : null}
      {items.length && wide ? (
        <DataTable rows={items} onRowPress={open} searchKeys={['name', 'email']} placeholder="Buscar pessoa"
                   initialSort={{ key: 'name', dir: 'asc' }} columns={[
                     { key: 'name', label: 'Nome', flex: 2, render: (u) => <Text style={s.bodyBold}>{u.name}</Text> },
                     { key: 'email', label: 'E-mail', flex: 2 },
                     { key: 'role', label: 'Papel', render: (u) => <Badge info={ROLE_BADGE[u.role]} /> },
                     { key: 'barber_name', label: v.Pro },
                     { key: 'active', label: 'Situação', render: (u) => (
                       <Text style={s.body}>{!u.active ? 'Desativado' : u.first_login ? 'Aguardando 1º acesso' : 'Ativo'}</Text>) },
                   ]} />
      ) : items.map((u) => (
        <Card key={u.id} onPress={() => open(u)}>
          <View style={[s.row, { gap: SPACE(2) }]}>
            <Text style={[s.bodyBold, { flex: 1 }]}>{u.name}</Text>
            <Badge info={ROLE_BADGE[u.role]} />
          </View>
          <Text style={s.caption}>
            {u.email}{u.barber_name ? ` · ${u.barber_name}` : ''}
            {!u.active ? ' · desativado' : u.first_login ? ' · aguardando primeiro acesso' : ''}
          </Text>
        </Card>
      ))}
    </Screen>
  );
}

export function UserEditScreen({ navigation, route }) {
  const { s, v } = useTheme();
  const item = route.params?.item;
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [name, setName] = useState(item?.name || '');
  const [email, setEmail] = useState(item?.email || '');
  const [role, setRole] = useState(item?.role || 'reception');
  const [barberId, setBarberId] = useState(item?.barber_id || null);
  const [active, setActive] = useState(item ? item.active : true);
  const [shown, setShown] = useState(null);
  const save = () => run(async () => {
    if (item) {
      await api.put(`/users/${item.id}`, { name, role, barber_id: barberId, active });
      navigation.goBack();
      return;
    }
    setShown(await api.post('/users', { name, email, role, barber_id: barberId }));
  }, item ? 'Salvo. Se mudou o papel, a pessoa entra de novo.' : undefined);
  const reset = () => confirm('Gerar nova senha provisória?', `${item.name} sai de todos os aparelhos e troca a senha no próximo acesso.`,
    () => run(async () => setShown(await api.post(`/users/${item.id}/reset-password`))), 'Gerar');
  return (
    <Screen footer={<Button title={item ? 'Salvar' : 'Convidar'} icon={item ? 'checkmark' : 'person-add'} onPress={save}
                            disabled={!name || (!item && !email) || (role === 'professional' && !barberId)}
                            style={{ marginBottom: 0 }} />}>
      <Field label="Nome" value={name} onChangeText={setName} autoCapitalize="words" />
      {item ? <Text style={[s.muted, { marginBottom: SPACE(4) }]}>{item.email}</Text> : (
        <Field label="E-mail (login)" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
      )}
      <Section title="Papel">
        <Chips value={role} onChange={setRole} options={Object.entries(ROLE_LABEL).map(([k, l]) => ({ value: k, label: l }))} />
        <Text style={[s.caption, { marginTop: -SPACE(2), marginBottom: SPACE(4) }]}>{ROLE_HELP[role]}</Text>
      </Section>
      {role === 'professional' ? (
        <Section title={`Agenda de qual ${v.pro}?`}>
          <Chips value={barberId} onChange={setBarberId} options={(barbers.data || []).filter((b) => b.active)
            .map((b) => ({ value: b.id, label: b.name }))} />
        </Section>
      ) : null}
      {item ? (
        <>
          <Toggle label="Pode entrar no app" value={active} onValueChange={setActive}
                  hint="Desativar tira o acesso na hora, em todos os aparelhos." />
          <Button title="Nova senha provisória" kind="ghost" icon="key-outline" onPress={reset} />
        </>
      ) : (
        <Banner tone="info" icon="information-circle-outline"
                text="O app gera uma senha provisória para você passar à pessoa. No primeiro acesso ela escolhe a própria senha." />
      )}
      <PasswordSheet data={shown} onClose={() => { setShown(null); navigation.goBack(); }} />
    </Screen>
  );
}

// Troca de senha: obrigatória no primeiro acesso de quem foi convidado (first), ou pelo menu Mais
export function ChangePasswordScreen({ navigation, first, onDone }) {
  const { s } = useTheme();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false);
  const error = next && next.length < 8 ? 'Use pelo menos 8 caracteres.'
    : again && next !== again ? 'As senhas não conferem.' : '';
  const save = async () => {
    setBusy(true);
    const r = await run(() => changePassword(current, next), 'Senha alterada.');
    setBusy(false);
    if (r) {
      if (onDone) onDone(r);
      else navigation?.goBack();
    }
  };
  return (
    <Screen footer={<Button title="Salvar senha" icon="checkmark" onPress={save} loading={busy}
                            disabled={!current || !next || !!error || next !== again} style={{ marginBottom: 0 }} />}>
      {first ? (
        <Banner tone="accent" icon="key-outline" title="Crie a sua senha"
                text="Você entrou com uma senha provisória. Escolha uma senha só sua para continuar." />
      ) : null}
      <Field label={first ? 'Senha provisória' : 'Senha atual'} value={current} onChangeText={setCurrent} secureTextEntry
             autoComplete="current-password" />
      <Field label="Nova senha" value={next} onChangeText={setNext} secureTextEntry autoComplete="new-password"
             error={error} hint="Pelo menos 8 caracteres." />
      <Field label="Repita a nova senha" value={again} onChangeText={setAgain} secureTextEntry autoComplete="new-password" />
      <Text style={s.caption}>Ao trocar a senha, os outros aparelhos saem da conta.</Text>
    </Screen>
  );
}

