import React, { useEffect, useState } from 'react';
import { Image, Modal, Pressable, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { api, apiUrl, authHeaders, download, saveFile } from '../api';
import { IS_WEB } from '../storage';
import { ago, dtLabel, money } from '../format';
import { useSession } from '../session';
import { SPACE, TOUCH } from '../theme';
import { useTheme } from '../ThemeProvider';
import { a11yState, Badge, Button, confirm, IconButton, run, ToastHost } from '../ui';

// Comprovante de Pix lido pela IA: PRÉ-CONFERÊNCIA. O selo diz se os dados batem; quem confirma é o dono, depois
// de olhar o extrato (o sistema não acessa o banco).
export const RECEIPT_RESULT = {
  confere: { label: 'Comprovante confere', tone: 'success', icon: 'checkmark-circle' },
  divergente: { label: 'Comprovante divergente', tone: 'warning', icon: 'alert-circle' },
  ilegivel: { label: 'Comprovante ilegível', tone: 'neutral', icon: 'help-circle-outline' },
};
const WAITING = { label: 'Aguardando o cliente dizer qual pagamento', tone: 'neutral', icon: 'hourglass-outline' };
const AUTO = { label: 'Automática pelo comprovante', tone: 'accent', icon: 'flash-outline' };
const DOC_TYPE = { comprovante_pix: 'Comprovante de Pix', agendamento_pix: 'Pix agendado (não pago)', outro: 'Outro documento' };

// Imagem com o login: no celular vai no cabeçalho; no navegador, <img> não manda cabeçalho, então baixa e usa blob:
function useReceiptSource(r) {
  const [webUri, setWebUri] = useState(null);
  const path = `/receipts/${r.id}/file`;
  const isImage = r.has_file && r.mime !== 'application/pdf';
  useEffect(() => {
    if (!IS_WEB || !isImage) return undefined;
    let url = null;
    download(path, null, `comprovante-${r.id}`).then((u) => { url = u; setWebUri(u); }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [r.id, isImage]); // eslint-disable-line
  return { path, isImage, src: IS_WEB ? { uri: webUri || undefined } : { uri: apiUrl(path), headers: authHeaders() } };
}

// Visualizador preto (cores fixas de propósito: a imagem do comprovante aparece igual em qualquer tema).
// Com onConfirm/onReject, o rodapé tem Confirmar e Recusar: não é preciso fechar e procurar o botão.
function FullScreen({ visible, onClose, src, onConfirm, onReject }) {
  const { s, font } = useTheme();
  const act = (fn) => { onClose(); fn(); };
  return (
    <Modal visible={visible} onRequestClose={onClose} animationType="fade" presentationStyle="fullScreen"
           supportedOrientations={['portrait', 'landscape']} aria-label="Comprovante em tela cheia">
      <View style={{ flex: 1, backgroundColor: '#000' }}>
        <View style={[s.row, { justifyContent: 'flex-end', padding: SPACE(3), paddingTop: SPACE(10) }]}>
          <IconButton icon="close" label="Fechar comprovante" color="#fff" onPress={onClose} />
        </View>
        <Image source={src} resizeMode="contain" style={{ flex: 1, width: '100%', backgroundColor: '#000' }}
               accessibilityLabel="Comprovante em tela cheia" />
        <Text style={[s.caption, { color: '#BDBDBD', fontFamily: font.medium, textAlign: 'center', padding: SPACE(4) }]}>
          O comprovante não prova que o dinheiro caiu: confira no extrato.
        </Text>
        {onConfirm || onReject ? (
          <View style={[s.row, { gap: SPACE(2), paddingHorizontal: SPACE(4), paddingBottom: SPACE(6) }]}>
            {onConfirm ? <Button title="Confirmar" icon="checkmark-circle" style={{ flex: 1, marginBottom: 0 }}
                                 onPress={() => act(onConfirm)} /> : null}
            {onReject ? <Button title="Recusar" icon="close-circle-outline" kind="danger" style={{ flex: 1, marginBottom: 0 }}
                                onPress={() => act(onReject)} /> : null}
          </View>
        ) : null}
        <ToastHost placement="top" active={visible} />
      </View>
    </Modal>
  );
}

function Row({ label, value }) {
  const { s } = useTheme();
  if (value === null || value === undefined || value === '') return null;
  return (
    <View style={[s.row, { gap: SPACE(3), paddingVertical: 3, alignItems: 'flex-start' }]}>
      <Text style={[s.caption, { width: 120 }]}>{label}</Text>
      <Text style={[s.body, { flex: 1 }]} selectable>{value}</Text>
    </View>
  );
}

// receipt: ReceiptOut da API. paid: o pagamento já está pago (mostra "Desfazer" na confirmação automática).
// onConfirm/onReject: as mesmas ações do card, repetidas na tela cheia do comprovante.
export function ReceiptReview({ receipt: r, paid, onChanged, onConfirm, onReject }) {
  const { c, s } = useTheme();
  const { isOwner } = useSession();
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState(false);
  const { path, isImage, src } = useReceiptSource(r);
  const result = r.result ? RECEIPT_RESULT[r.result] : WAITING;
  const failed = (r.checks || []).filter((x) => !x.ok);

  const undo = () => confirm('Desfazer a confirmação automática?',
    'O pagamento volta para pendente e o cliente recebe uma mensagem dizendo que a barbearia vai conferir de novo.',
    () => run(async () => { await api.post(`/receipts/${r.id}/undo`); onChanged?.(); }, 'Confirmação desfeita. O cliente foi avisado.'),
    'Desfazer', true);

  return (
    <View style={{ marginBottom: SPACE(3), gap: SPACE(2) }}>
      <View style={[s.row, { gap: SPACE(3), alignItems: 'flex-start' }]}>
        {r.has_file && isImage ? (
          <Pressable onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel="Ver comprovante em tela cheia">
            <Image source={src} style={{ width: 64, height: 88, borderRadius: 8, backgroundColor: c.neutralBg }} />
          </Pressable>
        ) : null}
        <View style={{ flex: 1, gap: SPACE(1.5) }}>
          <View style={[s.row, { gap: SPACE(1.5), flexWrap: 'wrap' }]}>
            <Badge info={result} large />
            {r.auto_confirmed ? <Badge info={AUTO} /> : null}
          </View>
          <Text style={s.caption}>
            Recebido {ago(r.created_at)}
            {r.amount ? ` · ${money(r.amount)}` : ''}
            {r.has_file && isImage ? ' · toque na imagem para ampliar' : ''}
            {!r.has_file && r.file_deleted_at ? ' · arquivo apagado (prazo de retenção)' : ''}
          </Text>
          {failed.map((x) => (
            <View key={x.key} style={[s.row, { gap: SPACE(1.5), alignItems: 'flex-start' }]}>
              <Ionicons name="alert-circle" size={16} color={c.statusText.warning} style={{ marginTop: 2 }} />
              <Text style={[s.body, { flex: 1, color: c.statusText.warning }]}>{x.detail}</Text>
            </View>
          ))}
        </View>
      </View>
      {r.has_file && !isImage ? (
        <Button title="Abrir comprovante (PDF)" kind="ghost" icon="document-text-outline" compact
                style={{ alignSelf: 'flex-start' }}
                onPress={() => run(() => saveFile(path, null, `comprovante-${r.id}.pdf`, 'application/pdf'))} />
      ) : null}
      <Pressable onPress={() => setDetails(!details)} accessibilityRole="button" {...a11yState({ expanded: details })}
                 style={[s.row, { gap: SPACE(1), minHeight: TOUCH, alignSelf: 'flex-start' }]}>
        <Ionicons name={details ? 'chevron-up' : 'chevron-down'} size={16} color={c.accentText} />
        <Text style={[s.caption, { color: c.accentText }]}>{details ? 'Esconder' : 'Ver'} dados lidos e conferências</Text>
      </Pressable>
      {details ? (
        <View style={{ backgroundColor: c.neutralBg, borderRadius: 10, padding: SPACE(3) }}>
          <Row label="Valor" value={r.amount ? money(r.amount) : null} />
          <Row label="Data e hora" value={r.paid_at ? dtLabel(r.paid_at) : null} />
          <Row label="Recebedor" value={r.receiver_name} />
          <Row label="Chave Pix" value={r.receiver_key} />
          <Row label="Banco recebedor" value={r.receiver_bank} />
          <Row label="Pagador" value={r.payer_name} />
          <Row label="Banco pagador" value={r.payer_bank} />
          <Row label="ID da transação" value={r.e2e_id} />
          <Row label="Tipo" value={r.doc_type ? DOC_TYPE[r.doc_type] || r.doc_type : null} />
          <Row label="Confiança" value={r.confidence !== null && r.confidence !== undefined
            ? `${Math.round(Number(r.confidence) * 100)}%` : null} />
          <View style={{ height: SPACE(2) }} />
          {(r.checks || []).map((x) => (
            <View key={x.key} style={[s.row, { gap: SPACE(1.5), paddingVertical: 2, alignItems: 'flex-start' }]}>
              <Ionicons name={x.ok ? 'checkmark-circle' : 'close-circle'} size={16} style={{ marginTop: 2 }}
                        color={x.ok ? c.statusText.success : c.statusText.warning} />
              <Text style={[s.body, { flex: 1 }]}><Text style={s.bodyBold}>{x.label}: </Text>{x.detail}</Text>
            </View>
          ))}
          <Text style={[s.caption, { marginTop: SPACE(2) }]}>
            Leitura automática por IA. O comprovante não prova que o dinheiro caiu: confira no extrato.
          </Text>
        </View>
      ) : null}
      {paid && r.decision === 'auto_confirmed' && isOwner ? (
        <Button title="Desfazer confirmação automática" kind="ghost" icon="arrow-undo-outline" compact
                style={{ alignSelf: 'flex-start' }} onPress={undo} />
      ) : null}
      {isImage ? <FullScreen visible={open} onClose={() => setOpen(false)} src={src}
                             onConfirm={paid ? null : onConfirm} onReject={paid ? null : onReject} /> : null}
    </View>
  );
}
