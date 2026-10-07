"""Cria uma barbearia de demonstração. Uso: python -m app.seed"""
from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import hash_password
from .config import now_local
from .db import Base, SessionLocal, engine
from .models import (
    AccessStatus, Barber, Beneficiary, CommissionRule, Customer, CustomerConflict, Expense, PayMethod, Service, Shop,
    User, WorkingHour,
)
from .services.expenses import ensure_recurring, same_day_in

# (descrição, categoria, valor, dia do vencimento) - contas fixas, cadastradas como recorrentes no mês passado
RECURRING_EXPENSES = [
    ("Aluguel do ponto", "aluguel", "1800.00", 5),
    ("Internet", "internet", "119.90", 10),
    ("Conta de luz", "energia", "320.00", 15),
    ("Conta de água", "agua", "95.00", 15),
    ("Contador", "impostos", "250.00", 20),
]
# Gastos avulsos do mês atual
ONE_OFF_EXPENSES = [
    ("Pomadas e lâminas", "produtos", "460.00", 3),
    ("Impulsionamento no Instagram", "marketing", "150.00", 22),
    ("Afiação das tesouras", "manutencao", "80.00", 26),
]


# (telefone, nome, acesso, motivo interno) - exemplos do controle de clientes.
# DDD 00 não existe: nenhuma mensagem chega a uma pessoa real se o WhatsApp estiver conectado.
DEMO_CUSTOMERS = [
    ("5500955550001", "Marcos Teixeira", AccessStatus.BLOCKED,
     "Faltou 3 vezes sem avisar e saiu sem pagar o último corte."),
    ("5500955550002", "Paulo Duarte", AccessStatus.APPROVAL, "Cancela em cima da hora com frequência."),
    ("5500955550003", "Renato Vasconcelos", AccessStatus.NORMAL, ""),
    ("5500955550004", "Alexandre Pinto", AccessStatus.NORMAL, ""),
]
DEMO_PHONES = {p for p, *_ in DEMO_CUSTOMERS}


def seed_customers(db: Session, shop: Shop) -> dict[str, Customer]:
    """Um cliente bloqueado, um que precisa de aprovação e um par que não pode se encontrar (distância padrão
    da barbearia). Só cria o que ainda não existe. Devolve os clientes pelo nome."""
    out = {}
    for phone, name, status, reason in DEMO_CUSTOMERS:
        c = db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone))
        if c is None:
            c = Customer(shop_id=shop.id, phone=phone, name=name, access_status=status, access_reason=reason,
                         access_changed_at=now_local() if status != AccessStatus.NORMAL else None)
            db.add(c)
        out[name] = c
    db.flush()
    a, b = sorted((out["Renato Vasconcelos"].id, out["Alexandre Pinto"].id))
    if not db.scalar(select(CustomerConflict).where(CustomerConflict.shop_id == shop.id,
                                                    CustomerConflict.customer_a_id == a,
                                                    CustomerConflict.customer_b_id == b)):
        db.add(CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b,
                                notes="Discutiram feio na barbearia em agosto. Não deixar os dois juntos."))
    db.commit()
    return out


