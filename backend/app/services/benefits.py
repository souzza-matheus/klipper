"""Saldo do cliente: pacotes (sessões pré-pagas com validade) e clube de assinatura (serviços incluídos com limite por
período). Usado no agendamento (app, bot e IA) e na comanda."""
import calendar
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Appointment, Charge, Customer, CustomerPackage, PackagePlan, PackageUse, PayStatus, Service, Shop,
    SubStatus, Subscription, SubscriptionPlanItem, SubscriptionUse,
)

CENT = Decimal("0.01")


class BenefitError(ValueError):
    pass


# ---------------------------------------------------------------- pacotes

def package_used(db: Session, cp: CustomerPackage) -> int:
    return -int(db.scalar(select(func.coalesce(func.sum(PackageUse.delta), 0))
                          .where(PackageUse.customer_package_id == cp.id)) or 0)


def package_balance(db: Session, cp: CustomerPackage) -> int:
    return cp.sessions - package_used(db, cp)


def package_expired(cp: CustomerPackage, day: date | None = None) -> bool:
    return cp.expires_at is not None and (day or now_local().date()) > cp.expires_at


def package_state(db: Session, cp: CustomerPackage, day: date | None = None) -> str:
    """ativo | vencido | esgotado | aguardando_pagamento | cancelado"""
    if cp.status == "pending_payment":
        return "aguardando_pagamento"
    if cp.status == "cancelled":
        return "cancelado"
    if package_expired(cp, day):
        return "vencido"
    return "ativo" if package_balance(db, cp) > 0 else "esgotado"


def usable_package(db: Session, shop: Shop, customer: Customer, service: Service,
                   day: date | None = None) -> CustomerPackage | None:
    """Pacote ativo, dentro da validade e com saldo para o serviço; o que vence primeiro é usado primeiro."""
    day = day or now_local().date()
    cps = db.scalars(select(CustomerPackage).where(
        CustomerPackage.shop_id == shop.id, CustomerPackage.customer_id == customer.id,
        CustomerPackage.service_id == service.id, CustomerPackage.status == "active",
    ).order_by(CustomerPackage.expires_at.is_(None), CustomerPackage.expires_at, CustomerPackage.id)).all()
    for cp in cps:
        if not package_expired(cp, day) and package_balance(db, cp) > 0:
            return cp
    return None


def use_package(db: Session, shop: Shop, cp: CustomerPackage, appointment: Appointment | None = None,
                item=None, day: date | None = None) -> PackageUse:
    if cp.status != "active":
        raise BenefitError("Esse pacote não está ativo.")
    if package_expired(cp, day):
        raise BenefitError(f"Esse pacote venceu em {cp.expires_at:%d/%m/%Y}.")
    if package_balance(db, cp) <= 0:
        raise BenefitError("Esse pacote não tem mais sessões.")
    u = PackageUse(shop_id=shop.id, customer_package_id=cp.id, delta=-1,
                   appointment_id=appointment.id if appointment else None, comanda_item_id=item.id if item else None)
    db.add(u)
    db.flush()
    return u


def return_package(db: Session, shop: Shop, cp: CustomerPackage, appointment: Appointment | None = None,
                   item=None) -> PackageUse:
    u = PackageUse(shop_id=shop.id, customer_package_id=cp.id, delta=1,
                   appointment_id=appointment.id if appointment else None, comanda_item_id=item.id if item else None)
    db.add(u)
    db.flush()
    return u


def sell_package(db: Session, shop: Shop, customer: Customer, plan: PackagePlan, *, pending: bool = False,
                 comanda_id: int | None = None) -> CustomerPackage:
    if plan.shop_id != shop.id or not plan.active:
        raise BenefitError("Pacote não encontrado.")
    value = (plan.price / plan.sessions).quantize(CENT, rounding=ROUND_HALF_UP)
    cp = CustomerPackage(shop_id=shop.id, customer_id=customer.id, plan_id=plan.id, service_id=plan.service_id,
                         name=plan.name, sessions=plan.sessions, price=plan.price, session_value=value,
                         status="pending_payment" if pending else "active", comanda_id=comanda_id)
    if not pending:
        activate_package(cp, plan.validity_days)
    db.add(cp)
    db.flush()
    return cp


