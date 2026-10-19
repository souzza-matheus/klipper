"""Cobranças avulsas (mensalidade do clube de assinatura e pacote comprado pelo WhatsApp).

Hoje a cobrança é um Pix da chave do estabelecimento, enviado pelo WhatsApp e confirmado à mão (ManualPixGateway).
Um gateway com Pix automático entra implementando PaymentGateway e registrando em GATEWAYS: o resto (cobrança,
confirmação, status da assinatura) não muda.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Charge, Customer, CustomerPackage, PackagePlan, PayStatus, Shop, SubStatus, Subscription, SubscriptionPlan, User,
)
from . import benefits
from .fmt import money
from .payments import pix_ready
from .pix import build_brcode, new_txid

log = logging.getLogger("billing")


class PaymentGateway(Protocol):
    name: str

    def issue(self, shop: Shop, charge: Charge) -> None:
        """Preenche txid e brcode (ou o link/QR do gateway)."""

    def automatic(self) -> bool:
        """True quando o gateway confirma sozinho (webhook); False = o dono confirma no app."""


class ManualPixGateway:
    name = "manual_pix"

    def issue(self, shop: Shop, charge: Charge) -> None:
        charge.txid = new_txid()
        what = "Mensalidade" if charge.kind == "subscription" else "Pacote"
        charge.brcode = build_brcode(shop.pix_key, shop.pix_key_type, charge.amount, shop.pix_receiver_name,
                                     shop.pix_city, charge.txid, description=f"{what} {charge.id}")

    def automatic(self) -> bool:
        return False


GATEWAYS: dict[str, PaymentGateway] = {"manual_pix": ManualPixGateway()}


class BillingError(ValueError):
    pass


def create_charge(db: Session, shop: Shop, customer: Customer, kind: str, amount, due: date,
                  subscription: Subscription | None = None, package: CustomerPackage | None = None,
                  gateway: str = "manual_pix") -> Charge:
    ch = Charge(shop_id=shop.id, customer_id=customer.id, kind=kind, amount=amount, due_date=due, gateway=gateway,
                subscription_id=subscription.id if subscription else None,
                customer_package_id=package.id if package else None)
    db.add(ch)
    db.flush()
    if pix_ready(shop):
        GATEWAYS[gateway].issue(shop, ch)
    return ch


def charge_messages(shop: Shop, ch: Charge) -> list[str]:
    if not ch.brcode:
        return []
    if ch.kind == "subscription":
        what = f"Mensalidade do plano *{ch.subscription.plan.name}* (vencimento {ch.due_date:%d/%m})"
    else:
        cp = _package(ch) if ch.customer_package_id else None
        what = f"Pacote *{cp.name}*" if cp else "Pacote"
    intro = (f"💳 *Pagamento via Pix*\n\n{what}\nValor: *{money(ch.amount)}*\nRecebedor: {shop.pix_receiver_name}\n"
             f"Chave Pix: {shop.pix_key}\n\nCopie o código da próxima mensagem e cole no app do seu banco em "
             "*Pix > Copia e cola*. Depois de pagar, responda *paguei*.")
    return [intro, ch.brcode]


def _package(ch: Charge) -> CustomerPackage | None:
    from sqlalchemy.orm import object_session
    return object_session(ch).get(CustomerPackage, ch.customer_package_id)


def send_charge(db: Session, shop: Shop, ch: Charge) -> bool:
    from .whatsapp import send_text
    msgs = charge_messages(shop, ch)
    for m in msgs:
        send_text(db, shop, ch.customer.phone, m)
    if msgs:
        ch.sent_at = now_local()
    return bool(msgs)


def confirm_charge(db: Session, shop: Shop, ch: Charge, user: User | None = None) -> None:
    """Pix conferido no extrato. Pacote: passa a valer. Mensalidade: assinatura volta a ficar em dia."""
    if ch.status == PayStatus.PAID:
        return
    if ch.status != PayStatus.PENDING:
        raise BillingError("Essa cobrança não está mais pendente.")
    ch.status, ch.confirmed_at = PayStatus.PAID, now_local()
    ch.confirmed_by_id = user.id if user else None
    if ch.kind == "package":
        cp = db.get(CustomerPackage, ch.customer_package_id)
        plan = db.get(PackagePlan, cp.plan_id) if cp and cp.plan_id else None
        if cp and cp.status == "pending_payment":
            benefits.activate_package(cp, plan.validity_days if plan else 90)
    elif ch.subscription:
        db.flush()
        benefits.refresh_status(db, ch.subscription)


def confirm_and_notify(db: Session, shop: Shop, ch: Charge, user: User | None = None) -> None:
    """Confirma a cobrança e avisa o cliente (só na primeira vez)."""
    from .whatsapp import send_text
    was = ch.status
    confirm_charge(db, shop, ch, user)
    if was != PayStatus.PAID:
        what = "a mensalidade" if ch.kind == "subscription" else "o pacote"
        send_text(db, shop, ch.customer.phone, f"✅ Recebemos o seu Pix de {money(ch.amount)} referente a {what}. "
                                               "Obrigado!")


def cancel_charge(ch: Charge) -> None:
    if ch.status == PayStatus.PENDING:
        ch.status = "cancelled"
        if ch.kind == "package" and ch.customer_package_id:
            cp = _package(ch)
            if cp and cp.status == "pending_payment":
                cp.status = "cancelled"


# ---------------------------------------------------------------- pacote pelo WhatsApp

def buy_package(db: Session, shop: Shop, customer: Customer, plan: PackagePlan) -> Charge:
    """Pacote comprado pelo cliente no WhatsApp: fica aguardando o Pix; só vale depois da confirmação."""
    if not pix_ready(shop):
        raise BillingError("Este estabelecimento não recebe Pix pelo WhatsApp.")
    cp = benefits.sell_package(db, shop, customer, plan, pending=True)
    return create_charge(db, shop, customer, "package", plan.price, now_local().date(), package=cp)


# ---------------------------------------------------------------- clube de assinatura

def subscribe(db: Session, shop: Shop, customer: Customer, plan: SubscriptionPlan, start: date | None = None,
              charge_now: bool = True) -> Subscription:
    if plan.shop_id != shop.id or not plan.active:
        raise BillingError("Plano não encontrado.")
    open_sub = db.scalar(select(Subscription).where(
        Subscription.shop_id == shop.id, Subscription.customer_id == customer.id, Subscription.plan_id == plan.id,
        Subscription.status != SubStatus.CANCELLED))
    if open_sub:
        raise BillingError("Esse cliente já tem esse plano.")
    start = start or now_local().date()
    sub = Subscription(shop_id=shop.id, customer_id=customer.id, plan_id=plan.id, price=plan.price,
                       started_at=start, next_due_date=start, status=SubStatus.ACTIVE)
    db.add(sub)
    db.flush()
    if charge_now:
        bill_subscription(db, shop, sub, start)
    return sub


def bill_subscription(db: Session, shop: Shop, sub: Subscription, today: date) -> Charge | None:
    """Gera a cobrança do vencimento (uma por vencimento) e manda o Pix. Avança next_due_date em um mês."""
    if sub.status == SubStatus.CANCELLED or sub.next_due_date > today:
        return None
    due = sub.next_due_date
    exists = db.scalar(select(func.count()).select_from(Charge).where(
        Charge.subscription_id == sub.id, Charge.due_date == due))
    sub.next_due_date = benefits.add_months(sub.started_at, _months_between(sub.started_at, due) + 1)
    if exists:
        return None
    ch = create_charge(db, shop, sub.customer, "subscription", sub.price, due, subscription=sub)
    send_charge(db, shop, ch)
    return ch


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def cancel_subscription(db: Session, sub: Subscription) -> None:
    sub.status, sub.cancelled_at = SubStatus.CANCELLED, now_local()
    for ch in db.scalars(select(Charge).where(Charge.subscription_id == sub.id, Charge.status == PayStatus.PENDING)):
        cancel_charge(ch)


def run_subscriptions(db: Session, shop: Shop, today: date | None = None) -> dict:
    """Rotina diária: cobra os vencimentos do dia e atualiza o status (em dia / atrasada)."""
    today = today or now_local().date()
    billed = late = 0
    for sub in db.scalars(select(Subscription).where(Subscription.shop_id == shop.id,
                                                     Subscription.status != SubStatus.CANCELLED)):
        while sub.next_due_date <= today:  # recupera vencimentos perdidos (servidor parado)
            if bill_subscription(db, shop, sub, today):
                billed += 1
        db.flush()
        if benefits.refresh_status(db, sub, today) == SubStatus.LATE:
            late += 1
    return {"billed": billed, "late": late}


def subscriptions_report(db: Session, shop: Shop, today: date | None = None) -> dict:
    today = today or now_local().date()
    rows, mrr = [], Decimal(0)
    counts = {s: 0 for s in SubStatus.ALL}
    for sub in db.scalars(select(Subscription).where(Subscription.shop_id == shop.id)
                          .order_by(Subscription.status, Subscription.next_due_date)):
        benefits.refresh_status(db, sub, today)
        counts[sub.status] += 1
        if sub.status != SubStatus.CANCELLED:
            mrr += sub.price
        rows.append({"id": sub.id, "uuid": sub.uuid, "customer_id": sub.customer_id,
                     "customer_name": sub.customer.name or sub.customer.phone, "plan_id": sub.plan_id,
                     "plan_name": sub.plan.name, "price": str(sub.price), "status": sub.status,
                     "started_at": sub.started_at, "next_due_date": sub.next_due_date,
                     "days_late": benefits.days_late(db, sub, today),
                     "benefits_blocked": benefits.benefits_blocked(db, sub, today)})
    return {"active": counts[SubStatus.ACTIVE], "late": counts[SubStatus.LATE],
            "cancelled": counts[SubStatus.CANCELLED], "mrr": str(mrr), "subscribers": rows}
