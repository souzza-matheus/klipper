from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.models import (
    Appointment, ApptStatus, Barber, Block, Customer, Expense, OutboxMessage, PayStatus, Service, Shop,
)


@pytest.fixture()
def ctx(db):
    from app.main import app
    c = TestClient(app)
    token = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    shop = db.scalar(select(Shop))
    barbers = {b.name: b for b in db.scalars(select(Barber))}
    services = {s.name: s for s in db.scalars(select(Service))}
    customer = Customer(shop_id=shop.id, phone="5531977776666", name="Carlos")
    db.add(customer)
    db.commit()

    def appt(barber, service, day, price=None, status=ApptStatus.COMPLETED, hour=10, **kw):
        svc = services[service]
        start = datetime.combine(day, time(hour))
        a = Appointment(shop_id=shop.id, customer_id=customer.id, barber_id=barbers[barber].id, service_id=svc.id,
                        start=start, end=start + timedelta(minutes=svc.duration_minutes),
                        price=Decimal(price) if price else svc.price, status=status, **kw)
        db.add(a)
        db.commit()
        return a

    def expense(description, amount, due, paid_at=None, category="outros", recurring=False):
        body = {"description": description, "amount": amount, "due_date": str(due), "category": category,
                "paid_at": str(paid_at) if paid_at else None, "recurring": recurring}
        r = c.post("/api/expenses", json=body)
        assert r.status_code == 200, r.text
        return r.json()

    return c, shop, barbers, appt, expense


# ---------------------------------------------------------------- forma de pagamento ao concluir

