import React, { useLayoutEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api, saveFile } from '../api';
import { BarChart } from '../chart';
import { MonthNav } from './Agenda';
import {
  addDays, change, dmy, EXPENSE_CATEGORIES, money, moneyInput, monthBounds, monthRange,
  parseBRDate, parseMoney, PAY_METHODS, payMethodLabel, pct, todayISO,
} from '../format';
import { SPACE } from '../theme';
import { useTheme } from '../ThemeProvider';
import { useSession } from '../session';
import {
  Badge, Button, Card, Chips, confirm, Empty, Field, IconButton, ListRow, Loading, Muted, Screen, Section, Stat, StatValue,
  Toggle, run, useLoad,
} from '../ui';

const PERIODS = {
  month: () => monthRange(0),
  last: () => monthRange(-1),
  d30: () => [addDays(todayISO(), -29), todayISO()],
};

const brDate = (iso) => (iso ? dmy(iso + 'T') : '');
const isOpen = (v) => Number(v) > 0.004;

// ---------------------------------------------------------------- resumo financeiro (aba Financeiro)

const SUMMARY_PERIODS = {
  month: () => monthRange(0),
  last: () => monthRange(-1),
  d7: () => [addDays(todayISO(), -6), todayISO()],
};

// Card com valor e variação contra o período anterior. upIsGood=false: subir é ruim (gastos).
function Kpi({ label, value, delta, upIsGood = true }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const txt = change(delta);
  const n = Number(delta);
  const color = !txt || n === 0 ? c.textMuted : (n > 0) === upIsGood ? c.statusText.success : c.statusText.danger;
  return (
    <View style={[s.stat, { minWidth: '45%' }]}>
      <Muted>{label}</Muted>
      <StatValue value={value} />
      <Text style={[s.caption, { color, marginTop: 2 }]}>{txt ? `${txt} vs. anterior` : 'sem base anterior'}</Text>
    </View>
  );
}

// Linha com valor e barra proporcional ao maior do grupo
function ShareRow({ title, subtitle, value, max, color }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const w = max > 0 ? Math.max(2, (Number(value) / max) * 100) : 0;
  return (
    <View style={{ paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: c.divider }}>
      <View style={s.row}>
        <Text style={[s.body, { flex: 1 }]} numberOfLines={1}>{title}</Text>
        <Text style={[s.body, { fontFamily: font.bold }]}>{money(value)}</Text>
      </View>
      {subtitle ? <Muted>{subtitle}</Muted> : null}
      <View style={{ height: 4, backgroundColor: c.neutralBg, borderRadius: 2, marginTop: 6 }}>
        <View style={{ height: 4, width: `${w}%`, backgroundColor: color || c.accentText, borderRadius: 2 }} />
      </View>
    </View>
  );
}

function Breakdown({ title, rows, color }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const max = Math.max(0, ...rows.map((g) => Number(g.revenue)));
  return (
    <Section title={title}>
      <Card>
        {!rows.length ? <Muted>Sem {v.services} {v.doneMany} no período.</Muted> : null}
        {rows.map((g) => (
          <ShareRow key={g.method || g.id || g.name} title={g.label || g.name} value={g.revenue} max={max} color={color}
                    subtitle={v.count(g.appointments, v.service, v.services)} />
        ))}
      </Card>
    </Section>
  );
}

