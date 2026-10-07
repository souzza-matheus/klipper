"""Linhas de faturamento e de comissão do período, juntando as fontes:

- atendimento concluído SEM comanda (como antes das comandas): valor do atendimento;
- comanda fechada: cada item (serviço, produto, pacote vendido) com o desconto rateado e o valor repartido entre as
  formas de pagamento; estornos feitos depois do fechamento entram na data do estorno;
- cobranças confirmadas (mensalidade do clube, pacote comprado pelo WhatsApp);
- sinal retido (cancelamento fora do prazo ou falta).

Pago com saldo (pacote/assinatura) não é faturamento de novo (o pacote/mensalidade já entrou quando foi pago), mas
gera comissão: sessão de pacote pelo valor proporcional, assinatura pelo preço do serviço. Gorjeta não é
faturamento: vai para o profissional.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    Appointment, ApptStatus, Charge, Comanda, ComandaItem, ComandaStatus, CustomerPackage, DepositStatus, ItemKind,
    PayStatus, Product, Shop,
)

CENT = Decimal("0.01")


def q2(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Line:
    start: datetime          # quando entra no período
    price: Decimal           # valor faturado
    barber_id: int | None
    service_id: int | None
    payment_method: str | None
    visits: int = 0          # conta como atendimento (1 por agendamento/comanda com serviço)
    kind: str = "service"    # service | product | package | subscription | deposit
    label: str = ""
    customer_name: str = ""


@dataclass
class CommissionLine:
    day: date
    barber_id: int
    service_id: int | None
    base: Decimal


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return datetime.combine(date_from, datetime.min.time()), datetime.combine(date_to + timedelta(days=1),
                                                                              datetime.min.time())


def _with_comanda_ids(db: Session, shop: Shop) -> set[int]:
    """Agendamentos cuja conta está numa comanda (aberta ou fechada): o valor vem da comanda, não do agendamento."""
    return set(db.scalars(select(Comanda.appointment_id).where(
        Comanda.shop_id == shop.id, Comanda.appointment_id.is_not(None),
        Comanda.status != ComandaStatus.CANCELLED)))


def _legacy_appointments(db: Session, shop: Shop, start: datetime, end: datetime) -> list[Appointment]:
    skip = _with_comanda_ids(db, shop)
    appts = db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.status == ApptStatus.COMPLETED,
        Appointment.start >= start, Appointment.start < end).order_by(Appointment.start)).all()
    return [a for a in appts if a.id not in skip]


def _comandas(db: Session, shop: Shop, start: datetime, end: datetime) -> list[Comanda]:
    late = select(ComandaItem.comanda_id).where(ComandaItem.shop_id == shop.id, ComandaItem.created_at >= start,
                                                ComandaItem.created_at < end)
    return list(db.scalars(select(Comanda).options(selectinload(Comanda.items), selectinload(Comanda.payments))
                           .where(Comanda.shop_id == shop.id, Comanda.status == ComandaStatus.CLOSED,
                                  Comanda.closed_at < end,
                                  or_(Comanda.closed_at >= start, Comanda.id.in_(late)))
                           .order_by(Comanda.closed_at)).all())


def _when(item: ComandaItem, c: Comanda) -> datetime:
    return max(item.created_at, c.closed_at)


def _factor(c: Comanda) -> Decimal:
    """Quanto de cada item sobra depois do desconto (rateio proporcional)."""
    sub = sum((i.amount for i in c.items if i.kind not in (ItemKind.DISCOUNT, ItemKind.TIP)), Decimal(0))
    disc = sum((i.amount for i in c.items if i.kind == ItemKind.DISCOUNT), Decimal(0))
    return (sub + disc) / sub if sub else Decimal(0)


def _method_shares(c: Comanda) -> list[tuple[str | None, Decimal]]:
    by: dict[str, Decimal] = defaultdict(Decimal)
    for p in c.payments:
        by[p.method] += p.amount
    total = sum((v for v in by.values() if v > 0), Decimal(0))
    if not total:
        return [(None, Decimal(1))]
    return [(m, v / total) for m, v in by.items() if v > 0]


def lines(db: Session, shop: Shop, date_from: date, date_to: date) -> list[Line]:
    start, end = _bounds(date_from, date_to)
    out: list[Line] = []
    for a in _legacy_appointments(db, shop, start, end):
        paid_with_balance = a.customer_package_id or a.subscription_id
        out.append(Line(a.start, Decimal(0) if paid_with_balance else a.price, a.barber_id, a.service_id,
                        a.payment_method, 1, "service", a.service.name, a.customer.name))

    for c in _comandas(db, shop, start, end):
        factor, shares = _factor(c), _method_shares(c)
        counted = False
        for it in c.items:
            when = _when(it, c)
            if not (start <= when < end) or it.kind in (ItemKind.DISCOUNT, ItemKind.TIP):
                continue
            net = it.amount * factor
            visit = 0
            if it.kind == ItemKind.SERVICE and not it.reverses_id and not counted:
                visit, counted = 1, True
            kind = {ItemKind.SERVICE: "service", ItemKind.PRODUCT: "product", ItemKind.PACKAGE: "package"}[it.kind]
            first = True
            for method, share in shares:
                out.append(Line(when, q2(net * share), it.barber_id, it.service_id, method, visit if first else 0,
                                kind, it.description, c.customer.name if c.customer else ""))
                first = False

    for ch in db.scalars(select(Charge).where(Charge.shop_id == shop.id, Charge.status == PayStatus.PAID,
                                              Charge.confirmed_at >= start, Charge.confirmed_at < end)):
        label = "Mensalidade" if ch.kind == "subscription" else "Pacote"
        if ch.kind == "package" and ch.customer_package_id:
            cp = db.get(CustomerPackage, ch.customer_package_id)
            label = f"Pacote {cp.name}" if cp else label
        out.append(Line(ch.confirmed_at, ch.amount, None, None, "pix", 0, ch.kind, label, ch.customer.name))

    for a in db.scalars(select(Appointment).where(
            Appointment.shop_id == shop.id, Appointment.deposit_status == DepositStatus.FORFEITED,
            or_(Appointment.cancelled_at.between(start, end), Appointment.cancelled_at.is_(None)))):
        when = a.cancelled_at or a.start
        if start <= when < end and a.deposit_amount:
            out.append(Line(when, a.deposit_amount, a.barber_id, a.service_id, "pix", 0, "deposit",
                            "Sinal retido", a.customer.name))
    out.sort(key=lambda x: x.start)
    return out


def commission_lines(db: Session, shop: Shop, date_from: date, date_to: date) -> list[CommissionLine]:
    """Base da comissão de serviço por profissional (o repasse incide sobre isso)."""
    start, end = _bounds(date_from, date_to)
    out: list[CommissionLine] = []
    for a in _legacy_appointments(db, shop, start, end):
        base = a.price
        if a.customer_package_id:
            cp = db.get(CustomerPackage, a.customer_package_id)
            base = cp.session_value if cp else base
        out.append(CommissionLine(a.start.date(), a.barber_id, a.service_id, base))
    for c in _comandas(db, shop, start, end):
        factor = _factor(c)
        for it in c.items:
            when = _when(it, c)
            if it.kind != ItemKind.SERVICE or not it.barber_id or not (start <= when < end):
                continue
            base = it.commission_base if it.covered_by != "none" else it.commission_base * factor
            out.append(CommissionLine(when.date(), it.barber_id, it.service_id, q2(base)))
    return out


def extras_by_barber(db: Session, shop: Shop, date_from: date, date_to: date) -> dict[int, dict[str, Decimal]]:
    """Gorjetas e comissão de produto que cada profissional recebe no período."""
    start, end = _bounds(date_from, date_to)
    out: dict[int, dict[str, Decimal]] = defaultdict(lambda: {"tips": Decimal(0), "product_commission": Decimal(0)})
    products = {p.id: p for p in db.scalars(select(Product).where(Product.shop_id == shop.id))}
    for c in _comandas(db, shop, start, end):
        factor = _factor(c)
        for it in c.items:
            if not it.barber_id or not (start <= _when(it, c) < end):
                continue
            if it.kind == ItemKind.TIP:
                out[it.barber_id]["tips"] += it.amount
            elif it.kind == ItemKind.PRODUCT:
                p = products.get(it.product_id)
                if p and p.commission_pct:
                    out[it.barber_id]["product_commission"] += it.amount * factor * p.commission_pct / 100
    return {k: {n: q2(v) for n, v in d.items()} for k, d in out.items()}
