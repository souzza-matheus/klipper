"""Comprovante de Pix mandado pelo cliente no WhatsApp: PRÉ-CONFERÊNCIA para o dono confirmar com um toque.

Comprovante não prova que o dinheiro caiu (pode ser editado ou reaproveitado). O fluxo:
1. recebimento: imagem (JPG, PNG, WEBP) ou PDF de até 2 páginas, até 5 MB, tipo conferido pelos bytes; só quando o
   cliente tem pagamento pendente (Pix de agendamento ou sinal, pacote ou mensalidade);
2. leitura com IA (receipt_reader), que só extrai campos;
3. conferências no código (valor, recebedor, data, ID da transação único na plataforma, tipo do documento, arquivo
   repetido) e o resultado: confere, divergente ou ilegível;
4. alerta ao dono, que confirma (1) ou recusa (2) no WhatsApp ou no app. A confirmação automática (desligada por
   padrão) só vale para valores baixos e dentro de todas as regras de auto_confirm_blocker.
O cliente nunca ouve "confirmado" antes da confirmação de verdade.
"""
import hashlib
import io
import logging
import os
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import now_local, settings
from ..models import (
    Appointment, ApptStatus, Charge, Customer, CustomerPackage, DepositStatus, PayMethod, PayStatus, Payment,
    PaymentReceipt, ReceiptDecision, ReceiptResult, Shop, User,
)
from . import receipt_reader as reader
from .fmt import dt_label, money

log = logging.getLogger("receipts")

AUTO_CONFIRM_CEILING = Decimal("100.00")  # teto do valor da confirmação automática
AUTO_MIN_CONFIDENCE = Decimal("0.9")
AUTO_MAX_PER_MONTH = 3                    # confirmações automáticas por cliente por mês
OWNER_REPLY_WINDOW = timedelta(hours=12)  # depois disso, "1" no WhatsApp do dono volta a ser a opção do menu
MAX_AGE = timedelta(hours=48)             # comprovante de pagamento feito há mais de 48 h não confere

MSG_RECEIVED = "Recebi seu comprovante! A barbearia vai conferir e te aviso assim que confirmar."
MSG_NO_PENDING = "Não encontrei nenhum pagamento em aberto no seu nome. 🙂"
MSG_SEND_PHOTO = ("Não consegui abrir esse arquivo. 🙏 Pode mandar uma *foto* (ou print) do comprovante do Pix? "
                  "Aceito imagem JPG, PNG ou WEBP, ou PDF de até 2 páginas, com até 5 MB.")
MSG_LIMIT = ("Você já mandou vários comprovantes hoje. A barbearia vai conferir os que já recebemos e te aviso por "
             "aqui.")
MSG_ALREADY = "Esse comprovante já tinha chegado. A barbearia vai conferir e te aviso assim que confirmar."


class ReceiptError(ValueError):
    """Ação que não vale mais (pagamento já confirmado, recusado ou expirado)."""


# ---------------------------------------------------------------- arquivo

