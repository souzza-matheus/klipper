"""Permissões por papel em TODAS as rotas da API.

Cada rota cai em um destes grupos (rota nova sem grupo = o dono pode, os outros recebem 403; o teste confere isso
para toda a lista do OpenAPI, então uma rota nova que esqueça a checagem de papel falha aqui).
"""
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from .test_isolation import ROUTE_CASES, all_routes

PUBLIC = {("POST", "/api/auth/login"), ("POST", "/api/auth/register"), ("POST", "/api/auth/token")}

# Qualquer papel (a rota filtra o que o profissional enxerga)
TEAM = {
    ("GET", "/api/me"), ("POST", "/api/auth/refresh"), ("POST", "/api/auth/logout-all"),
    ("POST", "/api/auth/change-password"), ("GET", "/api/shop"), ("GET", "/api/services"), ("GET", "/api/barbers"),
    ("GET", "/api/blocks"), ("GET", "/api/appointments"), ("GET", "/api/agenda/day"),
    ("GET", "/api/appointments/month"), ("PATCH", "/api/appointments/{aid}"),
    ("POST", "/api/appointments/{aid}/check-in"), ("GET", "/api/customers"), ("GET", "/api/customers/{cid}"),
    ("GET", "/api/reviews"), ("GET", "/api/sync/pull"), ("POST", "/api/sync/push"),
}
# Só o profissional (além do dono): as próprias comissões
PRO_ONLY = {("GET", "/api/finance/commissions")}
# Dono e recepção
STAFF = {
    ("POST", "/api/blocks"), ("DELETE", "/api/blocks/{bid}"), ("GET", "/api/availability"),
    ("POST", "/api/appointments"), ("POST", "/api/appointments/{aid}/reschedule"),
    ("POST", "/api/appointments/{aid}/send-pix"), ("PUT", "/api/customers/{cid}"), ("GET", "/api/payments"),
    ("POST", "/api/payments/{pid}/confirm"), ("POST", "/api/payments/{pid}/reject"),
    ("GET", "/api/payments/{pid}/receipt"), ("GET", "/api/approvals"), ("POST", "/api/appointments/{aid}/approve"),
    ("POST", "/api/appointments/{aid}/refuse"), ("GET", "/api/customer-conflicts/day"),
    ("GET", "/api/products"), ("GET", "/api/products/low-stock"), ("POST", "/api/products/{pid}/movements"),
    ("GET", "/api/services/{sid}/consumption"), ("GET", "/api/package-plans"), ("GET", "/api/customers/{cid}/balance"),
    ("GET", "/api/subscription-plans"), ("GET", "/api/subscriptions"), ("POST", "/api/subscriptions"),
    ("POST", "/api/subscriptions/{sid}/cancel"), ("GET", "/api/charges"), ("POST", "/api/charges/{chid}/confirm"),
    ("POST", "/api/charges/{chid}/resend"), ("GET", "/api/comandas"), ("POST", "/api/comandas"),
    ("GET", "/api/comandas/{cid}"), ("POST", "/api/comandas/{cid}/items"),
    ("POST", "/api/comandas/{cid}/items/{iid}/reverse"), ("POST", "/api/comandas/{cid}/payments"),
    ("POST", "/api/comandas/{cid}/payments/{pid}/reverse"), ("POST", "/api/comandas/{cid}/close"),
    ("POST", "/api/comandas/{cid}/cancel"), ("GET", "/api/waitlist"), ("POST", "/api/waitlist"),
    ("DELETE", "/api/waitlist/{wid}"), ("GET", "/api/receipts/{rid}"), ("GET", "/api/receipts/{rid}/file"),
    ("POST", "/api/receipts/{rid}/confirm"), ("POST", "/api/receipts/{rid}/reject"),
}


# Encerram a própria sessão: testadas à parte (no meio da varredura derrubariam o token)
SESSION_ENDERS = {("POST", "/api/auth/logout-all"), ("POST", "/api/auth/change-password")}