export function FinanceHomeScreen({ navigation }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const [period, setPeriod] = useState('month');
  const [custom, setCustom] = useState({ from: brDate(monthRange(0)[0]), to: brDate(todayISO()) });
  const [range, setRange] = useState(monthRange(0));
  const [from, to] = range;
  const [exporting, setExporting] = useState(false);
  const r = useLoad(async () => {
    const q = { date_from: from, date_to: to };
    const [summary, daily] = await Promise.all([api.get('/finance/summary', q), api.get('/finance/daily', q)]);
    return { summary, daily };
  }, [from, to]);
  const d = r.data?.summary;

  const pick = (p) => {
    setPeriod(p);
    if (SUMMARY_PERIODS[p]) setRange(SUMMARY_PERIODS[p]());
  };
  const applyCustom = () => {
    const a = parseBRDate(custom.from);
    const b = parseBRDate(custom.to);
    if (!a || !b) return run(() => { throw new Error('Datas inválidas. Use dd/mm/aaaa.'); });
    if (b < a) return run(() => { throw new Error('A data final precisa ser depois da inicial.'); });
    setRange([a, b]);
    return null;
  };
  const exportCsv = async () => {
    setExporting(true);
    await run(async () => {
      await saveFile('/finance/export.csv', { date_from: from, date_to: to }, `financeiro_${from}_${to}.csv`, 'text/csv');
    });
    setExporting(false);
  };

  const chart = (r.data?.daily || []).map((x) => ({ key: x.date, label: x.date.slice(8, 10), a: Number(x.revenue), b: Number(x.expenses) }));

  return (
    <Screen onRefresh={r.reload} refreshing={r.loading && !!r.data}>
      <Chips value={period} onChange={pick} options={[
        { value: 'month', label: 'Este mês' }, { value: 'last', label: 'Mês passado' },
        { value: 'd7', label: '7 dias' }, { value: 'custom', label: 'Personalizado' },
      ]} />
      {period === 'custom' ? (
        <View style={[s.row, { gap: 8, alignItems: 'flex-end' }]}>
          <View style={{ flex: 1 }}>
            <Field label="De" value={custom.from} onChangeText={(v) => setCustom({ ...custom, from: v })}
                   placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
          </View>
          <View style={{ flex: 1 }}>
            <Field label="Até" value={custom.to} onChangeText={(v) => setCustom({ ...custom, to: v })}
                   placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
          </View>
          <Button title="Ver" onPress={applyCustom} style={{ marginBottom: 14 }} />
        </View>
      ) : null}
      {!d ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Muted style={{ marginBottom: 10 }}>
            {brDate(from)} a {brDate(to)} · comparado com {brDate(d.previous.date_from)} a {brDate(d.previous.date_to)}
          </Muted>
          <View style={[s.row, { gap: 8, flexWrap: 'wrap', marginBottom: 8 }]}>
            <Kpi label="Faturamento" value={money(d.revenue)} delta={d.change.revenue} />
            <Kpi label="Gastos pagos" value={money(d.expenses_paid)} delta={d.change.expenses_paid} upIsGood={false} />
            <Kpi label="Lucro" value={money(d.profit)} delta={d.change.profit} />
            <Kpi label="Ticket médio" value={money(d.avg_ticket)} delta={d.change.avg_ticket} />
          </View>
          <Muted style={{ marginBottom: 16 }}>
            {v.count(d.appointments, v.service, v.services)} {v.doneMany}
            {isOpen(d.expenses_open) ? ` · ${money(d.expenses_open)} em gastos a pagar no período` : ''}
          </Muted>

          <Section title="Faturamento x gastos por dia">
            <Card>
              <BarChart data={chart} detail={(x) => brDate(x.key)} />
            </Card>
          </Section>

          <View style={{ borderRadius: 12, overflow: 'hidden', marginBottom: 18 }}>
            <ListRow icon="receipt-outline" title="Gastos" subtitle="Contas do mês, pagas e em aberto"
                     onPress={() => navigation.navigate('Expenses')} />
            <ListRow icon="people-outline" title="Comissões e repasses" subtitle="Bruto, repasses, líquido e acertos"
                     onPress={() => navigation.navigate('Commissions')} />
          </View>

          <Breakdown title={`Por ${v.pro}`} rows={d.by_barber} />
          <Breakdown title="Por serviço" rows={d.by_service} color={c.accentText} />
          <Breakdown title="Por forma de pagamento" rows={d.by_payment_method} color={c.statusText.success} />

          {d.expenses_by_category.length ? (
            <Section title="Gastos por categoria">
              <Card>
                {d.expenses_by_category.map((cat) => (
                  <ShareRow key={cat.category} title={cat.label} color={c.statusText.danger}
                            value={Number(cat.paid) + Number(cat.open)}
                            max={Math.max(...d.expenses_by_category.map((x) => Number(x.paid) + Number(x.open)))}
                            subtitle={`pago ${money(cat.paid)}${isOpen(cat.open) ? ` · em aberto ${money(cat.open)}` : ''}`} />
                ))}
              </Card>
            </Section>
          ) : null}

          <Button title={exporting ? 'Gerando arquivo...' : 'Exportar CSV (Excel)'} kind="ghost" icon="share-outline"
                  onPress={exportCsv} disabled={exporting} />
        </>
      )}
    </Screen>
  );
}

// ---------------------------------------------------------------- gastos

