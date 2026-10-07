"""CRM fase 1: comanda com pagamento dividido e estorno, estoque, pacotes, clube de assinatura, sinal e lista de
espera."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bot.router import handle_incoming
from app.config import now_local
from app.models import (
    Appointment, ApptStatus, Charge, CommissionRule, Customer, CustomerPackage, OutboxMessage, Payment,
    Shop, SubStatus, Subscription, SubscriptionPlan, WaitlistEntry,
)

INST = "barbearia-demo"
CLIENT = "5531977776666"
D = Decimal


def weekday(days: int):
    d = now_local().date() + timedelta(days=days)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def at(day, hour, minute=0) -> str:
    return datetime.combine(day, time(hour, minute)).isoformat()


def msgs_to(db, phone):
    return [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == phone)
                                       .order_by(OutboxMessage.id))]


@pytest.fixture()
def env(db):
    from app.main import app
    shop = db.scalar(select(Shop).where(Shop.evolution_instance == INST))
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"})
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    e = SimpleNamespace(db=db, shop=shop, c=c, svc={s.name: s for s in shop.services},
                        pro={b.name: b for b in shop.barbers})

    def book(phone=CLIENT, name="Carlos", day=None, hour=10, service="Corte", barber="João", **extra):
        r = c.post("/api/appointments", json={
            "customer_phone": phone, "customer_name": name, "barber_id": e.pro[barber].id,
            "service_id": e.svc[service].id, "start": at(day or weekday(2), hour), **extra})
        assert r.status_code == 200, r.text
        return r.json()

    def product(name="Pomada", price="45", cost="18", minimum="3", stock="10", pct=None, kind="both", unit="un"):
        r = c.post("/api/products", json={"name": name, "price": price, "cost": cost, "min_stock": minimum,
                                          "commission_pct": pct, "kind": kind, "unit": unit})
        assert r.status_code == 200, r.text
        p = r.json()
        if stock:
            assert c.post(f"/api/products/{p['id']}/movements", json={"delta": stock, "reason": "purchase"}
                          ).status_code == 200
        return p

    def stock_of(pid):
        return D(next(p for p in c.get("/api/products?include_inactive=true").json() if p["id"] == pid)["stock"])

    e.book, e.product, e.stock_of = book, product, stock_of
    return e


# ---------------------------------------------------------------- comanda

def test_comanda_split_payment_feeds_finance_and_commissions(env):
    c, db = env.c, env.db
    joao = env.pro["João"]
    db.add(CommissionRule(shop_id=env.shop.id, barber_id=joao.id, beneficiary_type="shop", percentage=D("50"),
                          valid_from=now_local().date() - timedelta(days=30)))
    db.commit()
    pomada = env.product(pct="10")
    a = env.book()
    com = c.post("/api/comandas", json={"appointment_id": a["id"]}).json()
    assert [i["description"] for i in com["items"]] == ["Corte"] and com["due"] == "40.00"
    # Abrir de novo devolve a mesma comanda
    assert c.post("/api/comandas", json={"appointment_id": a["id"]}).json()["id"] == com["id"]
    cid = com["id"]
    c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"], "barber_id": joao.id})
    c.post(f"/api/comandas/{cid}/items", json={"kind": "discount", "percent": "10"})
    com = c.post(f"/api/comandas/{cid}/items", json={"kind": "tip", "value": "10", "barber_id": joao.id}).json()
    assert (com["subtotal"], com["discount"], com["tips"], com["due"]) == ("85.00", "-8.50", "10.00", "86.50")
    c.post(f"/api/comandas/{cid}/payments", json={"method": "pix", "amount": "50"})
    r = c.post(f"/api/comandas/{cid}/close")
    assert r.status_code == 409 and "Faltam 36,50" in r.json()["detail"]
    c.post(f"/api/comandas/{cid}/payments", json={"method": "dinheiro", "amount": "36.50"})
    com = c.post(f"/api/comandas/{cid}/close").json()
    assert com["status"] == "closed" and com["balance"] == "0.00"
    # Fechada não aceita lançamento novo
    assert c.post(f"/api/comandas/{cid}/payments", json={"method": "pix", "amount": "1"}).status_code == 409

    db.expire_all()
    appt = db.get(Appointment, a["id"])
    assert appt.status == ApptStatus.COMPLETED and appt.payment_method == "pix"
    today = now_local().date().isoformat()
    fin = c.get("/api/finance/summary", params={"date_from": today, "date_to": today}).json()
    assert fin["revenue"] == "76.50" and fin["appointments"] == 1  # gorjeta não é faturamento
    methods = {m["method"]: D(m["revenue"]) for m in fin["by_payment_method"]}
    assert set(methods) == {"pix", "dinheiro"} and sum(methods.values()) == D("76.50")
    services = {s["name"]: s["revenue"] for s in fin["by_service"]}
    assert services == {"Corte": "36.00", "Produtos": "40.50"}
    rep = c.get("/api/finance/commissions", params={"date_from": today, "date_to": today}).json()
    row = next(b for b in rep["barbers"] if b["barber_id"] == joao.id)
    assert row["gross"] == "36.00" and row["total_due"] == "18.00"  # 50% sobre o corte com desconto
    assert row["tips"] == "10.00" and row["product_commission"] == "4.05"  # 10% de 40,50
    assert env.stock_of(pomada["id"]) == D(9)


def test_reversal_is_a_negative_entry_and_restores_stock(env):
    c = env.c
    pomada = env.product()
    cid = c.post("/api/comandas", json={}).json()["id"]
    com = c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"], "quantity": 2}
                 ).json()
    item = com["items"][0]
    assert env.stock_of(pomada["id"]) == D(8)
    com = c.post(f"/api/comandas/{cid}/items/{item['id']}/reverse").json()
    assert [(i["amount"], i["reversed"]) for i in com["items"]] == [("90.00", True), ("-90.00", False)]
    assert com["items"][1]["reverses_id"] == item["id"] and com["due"] == "0.00"
    assert env.stock_of(pomada["id"]) == D(10)
    assert c.post(f"/api/comandas/{cid}/items/{item['id']}/reverse").status_code == 409  # só uma vez
    assert c.post(f"/api/comandas/{cid}/items/{com['items'][1]['id']}/reverse").status_code == 409
    assert c.post(f"/api/comandas/{cid}/cancel").json()["status"] == "cancelled"


def test_reversal_after_closing_is_owner_only_and_hits_finance(env):
    from app.auth import hash_password
    from app.models import User
    c, db = env.c, env.db
    pomada = env.product()
    db.add(User(shop_id=env.shop.id, name="Rec", email="rec@demo.com", password_hash=hash_password("senha-rec-1"),
                role="reception"))
    db.commit()
    rec = TestClient(c.app)
    rec.headers["Authorization"] = "Bearer " + rec.post("/api/auth/login", json={
        "email": "rec@demo.com", "password": "senha-rec-1"}).json()["token"]
    cid = rec.post("/api/comandas", json={}).json()["id"]
    item = rec.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"]}
                    ).json()["items"][0]
    pay = rec.post(f"/api/comandas/{cid}/payments", json={"method": "credito", "amount": "45"}).json()["payments"][0]
    assert rec.post(f"/api/comandas/{cid}/close").json()["status"] == "closed"  # recepção fecha comanda
    assert rec.post(f"/api/comandas/{cid}/items/{item['id']}/reverse").status_code == 403
    assert rec.post(f"/api/comandas/{cid}/payments/{pay['id']}/reverse").status_code == 403
    today = now_local().date().isoformat()
    assert c.get("/api/finance/summary", params={"date_from": today, "date_to": today}).json()["revenue"] == "45.00"
    assert rec.get("/api/finance/summary", params={"date_from": today, "date_to": today}).status_code == 403
    c.post(f"/api/comandas/{cid}/items/{item['id']}/reverse")
    com = c.post(f"/api/comandas/{cid}/payments/{pay['id']}/reverse").json()  # devolveu o dinheiro
    assert com["balance"] == "0.00" and com["status"] == "closed"
    assert c.get("/api/finance/summary", params={"date_from": today, "date_to": today}).json()["revenue"] == "0.00"


# ---------------------------------------------------------------- estoque

def test_stock_deduction_on_sale_and_service_and_low_stock_alert(env):
    from app.jobs import send_daily_summary
    c, db = env.c, env.db
    shampoo = env.product(name="Shampoo", kind="internal", unit="ml", price="0", minimum="200", stock="250")
    pomada = env.product(minimum="9", stock="10")
    corte = env.svc["Corte"]
    r = c.put(f"/api/services/{corte.id}/consumption", json=[{"product_id": shampoo["id"], "quantity": "30"}])
    assert r.status_code == 200
    a = env.book()
    cid = c.post("/api/comandas", json={"appointment_id": a["id"]}).json()["id"]  # o serviço entra e consome
    assert env.stock_of(shampoo["id"]) == D(220)
    c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"]})
    assert env.stock_of(pomada["id"]) == D(9)
    # Produto só de uso interno não é vendido
    r = c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": shampoo["id"]})
    assert r.status_code == 409
    # Uso interno avulso: saída (sempre negativa)
    c.post(f"/api/products/{shampoo['id']}/movements", json={"delta": "30", "reason": "internal"})
    assert env.stock_of(shampoo["id"]) == D(190)
    low = {p["name"] for p in c.get("/api/products/low-stock").json()}
    assert low == {"Shampoo", "Pomada"}
    movements = c.get(f"/api/products/{shampoo['id']}/movements").json()
    assert [m["reason"] for m in movements] == ["internal", "consumption", "purchase"]  # nada sobrescrito
    db.expire_all()
    shop = db.get(Shop, env.shop.id)
    shop.daily_summary_hour, shop.last_summary_date = 0, None
    assert send_daily_summary(db, shop)
    db.commit()
    assert "Estoque baixo" in msgs_to(db, shop.owner_phone)[-1] and "Shampoo" in msgs_to(db, shop.owner_phone)[-1]


def test_selling_more_than_stock_needs_confirmation(env):
    c = env.c
    pomada = env.product(stock="1")
    cid = c.post("/api/comandas", json={}).json()["id"]
    r = c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"], "quantity": 2})
    assert r.status_code == 409 and "Estoque insuficiente" in r.json()["detail"]
    assert env.stock_of(pomada["id"]) == D(1) and c.get(f"/api/comandas/{cid}").json()["items"] == []
    r = c.post(f"/api/comandas/{cid}/items", json={"kind": "product", "product_id": pomada["id"], "quantity": 2,
                                                  "allow_negative_stock": True})
    assert r.status_code == 200
    assert env.stock_of(pomada["id"]) == D(-1)  # registra a realidade; o produto aparece em estoque baixo
    assert any(p["id"] == pomada["id"] and p["low_stock"] for p in c.get("/api/products").json())


# ---------------------------------------------------------------- pacotes

def _package(env, sessions=4, price="140", validity=90):
    r = env.c.post("/api/package-plans", json={"name": "4 cortes", "service_id": env.svc["Corte"].id,
                                               "sessions": sessions, "price": price, "validity_days": validity})
    assert r.status_code == 200, r.text
    return r.json()


def _sell_package(env, plan, phone=CLIENT):
    c = env.c
    cust = env.db.scalar(select(Customer).where(Customer.phone == phone))
    cid = c.post("/api/comandas", json={"customer_id": cust.id}).json()["id"]
    c.post(f"/api/comandas/{cid}/items", json={"kind": "package", "package_plan_id": plan["id"]})
    c.post(f"/api/comandas/{cid}/payments", json={"method": "pix", "amount": plan["price"]})
    assert c.post(f"/api/comandas/{cid}/close").json()["status"] == "closed"
    return cust


def test_package_consumed_on_booking_returned_on_cancel_and_commission_uses_session_value(env):
    c, db = env.c, env.db
    joao = env.pro["João"]
    db.add(CommissionRule(shop_id=env.shop.id, barber_id=joao.id, beneficiary_type="shop", percentage=D("40"),
                          valid_from=now_local().date() - timedelta(days=30)))
    db.commit()
    plan = _package(env)
    first = env.book(day=weekday(1))  # cria o cliente
    c.patch(f"/api/appointments/{first['id']}", json={"status": "cancelled", "notify_customer": False})
    cust = _sell_package(env, plan)
    bal = c.get(f"/api/customers/{cust.id}/balance").json()["packages"][0]
    assert (bal["balance"], bal["state"], bal["session_value"]) == (4, "ativo", "35.00")

    a = env.book(day=weekday(3))
    assert a["customer_package_id"] is not None
    assert "Usei 1 sessão do seu pacote" in msgs_to(db, CLIENT)[-1]
    assert c.get(f"/api/customers/{cust.id}/balance").json()["packages"][0]["balance"] == 3
    c.patch(f"/api/appointments/{a['id']}", json={"status": "cancelled", "notify_customer": False})
    assert c.get(f"/api/customers/{cust.id}/balance").json()["packages"][0]["balance"] == 4

    a = env.book(day=weekday(4), hour=11)
    com = c.post("/api/comandas", json={"appointment_id": a["id"]}).json()
    item = com["items"][0]
    assert (item["covered_by"], item["amount"], item["commission_base"], com["due"]) == \
        ("package", "0.00", "35.00", "0.00")
    assert c.post(f"/api/comandas/{com['id']}/close").json()["status"] == "closed"
    assert c.get(f"/api/customers/{cust.id}/balance").json()["packages"][0]["balance"] == 3  # não consumiu 2 vezes
    today = now_local().date().isoformat()
    rep = c.get("/api/finance/commissions", params={"date_from": today, "date_to": today}).json()
    row = next(b for b in rep["barbers"] if b["barber_id"] == joao.id)
    assert row["gross"] == "35.00" and row["total_due"] == "14.00"
    fin = c.get("/api/finance/summary", params={"date_from": today, "date_to": today}).json()
    assert fin["revenue"] == "140.00"  # o pacote entrou quando foi pago; a sessão não conta de novo


def test_expired_package_is_not_used(env):
    c, db = env.c, env.db
    plan = _package(env)
    first = env.book(day=weekday(1))
    c.patch(f"/api/appointments/{first['id']}", json={"status": "cancelled", "notify_customer": False})
    cust = _sell_package(env, plan)
    cp = db.scalar(select(CustomerPackage).where(CustomerPackage.customer_id == cust.id))
    cp.expires_at = now_local().date() - timedelta(days=1)
    db.commit()
    assert c.get(f"/api/customers/{cust.id}/balance").json()["packages"][0]["state"] == "vencido"
    a = env.book(day=weekday(3))
    assert a["customer_package_id"] is None
    cid = c.post("/api/comandas", json={"customer_id": cust.id}).json()["id"]
    r = c.post(f"/api/comandas/{cid}/items", json={"kind": "service", "service_id": env.svc["Corte"].id,
                                                   "barber_id": env.pro["João"].id, "cover": "package"})
    assert r.status_code == 409 and "pacote" in r.json()["detail"]


# ---------------------------------------------------------------- assinatura

def _club(env, limit=2):
    r = env.c.post("/api/subscription-plans", json={
        "name": "Clube", "price": "99.90", "block_after_days": 5,
        "items": [{"service_id": env.svc["Corte"].id}, {"service_id": env.svc["Barba"].id, "limit_per_period": limit}]})
    assert r.status_code == 200, r.text
    return r.json()


def _customer(env, phone=CLIENT):
    first = env.book(phone=phone, day=weekday(1), hour=9)
    env.c.patch(f"/api/appointments/{first['id']}", json={"status": "cancelled", "notify_customer": False})
    return env.db.scalar(select(Customer).where(Customer.phone == phone))


def test_subscription_limit_per_period(env):
    c, db = env.c, env.db
    club = _club(env)
    cust = _customer(env)
    r = c.post("/api/subscriptions", json={"customer_id": cust.id, "plan_id": club["id"]})
    assert r.status_code == 200 and r.json()["status"] == "ativa"
    charge = c.get("/api/charges?status=pending").json()[0]
    assert charge["amount"] == "99.90" and charge["brcode"]
    assert "Mensalidade" in msgs_to(db, CLIENT)[-2]  # Pix da mensalidade pelo WhatsApp
    assert c.post(f"/api/charges/{charge['id']}/confirm").json()["status"] == "paid"
    assert c.post("/api/subscriptions", json={"customer_id": cust.id, "plan_id": club["id"]}).status_code == 409

    cid = c.post("/api/comandas", json={"customer_id": cust.id}).json()["id"]
    body = {"kind": "service", "service_id": env.svc["Barba"].id, "barber_id": env.pro["João"].id,
            "cover": "subscription"}
    for _ in range(2):
        assert c.post(f"/api/comandas/{cid}/items", json=body).status_code == 200
    r = c.post(f"/api/comandas/{cid}/items", json=body)
    assert r.status_code == 409 and "limite" in r.json()["detail"]
    # Corte: sem limite
    for _ in range(3):
        assert c.post(f"/api/comandas/{cid}/items", json={**body, "service_id": env.svc["Corte"].id}
                      ).status_code == 200
    items = c.get(f"/api/customers/{cust.id}/balance").json()["subscriptions"][0]["items"]
    barba = next(i for i in items if i["service_name"] == "Barba")
    assert (barba["used"], barba["remaining"]) == (2, 0)
    # Estorno devolve o uso
    first = c.get(f"/api/comandas/{cid}").json()["items"][0]
    c.post(f"/api/comandas/{cid}/items/{first['id']}/reverse")
    assert c.post(f"/api/comandas/{cid}/items", json=body).status_code == 200


def test_subscription_late_blocks_benefits_and_mrr(env):
    from app.services import billing
    c, db = env.c, env.db
    club = _club(env)
    cust = _customer(env)
    other = _customer(env, "5531966665555")
    today = now_local().date()
    c.post("/api/subscriptions", json={"customer_id": other.id, "plan_id": club["id"]})
    # Começou há 40 dias: a primeira mensalidade foi paga, a deste mês venceu há ~10 dias e não foi paga
    sub = billing.subscribe(db, env.shop, cust, db.get(SubscriptionPlan, club["id"]), today - timedelta(days=40),
                            charge_now=False)
    billing.run_subscriptions(db, env.shop, today)
    charges = db.scalars(select(Charge).where(Charge.subscription_id == sub.id).order_by(Charge.due_date)).all()
    assert len(charges) == 2  # recuperou os dois vencimentos
    billing.confirm_charge(db, env.shop, charges[0])
    db.commit()
    rep = c.get("/api/subscriptions/report").json()
    assert (rep["active"], rep["late"], rep["mrr"]) == (1, 1, "199.80")
    late = next(s for s in rep["subscribers"] if s["customer_id"] == cust.id)
    assert late["status"] == "atrasada" and late["days_late"] >= 6 and late["benefits_blocked"]
    cid = c.post("/api/comandas", json={"customer_id": cust.id}).json()["id"]
    body = {"kind": "service", "service_id": env.svc["Corte"].id, "barber_id": env.pro["João"].id,
            "cover": "subscription"}
    r = c.post(f"/api/comandas/{cid}/items", json=body)
    assert r.status_code == 409 and "atrasada" in r.json()["detail"]
    assert c.post(f"/api/charges/{charges[1].id}/confirm").status_code == 200
    db.expire_all()
    assert db.get(Subscription, sub.id).status == SubStatus.ACTIVE
    assert c.post(f"/api/comandas/{cid}/items", json=body).status_code == 200
    assert c.post(f"/api/subscriptions/{sub.id}/cancel").status_code == 200
    assert c.get("/api/subscriptions/report").json()["mrr"] == "99.90"


# ---------------------------------------------------------------- sinal

def say(db, text, phone=CLIENT):
    return "\n---\n".join(handle_incoming(db, INST, phone, text, "Carlos Silva"))


def _bot_book(db):
    db.expire_all()  # a sessão do teste guardava a loja de antes da configuração do sinal
    say(db, "oi")
    say(db, "1")       # agendar
    say(db, "1")       # Corte
    say(db, "1")       # João
    say(db, "2")       # segundo dia da lista
    say(db, "1")       # primeiro horário
    say(db, "Carlos")  # nome
    return say(db, "1")


def test_unpaid_deposit_releases_the_slot(env):
    from app.jobs import run_crm
    db, c = env.db, env.c
    assert c.put("/api/shop", json={"deposit_mode": "fixed", "deposit_value": "20", "deposit_expire_minutes": 30}
                 ).status_code == 200
    r = _bot_book(db)
    assert "sinal" in r and "R$ 20,00" in r
    a = db.scalar(select(Appointment).order_by(Appointment.id.desc()))
    assert a.status == ApptStatus.AWAITING_DEPOSIT and a.payment.kind == "deposit" and a.payment.amount == D("20.00")
    free = c.get("/api/availability", params={"service_id": a.service_id, "day": a.start.date().isoformat(),
                                              "barber_id": a.barber_id}).json()
    assert a.start.isoformat() not in [s["start"] for s in free]  # o horário fica reservado
    run_crm(db, env.shop)
    db.commit()
    assert db.get(Appointment, a.id).status == ApptStatus.AWAITING_DEPOSIT  # ainda no prazo
    a.created_at = now_local() - timedelta(minutes=31)
    db.commit()
    run_crm(db, env.shop)
    db.commit()
    db.expire_all()
    a = db.get(Appointment, a.id)
    assert a.status == ApptStatus.CANCELLED and a.deposit_status == "none"
    assert "liberado" in msgs_to(db, CLIENT)[-1]
    free = c.get("/api/availability", params={"service_id": a.service_id, "day": a.start.date().isoformat(),
                                              "barber_id": a.barber_id}).json()
    assert a.start.isoformat() in [s["start"] for s in free]


def test_paid_deposit_confirms_and_refund_rule(env):
    db, c = env.db, env.c
    c.put("/api/shop", json={"deposit_mode": "percent", "deposit_value": "50", "deposit_refund_hours": 0})
    _bot_book(db)
    a = db.scalar(select(Appointment).order_by(Appointment.id.desc()))
    assert a.deposit_amount == D("20.00")  # 50% do corte
    r = c.post(f"/api/payments/{a.payment.id}/confirm")
    assert r.status_code == 200
    db.expire_all()
    a = db.get(Appointment, a.id)
    assert a.status == ApptStatus.SCHEDULED and a.deposit_status == "paid"
    assert "sinal" in msgs_to(db, CLIENT)[-1] and "confirmado" in msgs_to(db, CLIENT)[-1]
    # Comanda do atendimento já vem com o sinal pago
    com = c.post("/api/comandas", json={"appointment_id": a.id}).json()
    assert com["paid"] == "20.00" and com["payments"][0]["from_deposit"] and com["balance"] == "20.00"
    assert c.post(f"/api/comandas/{com['id']}/cancel").status_code == 409  # tem valor: não cancela
    # Cancelado dentro do prazo de devolução: sinal a devolver; o dono marca como devolvido
    c.patch(f"/api/appointments/{a.id}", json={"status": "cancelled", "notify_customer": False})
    db.expire_all()
    assert db.get(Appointment, a.id).deposit_status == "refund_due"
    assert c.post(f"/api/appointments/{a.id}/deposit-refunded").json()["deposit_status"] == "refunded"


def test_deposit_kept_when_cancelled_late_counts_as_revenue(env):
    db, c = env.db, env.c
    c.put("/api/shop", json={"deposit_mode": "fixed", "deposit_value": "15", "deposit_refund_hours": 720})
    a = env.book(day=weekday(1), require_deposit=True)
    assert a["status"] == "awaiting_deposit" and a["deposit_amount"] == "15.00"
    pay = db.scalar(select(Payment).where(Payment.appointment_id == a["id"]))
    c.post(f"/api/payments/{pay.id}/confirm")
    c.patch(f"/api/appointments/{a['id']}", json={"status": "cancelled", "notify_customer": False})
    db.expire_all()
    assert db.get(Appointment, a["id"]).deposit_status == "forfeited"
    today = now_local().date().isoformat()
    fin = c.get("/api/finance/summary", params={"date_from": today, "date_to": today}).json()
    assert fin["revenue"] == "15.00" and {s["name"] for s in fin["by_service"]} == {"Sinais retidos"}


# ---------------------------------------------------------------- lista de espera

def test_waitlist_order_with_reservation(env):
    from app.services.waitlist import expire_offers
    db, c = env.db, env.c
    day = weekday(3)
    first, second = "5531955550001", "5531955550002"
    for phone, name in ((first, "Primeiro"), (second, "Segundo")):
        r = c.post("/api/waitlist", json={"customer_phone": phone, "customer_name": name,
                                          "service_id": env.svc["Corte"].id, "day": day.isoformat()})
        assert r.status_code == 200
    assert [w["position"] for w in c.get("/api/waitlist").json()] == [1, 2]
    a = env.book(day=day, hour=10)
    c.patch(f"/api/appointments/{a['id']}", json={"status": "cancelled", "notify_customer": False})
    db.expire_all()
    e1, e2 = db.scalars(select(WaitlistEntry).order_by(WaitlistEntry.id)).all()
    assert e1.status == "offered" and e2.status == "waiting"
    hold = db.get(Appointment, e1.offer_appointment_id)
    assert hold.status == ApptStatus.HELD and hold.start == datetime.combine(day, time(10))
    assert "Abriu um horário" in msgs_to(db, first)[-1] and not msgs_to(db, second)
    # Reservado: ninguém mais pega o horário
    r = c.post("/api/appointments", json={"customer_phone": "5531944443333", "barber_id": hold.barber_id,
                                          "service_id": env.svc["Corte"].id, "start": at(day, 10)})
    assert r.status_code == 409
    # Sem resposta em 10 minutos: passa a vez
    e1.offer_expires_at = now_local() - timedelta(seconds=1)
    db.commit()
    expire_offers(db, env.shop)
    db.commit()
    db.expire_all()
    e1, e2 = db.scalars(select(WaitlistEntry).order_by(WaitlistEntry.id)).all()
    assert e1.status == "expired" and e2.status == "offered"
    assert "Abriu um horário" in msgs_to(db, second)[-1]
    # O primeiro responde tarde: não leva
    assert "não está mais reservado" in say(db, "1", first) or "menu" in say(db, "menu", first)
    r = say(db, "1", second)
    assert "Agendado" in r
    db.expire_all()
    booked = db.get(Appointment, db.get(WaitlistEntry, e2.id).offer_appointment_id)
    assert booked.status == ApptStatus.SCHEDULED and booked.customer.phone == second
    assert db.get(WaitlistEntry, e2.id).status == "booked"


def test_bot_offers_waitlist_when_day_is_full(env):
    from app.services import scheduling as sch
    db, shop = env.db, env.shop
    joao, corte = env.pro["João"], env.svc["Corte"]
    days = sch.open_days(db, shop, corte, joao)
    day = next(d for d in days if d > now_local().date() and d.weekday() < 5)
    filler = Customer(shop_id=shop.id, phone="5531900001111", name="Agenda Cheia")
    db.add(filler)
    db.flush()
    for start, end in ((9, 12), (13, 19)):  # todo o expediente do João ocupado
        t = datetime.combine(day, time(start))
        while t < datetime.combine(day, time(end)):
            db.add(Appointment(shop_id=shop.id, customer_id=filler.id, barber_id=joao.id, service_id=corte.id,
                               start=t, end=t + timedelta(minutes=30), price=corte.price))
            t += timedelta(minutes=30)
    db.commit()
    say(db, "oi")
    say(db, "1")  # agendar
    say(db, "1")  # Corte
    say(db, "1")  # João
    r = say(db, str(days.index(day) + 1))
    assert "Não há horários livres" in r and "lista de espera" in r
    r = say(db, str(len(days) + 1))  # última opção: lista de espera
    assert "lista de espera" in r and "posição 1" in r
    e = db.scalar(select(WaitlistEntry))
    assert (e.day, e.barber_id, e.service_id, e.created_via) == (day, joao.id, corte.id, "bot")
