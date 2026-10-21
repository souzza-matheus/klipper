"""Dados de exemplo do CRM (fase 1): equipe com os três papéis, produtos com estoque, pacote, clube de assinatura com
assinantes, comandas fechadas e lista de espera. Chamado por app.seed_mock e app.seed_niches.

Os logins de exemplo usam a senha demo123 e só existem na demo (dados fictícios)."""
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .auth import hash_password
from .models import (
    Appointment, ApptStatus, Barber, Charge, Comanda, ComandaItem, ComandaPayment, Customer, CustomerPackage,
    Membership, PackagePlan, PackageUse, PayMethod, PayStatus, Product, ProductKind, Role, Service, ServiceProduct,
    Shop, StockMovement, StockReason, SubStatus, Subscription, SubscriptionPlan, SubscriptionPlanItem, SubscriptionUse,
    SyncOperation, User, WaitlistEntry,
)
from .services import billing, comandas as cs, stock

# (nome, tipo, unidade, custo, preço, mínimo, comissão %)
PRODUCTS = {
    "barbershop": [("Pomada modeladora", ProductKind.SALE, "un", "18.00", "45.00", "5", "10"),
                   ("Óleo para barba", ProductKind.SALE, "un", "15.00", "39.90", "4", "10"),
                   ("Shampoo 1 L", ProductKind.INTERNAL, "ml", "0.03", "0", "1500", None),
                   ("Lâmina descartável", ProductKind.INTERNAL, "un", "0.60", "0", "50", None)],
    "beauty": [("Máscara capilar", ProductKind.SALE, "un", "25.00", "69.90", "4", "10"),
               ("Esmalte", ProductKind.BOTH, "un", "4.00", "12.00", "10", None),
               ("Shampoo 1 L", ProductKind.INTERNAL, "ml", "0.03", "0", "1500", None)],
    "petshop": [("Shampoo pet 5 L", ProductKind.INTERNAL, "ml", "0.02", "0", "3000", None),
                ("Petisco natural", ProductKind.SALE, "un", "8.00", "19.90", "10", None)],
    "clinic": [("Kit higiene bucal", ProductKind.SALE, "un", "12.00", "29.90", "5", None),
               ("Luva descartável", ProductKind.INTERNAL, "par", "0.40", "0", "100", None)],
    "fitness": [("Garrafa squeeze", ProductKind.SALE, "un", "9.00", "24.90", "5", None),
                ("Toalha descartável", ProductKind.INTERNAL, "un", "0.50", "0", "50", None)],
}

TEAM_PASSWORD = "demo123"


def ensure_team(db: Session, shop: Shop, tag: str = "") -> list[User]:
    """Um login de recepção e um de profissional (ligado ao primeiro profissional ativo): recepcao<tag>@demo.com e
    profissional<tag>@demo.com."""
    barber = db.scalar(select(Barber).where(Barber.shop_id == shop.id, Barber.active.is_(True)).order_by(Barber.id))
    out = []
    for role, name, local in ((Role.RECEPTION, "Recepção Demo", "recepcao"),
                              (Role.PROFESSIONAL, barber.name if barber else "Profissional", "profissional")):
        email = f"{local}{tag}@demo.com"
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(shop_id=shop.id, name=name, email=email, password_hash=hash_password(TEAM_PASSWORD), role=role,
                        barber_id=barber.id if role == Role.PROFESSIONAL and barber else None)
            db.add(user)
        out.append(user)
    db.commit()
    return out


def reset_crm(db: Session, shop: Shop) -> None:
    """Apaga o movimento do CRM (comandas, saldos, cobranças, lista de espera). Catálogo (produtos e planos) fica."""
    sid = shop.id
    db.execute(delete(PackageUse).where(PackageUse.shop_id == sid))
    db.execute(delete(SubscriptionUse).where(SubscriptionUse.shop_id == sid))
    db.execute(delete(StockMovement).where(StockMovement.shop_id == sid, StockMovement.comanda_item_id.is_not(None)))
    db.execute(delete(ComandaPayment).where(ComandaPayment.shop_id == sid))
    db.execute(update(ComandaItem).where(ComandaItem.shop_id == sid).values(reverses_id=None))
    db.execute(delete(ComandaItem).where(ComandaItem.shop_id == sid))
    db.execute(update(Appointment).where(Appointment.shop_id == sid).values(customer_package_id=None,
                                                                            subscription_id=None))
    db.execute(delete(Charge).where(Charge.shop_id == sid))
    db.execute(delete(CustomerPackage).where(CustomerPackage.shop_id == sid))
    db.execute(delete(Comanda).where(Comanda.shop_id == sid))
    db.execute(delete(WaitlistEntry).where(WaitlistEntry.shop_id == sid))
    db.execute(delete(Subscription).where(Subscription.shop_id == sid))
    db.execute(delete(SyncOperation).where(SyncOperation.shop_id == sid))
    db.commit()