export function ExpensesScreen({ navigation }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const [month, setMonth] = useState(todayISO().slice(0, 7));
  const [status, setStatus] = useState(null);
  const list = useLoad(() => api.get('/expenses', { month }), [month]);

  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <IconButton icon="add-circle" size={30} label="Novo gasto" onPress={() => navigation.navigate('ExpenseEdit', { month })} />
      ),
    });
  }, [navigation, month]);

  const all = list.data || [];
  const items = all.filter((e) => (status === 'paid' ? e.paid_at : status === 'open' ? !e.paid_at : true));
  const sum = (xs) => xs.reduce((t, e) => t + Number(e.amount), 0);
  const groups = {};
  items.forEach((e) => { (groups[e.category_label] = groups[e.category_label] || []).push(e); });
  const sorted = Object.entries(groups).sort((a, b) => sum(b[1]) - sum(a[1]));

  const pay = (e) => confirm('Marcar como pago?', `${e.description} · ${money(e.amount)}\nPago hoje.`,
    () => run(async () => { await api.post(`/expenses/${e.id}/pay`); list.reload(); }), 'Marcar como pago');

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      <MonthNav month={month} onChange={setMonth} />
      <View style={[s.row, { gap: 8, marginBottom: 12, flexWrap: 'wrap' }]}>
        <Stat label="Total do mês" value={money(sum(all))} />
        <Stat label="Pago" value={money(sum(all.filter((e) => e.paid_at)))} />
        <Stat label="Em aberto" value={money(sum(all.filter((e) => !e.paid_at)))} />
      </View>
      <Chips value={status} onChange={setStatus} options={[
        { value: null, label: 'Todos' }, { value: 'open', label: 'Em aberto' }, { value: 'paid', label: 'Pagos' },
      ]} />
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !items.length ? <Empty text="Nenhum gasto neste mês. Toque no + para cadastrar." /> : null}
      {sorted.map(([label, rows]) => (
        <Section key={label} title={label} right={<Text style={[s.muted, { fontFamily: font.bold }]}>{money(sum(rows))}</Text>}>
          {rows.map((e) => (
            <Card key={e.id} onPress={() => navigation.navigate('ExpenseEdit', { item: e })}
                  style={e.overdue && { borderColor: c.statusText.danger, backgroundColor: c.statusBg.danger }}>
              <View style={s.row}>
                <View style={{ flex: 1 }}>
                  <View style={[s.row, { gap: 6 }]}>
                    <Text style={[s.body, { flexShrink: 1 }]} numberOfLines={1}>{e.description}</Text>
                    {e.recurring || e.recurring_source_id ? <Ionicons name="repeat" size={15} color={c.textMuted} /> : null}
                  </View>
                  <Muted style={e.overdue && { color: c.statusText.danger, fontFamily: font.semibold }}>
                    {e.paid_at ? `Pago em ${brDate(e.paid_at)}${e.payment_method ? ` · ${payMethodLabel(e.payment_method)}` : ''}`
                      : e.overdue ? `Venceu em ${brDate(e.due_date)}` : `Vence em ${brDate(e.due_date)}`}
                    {e.barber_name ? ` · ${e.barber_name}` : ''}
                  </Muted>
                </View>
                <Text style={[s.body, { fontFamily: font.bold, color: e.overdue ? c.statusText.danger : c.text }]}>{money(e.amount)}</Text>
              </View>
              {!e.paid_at ? (
                <Button title="Marcar como pago" kind="ghost" icon="checkmark-done-outline" onPress={() => pay(e)}
                        style={{ marginTop: 10, marginBottom: 0, paddingVertical: 9 }} />
              ) : null}
            </Card>
          ))}
        </Section>
      ))}
    </Screen>
  );
}