def sniff(data: bytes) -> str | None:
    """Tipo real pelos primeiros bytes (a extensão e o tipo declarado não valem)."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def pdf_pages(data: bytes) -> int | None:
    """Número de páginas do PDF; None se ele não abre (corrompido ou com senha)."""
    from pypdf import PdfReader
    try:
        doc = PdfReader(io.BytesIO(data))
        if doc.is_encrypted:
            return None
        return len(doc.pages)
    except Exception:
        return None


def validate(data: bytes) -> str | None:
    """Tipo do arquivo se ele pode ser lido como comprovante; None = pedir uma foto."""
    if not data or len(data) > settings.receipt_max_bytes:
        return None
    mime = sniff(data)
    if mime == "application/pdf":
        pages = pdf_pages(data)
        if not pages or pages > settings.receipt_max_pdf_pages:
            return None
    return mime


def _root() -> Path:
    return Path(settings.receipts_dir).resolve()


def store_file(shop: Shop, data: bytes) -> str:
    """Grava fora da pasta pública com nome aleatório (sem nada do nome enviado). Devolve o caminho relativo."""
    rel = f"{shop.id}/{secrets.token_hex(16)}"
    path = _root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return rel


def read_file(r: PaymentReceipt) -> bytes | None:
    if not r.file_path:
        return None
    path = (_root() / r.file_path).resolve()
    if _root() not in path.parents:  # caminho sempre gerado aqui; a checagem é só defesa extra
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def delete_file(r: PaymentReceipt) -> None:
    if r.file_path:
        try:
            (_root() / r.file_path).unlink(missing_ok=True)
        except OSError:
            log.warning("Não foi possível apagar o arquivo do comprovante %s", r.id)
    r.file_path, r.file_deleted_at = None, now_local()


def purge_expired(db: Session, days: int | None = None) -> int:
    """LGPD: apaga os arquivos com mais de N dias (padrão RECEIPT_RETENTION_DAYS). Ficam os dados lidos e o ID da
    transação (que continua barrando o reaproveitamento). Também limpa os comprovantes antigos guardados no banco."""
    limit = now_local() - timedelta(days=settings.receipt_retention_days if days is None else days)
    n = 0
    for r in db.scalars(select(PaymentReceipt).where(PaymentReceipt.file_path.is_not(None),
                                                     PaymentReceipt.created_at < limit)):
        delete_file(r)
        n += 1
    legacy = db.query(Payment).filter(Payment.receipt_data.is_not(None), Payment.receipt_at < limit) \
        .update({Payment.receipt_data: None}, synchronize_session=False)
    return n + legacy


# ---------------------------------------------------------------- pagamentos pendentes

@dataclass
class Target:
    """Um pagamento pendente que o comprovante pode quitar: Pix de agendamento/sinal ou cobrança avulsa."""
    obj: Payment | Charge

    @property
    def is_payment(self) -> bool:
        return isinstance(self.obj, Payment)

    @property
    def ref(self) -> list:
        return ["p" if self.is_payment else "c", self.obj.id]

    @property
    def amount(self) -> Decimal:
        return Decimal(self.obj.amount)

    @property
    def generated_at(self) -> datetime:
        return self.obj.created_at

    @property
    def pending(self) -> bool:
        return self.obj.status == PayStatus.PENDING

    @property
    def customer(self) -> Customer:
        return self.obj.appointment.customer if self.is_payment else self.obj.customer

    def label(self) -> str:
        if self.is_payment:
            a = self.obj.appointment
            what = "Sinal do horário" if self.obj.kind == "deposit" else "Horário"
            return f"{what} de {dt_label(a.start).lower()} ({a.service.name})"
        if self.obj.kind == "subscription":
            plan = self.obj.subscription.plan.name if self.obj.subscription else ""
            return f"Mensalidade {plan}".strip()
        cp = self.obj.customer_package_id and _db(self.obj).get(CustomerPackage, self.obj.customer_package_id)
        return f"Pacote {cp.name}" if cp else "Pacote"


def _db(obj) -> Session:
    from sqlalchemy.orm import object_session
    return object_session(obj)


def target_of(db: Session, r: PaymentReceipt) -> Target | None:
    if r.payment_id:
        p = db.get(Payment, r.payment_id)
        return Target(p) if p else None
    if r.charge_id:
        ch = db.get(Charge, r.charge_id)
        return Target(ch) if ch else None
    return None


def pending_targets(db: Session, shop: Shop, customer: Customer) -> list[Target]:
    pays = db.scalars(select(Payment).join(Appointment).where(
        Payment.shop_id == shop.id, Payment.status == PayStatus.PENDING, Appointment.customer_id == customer.id,
        Appointment.status != ApptStatus.CANCELLED).order_by(Appointment.start)).all()
    charges = db.scalars(select(Charge).where(
        Charge.shop_id == shop.id, Charge.customer_id == customer.id, Charge.status == PayStatus.PENDING,
        Charge.brcode != "").order_by(Charge.due_date)).all()
    return [Target(p) for p in pays] + [Target(c) for c in charges]


def latest_for(db: Session, payment_id: int | None = None, charge_id: int | None = None) -> PaymentReceipt | None:
    col, val = (PaymentReceipt.payment_id, payment_id) if payment_id else (PaymentReceipt.charge_id, charge_id)
    return db.scalar(select(PaymentReceipt).where(col == val).order_by(PaymentReceipt.id.desc()).limit(1))


def latest_by_target(db: Session, ids: list[int], charges: bool = False) -> dict[int, PaymentReceipt]:
    """Último comprovante de cada pagamento (uma consulta para a lista do app)."""
    if not ids:
        return {}
    col = PaymentReceipt.charge_id if charges else PaymentReceipt.payment_id
    out: dict[int, PaymentReceipt] = {}
    for r in db.scalars(select(PaymentReceipt).where(col.in_(ids)).order_by(PaymentReceipt.id)):
        out[getattr(r, col.key)] = r
    return out


# ---------------------------------------------------------------- conferências (no código, não na IA)

_COMPANY = re.compile(r"\b(ltda|me|epp|eireli|s ?a|mei|cia|limitada)\b")


def norm_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = _COMPANY.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_matches(read: str | None, registered: str | None) -> bool:
    """Parecido sem acentos e maiúsculas. O nome do Pix tem até 25 caracteres (o banco mostra o nome completo):
    vale também quando um começa com o outro."""
    a, b = norm_name(read), norm_name(registered)
    if not a or not b:
        return False
    if a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a))):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


_MASK = "*•●∗"


def key_matches(read: str | None, key: str, key_type: str) -> bool:
    """Chave lida (completa ou mascarada, ex.: CPF ***.456.789-**) compatível com a chave cadastrada. A parte
    visível precisa ter pelo menos 4 caracteres e aparecer na mesma ordem."""
    from .pix import normalize_key
    if not read or not key:
        return False
    numeric = key_type in ("cpf", "cnpj", "phone")
    full = normalize_key(key, key_type).lower().lstrip("+")
    r = read.strip().lower()
    if numeric:
        r = re.sub(r"[^0-9" + _MASK + "]", "", r)
    else:
        r = re.sub(r"\s", "", r)
    if not any(m in r for m in _MASK):
        if key_type == "phone":  # com ou sem o 55
            return len(r) >= 10 and full.endswith(r)
        return r == full
    visible = re.sub("[" + _MASK + "]", "", r)
    if len(visible) < 4:
        return False
    pattern = "".join(".*" if ch in _MASK else re.escape(ch) for ch in re.sub("[" + _MASK + "]+", "*", r))
    return re.fullmatch(pattern, full) is not None or (key_type == "phone" and re.search(pattern.strip(".*"), full)
                                                       is not None)


def _check(key: str, ok: bool, label: str, detail: str) -> dict:
    return {"key": key, "ok": bool(ok), "label": label, "detail": detail}


def run_checks(db: Session, shop: Shop, r: PaymentReceipt, t: Target, reused_elsewhere: bool) -> list[dict]:
    out = []
    # 1. valor (tolerância zero)
    if r.amount is None:
        out.append(_check("valor", False, "Valor", "O valor não aparece no comprovante."))
    elif r.amount == t.amount:
        out.append(_check("valor", True, "Valor", f"{money(r.amount)}, igual ao cobrado."))
    else:
        out.append(_check("valor", False, "Valor", f"Valor {money(r.amount)}, cobrado {money(t.amount)}."))
    # 2. recebedor: nome parecido com o do Pix cadastrado ou chave compatível
    name_ok = name_matches(r.receiver_name, shop.pix_receiver_name)
    key_ok = key_matches(r.receiver_key, shop.pix_key, shop.pix_key_type)
    if name_ok or key_ok:
        how = "nome" if name_ok else "chave"
        out.append(_check("recebedor", True, "Recebedor", f"Confere pelo {how} ({r.receiver_name or r.receiver_key})."))
    elif not r.receiver_name and not r.receiver_key:
        out.append(_check("recebedor", False, "Recebedor", "O recebedor não aparece no comprovante."))
    else:
        out.append(_check("recebedor", False, "Recebedor",
                          f"Pago para {r.receiver_name or r.receiver_key}, não para {shop.pix_receiver_name}."))
    # 3. data: depois da geração do Pix e no máximo 48 h antes do envio (o banco mostra só os minutos)
    sent = r.created_at or now_local()
    gen = t.generated_at.replace(second=0, microsecond=0)
    if r.paid_at is None:
        out.append(_check("data", False, "Data e hora", "A data do pagamento não aparece no comprovante."))
    elif r.paid_at < gen:
        out.append(_check("data", False, "Data e hora",
                          f"Pagamento em {r.paid_at:%d/%m %H:%M}, antes de o Pix ser gerado ({gen:%d/%m %H:%M})."))
    elif r.paid_at < sent - MAX_AGE:
        out.append(_check("data", False, "Data e hora", f"Pagamento antigo ({r.paid_at:%d/%m %H:%M})."))
    elif r.paid_at > sent + timedelta(minutes=5):
        out.append(_check("data", False, "Data e hora", f"Data no futuro ({r.paid_at:%d/%m %H:%M})."))
    else:
        out.append(_check("data", True, "Data e hora", f"Pago em {r.paid_at:%d/%m às %H:%M}."))
    # 4. ID da transação nunca usado em outro pagamento da plataforma
    out.append(_e2e_check(db, r, t))
    # 5. tipo do documento
    if r.doc_type == "agendamento_pix":
        out.append(_check("tipo", False, "Tipo", "É um Pix AGENDADO: ainda não foi pago."))
    elif r.doc_type != "comprovante_pix":
        out.append(_check("tipo", False, "Tipo", "Não parece um comprovante de Pix."))
    else:
        out.append(_check("tipo", True, "Tipo", "Comprovante de Pix."))
    # 6. o mesmo arquivo já mandado para outro pagamento
    if reused_elsewhere:
        out.append(_check("arquivo", False, "Arquivo", "Este arquivo já foi enviado para outro pagamento."))
    else:
        out.append(_check("arquivo", True, "Arquivo", "Arquivo novo."))
    return out


def _same_target(a: PaymentReceipt, t: Target) -> bool:
    return (a.payment_id == t.obj.id) if t.is_payment else (a.charge_id == t.obj.id)


def _e2e_check(db: Session, r: PaymentReceipt, t: Target) -> dict:
    label = "ID da transação"
    if not r.e2e_read:
        return _check("e2e", False, label, "O ID da transação não aparece no comprovante.")
    owner = db.scalar(select(PaymentReceipt).where(PaymentReceipt.e2e_id == r.e2e_read))
    if owner is not None and owner.id != r.id:
        if _same_target(owner, t):  # o mesmo Pix reenviado (print e PDF, por exemplo)
            return _check("e2e", True, label, f"Final ...{r.e2e_read[-4:]} (já recebido para este pagamento).")
        return _check("e2e", False, label, "Este comprovante já foi usado em outro pagamento.")
    try:  # índice único: dois comprovantes iguais ao mesmo tempo, só um fica com o ID
        with db.begin_nested():
            r.e2e_id = r.e2e_read
            db.flush()
    except IntegrityError:
        r.e2e_id = None
        return _check("e2e", False, label, "Este comprovante já foi usado em outro pagamento.")
    return _check("e2e", True, label, f"Final ...{r.e2e_read[-4:]}, não usado antes.")


def unreadable(r: PaymentReceipt) -> bool:
    return r.read_status == "failed" or (r.amount is None and r.e2e_read is None and r.paid_at is None)


def evaluate(db: Session, shop: Shop, r: PaymentReceipt, t: Target, reused_elsewhere: bool = False) -> str:
    if unreadable(r):
        r.checks = [_check("leitura", False, "Leitura", "Não foi possível ler o comprovante.")]
        r.result = ReceiptResult.UNREADABLE
    else:
        r.checks = run_checks(db, shop, r, t, reused_elsewhere)
        r.result = ReceiptResult.OK if all(c["ok"] for c in r.checks) else ReceiptResult.DIVERGENT
    return r.result


# ---------------------------------------------------------------- recebimento

def _customer(db: Session, shop: Shop, phone: str) -> Customer | None:
    return db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone))


def today_count(db: Session, customer: Customer) -> int:
    start = now_local().replace(hour=0, minute=0, second=0)
    return db.scalar(select(func.count()).select_from(PaymentReceipt).where(
        PaymentReceipt.customer_id == customer.id, PaymentReceipt.created_at >= start)) or 0


def _apply_read(r: PaymentReceipt, rd: "reader.ReceiptRead | PaymentReceipt", status: str) -> None:
    src = rd
    r.read_status = status
    if isinstance(src, PaymentReceipt):
        for f in ("amount", "paid_at", "receiver_name", "receiver_key", "receiver_bank", "payer_name", "payer_bank",
                  "e2e_read", "doc_type", "confidence"):
            setattr(r, f, getattr(src, f))
        if src.read_status == "failed":
            r.read_status = "failed"
        return
    if not src.ok:
        return
    r.amount, r.paid_at = src.amount, src.paid_at
    r.receiver_name, r.receiver_key, r.receiver_bank = src.receiver_name, src.receiver_key, src.receiver_bank
    r.payer_name, r.payer_bank = src.payer_name, src.payer_bank
    r.e2e_read, r.doc_type, r.confidence = src.e2e, src.doc_type, src.confidence


def match(targets: list[Target], r: PaymentReceipt) -> Target | None:
    """Um pendente só: é ele. Vários: o único com o valor lido. Senão, pergunta ao cliente."""
    if len(targets) == 1:
        return targets[0]
    same = [t for t in targets if r.amount is not None and t.amount == r.amount]
    return same[0] if len(same) == 1 else None


def handle_media(db: Session, shop: Shop, phone: str, media: dict) -> PaymentReceipt | None:
    """Imagem ou PDF de um cliente. Sem pagamento pendente: não chama a IA, responde e mostra o menu. Com pendente:
    baixa, valida, guarda, responde "Recebi", lê, confere e alerta o dono (ou pergunta a qual pagamento se refere).
    Devolve o comprovante criado (None se nada foi guardado). Faz os próprios commits."""
    from ..bot.context import Ctx, conversation_for
    from .whatsapp import EvolutionError, media_base64, send_text
    customer = _customer(db, shop, phone)
    targets = pending_targets(db, shop, customer) if customer else []
    conv = conversation_for(db, shop, phone)
    paused = bool(conv.paused_until and conv.paused_until > now_local())  # atendimento humano: o bot fica quieto

    def say(text: str) -> None:
        if not paused:
            send_text(db, shop, phone, text)

    if not targets:
        if not paused:
            from ..bot import customer as customer_bot
            ctx = Ctx(db, shop, conv, phone, "")
            ctx.say(MSG_NO_PENDING)
            customer_bot.show_menu(ctx)
            ctx.flush()
        db.commit()
        return None
    if today_count(db, customer) >= settings.receipt_daily_limit:
        say(MSG_LIMIT)
        db.commit()
        return None
    try:
        declared, data = media_base64(shop, media)
    except EvolutionError:
        log.warning("Comprovante: não foi possível baixar a mídia")
        say(MSG_SEND_PHOTO)
        db.commit()
        return None
    # Vale o conteúdo; o tipo declarado só pode recusar (áudio, vídeo ou texto não viram comprovante)
    declared_ok = not declared or declared.startswith(("image/", "application/pdf", "application/octet-stream"))
    mime = validate(data) if declared_ok else None
    if mime is None:
        say(MSG_SEND_PHOTO)
        db.commit()
        return None
    digest = hashlib.sha256(data).hexdigest()
    prev = db.scalar(select(PaymentReceipt).where(PaymentReceipt.file_hash == digest).order_by(PaymentReceipt.id)
                     .limit(1))
    if prev and prev.shop_id == shop.id and prev.customer_id == customer.id:
        pt = target_of(db, prev)
        if pt is None or pt.pending:  # o mesmo arquivo para o mesmo pagamento: nada novo para conferir
            say(MSG_ALREADY)
            db.commit()
            return None
    r = PaymentReceipt(shop_id=shop.id, customer_id=customer.id, file_hash=digest, mime=mime, size_bytes=len(data),
                       file_path=store_file(shop, data), created_at=now_local())
    db.add(r)
    db.flush()
    say(MSG_RECEIVED)
    db.commit()

    if prev is not None:  # mesmo arquivo já lido: reaproveita a leitura, sem chamar a IA
        _apply_read(r, prev, "reused")
    else:
        ok, why = reader.available(db, shop)
        if ok:
            _apply_read(r, reader.read(db, shop, phone, data, mime), "ok")
            if r.read_status == "ok" and r.doc_type is None:
                r.read_status = "failed"
        else:
            log.info("Comprovante sem leitura automática: %s", why)
            r.read_status = "failed"
    db.commit()

    t = match(targets, r)
    if t is None:
        ask_target(db, shop, conv, r, targets, paused)
    else:
        finalize(db, shop, r, t, reused_elsewhere=prev is not None)
    db.commit()
    return r


def ask_target(db: Session, shop: Shop, conv, r: PaymentReceipt, targets: list[Target], paused: bool) -> None:
    from ..bot.context import Ctx
    lines = [f"*{i}* - {t.label()} | {money(t.amount)}" for i, t in enumerate(targets, 1)]
    ctx = Ctx(db, shop, conv, conv.phone, "")
    ctx.go("receipt_pick", receipt_id=r.id, receipt_targets=[t.ref for t in targets])
    if not paused:
        ctx.say("Você tem mais de um pagamento em aberto. A qual deles esse comprovante se refere?\n\n"
                + "\n".join(lines) + "\n\nResponda com o número.")
        ctx.flush()


def resolve_ref(db: Session, shop: Shop, ref) -> Target | None:
    kind, oid = ref
    obj = db.get(Payment if kind == "p" else Charge, oid)
    return Target(obj) if obj is not None and obj.shop_id == shop.id else None


def finalize(db: Session, shop: Shop, r: PaymentReceipt, t: Target, reused_elsewhere: bool | None = None) -> None:
    """Vincula ao pagamento, confere, marca "cliente disse que pagou" e confirma sozinho (se as regras deixarem) ou
    alerta o dono."""
    if reused_elsewhere is None:
        reused_elsewhere = r.read_status == "reused"
    if t.is_payment:
        r.payment_id, r.charge_id = t.obj.id, None
        t.obj.receipt_mime, t.obj.receipt_at = r.mime, r.created_at  # "tem comprovante" na lista do app
    else:
        r.charge_id, r.payment_id = t.obj.id, None
    t.obj.customer_reported_at = t.obj.customer_reported_at or now_local()
    evaluate(db, shop, r, t, reused_elsewhere)
    db.flush()
    if not t.pending:
        return
    if auto_confirm_blocker(db, shop, r, t) is None:
        _confirm_target(db, shop, t, None)
        r.decision, r.decided_at, r.auto_confirmed = ReceiptDecision.AUTO_CONFIRMED, now_local(), True
        alert_owner(db, shop, r, t, auto=True)
    else:
        alert_owner(db, shop, r, t)


# ---------------------------------------------------------------- confirmação automática

def auto_confirm_blocker(db: Session, shop: Shop, r: PaymentReceipt, t: Target) -> str | None:
    """None = pode confirmar sozinho. Todas as condições precisam valer."""
    limit = min(Decimal(shop.receipt_auto_confirm_max or 0), AUTO_CONFIRM_CEILING)
    if not shop.receipt_auto_confirm or limit <= 0:
        return "desligada"
    if r.result != ReceiptResult.OK:
        return "não confere"
    if r.confidence is None or Decimal(r.confidence) < AUTO_MIN_CONFIDENCE:
        return "confiança baixa"
    if t.amount > limit:
        return "valor acima do limite"
    bad = db.scalar(select(func.count()).select_from(PaymentReceipt).where(
        PaymentReceipt.customer_id == r.customer_id, PaymentReceipt.id != r.id,
        or_(PaymentReceipt.result == ReceiptResult.DIVERGENT,
            PaymentReceipt.decision.in_((ReceiptDecision.REJECTED, ReceiptDecision.UNDONE)))))
    if bad:
        return "cliente com comprovante divergente ou recusado"
    start = now_local().replace(day=1, hour=0, minute=0, second=0)
    autos = db.scalar(select(func.count()).select_from(PaymentReceipt).where(
        PaymentReceipt.customer_id == r.customer_id, PaymentReceipt.auto_confirmed.is_(True),
        PaymentReceipt.decided_at >= start))
    if autos >= AUTO_MAX_PER_MONTH:
        return "limite mensal de confirmações automáticas do cliente"
    return None


# ---------------------------------------------------------------- confirmar, recusar, desfazer

def _confirm_target(db: Session, shop: Shop, t: Target, user: User | None) -> None:
    if t.is_payment:
        from .payments import confirm_and_notify
        confirm_and_notify(db, shop, t.obj)
    else:
        from .billing import confirm_and_notify
        confirm_and_notify(db, shop, t.obj, user)


def settle(db: Session, decision: str, user: User | None = None, payment_id: int | None = None,
           charge_id: int | None = None) -> None:
    """O pagamento foi confirmado ou recusado por fora do comprovante (lista de Pix): registra a decisão no último
    comprovante ainda sem decisão (vale para o histórico do cliente na confirmação automática)."""
    r = latest_for(db, payment_id, charge_id)
    if r is not None and r.decision is None:
        r.decision, r.decided_at, r.decided_by_id = decision, now_local(), user.id if user else None


def confirm(db: Session, shop: Shop, r: PaymentReceipt, user: User | None = None) -> None:
    t = target_of(db, r)
    if t is None or not t.pending:
        raise ReceiptError("Esse pagamento não está mais pendente.")
    _confirm_target(db, shop, t, user)
    r.decision, r.decided_at, r.decided_by_id = ReceiptDecision.CONFIRMED, now_local(), user.id if user else None


def reject_text(t: Target) -> str:
    return (f"Não conseguimos confirmar o seu Pix de {money(t.amount)} ({t.label()}). Confira o pagamento no app do "
            "seu banco ou fale com a barbearia por aqui.")


def reject(db: Session, shop: Shop, r: PaymentReceipt, user: User | None = None) -> None:
    """O dono não achou o dinheiro: o cliente recebe uma mensagem neutra. Pix de agendamento segue o fluxo de
    recusa que já existia (expira; o horário continua marcado); cobrança de pacote ou mensalidade continua aberta."""
    from .payments import reject_payment
    from .whatsapp import send_text
    t = target_of(db, r)
    if t is None or not t.pending:
        raise ReceiptError("Esse pagamento não está mais pendente.")
    if t.is_payment:
        reject_payment(db, t.obj)
    else:
        t.obj.customer_reported_at = None
    r.decision, r.decided_at, r.decided_by_id = ReceiptDecision.REJECTED, now_local(), user.id if user else None
    send_text(db, shop, t.customer.phone, reject_text(t))


def undo_auto(db: Session, shop: Shop, r: PaymentReceipt, user: User | None = None) -> None:
    """Desfaz a confirmação automática: o pagamento volta para pendente e o cliente é avisado."""
    from . import benefits
    from .whatsapp import send_text
    t = target_of(db, r)
    if r.decision != ReceiptDecision.AUTO_CONFIRMED or t is None or t.obj.status != PayStatus.PAID:
        raise ReceiptError("Só dá para desfazer uma confirmação automática que ainda vale.")
    o = t.obj
    o.status, o.confirmed_at = PayStatus.PENDING, None
    if t.is_payment:
        a = o.appointment
        if o.kind == "deposit":
            a.deposit_status = DepositStatus.PENDING
            if a.status == ApptStatus.SCHEDULED and a.start > now_local():
                a.status = ApptStatus.AWAITING_DEPOSIT
        else:
            a.payment_status = PayStatus.PENDING
            if a.payment_method == PayMethod.PIX and a.status != ApptStatus.COMPLETED:
                a.payment_method = None
    else:
        o.confirmed_by_id = None
        if o.kind == "package" and o.customer_package_id:
            cp = db.get(CustomerPackage, o.customer_package_id)
            if cp and cp.status == "active":
                cp.status = "pending_payment"
        elif o.subscription:
            db.flush()
            benefits.refresh_status(db, o.subscription)
    r.decision, r.decided_at, r.decided_by_id = ReceiptDecision.UNDONE, now_local(), user.id if user else None
    send_text(db, shop, t.customer.phone,
              f"Precisamos conferir de novo o seu Pix de {money(t.amount)} ({t.label()}). A barbearia vai verificar "
              "e te avisa por aqui. Se precisar, fale com a gente.")


# ---------------------------------------------------------------- dono

def _who(t: Target) -> str:
    c = t.customer
    return c.name or c.phone


def owner_text(shop: Shop, r: PaymentReceipt, t: Target, auto: bool = False) -> str:
    who = _who(t)
    head = f"{who} - {t.label()}"
    if auto:
        return (f"✅ *Pix confirmado automaticamente pelo comprovante*\n{head}\n{money(t.amount)}"
                f"{_ending(r)}\n\nO sistema não acessa seu extrato: confira. Responda *2* para desfazer.")
    if r.result == ReceiptResult.OK:
        when = (f" às {r.paid_at:%H:%M}" if r.paid_at.date() == now_local().date()
                else f" em {r.paid_at:%d/%m às %H:%M}")
        receiver = r.receiver_name or shop.pix_receiver_name
        return (f"🧾 Comprovante confere: {money(r.amount)} para {receiver}{when}{_ending(r)}.\n{head}\n\n"
                "Confira no extrato e responda *1* para confirmar (ou *2* para recusar).")
    if r.result == ReceiptResult.UNREADABLE:
        return (f"🧾 {who} mandou um comprovante que não consegui ler ({t.label()}, {money(t.amount)}).\n"
                "Veja a imagem no app e confira no extrato. Responda *1* para confirmar ou *2* para recusar.")
    bad = [c for c in r.checks or [] if not c["ok"]]
    lines = "\n".join(f"• {c['detail']}" for c in bad)
    return (f"⚠️ *Atenção no comprovante de {who}*\n{t.label()}\n{lines}\n\n"
            "Confira no extrato. Responda *1* para confirmar mesmo assim ou *2* para recusar.")


def _ending(r: PaymentReceipt) -> str:
    e2e = r.e2e_read
    return f" (ID final ...{e2e[-4:]})" if e2e else ""


def alert_owner(db: Session, shop: Shop, r: PaymentReceipt, t: Target, auto: bool = False) -> None:
    """Manda o resultado para o WhatsApp do dono e deixa a conversa dele pronta para o 1 (confirmar) ou 2 (recusar
    ou desfazer)."""
    from ..bot.context import conversation_for
    from .whatsapp import send_text
    if not shop.owner_phone:
        return
    send_text(db, shop, shop.owner_phone, owner_text(shop, r, t, auto))
    conv = conversation_for(db, shop, shop.owner_phone)
    if (conv.data or {}).get("as_customer"):
        return  # dono testando como cliente: não mexe na conversa
    conv.state = "o_receipt"
    conv.data = {**(conv.data or {}), "receipt_id": r.id, "receipt_alert_at": now_local().isoformat()}


def auto_confirmed_text(db: Session, shop: Shop, since: datetime) -> str:
    """Resumo diário: confirmações automáticas para o dono conferir com o extrato."""
    rows = db.scalars(select(PaymentReceipt).where(
        PaymentReceipt.shop_id == shop.id, PaymentReceipt.decision == ReceiptDecision.AUTO_CONFIRMED,
        PaymentReceipt.decided_at >= since).order_by(PaymentReceipt.decided_at)).all()
    if not rows:
        return ""
    lines = []
    for r in rows:
        t = target_of(db, r)
        if t:
            lines.append(f"• {_who(t)} - {money(t.amount)} ({r.decided_at:%d/%m %H:%M}){_ending(r)}")
    return ("🧾 *Pix confirmados automaticamente pelo comprovante* (confira no extrato; dá para desfazer no app):\n"
            + "\n".join(lines))