def activate_package(cp: CustomerPackage, validity_days: int) -> None:
    now = now_local()
    cp.status, cp.purchased_at = "active", now
    cp.expires_at = now.date() + timedelta(days=validity_days) if validity_days else None


# ---------------------------------------------------------------- assinatura

def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def period_start(sub: Subscription, day: date) -> date:
    """Início do ciclo que contém o dia: o "aniversário" mensal da data de início."""
    months = (day.year - sub.started_at.year) * 12 + day.month - sub.started_at.month
    start = add_months(sub.started_at, months)
    if start > day:
        start = add_months(sub.started_at, months - 1)
    return max(start, sub.started_at)


def oldest_open_charge(db: Session, sub: Subscription) -> Charge | None:
    return db.scalar(select(Charge).where(Charge.subscription_id == sub.id, Charge.status == PayStatus.PENDING)
                     .order_by(Charge.due_date))


def days_late(db: Session, sub: Subscription, day: date | None = None) -> int:
    ch = oldest_open_charge(db, sub)
    day = day or now_local().date()
    return max(0, (day - ch.due_date).days) if ch else 0


def refresh_status(db: Session, sub: Subscription, day: date | None = None) -> str:
    if sub.status != SubStatus.CANCELLED:
        sub.status = SubStatus.LATE if days_late(db, sub, day) > 0 else SubStatus.ACTIVE
    return sub.status


def benefits_blocked(db: Session, sub: Subscription, day: date | None = None) -> bool:
    if sub.status == SubStatus.CANCELLED:
        return True
    return days_late(db, sub, day) > sub.plan.block_after_days


def plan_item(sub: Subscription, service: Service) -> SubscriptionPlanItem | None:
    return next((i for i in sub.plan.items if i.service_id == service.id), None)


def sub_used(db: Session, sub: Subscription, service: Service, day: date) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(SubscriptionUse.delta), 0)).where(
        SubscriptionUse.subscription_id == sub.id, SubscriptionUse.service_id == service.id,
        SubscriptionUse.period_start == period_start(sub, day))) or 0)


def sub_remaining(db: Session, sub: Subscription, service: Service, day: date) -> int | None:
    """Usos que ainda cabem no período (None = sem limite). Levanta BenefitError se o serviço não está no plano."""
    item = plan_item(sub, service)
    if item is None:
        raise BenefitError(f"{service.name} não faz parte do plano {sub.plan.name}.")
    if item.limit_per_period is None:
        return None
    return max(0, item.limit_per_period - sub_used(db, sub, service, day))


def check_subscription(db: Session, sub: Subscription, service: Service, day: date) -> None:
    if sub.status == SubStatus.CANCELLED:
        raise BenefitError("Essa assinatura foi cancelada.")
    if day < sub.started_at:
        raise BenefitError("A assinatura ainda não começou.")
    if benefits_blocked(db, sub, day):
        raise BenefitError("A assinatura está com a mensalidade atrasada: benefícios bloqueados até o pagamento.")
    remaining = sub_remaining(db, sub, service, day)
    if remaining is not None and remaining <= 0:
        raise BenefitError(f"O limite de {service.name} do plano neste período já foi usado.")


def usable_subscription(db: Session, shop: Shop, customer: Customer, service: Service,
                        day: date | None = None) -> Subscription | None:
    day = day or now_local().date()
    for sub in db.scalars(select(Subscription).where(
            Subscription.shop_id == shop.id, Subscription.customer_id == customer.id,
            Subscription.status != SubStatus.CANCELLED)):
        try:
            check_subscription(db, sub, service, day)
            return sub
        except BenefitError:
            continue
    return None


def explain_no_subscription(db: Session, shop: Shop, customer: Customer, service: Service, day: date) -> None:
    """Levanta BenefitError com o motivo de a assinatura não cobrir o serviço (limite, atraso, fora do plano)."""
    subs = db.scalars(select(Subscription).where(Subscription.shop_id == shop.id,
                                                 Subscription.customer_id == customer.id,
                                                 Subscription.status != SubStatus.CANCELLED)).all()
    for sub in subs:
        refresh_status(db, sub, day)
        check_subscription(db, sub, service, day)  # a primeira que falhar explica
    raise BenefitError("O cliente não tem assinatura ativa.")


