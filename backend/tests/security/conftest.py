"""Fixtures da suíte de segurança: duas barbearias (A e B) completas, cada uma com usuário, profissionais, serviços,
clientes, agendamentos, pagamento com comprovante, avaliação, gasto, regra de comissão, acerto, bloqueio, conflito
entre clientes e pedido aguardando aprovação. Tudo de B tem a marca "ZZB" para achar vazamentos."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import now_local
from app.models import (
    Appointment, ApptStatus, Barber, Beneficiary, Block, CommissionRule, CommissionSettlement, Customer,
    CustomerConflict, Expense, Payment, Review, Service, Shop, User, WorkingHour,
)
from app.services.payments import get_or_create_pix

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
B_MARK = "ZZB"
B_OWNER = "5531911110000"


@dataclass
class World:
    shop: Shop
    user_email: str
    password: str
    barber: Barber
    service: Service
    customer: Customer
    other_customer: Customer
    appt: Appointment            # futuro, agendado, com Pix pendente
    pending_appt: Appointment    # aguardando aprovação
    done_appt: Appointment       # concluído, com avaliação
    payment: Payment
    review: Review
    expense: Expense
    rule: CommissionRule
    settlement: CommissionSettlement
    block: Block
    conflict: CustomerConflict
    extra: dict = field(default_factory=dict)


def _future_weekday(days: int) -> date:
    d = now_local().date() + timedelta(days=days)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def build_world(db, shop: Shop, tag: str, email: str, password: str, phone_prefix: str) -> World:
    """Dados completos de uma barbearia. tag entra nos nomes (para achar vazamento nas respostas)."""
    if not db.scalar(select(User).where(User.email == email)):
        db.add(User(shop_id=shop.id, name=f"Dono {tag}", email=email, password_hash=hash_password(password)))
    shop.pix_enabled, shop.pix_key, shop.pix_key_type = True, f"pix{tag.lower()}@exemplo.com", "email"
    shop.pix_receiver_name, shop.pix_city = f"Loja {tag}"[:25], "Cidade"
    service = Service(shop_id=shop.id, name=f"Serviço {tag}", duration_minutes=30, price=Decimal("50"))
    db.add(service)
    db.flush()
    barber = Barber(shop_id=shop.id, name=f"Barbeiro {tag}", phone=f"{phone_prefix}0001", services=[service])
    for wd in range(5):
        barber.working_hours.append(WorkingHour(weekday=wd, start=time(9), end=time(18)))
    second = Barber(shop_id=shop.id, name=f"Padrinho {tag}", phone="")
    db.add_all([barber, second])
    customer = Customer(shop_id=shop.id, phone=f"{phone_prefix}1111", name=f"Cliente {tag}")
    other = Customer(shop_id=shop.id, phone=f"{phone_prefix}2222", name=f"Outro {tag}")
    db.add_all([customer, other])
    db.flush()

    def appt(c, day, hour, status=ApptStatus.SCHEDULED):
        start = datetime.combine(day, time(hour))
        a = Appointment(shop_id=shop.id, customer_id=c.id, barber_id=barber.id, service_id=service.id, start=start,
                        end=start + timedelta(minutes=30), price=service.price, status=status)
        db.add(a)
        db.flush()
        return a

    a1 = appt(customer, _future_weekday(3), 10)
    pending = appt(other, _future_weekday(4), 11, ApptStatus.PENDING_APPROVAL)
    pending.approval_requested_at = now_local()
    done = appt(customer, now_local().date() - timedelta(days=3), 10, ApptStatus.COMPLETED)
    pay = get_or_create_pix(db, shop, a1)
    pay.customer_reported_at, pay.receipt_mime, pay.receipt_data, pay.receipt_at = now_local(), "image/png", PNG, now_local()
    review = Review(shop_id=shop.id, appointment_id=done.id, rating=5, comment=f"Ótimo {tag}")
    expense = Expense(shop_id=shop.id, description=f"Aluguel {tag}", category="aluguel", amount=Decimal("900"),
                      due_date=now_local().date(), barber_id=barber.id)
    rule = CommissionRule(shop_id=shop.id, barber_id=barber.id, beneficiary_type=Beneficiary.SHOP,
                          percentage=Decimal("30"), valid_from=date(2026, 1, 1))
    settlement = CommissionSettlement(shop_id=shop.id, payer_barber_id=barber.id, beneficiary_type=Beneficiary.SHOP,
                                      period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
                                      amount=Decimal("100"), notes=f"Acerto {tag}")
    day = _future_weekday(5)
    block = Block(shop_id=shop.id, barber_id=barber.id, start=datetime.combine(day, time(12)),
                  end=datetime.combine(day, time(13)), reason=f"Almoço {tag}")
    a, b = sorted((customer.id, other.id))
    conflict = CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, notes=f"Briga {tag}")
    db.add_all([review, expense, rule, settlement, block, conflict])
    db.commit()
    extra = {"second_barber": second, **build_crm(db, shop, tag, barber, service, customer, a1)}
    return World(shop=shop, user_email=email, password=password, barber=barber, service=service, customer=customer,
                 other_customer=other, appt=a1, pending_appt=pending, done_appt=done, payment=pay, review=review,
                 expense=expense, rule=rule, settlement=settlement, block=block, conflict=conflict, extra=extra)


def build_crm(db, shop: Shop, tag: str, barber: Barber, service: Service, customer: Customer, appt) -> dict:
    """CRM da loja: um login de cada papel, produto, pacote vendido, plano e assinatura com cobrança, comanda aberta
    com item e pagamento, e lista de espera."""
    from app.models import Charge, PackagePlan, Product, Role, StockReason, SubscriptionPlan, SubscriptionPlanItem
    from app.services import benefits, billing, comandas as cs, stock, waitlist
    slug = tag.lower()
    reception = User(shop_id=shop.id, name=f"Recepção {tag}", email=f"recepcao@{slug}.com.br",
                     password_hash=hash_password("senha-recepcao-1"), role=Role.RECEPTION)
    pro = User(shop_id=shop.id, name=f"Pro {tag}", email=f"pro@{slug}.com.br",
               password_hash=hash_password("senha-pro-1"), role=Role.PROFESSIONAL, barber_id=barber.id)
    db.add_all([reception, pro])
    product = Product(shop_id=shop.id, name=f"Pomada {tag}", price=Decimal("40"), cost=Decimal("15"),
                      min_stock=Decimal("2"))
    plan = PackagePlan(shop_id=shop.id, name=f"Pacote {tag}", service_id=service.id, sessions=4, price=Decimal("160"),
                       validity_days=60)
    club = SubscriptionPlan(shop_id=shop.id, name=f"Clube {tag}", price=Decimal("90"))
    club.items = [SubscriptionPlanItem(service_id=service.id, limit_per_period=2)]
    db.add_all([product, plan, club])
    db.flush()
    stock.move(db, shop, product, Decimal(10), StockReason.PURCHASE)
    cp = benefits.sell_package(db, shop, customer, plan)
    sub = billing.subscribe(db, shop, customer, club, charge_now=True)
    charge = db.scalar(select(Charge).where(Charge.subscription_id == sub.id))
    owner = db.scalar(select(User).where(User.shop_id == shop.id, User.role == Role.OWNER))
    comanda = cs.open_comanda(db, shop, owner, appointment=appt)
    item = cs.add_product(db, shop, owner, comanda, product, 1, barber)
    cpay = cs.add_payment(db, shop, owner, comanda, "dinheiro", Decimal("10"))
    wait = waitlist.join(db, shop, customer, service, _future_weekday(6), via="app")
    db.commit()
    return {"reception": reception, "pro": pro, "reception_password": "senha-recepcao-1",
            "pro_password": "senha-pro-1", "product": product, "package_plan": plan, "customer_package": cp,
            "club": club, "subscription": sub, "charge": charge, "comanda": comanda, "item": item,
            "comanda_payment": cpay, "wait": wait}


@dataclass
class Two:
    db: object
    a: World
    b: World
    ca: TestClient
    cb: TestClient
    anon: TestClient


def _client(email: str, password: str) -> TestClient:
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c


@pytest.fixture()
def two(db) -> Two:
    shop_a = db.scalar(select(Shop).where(Shop.evolution_instance == "barbearia-demo"))
    shop_b = Shop(name=f"Barbearia Bravo {B_MARK}", evolution_instance="bravo-zzb", owner_phone=B_OWNER,
                  address=f"Rua {B_MARK}, 1")
    db.add(shop_b)
    db.commit()
    a = build_world(db, shop_a, "AAA", "admin@demo.com", "demo123", "553190000")
    b = build_world(db, shop_b, B_MARK, "dono@bravo-zzb.com.br", "senha-bravo-123", "553191111")
    from app.main import app
    return Two(db=db, a=a, b=b, ca=_client(a.user_email, a.password), cb=_client(b.user_email, b.password),
               anon=TestClient(app))


def no_leak(text: str, world: World) -> bool:
    """A resposta não tem nenhum dado da outra barbearia."""
    marks = [B_MARK, world.customer.phone, world.other_customer.phone, B_OWNER]
    return not any(m in text for m in marks)
