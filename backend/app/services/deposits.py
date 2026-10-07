"""Sinal contra faltas: Pix antecipado que garante o horário.

Regra do estabelecimento (desligado, valor fixo ou % do serviço), que cada serviço pode sobrescrever. Com sinal, o
agendamento feito pelo WhatsApp fica "aguardando sinal" (ocupa o horário) e só é confirmado quando o Pix do sinal é
confirmado. Sem confirmação em deposit_expire_minutes, o horário é liberado (e oferecido à lista de espera).
Cancelamento: com deposit_refund_hours ou mais de antecedência, o sinal fica "a devolver"; depois disso (ou falta),
fica com o estabelecimento e entra no faturamento.
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, DepositMode, DepositStatus, PayStatus, Payment, Service, Shop,
)
from .fmt import appt_summary, money

CENT = Decimal("0.01")


def deposit_for(shop: Shop, service: Service) -> Decimal:
    """Valor do sinal para o serviço (0 = sem sinal)."""
    mode, value = shop.deposit_mode, shop.deposit_value or Decimal(0)
    if service.deposit_mode:
        mode, value = service.deposit_mode, service.deposit_value or Decimal(0)
    if mode == DepositMode.FIXED:
        amount = min(Decimal(value), service.price)
    elif mode == DepositMode.PERCENT:
        amount = service.price * Decimal(value) / 100
    else:
        return Decimal(0)
    return max(Decimal(0), amount.quantize(CENT, rounding=ROUND_HALF_UP))


def needs_deposit(shop: Shop, appt: Appointment) -> Decimal:
    """Sinal exigido para um agendamento do WhatsApp (0 se não precisa: sem regra, sem Pix ou pago com saldo)."""
    from .payments import pix_ready
    if appt.customer_package_id or appt.subscription_id or not pix_ready(shop):
        return Decimal(0)
    return deposit_for(shop, appt.service)


def request_deposit(db: Session, shop: Shop, appt: Appointment, amount: Decimal) -> Payment:
    """Coloca o agendamento em "aguardando sinal" e gera o Pix do sinal."""
    from .payments import get_or_create_pix
    appt.status = ApptStatus.AWAITING_DEPOSIT
    appt.deposit_amount, appt.deposit_status = amount, DepositStatus.PENDING
    pay = get_or_create_pix(db, shop, appt, amount=amount, kind="deposit")
    return pay


def deadline(shop: Shop, appt: Appointment):
    return (appt.created_at or now_local()) + timedelta(minutes=shop.deposit_expire_minutes)


def deposit_messages(shop: Shop, appt: Appointment, pay: Payment) -> list[str]:
    until = deadline(shop, appt)
    intro = (f"📌 Para garantir o horário, falta só o *sinal* de *{money(pay.amount)}*.\n\n{appt_summary(appt)}\n\n"
             f"O horário fica reservado até {until:%H:%M}. Recebedor: {shop.pix_receiver_name}\n"
             f"Chave Pix: {shop.pix_key}\n\nCopie o código da próxima mensagem e cole no app do banco em "
             "*Pix > Copia e cola*. Depois de pagar, responda *paguei*. O sinal é descontado no dia do atendimento.")
    return [intro, pay.brcode]


def on_paid(appt: Appointment) -> bool:
    """Pix do sinal confirmado: o agendamento passa a valer. Devolve True se confirmou um agendamento."""
    appt.deposit_status = DepositStatus.PAID
    appt.payment_status = PayStatus.NONE  # o restante é pago no atendimento
    if appt.status == ApptStatus.AWAITING_DEPOSIT:
        appt.status = ApptStatus.SCHEDULED
        return True
    return False


def on_cancel(shop: Shop, appt: Appointment) -> None:
    if appt.deposit_status == DepositStatus.PAID:
        early = appt.start - now_local() >= timedelta(hours=shop.deposit_refund_hours)
        appt.deposit_status = DepositStatus.REFUND_DUE if early else DepositStatus.FORFEITED
    elif appt.deposit_status == DepositStatus.PENDING:
        appt.deposit_status = DepositStatus.NONE


def on_no_show(appt: Appointment) -> None:
    if appt.deposit_status == DepositStatus.PAID:
        appt.deposit_status = DepositStatus.FORFEITED


def expire_unpaid(db: Session, shop: Shop) -> list[Appointment]:
    """Libera os horários cujo sinal não foi confirmado a tempo (o cliente que avisou "paguei" ganha o prazo do Pix)."""
    from . import scheduling as sch
    from .whatsapp import send_text
    now = now_local()
    out = []
    for a in db.scalars(select(Appointment).where(Appointment.shop_id == shop.id,
                                                  Appointment.status == ApptStatus.AWAITING_DEPOSIT)):
        if deadline(shop, a) > now:
            continue
        if a.payment and a.payment.customer_reported_at and \
                a.payment.customer_reported_at + timedelta(hours=shop.pix_expire_hours) > now:
            continue  # disse que pagou: espera o dono conferir
        sch.cancel_appointment(db, a)
        send_text(db, shop, a.customer.phone,
                  f"⌛ O sinal do horário de {a.start:%d/%m às %H:%M} não foi confirmado a tempo e o horário foi "
                  "liberado. Para marcar de novo, mande *menu*.")
        out.append(a)
    return out