def _api_routes():
    return sorted((m, p) for m, p in all_routes()
                  if p.startswith("/api/") and (m, p) not in PUBLIC | SESSION_ENDERS)


def _own_view(two):
    """Os casos de ROUTE_CASES montam a URL com os dados de B; aqui queremos os dados de A (a própria loja)."""
    return SimpleNamespace(a=two.b, b=two.a, db=two.db)


def _url(two, method, path):
    case = ROUTE_CASES.get((method, path))
    if case:
        return path.format(**case[0](_own_view(two)))
    return re.sub(r"\{[^}]+\}", "1", path)


def _login(two, email, password) -> TestClient:
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c


@pytest.mark.parametrize("role", ["reception", "pro"])
def test_every_route_checks_the_role(two, role):
    user = two.a.extra[role]
    client = _login(two, user.email, two.a.extra[f"{role}_password"])
    allowed = TEAM | (STAFF if role == "reception" else PRO_ONLY)
    wrong = []
    for method, path in _api_routes():
        r = client.request(method, _url(two, method, path), json={})
        denied = r.status_code == 403
        if (method, path) in allowed and denied:
            wrong.append(f"{method} {path}: deveria liberar, deu 403 {r.text[:120]}")
        if (method, path) not in allowed and not denied:
            wrong.append(f"{method} {path}: deveria dar 403, deu {r.status_code}")
    assert not wrong, f"{role}:\n" + "\n".join(wrong)


def test_owner_is_never_forbidden(two):
    for method, path in _api_routes():
        r = two.ca.request(method, _url(two, method, path), json={})
        assert r.status_code != 403 or "senha" in r.text.lower() or "um dono" in r.text, \
            f"{method} {path}: {r.status_code} {r.text[:120]}"


def test_known_groups_only_list_real_routes():
    routes = set(_api_routes()) | SESSION_ENDERS
    assert not (TEAM | STAFF | PRO_ONLY) - routes


@pytest.mark.parametrize("role", ["reception", "pro"])
def test_any_role_can_end_its_own_sessions(two, role):
    user = two.a.extra[role]
    c = _login(two, user.email, two.a.extra[f"{role}_password"])
    assert c.post("/api/auth/logout-all").status_code == 200
    assert c.get("/api/me").status_code == 401


def test_professional_sees_only_own_agenda_customers_and_commissions(two):
    a = two.a
    pro = _login(two, a.extra["pro"].email, a.extra["pro_password"])
    other = a.extra["second_barber"]
    # Um agendamento do outro profissional, com um cliente que o profissional nunca atendeu
    from datetime import datetime, time, timedelta
    from app.models import Appointment, Customer
    stranger = Customer(shop_id=a.shop.id, phone="5531977770000", name="Cliente Só do Padrinho")
    two.db.add(stranger)
    two.db.flush()
    day = a.appt.start.date()
    start = datetime.combine(day, time(15))
    two.db.add(Appointment(shop_id=a.shop.id, customer_id=stranger.id, barber_id=other.id, service_id=a.service.id,
                           start=start, end=start + timedelta(minutes=30), price=a.service.price))
    two.db.commit()

    appts = pro.get("/api/appointments", params={"date_from": "2026-01-01", "date_to": "2027-12-31"}).json()
    assert appts and {x["barber_id"] for x in appts} == {a.barber.id}
    # Mesmo pedindo a agenda do outro, recebe a própria
    appts = pro.get("/api/appointments", params={"date_from": "2026-01-01", "date_to": "2027-12-31",
                                                 "barber_id": other.id}).json()
    assert {x["barber_id"] for x in appts} == {a.barber.id}
    cols = pro.get("/api/agenda/day", params={"day": day.isoformat()}).json()["barbers"]
    assert [c["id"] for c in cols] == [a.barber.id]
    names = [c["name"] for c in pro.get("/api/customers", params={"limit": 200}).json()]
    assert "Cliente Só do Padrinho" not in names and a.customer.name in names
    assert pro.get(f"/api/customers/{stranger.id}").status_code == 404
    detail = pro.get(f"/api/customers/{a.customer.id}").json()
    assert detail["balance"] is None  # saldo e financeiro do cliente: não para o profissional
    stranger_appt = two.db.query(Appointment).filter_by(customer_id=stranger.id).one()
    assert pro.patch(f"/api/appointments/{stranger_appt.id}", json={"status": "completed"}).status_code == 404
    assert pro.patch(f"/api/appointments/{a.appt.id}", json={"price": "1"}).status_code == 403
    assert pro.patch(f"/api/appointments/{a.appt.id}", json={"status": "cancelled"}).status_code == 403
    rep = pro.get("/api/finance/commissions", params={"date_from": "2026-01-01", "date_to": "2027-12-31"}).json()
    assert {b["barber_id"] for b in rep["barbers"]} <= {a.barber.id}