export function ExpenseEditScreen({ navigation, route }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const item = route.params?.item;
  const month = route.params?.month || todayISO().slice(0, 7);
  const defaultDue = todayISO().startsWith(month) ? todayISO() : monthBounds(month)[0];
  const barbers = useLoad(() => api.get('/barbers'), []);
  const [description, setDescription] = useState(item?.description || '');
  const [amount, setAmount] = useState(item ? moneyInput(item.amount) : '');
  const [category, setCategory] = useState(item?.category || 'outros');
  const [due, setDue] = useState(brDate(item?.due_date || defaultDue));
  const [paid, setPaid] = useState(!!item?.paid_at);
  const [paidAt, setPaidAt] = useState(brDate(item?.paid_at || todayISO()));
  const [method, setMethod] = useState(item?.payment_method || null);
  const [barberId, setBarberId] = useState(item?.barber_id ?? null);
  const [recurring, setRecurring] = useState(!!item?.recurring);
  const [notes, setNotes] = useState(item?.notes || '');
  const isCopy = !!item?.recurring_source_id;

  const save = () => run(async () => {
    const value = parseMoney(amount);
    if (!value || value <= 0) throw new Error('Informe um valor maior que zero.');
    const dueDate = parseBRDate(due);
    if (!dueDate) throw new Error('Vencimento inválido. Use dd/mm/aaaa.');
    const paidDate = paid ? parseBRDate(paidAt) : null;
    if (paid && !paidDate) throw new Error('Data do pagamento inválida. Use dd/mm/aaaa.');
    const body = {
      description, category, amount: value.toFixed(2), due_date: dueDate, paid_at: paidDate,
      payment_method: paid ? method : null, barber_id: barberId, recurring: isCopy ? false : recurring, notes,
    };
    if (item) await api.put(`/expenses/${item.id}`, body);
    else await api.post('/expenses', body);
    navigation.goBack();
  });

  return (
    <Screen>
      <Field label="Descrição" value={description} onChangeText={setDescription} placeholder="Ex.: Aluguel do salão" />
      <Field label="Valor (R$)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0,00" />
      <Section title="Categoria">
        <Chips value={category} onChange={setCategory} options={EXPENSE_CATEGORIES} />
      </Section>
      <Field label="Vencimento" value={due} onChangeText={setDue} placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
      <Toggle label="Já está pago" value={paid} onValueChange={setPaid} />
      {paid ? (
        <>
          <Field label="Pago em" value={paidAt} onChangeText={setPaidAt} placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
          <Section title="Forma de pagamento">
            <Chips value={method} onChange={setMethod} options={PAY_METHODS} />
          </Section>
        </>
      ) : null}
      <Section title={`Ligado a um ${v.pro} (opcional)`}>
        <Chips value={barberId} onChange={setBarberId}
               options={[{ value: null, label: 'Nenhum' }, ...(barbers.data || []).map((b) => ({ value: b.id, label: b.name }))]} />
      </Section>
      {isCopy ? (
        <Muted style={{ marginBottom: 14 }}>
          Conta gerada automaticamente a partir de um gasto recorrente. Para parar de repetir, edite o gasto original
          (o do primeiro mês) e desligue “Repetir todo mês”.
        </Muted>
      ) : (
        <Toggle label="Repetir todo mês" value={recurring} onValueChange={setRecurring}
                hint="A conta é criada automaticamente em cada mês seguinte, no mesmo dia de vencimento." />
      )}
      <Field label="Observações" value={notes} onChangeText={setNotes} multiline />
      <Button title="Salvar" onPress={save} disabled={!description || !amount || !due} />
      {item && !item.paid_at ? (
        <Button title="Marcar como pago hoje" kind="ghost" icon="checkmark-done-outline" onPress={() => run(async () => {
          await api.post(`/expenses/${item.id}/pay`, { payment_method: method });
          navigation.goBack();
        })} />
      ) : null}
      {item ? (
        <Button title="Excluir" kind="danger" onPress={() => confirm('Excluir gasto?',
          item.recurring ? 'As contas já geradas nos meses seguintes continuam. Para parar de gerar, desligue “Repetir todo mês”.' : '',
          () => run(async () => { await api.del(`/expenses/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}

// ---------------------------------------------------------------- regras de um profissional (Mais > Profissionais)

export function BarberCommissionRules({ barberId, navigation }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const list = useLoad(() => api.get('/commission-rules', { barber_id: barberId }), [barberId]);
  const today = todayISO();
  return (
    <Section title="Comissões">
      <Muted style={{ marginBottom: SPACE(2) }}>Quanto este {v.pro} repassa do que fatura, para {v.theBusiness} ou para um padrinho.</Muted>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Muted style={{ marginBottom: 8 }}>Nenhuma regra: fica com 100% do que fatura.</Muted> : null}
      {(list.data || []).map((x) => {
        const ended = x.valid_to && x.valid_to < today;
        return (
          <Card key={x.id} onPress={() => navigation.navigate('CommissionRuleEdit', { item: x })} style={ended && { opacity: 0.5 }}>
            <View style={s.row}>
              <Text style={[s.body, { flex: 1 }]}>Para {x.beneficiary_name}</Text>
              <Text style={[s.body, { fontFamily: font.bold }]}>{pct(x.percentage)}</Text>
            </View>
            <Muted>{x.service_name || 'Todos os serviços'} · desde {brDate(x.valid_from)}
              {x.valid_to ? ` até ${brDate(x.valid_to)}` : ''}{ended ? ' · encerrada' : ''}</Muted>
          </Card>
        );
      })}
      <Button title="Nova regra de comissão" kind="ghost" icon="add" onPress={() => navigation.navigate('CommissionRuleEdit', { barberId })} />
    </Section>
  );
}

// ---------------------------------------------------------------- repasses do período

export function CommissionsScreen({ navigation }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const { can } = useSession();
  const owner = can('finance'); // o profissional vê só a própria linha, sem acertos nem regras
  const [period, setPeriod] = useState('month');
  const [from, to] = PERIODS[period]();
  const r = useLoad(() => api.get('/finance/commissions', { date_from: from, date_to: to }), [period]);
  const d = r.data;

  useLayoutEffect(() => {
    if (!owner) return;
    navigation.setOptions({
      headerRight: () => (
        <View style={{ flexDirection: 'row' }}>
          <IconButton icon="time-outline" label="Acertos registrados" onPress={() => navigation.navigate('Settlements')} />
          <IconButton icon="options-outline" label="Regras de repasse" onPress={() => navigation.navigate('CommissionRules')} />
        </View>
      ),
    });
  }, [navigation, owner]);

  const settle = (b, due) => confirm('Registrar acerto?',
    `${b.barber_name} repassa ${money(due.open)} para ${due.beneficiary_name}, referente a ${brDate(from)} a ${brDate(to)}.`,
    () => run(async () => {
      await api.post('/finance/settlements', {
        payer_barber_id: b.barber_id, beneficiary_type: due.beneficiary_type,
        beneficiary_barber_id: due.beneficiary_barber_id, period_start: from, period_end: to, amount: due.open,
      });
      r.reload();
    }, `Acerto registrado. O ${v.pro} foi avisado pelo WhatsApp.`),
    'Registrar');

  return (
    <Screen onRefresh={r.reload} refreshing={r.loading && !!d}>
      <Chips value={period} onChange={setPeriod} options={[
        { value: 'month', label: 'Este mês' }, { value: 'last', label: 'Mês passado' }, { value: 'd30', label: '30 dias' },
      ]} />
      {!d ? <Loading error={r.error} onRetry={r.reload} /> : (
        <>
          <Muted style={{ marginBottom: 10 }}>{brDate(from)} a {brDate(to)} · só {v.services} {v.doneMany}</Muted>
          <View style={[s.row, { gap: 8, marginBottom: 18, flexWrap: 'wrap' }]}>
            <Stat label="Faturado" value={money(d.total_gross)} />
            <Stat label="Repasses" value={money(d.total_due)} />
            <Stat label="Em aberto" value={money(d.total_open)} />
          </View>
          {!d.barbers.length ? (
            <Empty text={`${v.noService} ${v.done} no período. Cadastre as regras de repasse no ícone acima.`} />
          ) : null}
          {d.barbers.map((b) => (
            <Card key={b.barber_id}>
              <View style={s.row}>
                <Text style={[s.body, { flex: 1, fontFamily: font.bold }]}>{b.barber_name}</Text>
                <Text style={[s.body, { fontFamily: font.bold }]}>{money(b.gross)}</Text>
              </View>
              <Muted>{v.count(b.appointments, v.service, v.services)} · líquido {money(b.net)}
                {isOpen(b.received) ? ` · recebe ${money(b.received)} de repasses` : ''}
                {isOpen(b.tips) ? ` · gorjetas ${money(b.tips)}` : ''}
                {isOpen(b.product_commission) ? ` · comissão de produtos ${money(b.product_commission)}` : ''}</Muted>
              {b.dues.map((due) => (
                <View key={`${due.beneficiary_type}-${due.beneficiary_barber_id}`}
                      style={{ borderTopWidth: 1, borderTopColor: c.divider, marginTop: 10, paddingTop: 10 }}>
                  <View style={s.row}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.body}>Para {due.beneficiary_name}</Text>
                      <Muted>{due.percentages.map(pct).join(' / ') || '-'} sobre {money(due.base)}</Muted>
                    </View>
                    <Text style={[s.body, { fontFamily: font.bold }]}>{money(due.amount)}</Text>
                  </View>
                  <View style={[s.row, { gap: 6, marginTop: 6 }]}>
                    {isOpen(due.settled) ? <Badge info={{ label: `Acertado ${money(due.settled)}`, tone: 'success', icon: 'checkmark-circle' }} /> : null}
                    {isOpen(due.open) ? <Badge info={{ label: `Em aberto ${money(due.open)}`, tone: 'warning', icon: 'time-outline' }} /> : null}
                    {!isOpen(due.open) && isOpen(due.amount) ? <Badge info={{ label: 'Quitado', tone: 'success', icon: 'checkmark-done' }} /> : null}
                  </View>
                  {isOpen(due.open) && owner ? (
                    <Button title="Registrar acerto" kind="ghost" icon="checkmark-done-outline"
                            onPress={() => settle(b, due)} style={{ marginTop: 10, marginBottom: 0 }} />
                  ) : null}
                </View>
              ))}
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

// ---------------------------------------------------------------- histórico de acertos

export function SettlementsScreen() {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const list = useLoad(() => api.get('/finance/settlements'), []);
  const remove = (x) => confirm('Excluir acerto?', 'O valor volta a aparecer como em aberto.',
    () => run(async () => { await api.del(`/finance/settlements/${x.id}`); list.reload(); }), 'Excluir', true);
  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? <Empty text="Nenhum acerto registrado ainda." /> : null}
      {(list.data || []).map((x) => (
        <Card key={x.id}>
          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.body}>{x.payer_name} → {x.beneficiary_name}</Text>
              <Muted>Período {brDate(x.period_start)} a {brDate(x.period_end)}</Muted>
              <Muted>Pago em {dmy(x.paid_at)}{x.notes ? ` · ${x.notes}` : ''}</Muted>
            </View>
            <Text style={{ fontSize: 20, fontFamily: font.extrabold, color: c.text, marginRight: SPACE(2) }}>{money(x.amount)}</Text>
            <IconButton icon="trash-outline" label="Remover acerto" color={c.statusText.danger} onPress={() => remove(x)} />
          </View>
        </Card>
      ))}
    </Screen>
  );
}

// ---------------------------------------------------------------- regras de repasse

export function CommissionRulesScreen({ navigation }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const list = useLoad(() => api.get('/commission-rules'), []);
  useLayoutEffect(() => {
    navigation.setOptions({
      headerRight: () => (
        <IconButton icon="add-circle" size={30} label="Nova regra de repasse" onPress={() => navigation.navigate('CommissionRuleEdit', {})} />
      ),
    });
  }, [navigation]);

  const today = todayISO();
  const byBarber = {};
  (list.data || []).forEach((x) => { (byBarber[x.barber_name] = byBarber[x.barber_name] || []).push(x); });

  return (
    <Screen onRefresh={list.reload} refreshing={list.loading && !!list.data}>
      {!list.data ? <Loading error={list.error} onRetry={list.reload} /> : null}
      {list.data && !list.data.length ? (
        <Empty text={`Cadastre quanto cada ${v.pro} repassa para ${v.theBusiness} ou para um padrinho.`} />
      ) : null}
      {Object.entries(byBarber).map(([name, rules]) => (
        <Section key={name} title={`${name} paga`}>
          {rules.map((x) => {
            const ended = x.valid_to && x.valid_to < today;
            const future = x.valid_from > today;
            return (
              <Card key={x.id} onPress={() => navigation.navigate('CommissionRuleEdit', { item: x })}
                    style={ended && { opacity: 0.5 }}>
                <View style={s.row}>
                  <Text style={[s.body, { flex: 1 }]}>Para {x.beneficiary_name}</Text>
                  <Text style={[s.body, { fontFamily: font.bold }]}>{pct(x.percentage)}</Text>
                </View>
                <Muted>{x.service_name || 'Todos os serviços'} · desde {brDate(x.valid_from)}
                  {x.valid_to ? ` até ${brDate(x.valid_to)}` : ''}</Muted>
                {ended ? <Muted>Encerrada</Muted> : null}
                {future ? <Muted>Começa no futuro</Muted> : null}
                {x.notes ? <Muted style={{ marginTop: 4 }}>{x.notes}</Muted> : null}
              </Card>
            );
          })}
        </Section>
      ))}
    </Screen>
  );
}

export function CommissionRuleEditScreen({ navigation, route }) {
  const { c, s, font, v } = useTheme(); // eslint-disable-line no-unused-vars
  const item = route.params?.item;
  const barbers = useLoad(() => api.get('/barbers'), []);
  const services = useLoad(() => api.get('/services'), []);
  const [barberId, setBarberId] = useState(item?.barber_id ?? route.params?.barberId ?? null);
  // 'shop' ou id do profissional beneficiário
  const [beneficiary, setBeneficiary] = useState(item ? (item.beneficiary_barber_id ?? 'shop') : 'shop');
  const [percentage, setPercentage] = useState(item ? String(item.percentage).replace('.', ',') : '');
  const [serviceId, setServiceId] = useState(item?.service_id ?? null);
  const [from, setFrom] = useState(brDate(item?.valid_from || todayISO()));
  const [hasEnd, setHasEnd] = useState(!!item?.valid_to);
  const [to, setTo] = useState(brDate(item?.valid_to));
  const [notes, setNotes] = useState(item?.notes || '');

  const activeBarbers = (barbers.data || []).filter((b) => b.active || b.id === barberId || b.id === beneficiary);

  const save = () => run(async () => {
    const validFrom = parseBRDate(from);
    if (!validFrom) throw new Error('Início inválido. Use dd/mm/aaaa.');
    const validTo = hasEnd ? parseBRDate(to) : null;
    if (hasEnd && !validTo) throw new Error('Fim inválido. Use dd/mm/aaaa.');
    const body = {
      barber_id: barberId,
      beneficiary_type: beneficiary === 'shop' ? 'shop' : 'barber',
      beneficiary_barber_id: beneficiary === 'shop' ? null : beneficiary,
      percentage: Number(percentage.replace(',', '.')),
      service_id: serviceId, valid_from: validFrom, valid_to: validTo, notes,
    };
    if (item) await api.put(`/commission-rules/${item.id}`, body);
    else await api.post('/commission-rules', body);
    navigation.goBack();
  });

  if (!barbers.data || !services.data) return <Loading error={barbers.error || services.error} />;

  return (
    <Screen>
      <Section title="Quem repassa">
        <Chips value={barberId} onChange={setBarberId}
               options={activeBarbers.map((b) => ({ value: b.id, label: b.name }))} />
      </Section>
      <Section title="Para quem">
        <Chips value={beneficiary} onChange={setBeneficiary}
               options={[{ value: 'shop', label: v.Business },
                 ...activeBarbers.filter((b) => b.id !== barberId).map((b) => ({ value: b.id, label: b.name }))]} />
      </Section>
      <Field label="Porcentagem (%)" value={percentage} onChangeText={setPercentage} keyboardType="decimal-pad"
             placeholder="Ex.: 30" hint={`A soma dos repasses de um ${v.pro} não pode passar de 100%.`} />
      <Section title="Serviço">
        <Chips value={serviceId} onChange={setServiceId}
               options={[{ value: null, label: 'Todos' }, ...services.data.map((x) => ({ value: x.id, label: x.name }))]} />
        <Muted>Uma regra de um serviço substitui a regra geral para o mesmo beneficiário.</Muted>
      </Section>
      <Field label="Vale a partir de" value={from} onChangeText={setFrom} placeholder="dd/mm/aaaa"
             keyboardType="numbers-and-punctuation" />
      <Toggle label="Tem data para acabar" value={hasEnd} onValueChange={setHasEnd} />
      {hasEnd ? (
        <Field label="Vale até" value={to} onChangeText={setTo} placeholder="dd/mm/aaaa" keyboardType="numbers-and-punctuation" />
      ) : null}
      <Field label="Observações" value={notes} onChangeText={setNotes} multiline placeholder="Ex.: padrinho nos 6 primeiros meses" />
      <Button title="Salvar" onPress={save} disabled={!barberId || !percentage || !from} />
      {item ? (
        <Button title="Excluir" kind="danger" onPress={() => confirm('Excluir regra?',
          'Os repasses de períodos passados serão recalculados sem ela. Para encerrar sem mexer no histórico, defina uma data de fim.',
          () => run(async () => { await api.del(`/commission-rules/${item.id}`); navigation.goBack(); }), 'Excluir', true)} />
      ) : null}
    </Screen>
  );
}
