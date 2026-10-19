"""Pix por chave direta do estabelecimento, com confirmação manual pelo dono."""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import Appointment, PayMethod, PayStatus, Payment, Shop
from .fmt import appt_summary, dt_label, money
from .pix import build_brcode, new_txid

log = logging.getLogger("payments")

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


def confirmed_text(pay: Payment, deposit_ok: bool) -> str:
    a = pay.appointment
    if pay.kind == "deposit":
        return (f"✅ Recebemos o sinal de {money(pay.amount)}! Seu horário de {dt_label(a.start)} está confirmado. "
                "O valor do sinal é descontado no atendimento." if deposit_ok else
                f"✅ Recebemos o sinal de {money(pay.amount)} do horário de {dt_label(a.start)}.")
    return f"✅ Recebemos o seu Pix de {money(pay.amount)}! Seu horário de {dt_label(a.start)} está pago. Até lá! 💈"


def confirm_and_notify(db: Session, shop: Shop, pay: Payment) -> None:
    """Confirma (app, bot do dono ou comprovante) e avisa o cliente."""
    from .whatsapp import send_text
    deposit_ok = confirm_payment(db, pay)
    send_text(db, shop, pay.appointment.customer.phone, confirmed_text(pay, deposit_ok))


def reject_payment(db: Session, pay: Payment) -> None:
    """O dono não achou o Pix no extrato: o pagamento expira e o atendimento volta a ser pago no local."""
    pay.status = PayStatus.EXPIRED
    if pay.kind != "deposit":
        pay.appointment.payment_status = PayStatus.EXPIRED


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