def _catalog(db: Session, shop: Shop, services: list[Service]) -> tuple[list[Product], PackagePlan, SubscriptionPlan]:
    products = list(db.scalars(select(Product).where(Product.shop_id == shop.id).order_by(Product.id)))
    if not products:
        for name, kind, unit, cost, price, minimum, pct in PRODUCTS.get(shop.niche, PRODUCTS["barbershop"]):
            p = Product(shop_id=shop.id, name=name, kind=kind, unit=unit, cost=Decimal(cost), price=Decimal(price),
                        min_stock=Decimal(minimum), commission_pct=Decimal(pct) if pct else None)
            db.add(p)
            products.append(p)
        db.flush()
        for p in products:  # estoque inicial: uma compra; o primeiro produto de venda fica abaixo do mínimo
            qty = p.min_stock * 4 if p.kind == ProductKind.INTERNAL else Decimal(12)
            if p is products[0]:
                qty = max(Decimal(1), p.min_stock - 2)
            stock.move(db, shop, p, qty, StockReason.PURCHASE, unit_cost=p.cost, notes="Estoque inicial")
        internal = [p for p in products if p.kind == ProductKind.INTERNAL]
        if internal and services:  # o primeiro serviço consome um pouco do primeiro produto de uso interno
            db.add(ServiceProduct(service_id=services[0].id, product_id=internal[0].id,
                                  quantity=Decimal(20) if internal[0].unit == "ml" else Decimal(1)))
    main = services[0]
    plan = db.scalar(select(PackagePlan).where(PackagePlan.shop_id == shop.id))
    if plan is None:
        price = (main.price * 4 * Decimal("0.875")).quantize(Decimal("1"))
        plan = PackagePlan(shop_id=shop.id, name=f"4x {main.name}", service_id=main.id, sessions=4, price=price,
                           validity_days=90)
        db.add(plan)
    club = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.shop_id == shop.id))
    if club is None:
        club = SubscriptionPlan(shop_id=shop.id, name="Clube Mensal", price=(main.price * 2).quantize(Decimal("1")),
                                block_after_days=5)
        club.items = [SubscriptionPlanItem(service_id=main.id, limit_per_period=None)]
        if len(services) > 1:
            club.items.append(SubscriptionPlanItem(service_id=services[1].id, limit_per_period=2))
        db.add(club)
    db.flush()
    return products, plan, club


