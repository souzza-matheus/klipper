from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Appointment, ApptStatus, Barber, Customer, OutboxMessage, Service, Shop

JOAO_PHONE = "5531988880001"
PEDRO_PHONE = "5531988880002"


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

    def appt(barber, service, day, price, status=ApptStatus.COMPLETED):
        start = datetime.combine(day, datetime.min.time()).replace(hour=10)
        db.add(Appointment(shop_id=shop.id, customer_id=customer.id, barber_id=barbers[barber].id,
                           service_id=services[service].id, start=start, end=start, price=Decimal(price), status=status))
        db.commit()

    def rule(barber, pct, frm="2026-01-01", to=None, beneficiary=None, service=None):
        body = {"barber_id": barbers[barber].id, "percentage": pct, "valid_from": frm, "valid_to": to,
                "beneficiary_type": "barber" if beneficiary else "shop",
                "beneficiary_barber_id": barbers[beneficiary].id if beneficiary else None,
                "service_id": services[service].id if service else None}
        return c.post("/api/commission-rules", json=body)

    return c, barbers, appt, rule


def report(c, frm="2026-09-01", to="2026-09-30"):
    r = c.get("/api/finance/commissions", params={"date_from": frm, "date_to": to})
    assert r.status_code == 200, r.text
    return {b["barber_name"]: b for b in r.json()["barbers"]}


def test_shop_and_mentor_split(ctx):
    c, barbers, appt, rule = ctx
    assert rule("Pedro", 30).status_code == 200
    assert rule("Pedro", 10, beneficiary="João").status_code == 200
    appt("Pedro", "Corte", date(2026, 9, 10), "40")
    appt("Pedro", "Corte + Barba", date(2026, 9, 11), "65")
    appt("Pedro", "Corte", date(2026, 9, 12), "40", status=ApptStatus.CANCELLED)  # não conta
    appt("Pedro", "Corte", date(2026, 9, 13), "40", status=ApptStatus.SCHEDULED)  # não conta

    pedro = report(c)["Pedro"]
    assert pedro["appointments"] == 2
    assert Decimal(pedro["gross"]) == Decimal("105")
    dues = {d["beneficiary_name"]: d for d in pedro["dues"]}
    assert Decimal(dues["Barbearia"]["amount"]) == Decimal("31.50")
    assert Decimal(dues["João"]["amount"]) == Decimal("10.50")
    assert Decimal(pedro["total_due"]) == Decimal("42.00")
    assert Decimal(pedro["net"]) == Decimal("63.00")
    assert Decimal(pedro["open"]) == Decimal("42.00")
    assert Decimal(report(c)["João"]["received"]) == Decimal("10.50")


def test_total_over_100_is_rejected(ctx):
    c, barbers, appt, rule = ctx
    assert rule("Pedro", 70).status_code == 200
    r = rule("Pedro", 40, beneficiary="João")
    assert r.status_code == 422 and "100%" in r.json()["detail"]
    # Sem sobreposição de datas pode
    assert rule("Pedro", 40, frm="2025-01-01", to="2025-12-31", beneficiary="João").status_code == 200
    # Editar para estourar também é bloqueado
    rid = rule("Pedro", 20, frm="2026-06-01", beneficiary="João").json()["id"]
    body = {"barber_id": barbers["Pedro"].id, "percentage": 50, "valid_from": "2026-06-01",
            "beneficiary_type": "barber", "beneficiary_barber_id": barbers["João"].id}
    assert c.put(f"/api/commission-rules/{rid}", json=body).status_code == 422
    assert Decimal(c.get(f"/api/commission-rules/{rid}").json()["percentage"]) == Decimal("20")


def test_service_rule_overrides_general_for_same_beneficiary(ctx):
    c, barbers, appt, rule = ctx
    assert rule("Pedro", 30).status_code == 200
    assert rule("Pedro", 50, service="Barba").status_code == 200  # 50% só na barba (substitui os 30%)
    assert rule("Pedro", 50, service="Barba", beneficiary="João").status_code == 200  # 50 + 50 = 100: ok
    assert rule("Pedro", 1, service="Barba", beneficiary="João", frm="2026-03-01").status_code == 200  # substitui
    appt("Pedro", "Corte", date(2026, 9, 10), "40")
    appt("Pedro", "Barba", date(2026, 9, 10), "30")
    dues = {d["beneficiary_name"]: d for d in report(c)["Pedro"]["dues"]}
    assert Decimal(dues["Barbearia"]["amount"]) == Decimal("27.00")  # 12 + 15
    assert Decimal(dues["João"]["amount"]) == Decimal("0.30")         # só a barba, regra mais recente (1%)


def test_rule_in_force_on_appointment_date(ctx):
    c, barbers, appt, rule = ctx
    assert rule("Pedro", 40, frm="2026-01-01", to="2026-09-14").status_code == 200
    assert rule("Pedro", 20, frm="2026-09-15").status_code == 200
    appt("Pedro", "Corte", date(2026, 9, 10), "100")
    appt("Pedro", "Corte", date(2026, 9, 20), "100")
    due = report(c)["Pedro"]["dues"][0]
    assert Decimal(due["amount"]) == Decimal("60.00")
    assert sorted(Decimal(p) for p in due["percentages"]) == [Decimal("20"), Decimal("40")]


def test_settlement_reduces_open_and_notifies(ctx, db):
    c, barbers, appt, rule = ctx
    rule("Pedro", 10, beneficiary="João")
    appt("Pedro", "Corte", date(2026, 9, 10), "200")
    body = {"payer_barber_id": barbers["Pedro"].id, "beneficiary_type": "barber",
            "beneficiary_barber_id": barbers["João"].id, "period_start": "2026-09-01",
            "period_end": "2026-09-30", "amount": "15.00"}
    r = c.post("/api/finance/settlements", json=body)
    assert r.status_code == 200, r.text
    pedro = report(c)["Pedro"]
    assert Decimal(pedro["settled"]) == Decimal("15.00")
    assert Decimal(pedro["open"]) == Decimal("5.00")
    hist = c.get("/api/finance/settlements").json()
    assert hist[0]["payer_name"] == "Pedro" and hist[0]["beneficiary_name"] == "João"
    msgs = [m.text for m in db.scalars(select(OutboxMessage))]
    assert any("Acerto registrado" in m for m in msgs)
    phones = {m.phone for m in db.scalars(select(OutboxMessage))}
    assert {PEDRO_PHONE, JOAO_PHONE} <= phones


def test_beneficiary_validation(ctx):
    c, barbers, appt, rule = ctx
    assert rule("Pedro", 10, beneficiary="Pedro").status_code == 422
    body = {"barber_id": barbers["Pedro"].id, "percentage": 10, "valid_from": "2026-01-01", "beneficiary_type": "barber"}
    assert c.post("/api/commission-rules", json=body).status_code == 422
    assert rule("Pedro", 101).status_code == 422
    assert rule("Pedro", 10, frm="2026-05-01", to="2026-04-01").status_code == 422
