"""Pix por chave direta do estabelecimento, com confirmação manual pelo dono."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import Appointment, PayStatus, Payment, Shop
from .fmt import appt_summary, money
from .pix import build_brcode, new_txid


def pix_ready(shop: Shop) -> bool:
    return bool(shop.pix_enabled and shop.pix_key and shop.pix_receiver_name and shop.pix_city)


def get_or_create_pix(db: Session, shop: Shop, appt: Appointment) -> Payment:
    pay = appt.payment
    if pay and pay.status == PayStatus.PENDING:
        return pay
    if pay and pay.status == PayStatus.PAID:
        return pay
    txid = new_txid()
    brcode = build_brcode(shop.pix_key, shop.pix_key_type, appt.price, shop.pix_receiver_name,
                          shop.pix_city, txid, description=f"Agendamento {appt.id}")
    if pay is None:
        pay = Payment(shop_id=shop.id, appointment_id=appt.id, amount=appt.price, txid=txid, brcode=brcode)
        db.add(pay)
        appt.payment = pay
    else:  # Pix anterior expirado: gera um novo
        pay.txid, pay.brcode, pay.amount = txid, brcode, appt.price
        pay.status, pay.created_at, pay.customer_reported_at = PayStatus.PENDING, now_local(), None
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


def confirm_payment(db: Session, pay: Payment) -> None:
    pay.status = PayStatus.PAID
    pay.confirmed_at = now_local()
    pay.appointment.payment_status = PayStatus.PAID


def pending_payments(db: Session, shop: Shop) -> list[Payment]:
    return list(db.scalars(select(Payment).where(
        Payment.shop_id == shop.id, Payment.status == PayStatus.PENDING
    ).order_by(Payment.customer_reported_at.desc().nullslast(), Payment.created_at)).all())


def expire_old(db: Session, shop: Shop) -> int:
    limit = now_local() - timedelta(hours=shop.pix_expire_hours)
    count = 0
    for pay in pending_payments(db, shop):
        if pay.created_at < limit and pay.customer_reported_at is None:
            pay.status = PayStatus.EXPIRED
            pay.appointment.payment_status = PayStatus.EXPIRED
            count += 1
    return count