def seed_finance(db: Session, shop: Shop, today: date | None = None,
                 one_off: list[tuple[str, str, str, int]] = ONE_OFF_EXPENSES,
                 extras: tuple[tuple[str, str, str], tuple[str, str, str]] = (
                     ("Conserto do ar-condicionado", "manutencao", "280.00"),
                     ("Toalhas e capas", "equipamentos", "135.00"))) -> None:
    """Regras de comissão (só a barbearia demo, com João e Pedro) e gastos de exemplo. Só cria o que ainda não existe.
    one_off: gastos avulsos do mês; extras: (vencido há 2 dias, vence hoje)."""
    today = today or now_local().date()
    barbers = {b.name: b for b in shop.barbers}
    has_rules = db.scalar(select(func.count()).select_from(CommissionRule).where(CommissionRule.shop_id == shop.id))
    if not has_rules and {"João", "Pedro"} <= set(barbers):
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)  # desde o mês passado
        pedro, joao = barbers["Pedro"], barbers["João"]
        db.add_all([
            CommissionRule(shop_id=shop.id, barber_id=pedro.id, beneficiary_type=Beneficiary.SHOP,
                           percentage=Decimal("40"), valid_from=start, notes="Barbeiro novo: cadeira e produtos"),
            CommissionRule(shop_id=shop.id, barber_id=pedro.id, beneficiary_type=Beneficiary.BARBER,
                           beneficiary_barber_id=joao.id, percentage=Decimal("10"), valid_from=start,
                           notes="João é o padrinho nos primeiros meses"),
            CommissionRule(shop_id=shop.id, barber_id=joao.id, beneficiary_type=Beneficiary.SHOP,
                           percentage=Decimal("30"), valid_from=start),
        ])

    has_expenses = db.scalar(select(func.count()).select_from(Expense).where(Expense.shop_id == shop.id))
    if has_expenses:
        db.commit()
        return
    last_month = (today.replace(day=1) - timedelta(days=1))
    for desc, cat, amount, day in RECURRING_EXPENSES:
        due = same_day_in(last_month.year, last_month.month, day)
        db.add(Expense(shop_id=shop.id, description=desc, category=cat, amount=Decimal(amount), due_date=due,
                       paid_at=due, payment_method=PayMethod.PIX, recurring=True))
    db.flush()
    ensure_recurring(db, shop, today.year, today.month)
    for desc, cat, amount, day in one_off:
        db.add(Expense(shop_id=shop.id, description=desc, category=cat, amount=Decimal(amount),
                       due_date=same_day_in(today.year, today.month, day)))
    db.flush()
    # Contas do mês que já venceram ficam pagas
    first = today.replace(day=1)
    for e in db.scalars(select(Expense).where(Expense.shop_id == shop.id, Expense.due_date >= first)):
        if e.due_date < today:
            e.paid_at, e.payment_method = e.due_date, PayMethod.PIX if e.recurring_source_id else PayMethod.DEBIT
    # Uma conta vencida e uma que vence hoje, para aparecerem em vermelho no app e no resumo do WhatsApp
    (late_desc, late_cat, late_amount), (today_desc, today_cat, today_amount) = extras
    db.add_all([
        Expense(shop_id=shop.id, description=late_desc, category=late_cat, amount=Decimal(late_amount),
                due_date=today - timedelta(days=2)),
        Expense(shop_id=shop.id, description=today_desc, category=today_cat, amount=Decimal(today_amount),
                due_date=today),
    ])
    db.commit()


def seed(owner_phone: str = "5531999990000", demo_finance: bool = True, demo_customers: bool = True) -> Shop:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        shop = db.scalar(select(Shop).where(Shop.evolution_instance == "barbearia-demo"))
        if shop:
            if not shop.ai_allow_free_tier:  # a demo (dados fictícios) pode usar a IA no plano gratuito
                shop.ai_allow_free_tier = True
                db.commit()
            if demo_finance:
                seed_finance(db, shop)
            if demo_customers:
                seed_customers(db, shop)
            return shop
        shop = Shop(
            name="Barbearia Demo", address="Rua Exemplo, 123 - Centro, Conselheiro Lafaiete/MG",
            phone="(31) 3333-0000", owner_phone=owner_phone, instagram="@barbeariademo",
            evolution_instance="barbearia-demo", niche="barbershop", theme_mode="auto", ai_allow_free_tier=True,
            pix_enabled=True, pix_key="contato@barbeariademo.com.br",
            pix_key_type="email", pix_receiver_name="Barbearia Demo", pix_city="Cons Lafaiete",
        )
        db.add(shop)
        db.flush()
        db.add(User(shop_id=shop.id, name="Dono Demo", email="admin@demo.com", password_hash=hash_password("demo123")))
        corte = Service(shop_id=shop.id, name="Corte", duration_minutes=30, price=Decimal("40"), sort_order=1)
        barba = Service(shop_id=shop.id, name="Barba", duration_minutes=30, price=Decimal("30"), sort_order=2)
        combo = Service(shop_id=shop.id, name="Corte + Barba", duration_minutes=60, price=Decimal("65"), sort_order=3)
        db.add_all([corte, barba, combo])
        for name, phone in (("João", "5531988880001"), ("Pedro", "5531988880002")):
            b = Barber(shop_id=shop.id, name=name, phone=phone, services=[corte, barba, combo])
            for wd in range(0, 6):  # segunda a sábado
                b.working_hours.append(WorkingHour(weekday=wd, start=time(9), end=time(12)))
                if wd < 5:
                    b.working_hours.append(WorkingHour(weekday=wd, start=time(13), end=time(19)))
            db.add(b)
        db.commit()
        if demo_finance:
            seed_finance(db, shop)
        if demo_customers:
            seed_customers(db, shop)
        print("Barbearia demo criada. Login do app: admin@demo.com / demo123")
        return shop
    finally:
        db.close()


if __name__ == "__main__":
    seed()