def test_complete_with_payment_method_and_final_price(ctx):
    c, shop, barbers, appt, expense = ctx
    a = appt("Pedro", "Corte + Barba", date(2026, 9, 10), status=ApptStatus.CONFIRMED)
    r = c.patch(f"/api/appointments/{a.id}", json={"status": "completed", "payment_method": "dinheiro", "price": "60.00"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["payment_method"] == "dinheiro"
    assert Decimal(r.json()["price"]) == Decimal("60.00")
    # Forma de pagamento inválida é rejeitada
    assert c.patch(f"/api/appointments/{a.id}", json={"payment_method": "cheque"}).status_code == 422
    # Comissão usa o valor final cobrado
    c.post("/api/commission-rules", json={"barber_id": barbers["Pedro"].id, "percentage": 50, "valid_from": "2026-01-01",
                                          "beneficiary_type": "shop"})
    rep = c.get("/api/finance/commissions", params={"date_from": "2026-09-01", "date_to": "2026-09-30"}).json()
    assert Decimal(rep["barbers"][0]["total_due"]) == Decimal("30.00")


def test_pix_paid_by_bot_fills_method_automatically(ctx):
    c, shop, barbers, appt, expense = ctx
    a = appt("João", "Corte", date(2026, 9, 10), status=ApptStatus.SCHEDULED, payment_status=PayStatus.PAID)
    r = c.patch(f"/api/appointments/{a.id}", json={"status": "completed"})
    assert r.json()["payment_method"] == "pix"
    # Sem Pix pago, fica "não informado"
    b = appt("João", "Corte", date(2026, 9, 11), status=ApptStatus.SCHEDULED)
    assert c.patch(f"/api/appointments/{b.id}", json={"status": "completed"}).json()["payment_method"] is None


# ---------------------------------------------------------------- gastos

def test_expenses_crud_filters_and_pay(ctx):
    c, shop, barbers, appt, expense = ctx
    rent = expense("Aluguel", "1500.00", date(2026, 10, 5), category="aluguel")
    light = expense("Luz", "300.00", date(2026, 10, 15), paid_at=date(2026, 10, 14), category="energia")
    expense("Fora do mês", "10.00", date(2026, 11, 1))
    assert rent["category_label"] == "Aluguel" and rent["paid_at"] is None

    month = lambda **q: [e["description"] for e in c.get("/api/expenses", params={"month": "2026-10", **q}).json()]  # noqa: E731
    assert month() == ["Aluguel", "Luz"]
    assert month(status="paid") == ["Luz"]
    assert month(status="open") == ["Aluguel"]
    assert month(category="energia") == ["Luz"]
    assert c.get("/api/expenses", params={"month": "2026-13"}).status_code == 422

    r = c.post(f"/api/expenses/{rent['id']}/pay", json={"paid_at": "2026-10-06", "payment_method": "pix"})
    assert r.status_code == 200 and r.json()["paid_at"] == "2026-10-06" and r.json()["payment_method"] == "pix"
    assert month(status="open") == []

    body = {**{k: light[k] for k in ("description", "category", "due_date", "notes")}, "amount": "320.00", "paid_at": None}
    r = c.put(f"/api/expenses/{light['id']}", json=body)
    assert Decimal(r.json()["amount"]) == Decimal("320.00") and r.json()["paid_at"] is None
    assert c.delete(f"/api/expenses/{light['id']}").json()["ok"]
    assert month() == ["Aluguel"]
    assert c.post("/api/expenses", json={"description": "X", "amount": 0, "due_date": "2026-10-01"}).status_code == 422


def test_overdue_flag(ctx):
    from app.config import now_local
    c, shop, barbers, appt, expense = ctx
    today = now_local().date()
    late = expense("Vencida", "50.00", today - timedelta(days=1))
    expense("Vence hoje", "50.00", today)
    assert late["overdue"] is True
    ids = [e["id"] for e in c.get("/api/expenses", params={"status": "overdue"}).json()]
    assert ids == [late["id"]]


def test_recurring_expenses_generated_once_per_month(ctx, db):
    c, shop, barbers, appt, expense = ctx
    src = expense("Aluguel", "1500.00", date(2026, 1, 31), paid_at=date(2026, 1, 31), category="aluguel", recurring=True)
    expense("Avulso", "20.00", date(2026, 1, 10))

    for _ in range(3):  # abrir o mês várias vezes não duplica
        feb = c.get("/api/expenses", params={"month": "2026-02"}).json()
    assert [(e["description"], e["due_date"], e["paid_at"], e["recurring_source_id"]) for e in feb] == [
        ("Aluguel", "2026-02-28", None, src["id"])]  # dia 31 vira o último dia de fevereiro
    mar = c.get("/api/expenses", params={"month": "2026-03"}).json()
    assert [e["due_date"] for e in mar] == ["2026-03-31"]
    # O resumo também gera os meses do período, sem duplicar o que já existe
    c.get("/api/finance/summary", params={"date_from": "2026-02-01", "date_to": "2026-04-30"})
    copies = db.scalars(select(Expense).where(Expense.recurring_source_id == src["id"]).order_by(Expense.due_date)).all()
    assert [e.due_date for e in copies] == [date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    # Meses antes do original não recebem cópia
    assert c.get("/api/expenses", params={"month": "2025-12"}).json() == []

    # Uma cópia editada como "recorrente" não vira uma segunda recorrência
    copy = feb[0]
    body = {k: copy[k] for k in ("description", "category", "amount", "due_date", "notes")}
    assert c.put(f"/api/expenses/{copy['id']}", json={**body, "recurring": True}).json()["recurring"] is False
    # Desligar a recorrência do original para de gerar os meses seguintes
    body = {k: src[k] for k in ("description", "category", "amount", "due_date", "paid_at", "notes")}
    c.put(f"/api/expenses/{src['id']}", json={**body, "recurring": False})
    assert c.get("/api/expenses", params={"month": "2026-06"}).json() == []


def test_expenses_isolated_by_shop(ctx, db):
    c, shop, barbers, appt, expense = ctx
    other = Shop(name="Outra", evolution_instance="outra")
    db.add(other)
    db.flush()
    e = Expense(shop_id=other.id, description="Segredo", amount=Decimal("1"), due_date=date(2026, 10, 1))
    db.add(e)
    db.commit()
    assert c.get(f"/api/expenses/{e.id}").status_code == 404
    assert c.post(f"/api/expenses/{e.id}/pay").status_code == 404
    assert c.get("/api/expenses", params={"month": "2026-10"}).json() == []


# ---------------------------------------------------------------- relatórios

def test_finance_summary_and_comparison(ctx):
    c, shop, barbers, appt, expense = ctx
    # Setembro (30 dias); o período anterior de mesmo tamanho é 02/08 a 31/08
    appt("João", "Corte", date(2026, 9, 2), payment_method="pix")
    appt("Pedro", "Corte + Barba", date(2026, 9, 3), price="60", payment_method="dinheiro")
    appt("Pedro", "Barba", date(2026, 9, 4))
    appt("Pedro", "Corte", date(2026, 9, 5), status=ApptStatus.SCHEDULED)  # não conta
    appt("Pedro", "Corte", date(2026, 9, 6), status=ApptStatus.CANCELLED)  # não conta
    appt("João", "Corte", date(2026, 8, 15), price="50")
    appt("João", "Corte", date(2026, 8, 1), price="999")  # fora dos dois períodos
    expense("Aluguel", "100.00", date(2026, 9, 5), paid_at=date(2026, 9, 5), category="aluguel")
    expense("Luz", "50.00", date(2026, 9, 20), category="energia")
    expense("Produtos", "200.00", date(2026, 8, 10), paid_at=date(2026, 8, 10), category="produtos")
    expense("Paga em agosto, vence em setembro", "25.00", date(2026, 9, 1), paid_at=date(2026, 8, 30))

    r = c.get("/api/finance/summary", params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert r.status_code == 200, r.text
    d = r.json()
    D = Decimal
    assert D(d["revenue"]) == D("130.00")
    assert d["appointments"] == 3
    assert D(d["avg_ticket"]) == D("43.33")
    assert D(d["expenses_paid"]) == D("100.00")
    assert D(d["expenses_open"]) == D("50.00")
    assert D(d["profit"]) == D("30.00")
    assert {g["name"]: D(g["revenue"]) for g in d["by_barber"]} == {"Pedro": D("90.00"), "João": D("40.00")}
    assert {g["name"]: g["appointments"] for g in d["by_service"]} == {"Corte + Barba": 1, "Corte": 1, "Barba": 1}
    assert {g["method"]: D(g["revenue"]) for g in d["by_payment_method"]} == {
        "dinheiro": D("60.00"), "pix": D("40.00"), "nao_informado": D("30.00")}
    cats = {g["category"]: (D(g["paid"]), D(g["open"])) for g in d["expenses_by_category"]}
    assert cats == {"aluguel": (D("100.00"), D("0.00")), "energia": (D("0.00"), D("50.00"))}

    prev = d["previous"]
    assert (prev["date_from"], prev["date_to"]) == ("2026-08-02", "2026-08-31")
    assert D(prev["revenue"]) == D("50.00") and D(prev["expenses_paid"]) == D("225.00")
    ch = {k: (D(v) if v is not None else None) for k, v in d["change"].items()}
    assert ch["revenue"] == D("160.0")
    assert ch["appointments"] == D("200.0")
    assert ch["expenses_paid"] == D("-55.6")
    assert ch["profit"] == D("117.1")  # de -175 para +30
    assert ch["avg_ticket"] == D("-13.3")

    # Sem movimento no período anterior, não há base de comparação
    d = c.get("/api/finance/summary", params={"date_from": "2026-07-01", "date_to": "2026-07-31"}).json()
    assert d["change"]["revenue"] is None
    assert c.get("/api/finance/summary", params={"date_from": "2026-09-30", "date_to": "2026-09-01"}).status_code == 422


def test_finance_daily_series(ctx):
    c, shop, barbers, appt, expense = ctx
    appt("João", "Corte", date(2026, 9, 2))
    appt("Pedro", "Barba", date(2026, 9, 2))
    expense("Produtos", "80.00", date(2026, 9, 1), paid_at=date(2026, 9, 3))
    days = c.get("/api/finance/daily", params={"date_from": "2026-09-01", "date_to": "2026-09-04"}).json()
    assert [(x["date"], Decimal(x["revenue"]), Decimal(x["expenses"]), x["appointments"]) for x in days] == [
        ("2026-09-01", 0, 0, 0), ("2026-09-02", 70, 0, 2), ("2026-09-03", 0, 80, 0), ("2026-09-04", 0, 0, 0)]


def test_export_csv_for_excel(ctx):
    c, shop, barbers, appt, expense = ctx
    appt("João", "Corte + Barba", date(2026, 9, 2), price="1234.5", payment_method="credito")
    expense("Conta de água", "95.90", date(2026, 9, 15), category="agua")
    r = c.get("/api/finance/export.csv", params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "financeiro_2026-09-01_2026-09-30.csv" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    lines = r.content.decode("utf-8-sig").splitlines()
    assert "02/09/2026 10:00;Carlos;João;Corte + Barba;Crédito;1234,50" in lines
    assert "15/09/2026;Conta de água;Água;;Em aberto;;;95,90;" in lines
    assert "Total;;;;;1234,50" in lines


# ---------------------------------------------------------------- agenda do mês

def test_month_overview(ctx, db):
    c, shop, barbers, appt, expense = ctx
    # Novembro de 2026: dia 1 é domingo (sem expediente), dia 2 é segunda
    mon, tue = date(2026, 11, 2), date(2026, 11, 3)
    appt("João", "Corte", mon, status=ApptStatus.SCHEDULED, hour=9)
    appt("João", "Barba", mon, status=ApptStatus.COMPLETED, hour=10)
    appt("João", "Corte", mon, status=ApptStatus.NO_SHOW, hour=11)
    appt("João", "Corte", mon, status=ApptStatus.CANCELLED, hour=14)
    appt("Pedro", "Corte + Barba", mon, status=ApptStatus.CONFIRMED, hour=9)
    db.add(Block(shop_id=shop.id, barber_id=None, start=datetime.combine(tue, time(13)),
                 end=datetime.combine(tue, time(19)), reason="Reunião"))
    db.commit()

    queries = []
    from app.db import engine
    listener = lambda *a: queries.append(1)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        r = c.get("/api/appointments/month", params={"year": 2026, "month": 11})
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert r.status_code == 200, r.text
    assert len(queries) <= 8  # login/usuário + poucas consultas, não uma por dia
    days = {x["date"]: x for x in r.json()["days"]}
    assert len(days) == 30

    sun = days["2026-11-01"]
    assert sun["working"] is False and sun["total"] == 0 and sun["occupancy"] == 0
    m = days["2026-11-02"]
    # Seg a sex: 2 barbeiros x 9 h = 1080 min / duração média 40 min = 27 atendimentos
    assert (m["total"], m["cancelled"], m["capacity"]) == (4, 1, 27.0)
    assert Decimal(m["revenue_expected"]) == Decimal("135.00")  # 40 + 30 + 65 (a falta não conta)
    assert m["occupancy"] == round(4 / 27, 2) and m["has_block"] is False
    t = days["2026-11-03"]
    assert t["has_block"] is True and t["capacity"] == 9.0  # tarde bloqueada: 2 x 180 min / 40
    assert days["2026-11-07"]["capacity"] == 9.0  # sábado só de manhã

    joao = {x["date"]: x for x in c.get("/api/appointments/month",
                                        params={"year": 2026, "month": 11, "barber_id": barbers["João"].id}).json()["days"]}
    assert (joao["2026-11-02"]["total"], joao["2026-11-02"]["capacity"]) == (3, 13.5)
    assert c.get("/api/appointments/month", params={"year": 2026, "month": 13}).status_code == 422


# ---------------------------------------------------------------- resumo diário no WhatsApp

def test_daily_summary_warns_about_bills(ctx, db):
    from app.config import now_local
    from app.jobs import send_daily_summary
    c, shop, barbers, appt, expense = ctx
    today = now_local().date()
    expense("Aluguel", "1500.00", today, category="aluguel")
    expense("Luz", "300.00", today - timedelta(days=3), category="energia")
    expense("Paga", "10.00", today - timedelta(days=3), paid_at=today)
    expense("Futura", "10.00", today + timedelta(days=3))
    shop = db.get(Shop, shop.id)
    shop.daily_summary_hour, shop.last_summary_date = 0, None
    assert send_daily_summary(db, shop)
    db.commit()
    text = db.scalars(select(OutboxMessage).order_by(OutboxMessage.id.desc())).first().text
    assert "Contas a pagar" in text
    assert "Aluguel (Aluguel) - R$ 1.500,00 · vence hoje" in text
    assert f"Luz (Energia) - R$ 300,00 · venceu {today - timedelta(days=3):%d/%m}" in text
    assert "Paga" not in text and "Futura" not in text
    assert "Total: *R$ 1.800,00*" in text
