"""Comanda: a conta do atendimento.

Regras:
- Itens e pagamentos são lançamentos imutáveis. Corrigir = estornar (lançamento negativo que aponta para o original);
  cada lançamento só pode ser estornado uma vez.
- Serviço: baixa os produtos que ele consome. Produto: baixa o estoque. Estorno devolve ao estoque.
- Serviço pago com saldo: sessão de pacote (base da comissão = valor proporcional da sessão) ou uso da assinatura
  (base = preço do serviço). O item fica com valor a pagar 0.
- Desconto: em R$ ou % do subtotal no momento do lançamento. Gorjeta: vai inteira para o profissional e não é
  faturamento do estabelecimento.
- Pagamento dividido: Pix, dinheiro, débito, crédito (e o sinal já pago pelo Pix entra sozinho ao abrir).
- Só fecha com saldo zero. Fechada, alimenta o financeiro e as comissões (app/services/revenue.py).
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, Barber, Comanda, ComandaItem, ComandaPayment, ComandaStatus, Customer, CustomerPackage,
    DepositStatus, ItemKind, PackagePlan, PayMethod, Product, ProductKind, Service, Shop, StockReason, Subscription,
    User,
)
from . import benefits, stock

CENT = Decimal("0.01")


class ComandaError(ValueError):
    pass


def q2(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def _check_open(c: Comanda) -> None:
    if c.status != ComandaStatus.OPEN:
        raise ComandaError("Essa comanda já foi fechada.")


def _owned(obj, shop: Shop, what: str):
    if obj is None or obj.shop_id != shop.id:
        raise ComandaError(f"{what} não encontrado.")
    return obj


# ---------------------------------------------------------------- abrir

def open_comanda(db: Session, shop: Shop, user: User | None, customer: Customer | None = None,
                 appointment: Appointment | None = None, uuid: str | None = None) -> Comanda:
    """Avulsa (customer opcional) ou do agendamento: já entra com o serviço agendado (e o sinal pago, se houver)."""
    if appointment is not None:
        _owned(appointment, shop, "Agendamento")
        existing = db.scalar(select(Comanda).where(Comanda.appointment_id == appointment.id))
        if existing:
            return existing
        if appointment.status in (ApptStatus.CANCELLED, ApptStatus.HELD):
            raise ComandaError("Esse agendamento foi cancelado.")
        customer = appointment.customer
    if customer is not None:
        _owned(customer, shop, "Cliente")
    c = Comanda(shop_id=shop.id, customer_id=customer.id if customer else None,
                appointment_id=appointment.id if appointment else None, opened_by_id=user.id if user else None)
    if uuid:
        c.uuid = uuid
    db.add(c)
    db.flush()
    if appointment is not None:
        a = appointment
        cover = "package" if a.customer_package_id else "subscription" if a.subscription_id else "none"
        add_service(db, shop, user, c, a.service, a.barber, unit_price=a.price, cover=cover,
                    _prepaid_appointment=a)
        if a.deposit_status == DepositStatus.PAID and a.deposit_amount:
            add_payment(db, shop, user, c, PayMethod.PIX, a.deposit_amount, from_deposit=True)
    return c


# ---------------------------------------------------------------- itens

def _item(db: Session, shop: Shop, user: User | None, c: Comanda, uuid: str | None = None, **kw) -> ComandaItem:
    # comanda=c (e não comanda_id) mantém c.items atualizado na sessão para os totais
    it = ComandaItem(shop_id=shop.id, comanda=c, created_by_id=user.id if user else None, **kw)
    if uuid:
        it.uuid = uuid
    db.add(it)
    db.flush()
    return it


def add_service(db: Session, shop: Shop, user: User | None, c: Comanda, service: Service, barber: Barber | None,
                quantity: int = 1, unit_price: Decimal | None = None, cover: str = "none",
                uuid: str | None = None, _prepaid_appointment: Appointment | None = None) -> ComandaItem:
    """cover: none | package | subscription. Com saldo, a sessão/uso é consumido aqui, a não ser que o agendamento
    já tenha consumido (agendou usando o pacote)."""
    _check_open(c)
    _owned(service, shop, "Serviço")
    if barber is not None:
        _owned(barber, shop, "Profissional")
    if quantity < 1:
        raise ComandaError("Quantidade inválida.")
    price = q2(service.price if unit_price is None else unit_price)
    kw = dict(kind=ItemKind.SERVICE, description=service.name, service_id=service.id,
              barber_id=barber.id if barber else None, quantity=quantity, unit_price=price)
    day = now_local().date()
    a = _prepaid_appointment
    if cover == "package":
        if quantity != 1:
            raise ComandaError("Com pacote, lance uma sessão por vez.")
        cp = db.get(CustomerPackage, a.customer_package_id) if a and a.customer_package_id else None
        if cp is None:
            if c.customer is None:
                raise ComandaError("Escolha o cliente da comanda para usar o pacote.")
            cp = benefits.usable_package(db, shop, c.customer, service, day)
            if cp is None:
                raise ComandaError("O cliente não tem pacote com saldo para esse serviço.")
        it = _item(db, shop, user, c, uuid, amount=Decimal(0), covered_by="package", customer_package_id=cp.id,
                   commission_base=cp.session_value, **kw)
        if not (a and a.customer_package_id):
            benefits.use_package(db, shop, cp, item=it, day=day)
    elif cover == "subscription":
        if quantity != 1:
            raise ComandaError("Com assinatura, lance um serviço por vez.")
        sub = db.get(Subscription, a.subscription_id) if a and a.subscription_id else None
        if sub is None:
            if c.customer is None:
                raise ComandaError("Escolha o cliente da comanda para usar a assinatura.")
            sub = benefits.usable_subscription(db, shop, c.customer, service, day)
            if sub is None:
                benefits.explain_no_subscription(db, shop, c.customer, service, day)
        it = _item(db, shop, user, c, uuid, amount=Decimal(0), covered_by="subscription", subscription_id=sub.id,
                   commission_base=price, **kw)
        if not (a and a.subscription_id):
            benefits.use_subscription(db, shop, sub, service, day, item=it)
    elif cover == "none":
        total = q2(price * quantity)
        it = _item(db, shop, user, c, uuid, amount=total, commission_base=total, **kw)
    else:
        raise ComandaError("Forma de cobertura inválida.")
    stock.consume_for_service(db, shop, service, quantity, it, user)
    return it


def add_product(db: Session, shop: Shop, user: User | None, c: Comanda, product: Product, quantity: int,
                barber: Barber | None = None, unit_price: Decimal | None = None,
                uuid: str | None = None) -> ComandaItem:
    _check_open(c)
    _owned(product, shop, "Produto")
    if product.kind == ProductKind.INTERNAL:
        raise ComandaError("Esse produto é só de uso interno.")
    if barber is not None:
        _owned(barber, shop, "Profissional")
    if quantity < 1:
        raise ComandaError("Quantidade inválida.")
    price = q2(product.price if unit_price is None else unit_price)
    total = q2(price * quantity)
    it = _item(db, shop, user, c, uuid, kind=ItemKind.PRODUCT, description=product.name, product_id=product.id,
               barber_id=barber.id if barber else None, quantity=quantity, unit_price=price, amount=total,
               commission_base=total)
    stock.move(db, shop, product, -Decimal(quantity), StockReason.SALE, user, it)
    return it


def add_package_sale(db: Session, shop: Shop, user: User | None, c: Comanda, plan: PackagePlan,
                     barber: Barber | None = None, uuid: str | None = None) -> ComandaItem:
    """Venda de pacote: o pacote passa a valer quando a comanda fecha."""
    _check_open(c)
    _owned(plan, shop, "Pacote")
    if c.customer is None:
        raise ComandaError("Escolha o cliente da comanda para vender o pacote.")
    return _item(db, shop, user, c, uuid, kind=ItemKind.PACKAGE, description=plan.name, package_plan_id=plan.id,
                 barber_id=barber.id if barber else None, quantity=1, unit_price=plan.price, amount=plan.price,
                 commission_base=Decimal(0))


def add_discount(db: Session, shop: Shop, user: User | None, c: Comanda, value: Decimal | None = None,
                 percent: Decimal | None = None, uuid: str | None = None) -> ComandaItem:
    _check_open(c)
    t = totals(c)
    if (value is None) == (percent is None):
        raise ComandaError("Informe o desconto em R$ ou em %.")
    if percent is not None:
        if not 0 < percent <= 100:
            raise ComandaError("Desconto em % precisa ser entre 0 e 100.")
        amount = q2(t.subtotal * percent / 100)
    else:
        amount = q2(value)
    if amount <= 0 or amount > t.subtotal + t.discount:  # discount é negativo
        raise ComandaError("O desconto não pode passar do valor da comanda.")
    return _item(db, shop, user, c, uuid, kind=ItemKind.DISCOUNT,
                 description=f"Desconto {percent:g}%" if percent is not None else "Desconto",
                 quantity=1, unit_price=-amount, amount=-amount, percent=percent, commission_base=Decimal(0))


def add_tip(db: Session, shop: Shop, user: User | None, c: Comanda, value: Decimal, barber: Barber,
            uuid: str | None = None) -> ComandaItem:
    _check_open(c)
    _owned(barber, shop, "Profissional")
    if value <= 0:
        raise ComandaError("Gorjeta inválida.")
    return _item(db, shop, user, c, uuid, kind=ItemKind.TIP, description=f"Gorjeta para {barber.name}",
                 barber_id=barber.id, quantity=1, unit_price=q2(value), amount=q2(value), commission_base=Decimal(0))


# ---------------------------------------------------------------- pagamentos

def add_payment(db: Session, shop: Shop, user: User | None, c: Comanda, method: str, amount: Decimal,
                from_deposit: bool = False, uuid: str | None = None) -> ComandaPayment:
    _check_open(c)
    if method not in PayMethod.ALL:
        raise ComandaError("Forma de pagamento inválida.")
    amount = q2(amount)
    if amount <= 0:
        raise ComandaError("Valor inválido.")
    p = ComandaPayment(shop_id=shop.id, comanda=c, method=method, amount=amount, from_deposit=from_deposit,
                       created_by_id=user.id if user else None)
    if uuid:
        p.uuid = uuid
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------- estorno

def _reversed_ids(rows) -> set[int]:
    return {r.reverses_id for r in rows if r.reverses_id}


def reverse_item(db: Session, shop: Shop, user: User | None, item: ComandaItem,
                 uuid: str | None = None) -> ComandaItem:
    """Lançamento negativo igual ao original. Devolve estoque, sessão de pacote e uso de assinatura."""
    c = item.comanda
    if item.reverses_id:
        raise ComandaError("Não dá para estornar um estorno.")
    if item.id in _reversed_ids(c.items):
        raise ComandaError("Esse lançamento já foi estornado.")
    if c.status == ComandaStatus.CANCELLED:
        raise ComandaError("Comanda cancelada.")
    rev = _item(db, shop, user, c, uuid, kind=item.kind, description=f"Estorno: {item.description}"[:120],
                service_id=item.service_id, product_id=item.product_id, package_plan_id=item.package_plan_id,
                barber_id=item.barber_id, quantity=-item.quantity, unit_price=item.unit_price, amount=-item.amount,
                percent=item.percent, covered_by=item.covered_by, customer_package_id=item.customer_package_id,
                subscription_id=item.subscription_id, commission_base=-item.commission_base, reverses_id=item.id)
    stock.undo_for_item(db, shop, item, rev, user)
    if item.covered_by == "package" and item.customer_package_id:
        benefits.return_package(db, shop, db.get(CustomerPackage, item.customer_package_id), item=rev)
    elif item.covered_by == "subscription" and item.subscription_id:
        benefits.return_subscription(db, shop, db.get(Subscription, item.subscription_id), item.service,
                                     item.created_at.date(), item=rev)
    if item.kind == ItemKind.PACKAGE and c.status == ComandaStatus.CLOSED:
        cp = db.scalar(select(CustomerPackage).where(CustomerPackage.comanda_id == c.id,
                                                     CustomerPackage.plan_id == item.package_plan_id,
                                                     CustomerPackage.status == "active"))
        if cp:
            cp.status = "cancelled"
    if item.kind == ItemKind.SERVICE and c.appointment and item.covered_by != "none":
        # o saldo usado no agendamento foi devolvido aqui: o agendamento não segura mais o pacote/assinatura
        c.appointment.customer_package_id = None
        c.appointment.subscription_id = None
    return rev


def reverse_payment(db: Session, shop: Shop, user: User | None, pay: ComandaPayment,
                    uuid: str | None = None) -> ComandaPayment:
    c = pay.comanda
    if pay.reverses_id:
        raise ComandaError("Não dá para estornar um estorno.")
    if pay.id in _reversed_ids(c.payments):
        raise ComandaError("Esse pagamento já foi estornado.")
    p = ComandaPayment(shop_id=shop.id, comanda=c, method=pay.method, amount=-pay.amount,
                       from_deposit=pay.from_deposit, reverses_id=pay.id, created_by_id=user.id if user else None)
    if uuid:
        p.uuid = uuid
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------- totais e fechamento

@dataclass
class Totals:
    subtotal: Decimal   # serviços, produtos e pacotes a pagar (sem gorjeta e desconto)
    discount: Decimal   # negativo
    tips: Decimal
    due: Decimal        # subtotal + desconto + gorjeta
    paid: Decimal
    balance: Decimal    # due - paid (0 = pode fechar)
    covered: Decimal    # valor pago com saldo de pacote/assinatura (informativo)


def totals(c: Comanda) -> Totals:
    sub = disc = tips = covered = Decimal(0)
    for it in c.items:
        if it.kind == ItemKind.DISCOUNT:
            disc += it.amount
        elif it.kind == ItemKind.TIP:
            tips += it.amount
        else:
            sub += it.amount
            if it.covered_by != "none":
                covered += it.commission_base
    paid = sum((p.amount for p in c.payments), Decimal(0))
    due = sub + disc + tips
    return Totals(q2(sub), q2(disc), q2(tips), q2(due), q2(paid), q2(due - paid), q2(covered))


def close(db: Session, shop: Shop, user: User | None, c: Comanda) -> Comanda:
    _check_open(c)
    if not c.items:
        raise ComandaError("A comanda está vazia.")
    t = totals(c)
    if t.balance != 0:
        what = f"Faltam {t.balance:.2f}" if t.balance > 0 else f"Pagamento passou {-t.balance:.2f}"
        raise ComandaError(f"{what.replace('.', ',')} para fechar a comanda.")
    now = now_local()
    c.status, c.closed_at, c.closed_by_id = ComandaStatus.CLOSED, now, user.id if user else None
    # Pacotes vendidos passam a valer
    reversed_ids = _reversed_ids(c.items)
    for it in c.items:
        if it.kind == ItemKind.PACKAGE and not it.reverses_id and it.id not in reversed_ids:
            plan = db.get(PackagePlan, it.package_plan_id)
            benefits.sell_package(db, shop, c.customer, plan, comanda_id=c.id)
    a = c.appointment
    if a is not None and a.status != ApptStatus.COMPLETED:
        from .scheduling import complete_appointment
        complete_appointment(a, main_method(c))
    elif a is not None and a.payment_method is None:
        a.payment_method = main_method(c)
    return c


def main_method(c: Comanda) -> str | None:
    by: dict[str, Decimal] = {}
    for p in c.payments:
        by[p.method] = by.get(p.method, Decimal(0)) + p.amount
    by = {k: v for k, v in by.items() if v > 0}
    return max(by, key=by.get) if by else None


def cancel(db: Session, shop: Shop, user: User | None, c: Comanda) -> None:
    """Cancela uma comanda aberta sem valor (vazia ou com tudo estornado)."""
    _check_open(c)
    t = totals(c)
    if t.due != 0 or t.paid != 0:
        raise ComandaError("Estorne os lançamentos antes de cancelar a comanda.")
    c.status, c.closed_at, c.closed_by_id = ComandaStatus.CANCELLED, now_local(), user.id if user else None