def seed_crm(db: Session, shop: Shop, now: datetime, tag: str = "", rng: random.Random | None = None) -> dict:
    rng = rng or random.Random(7)
    ensure_team(db, shop, tag)
    services = list(db.scalars(select(Service).where(Service.shop_id == shop.id, Service.active.is_(True))
                               .order_by(Service.sort_order, Service.id)))
    if not services:
        return {}
    products, plan, club = _catalog(db, shop, services)
    owner = db.scalar(select(User).join(Membership).where(Membership.shop_id == shop.id,
                                                          Membership.role == Role.OWNER))
    customers = list(db.scalars(select(Customer).where(Customer.shop_id == shop.id, Customer.access_status == "normal")
                                .order_by(Customer.id)))
    stats = {"comandas": 0, "packages": 0, "subscribers": 0}

    # Clube de assinatura: 3 assinantes; o último começou há 40 dias e não pagou a mensalidade deste mês (atrasada)
    for i, c in enumerate(customers[:3]):
        if db.scalar(select(Subscription.id).where(Subscription.customer_id == c.id)):
            continue
        start = now.date() - timedelta(days=40 if i == 2 else 10 + i * 5)
        sub = billing.subscribe(db, shop, c, club, start, charge_now=False)
        billing.run_subscriptions(db, shop, now.date())
        for ch in db.scalars(select(Charge).where(Charge.subscription_id == sub.id).order_by(Charge.due_date)):
            if i < 2 or ch.due_date == start:
                billing.confirm_charge(db, shop, ch, owner)
        stats["subscribers"] += 1

    # Comandas fechadas dos últimos atendimentos concluídos (com produto, gorjeta, desconto e pagamento dividido)
    sale = [p for p in products if p.kind != ProductKind.INTERNAL]
    done = list(db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.status == ApptStatus.COMPLETED,
        Appointment.start >= now - timedelta(days=7), Appointment.start < now).order_by(Appointment.start.desc())))
    with_comanda = set(db.scalars(select(Comanda.appointment_id).where(Comanda.shop_id == shop.id)))
    for a in [x for x in done if x.id not in with_comanda][:12]:
        c = cs.open_comanda(db, shop, owner, appointment=a)
        c.opened_at = a.end
        if sale and rng.random() < 0.4:
            cs.add_product(db, shop, owner, c, rng.choice(sale), 1, a.barber)
        if rng.random() < 0.2:
            cs.add_discount(db, shop, owner, c, percent=Decimal(10))
        if rng.random() < 0.3:
            cs.add_tip(db, shop, owner, c, Decimal(rng.choice([5, 10])), a.barber)
        due = cs.totals(c).balance
        if due > 0:
            if due > 30 and rng.random() < 0.4:
                first = (due / 2).quantize(Decimal("0.01"))
                cs.add_payment(db, shop, owner, c, PayMethod.PIX, first)
                cs.add_payment(db, shop, owner, c, PayMethod.CASH, due - first)
            else:
                cs.add_payment(db, shop, owner, c, a.payment_method or rng.choice(PayMethod.ALL), due)
        cs.close(db, shop, owner, c)
        c.closed_at = a.end + timedelta(minutes=5)
        stats["comandas"] += 1

    # Pacote vendido em comanda avulsa para dois clientes; um já usou uma sessão
    for c in customers[3:5]:
        if db.scalar(select(CustomerPackage.id).where(CustomerPackage.customer_id == c.id)):
            continue
        cm = cs.open_comanda(db, shop, owner, customer=c)
        cs.add_package_sale(db, shop, owner, cm, plan)
        cs.add_payment(db, shop, owner, cm, PayMethod.PIX, plan.price)
        cs.close(db, shop, owner, cm)
        stats["packages"] += 1
    db.flush()
    first_pkg = db.scalar(select(CustomerPackage).where(CustomerPackage.shop_id == shop.id).order_by(CustomerPackage.id))
    if first_pkg and not db.scalar(select(func.count()).select_from(PackageUse)
                                   .where(PackageUse.customer_package_id == first_pkg.id)):
        cm = cs.open_comanda(db, shop, owner, customer=first_pkg.customer)
        barber = db.scalar(select(Barber).where(Barber.shop_id == shop.id, Barber.active.is_(True)))
        cs.add_service(db, shop, owner, cm, first_pkg.service, barber, cover="package")
        cs.close(db, shop, owner, cm)
        stats["comandas"] += 1

    # Lista de espera para amanhã
    if len(customers) > 5 and not db.scalar(select(WaitlistEntry.id).where(WaitlistEntry.shop_id == shop.id)):
        from .services import waitlist
        waitlist.join(db, shop, customers[5], services[0], now.date() + timedelta(days=1),
                      after=time(17), via="app")
    db.commit()
    return stats


def summary_lines(db: Session, shop: Shop) -> list[str]:
    n = lambda m: db.scalar(select(func.count()).select_from(m).where(m.shop_id == shop.id))  # noqa: E731
    late = db.scalar(select(func.count()).select_from(Subscription).where(
        Subscription.shop_id == shop.id, Subscription.status == SubStatus.LATE))
    pending = db.scalar(select(func.count()).select_from(Charge).where(
        Charge.shop_id == shop.id, Charge.status == PayStatus.PENDING))
    return [f"  Equipe: {n(Membership)} logins (dono, recepção e profissional)",
            f"  Produtos: {n(Product)} (estoque baixo: {len(stock.low_stock(db, shop))})",
            f"  Comandas fechadas: {n(Comanda)}",
            f"  Pacotes vendidos: {n(CustomerPackage)}",
            f"  Assinantes: {n(Subscription)} (atrasados: {late}; cobranças pendentes: {pending})",
            f"  Lista de espera: {n(WaitlistEntry)}"]
