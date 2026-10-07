"""Pix por chave direta do estabelecimento, com confirmação manual pelo dono."""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import Appointment, Customer, PayMethod, PayStatus, Payment, Shop
from .fmt import appt_summary, money
from .pix import build_brcode, new_txid

log = logging.getLogger("payments")

# Comprovante: só JPEG, PNG, WebP, GIF ou PDF, até 5 MB. O tipo vem dos bytes do arquivo, não do que foi
# declarado (um SVG ou HTML com o tipo "image/png" é recusado).
MAX_RECEIPT_BYTES = 5 * 1024 * 1024


def sniff_receipt(data: bytes) -> str | None:
    """Tipo real do arquivo pelos primeiros bytes, ou None se não for um formato aceito."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def pix_ready(shop: Shop) -> bool:
    """Pix ligado e com chave válida (uma chave inválida nunca vira código Pix quebrado para o cliente)."""
    from .pix import valid_pix_key
    return bool(shop.pix_enabled and shop.pix_key and shop.pix_receiver_name and shop.pix_city
                and valid_pix_key(shop.pix_key, shop.pix_key_type))


def get_or_create_pix(db: Session, shop: Shop, appt: Appointment, amount=None, kind: str = "full") -> Payment:
    """Pix do atendimento (kind=full, valor do atendimento menos o sinal já pago) ou do sinal (kind=deposit)."""
    pay = appt.payment
    if pay and pay.status == PayStatus.PENDING and pay.kind == kind:
        return pay
    if pay and pay.status == PayStatus.PAID and pay.kind == kind:
        return pay
    if amount is None:
        paid_deposit = appt.deposit_amount if appt.deposit_status == "paid" else 0
        amount = max(appt.price - (paid_deposit or 0), 0)
    txid = new_txid()
    label = "Sinal" if kind == "deposit" else "Agendamento"
    brcode = build_brcode(shop.pix_key, shop.pix_key_type, amount, shop.pix_receiver_name,
                          shop.pix_city, txid, description=f"{label} {appt.id}")
    if pay is None:
        pay = Payment(shop_id=shop.id, appointment_id=appt.id, amount=amount, txid=txid, brcode=brcode, kind=kind)
        db.add(pay)
        appt.payment = pay
    else:  # Pix anterior expirado (ou o sinal já pago, agora o restante): gera um novo
        pay.txid, pay.brcode, pay.amount, pay.kind = txid, brcode, amount, kind
        pay.status, pay.created_at, pay.customer_reported_at = PayStatus.PENDING, now_local(), None
        pay.receipt_mime, pay.receipt_data, pay.receipt_at, pay.confirmed_at = None, None, None, None
    if kind == "full":
        appt.payment_status = PayStatus.PENDING
    db.flush()
    return pay


def pix_messages(shop: Shop, appt: Appointment, pay: Payment) -> list[str]:
    """Duas mensagens: instruções e o código sozinho (fica fácil de copiar no celular)."""
    intro = (
        f"💳 *Pagamento via Pix*\n\n{appt_summary(appt)}\n\n"
        f"Valor: *{money(pay.amount)}*\n"
        f"Recebedor: {shop.pix_receiver_name}\n"
        f"Chave Pix: {shop.pix_key}\n\n"
        "Copie o código da próxima mensagem e cole no app do seu banco em *Pix > Copia e cola*.\n"
        "Depois de pagar, responda *paguei* (pode mandar o comprovante)."
    )
    return [intro, pay.brcode]


def confirm_payment(db: Session, pay: Payment) -> bool:
    """Devolve True quando o Pix era o sinal e confirmou um agendamento que aguardava sinal."""
    pay.status = PayStatus.PAID
    pay.confirmed_at = now_local()
    if pay.kind == "deposit":
        from .deposits import on_paid
        return on_paid(pay.appointment)
    pay.appointment.payment_status = PayStatus.PAID
    if pay.appointment.payment_method is None:
        pay.appointment.payment_method = PayMethod.PIX
    return False


def reject_payment(db: Session, pay: Payment) -> None:
    """O dono não achou o Pix no extrato: o pagamento expira e o atendimento volta a ser pago no local."""
    pay.status = PayStatus.EXPIRED
    if pay.kind != "deposit":
        pay.appointment.payment_status = PayStatus.EXPIRED


def save_receipt(db: Session, shop: Shop, phone: str, media: dict) -> int:
    """Guarda o comprovante (imagem ou PDF) mandado pelo cliente nos Pix pendentes dele. Devolve quantos recebeu.
    media: {"key": ..., "message": ...} do evento messages.upsert, usado para baixar o arquivo na Evolution API."""
    from .whatsapp import EvolutionError, mask_phone, media_base64
    customer = db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone))
    if customer is None:
        return 0
    pays = db.scalars(select(Payment).join(Appointment).where(
        Payment.shop_id == shop.id, Payment.status == PayStatus.PENDING, Appointment.customer_id == customer.id,
    )).all()
    if not pays:
        return 0
    try:
        mime, data = media_base64(shop, media)
    except EvolutionError:
        log.exception("Não foi possível baixar o comprovante de %s", mask_phone(phone))
        return 0
    if len(data) > MAX_RECEIPT_BYTES:
        log.warning("Comprovante de ...%s ignorado: %d bytes (limite %d)", phone[-4:], len(data), MAX_RECEIPT_BYTES)
        return 0
    real = sniff_receipt(data)
    if real is None or not mime.startswith(("image/", "application/pdf")):
        log.info("Anexo de ...%s ignorado: não é imagem nem PDF (declarado: %s)", phone[-4:], mime[:40])
        return 0
    mime = real
    now = now_local()
    for pay in pays:
        pay.receipt_mime, pay.receipt_data, pay.receipt_at = mime[:60], data, now
    return len(pays)


def pending_payments(db: Session, shop: Shop) -> list[Payment]:
    return list(db.scalars(select(Payment).where(
        Payment.shop_id == shop.id, Payment.status == PayStatus.PENDING
    ).order_by(Payment.customer_reported_at.desc().nullslast(), Payment.created_at)).all())


def expire_old(db: Session, shop: Shop) -> int:
    limit = now_local() - timedelta(hours=shop.pix_expire_hours)
    count = 0
    for pay in pending_payments(db, shop):
        if pay.created_at < limit and pay.customer_reported_at is None and pay.kind != "deposit":
            pay.status = PayStatus.EXPIRED  # o sinal tem prazo próprio (deposits.expire_unpaid)
            pay.appointment.payment_status = PayStatus.EXPIRED
            count += 1
    return count