def use_subscription(db: Session, shop: Shop, sub: Subscription, service: Service, day: date,
                     appointment: Appointment | None = None, item=None) -> SubscriptionUse:
    check_subscription(db, sub, service, day)
    u = SubscriptionUse(shop_id=shop.id, subscription_id=sub.id, service_id=service.id,
                        period_start=period_start(sub, day), delta=1,
                        appointment_id=appointment.id if appointment else None,
                        comanda_item_id=item.id if item else None)
    db.add(u)
    db.flush()
    return u


def return_subscription(db: Session, shop: Shop, sub: Subscription, service: Service, day: date,
                        appointment: Appointment | None = None, item=None) -> SubscriptionUse:
    u = SubscriptionUse(shop_id=shop.id, subscription_id=sub.id, service_id=service.id,
                        period_start=period_start(sub, day), delta=-1,
                        appointment_id=appointment.id if appointment else None,
                        comanda_item_id=item.id if item else None)
    db.add(u)
    db.flush()
    return u


# ---------------------------------------------------------------- no agendamento

def apply_on_booking(db: Session, shop: Shop, appt: Appointment) -> str:
    """Se o cliente tem assinatura ou pacote que cobre o serviço, usa (assinatura primeiro). Devolve o texto para o
    cliente ("" = pagamento normal)."""
    day = appt.start.date()
    sub = usable_subscription(db, shop, appt.customer, appt.service, day)
    if sub:
        use_subscription(db, shop, sub, appt.service, day, appointment=appt)
        appt.subscription_id = sub.id
        return f"Incluído na sua assinatura *{sub.plan.name}*. ✅"
    cp = usable_package(db, shop, appt.customer, appt.service, day)
    if cp:
        use_package(db, shop, cp, appointment=appt, day=day)
        appt.customer_package_id = cp.id
        left = package_balance(db, cp)
        return f"Usei 1 sessão do seu pacote *{cp.name}* (restam {left})."
    return ""


def release_on_cancel(db: Session, shop: Shop, appt: Appointment) -> None:
    """Cancelamento devolve a sessão do pacote ou o uso da assinatura. Falta (no-show) não devolve."""
    if appt.customer_package_id:
        cp = db.get(CustomerPackage, appt.customer_package_id)
        if cp:
            return_package(db, shop, cp, appointment=appt)
        appt.customer_package_id = None
    if appt.subscription_id:
        sub = db.get(Subscription, appt.subscription_id)
        if sub:
            return_subscription(db, shop, sub, appt.service, appt.start.date(), appointment=appt)
        appt.subscription_id = None


# ---------------------------------------------------------------- resumo do cliente

def customer_balance(db: Session, shop: Shop, customer: Customer, day: date | None = None) -> dict:
    day = day or now_local().date()
    packages = []
    for cp in db.scalars(select(CustomerPackage).where(
            CustomerPackage.shop_id == shop.id, CustomerPackage.customer_id == customer.id,
            CustomerPackage.status != "cancelled").order_by(CustomerPackage.created_at.desc())):
        packages.append({"id": cp.id, "uuid": cp.uuid, "name": cp.name, "service_id": cp.service_id,
                         "service_name": cp.service.name, "sessions": cp.sessions,
                         "balance": package_balance(db, cp), "expires_at": cp.expires_at,
                         "state": package_state(db, cp, day), "session_value": str(cp.session_value)})
    subs = []
    for sub in db.scalars(select(Subscription).where(
            Subscription.shop_id == shop.id, Subscription.customer_id == customer.id)
            .order_by(Subscription.created_at.desc())):
        refresh_status(db, sub, day)
        items = []
        for it in sub.plan.items:
            used = sub_used(db, sub, it.service, day)
            items.append({"service_id": it.service_id, "service_name": it.service.name,
                          "limit": it.limit_per_period, "used": used,
                          "remaining": None if it.limit_per_period is None else max(0, it.limit_per_period - used)})
        subs.append({"id": sub.id, "uuid": sub.uuid, "plan_name": sub.plan.name, "status": sub.status,
                     "price": str(sub.price), "next_due_date": sub.next_due_date, "days_late": days_late(db, sub, day),
                     "benefits_blocked": benefits_blocked(db, sub, day),
                     "period_start": period_start(sub, day), "items": items})
    return {"packages": packages, "subscriptions": subs}