def test_reception_sees_products_without_cost(two):
    rec = _login(two, two.a.extra["reception"].email, two.a.extra["reception_password"])
    prods = rec.get("/api/products").json()
    assert prods and all(p["cost"] is None for p in prods)
    assert all(p["cost"] is not None for p in two.ca.get("/api/products").json())
    # Recepção registra uso interno, mas não entrada nem ajuste
    pid = two.a.extra["product"].id
    assert rec.post(f"/api/products/{pid}/movements", json={"delta": "1", "reason": "internal"}).status_code == 200
    assert rec.post(f"/api/products/{pid}/movements", json={"delta": "1", "reason": "purchase"}).status_code == 403


def test_invited_user_must_change_password_first(two):
    r = two.ca.post("/api/users", json={"name": "Nova Recepção", "email": "nova@exemplo.com", "role": "reception"})
    assert r.status_code == 200
    temp = r.json()["provisional_password"]
    assert len(temp) >= 12 and r.json()["user"]["first_login"] is True
    c = _login(two, "nova@exemplo.com", temp)
    assert c.get("/api/me").json()["first_login"] is True
    assert c.get("/api/appointments", params={"date_from": "2026-10-01"}).status_code == 403
    assert c.post("/api/auth/change-password", json={"current_password": "errada", "new_password": "x" * 10}
                  ).status_code == 401
    r = c.post("/api/auth/change-password", json={"current_password": temp, "new_password": "senha-nova-123"})
    assert r.status_code == 200 and r.json()["first_login"] is False
    old = c.headers["Authorization"]
    assert c.get("/api/me").status_code == 401  # o token de antes da troca não vale mais
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert c.get("/api/appointments", params={"date_from": "2026-10-01"}).status_code == 200
    assert old != c.headers["Authorization"]


def test_role_change_and_deactivation_take_effect_now(two):
    rec = two.a.extra["reception"]
    c = _login(two, rec.email, two.a.extra["reception_password"])
    assert two.ca.put(f"/api/users/{rec.id}", json={"active": False}).status_code == 200
    assert c.get("/api/me").status_code == 401
    r = TestClient(c.app).post("/api/auth/login", json={"email": rec.email,
                                                        "password": two.a.extra["reception_password"]})
    assert r.status_code == 401  # desativado: mesma resposta de senha errada


def test_last_owner_cannot_be_removed_and_pro_needs_a_barber(two):
    from app.models import User
    owner = two.db.query(User).filter_by(email=two.a.user_email).one()
    assert two.ca.put(f"/api/users/{owner.id}", json={"role": "reception"}).status_code == 409
    assert two.ca.put(f"/api/users/{owner.id}", json={"active": False}).status_code == 409
    r = two.ca.post("/api/users", json={"name": "Pro", "email": "pro2@exemplo.com", "role": "professional"})
    assert r.status_code == 422
