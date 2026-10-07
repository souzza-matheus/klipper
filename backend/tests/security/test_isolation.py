"""Isolamento entre barbearias: com o token de A, nada de B pode ser lido, alterado ou apagado.

Os casos cobrem TODAS as rotas com {id}: test_every_id_route_is_covered falha se surgir uma rota nova sem caso aqui.
"""
from datetime import datetime, timedelta

import pytest

from app.main import app
from app.models import (
    Appointment, Barber, Block, CommissionRule, CommissionSettlement, Customer, CustomerConflict, Expense, Payment,
    Service,
)

from .conftest import B_MARK, no_leak

FUTURE = (datetime.now() + timedelta(days=9)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def rule_body(t):
    return {"barber_id": t.a.barber.id, "beneficiary_type": "shop", "percentage": "10", "valid_from": "2026-01-01"}


# (método, rota) -> (função que dá os parâmetros de caminho a partir de B, corpo válido ou None)
ROUTE_CASES = {
    ("PUT", "/api/services/{sid}"): (lambda t: {"sid": t.b.service.id},
                                     lambda t: {"name": "invadido", "duration_minutes": 30, "price": "1"}),
    ("DELETE", "/api/services/{sid}"): (lambda t: {"sid": t.b.service.id}, None),
    ("PUT", "/api/barbers/{bid}"): (lambda t: {"bid": t.b.barber.id}, lambda t: {"name": "invadido"}),
    ("DELETE", "/api/barbers/{bid}"): (lambda t: {"bid": t.b.barber.id}, None),
    ("DELETE", "/api/blocks/{bid}"): (lambda t: {"bid": t.b.block.id}, None),
    ("PATCH", "/api/appointments/{aid}"): (lambda t: {"aid": t.b.appt.id}, lambda t: {"status": "cancelled"}),
    ("POST", "/api/appointments/{aid}/reschedule"): (lambda t: {"aid": t.b.appt.id}, lambda t: {"start": FUTURE}),
    ("POST", "/api/appointments/{aid}/send-pix"): (lambda t: {"aid": t.b.appt.id}, None),
    ("POST", "/api/appointments/{aid}/approve"): (lambda t: {"aid": t.b.pending_appt.id}, None),
    ("POST", "/api/appointments/{aid}/refuse"): (lambda t: {"aid": t.b.pending_appt.id}, None),
    ("GET", "/api/customers/{cid}"): (lambda t: {"cid": t.b.customer.id}, None),
    ("PUT", "/api/customers/{cid}"): (lambda t: {"cid": t.b.customer.id}, lambda t: {"name": "invadido"}),
    ("PUT", "/api/customers/{cid}/access"): (lambda t: {"cid": t.b.customer.id},
                                             lambda t: {"access_status": "blocked", "access_reason": "x"}),
    ("POST", "/api/payments/{pid}/confirm"): (lambda t: {"pid": t.b.payment.id}, None),
    ("POST", "/api/payments/{pid}/reject"): (lambda t: {"pid": t.b.payment.id}, None),
    ("GET", "/api/payments/{pid}/receipt"): (lambda t: {"pid": t.b.payment.id}, None),
    ("GET", "/api/commission-rules/{rid}"): (lambda t: {"rid": t.b.rule.id}, None),
    ("PUT", "/api/commission-rules/{rid}"): (lambda t: {"rid": t.b.rule.id}, rule_body),
    ("DELETE", "/api/commission-rules/{rid}"): (lambda t: {"rid": t.b.rule.id}, None),
    ("DELETE", "/api/finance/settlements/{sid}"): (lambda t: {"sid": t.b.settlement.id}, None),
    ("GET", "/api/expenses/{eid}"): (lambda t: {"eid": t.b.expense.id}, None),
    ("PUT", "/api/expenses/{eid}"): (lambda t: {"eid": t.b.expense.id},
                                     lambda t: {"description": "invadido", "amount": "1", "due_date": "2026-10-01"}),
    ("DELETE", "/api/expenses/{eid}"): (lambda t: {"eid": t.b.expense.id}, None),
    ("POST", "/api/expenses/{eid}/pay"): (lambda t: {"eid": t.b.expense.id}, lambda t: {}),
    ("GET", "/api/customer-conflicts/{conf_id}"): (lambda t: {"conf_id": t.b.conflict.id}, None),
    ("PUT", "/api/customer-conflicts/{conf_id}"): (lambda t: {"conf_id": t.b.conflict.id},
                                                   lambda t: {"min_gap_minutes": 0, "notes": "invadido"}),
    ("DELETE", "/api/customer-conflicts/{conf_id}"): (lambda t: {"conf_id": t.b.conflict.id}, None),
}


def all_routes() -> set[tuple[str, str]]:
    """(método, rota) de todas as rotas, pelo schema OpenAPI (interface pública; não depende de internals)."""
    paths = app.openapi()["paths"]
    out = {(m.upper(), p) for p, ops in paths.items() for m in ops if m in ("get", "post", "put", "patch", "delete")}
    assert len(out) > 60, f"só {len(out)} rotas encontradas: a listagem de rotas quebrou"
    return out


def _id_routes() -> set[tuple[str, str]]:
    return {(m, p) for m, p in all_routes() if "{" in p}


def test_every_id_route_is_covered():
    """Rota nova com {id} sem caso de isolamento aqui = teste falha (adicione em ROUTE_CASES)."""
    routes = _id_routes()
    assert len(routes) >= len(ROUTE_CASES)
    missing = routes - set(ROUTE_CASES) - {("POST", "/webhook/evolution/{event}")}
    assert not missing, f"Rotas com id sem teste de isolamento: {sorted(missing)}"


def _snapshot(t):
    db = t.db
    db.expire_all()
    b = t.b
    return {
        "service": (db.get(Service, b.service.id).name, db.get(Service, b.service.id).active),
        "barber": (db.get(Barber, b.barber.id).name, db.get(Barber, b.barber.id).active),
        "block": db.get(Block, b.block.id) is not None,
        "appt": (db.get(Appointment, b.appt.id).status, db.get(Appointment, b.appt.id).start),
        "pending": db.get(Appointment, b.pending_appt.id).status,
        "customer": (db.get(Customer, b.customer.id).name, db.get(Customer, b.customer.id).access_status),
        "payment": db.get(Payment, b.payment.id).status,
        "rule": db.get(CommissionRule, b.rule.id) is not None,
        "settlement": db.get(CommissionSettlement, b.settlement.id) is not None,
        "expense": (db.get(Expense, b.expense.id).description, db.get(Expense, b.expense.id).paid_at),
        "conflict": (db.get(CustomerConflict, b.conflict.id).notes if db.get(CustomerConflict, b.conflict.id) else None),
    }


@pytest.mark.parametrize("method,path", sorted(ROUTE_CASES))
def test_shop_a_cannot_touch_shop_b(two, method, path):
    params, body = ROUTE_CASES[(method, path)]
    before = _snapshot(two)
    url = path.format(**params(two))
    r = two.ca.request(method, url, json=body(two) if body else None)
    assert r.status_code == 404, f"{method} {url}: {r.status_code} {r.text[:200]}"
    assert no_leak(r.text, two.b)
    assert _snapshot(two) == before, f"{method} {url} alterou dados da barbearia B"


@pytest.mark.parametrize("method,path", sorted(ROUTE_CASES))
def test_owner_can_use_the_same_route_on_its_own_data(two, method, path):
    """Controle: com o token de B, a mesma rota NÃO dá 404 (o 404 acima é isolamento, não rota quebrada)."""
    params, body = ROUTE_CASES[(method, path)]
    payload = body(two) if body else None
    if payload and "barber_id" in payload:  # o corpo do caso usa o barbeiro de A; aqui, o de B
        payload = {**payload, "barber_id": two.b.barber.id}
    r = two.cb.request(method, path.format(**params(two)), json=payload)
    assert r.status_code != 404, f"{method} {path}: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------- criar recursos com ids da outra barbearia

def cross_cases(t):
    a, b = t.a, t.b
    day = FUTURE[:10]
    return [
        ("POST", "/api/appointments", {"customer_phone": "31977776666", "barber_id": b.barber.id,
                                       "service_id": a.service.id, "start": FUTURE}),
        ("POST", "/api/appointments", {"customer_phone": "31977776666", "barber_id": a.barber.id,
                                       "service_id": b.service.id, "start": FUTURE}),
        ("POST", f"/api/appointments/{a.appt.id}/reschedule", {"start": FUTURE, "barber_id": b.barber.id}),
        ("POST", "/api/blocks", {"barber_id": b.barber.id, "start": FUTURE, "end": FUTURE[:11] + "11:00:00"}),
        ("POST", "/api/commission-rules", {**rule_body(t), "barber_id": b.barber.id}),
        ("POST", "/api/commission-rules", {**rule_body(t), "beneficiary_type": "barber",
                                           "beneficiary_barber_id": b.barber.id}),
        ("POST", "/api/commission-rules", {**rule_body(t), "service_id": b.service.id}),
        ("POST", "/api/finance/settlements", {"payer_barber_id": b.barber.id, "beneficiary_type": "shop",
                                              "period_start": "2026-09-01", "period_end": "2026-09-30",
                                              "amount": "10"}),
        ("POST", "/api/finance/settlements", {"payer_barber_id": a.barber.id, "beneficiary_type": "barber",
                                              "beneficiary_barber_id": b.barber.id, "period_start": "2026-09-01",
                                              "period_end": "2026-09-30", "amount": "10"}),
        ("POST", "/api/expenses", {"description": "x", "amount": "10", "due_date": day, "barber_id": b.barber.id}),
        ("POST", "/api/customer-conflicts", {"customer_id": b.customer.id, "other_customer_id": b.other_customer.id}),
        ("POST", "/api/customer-conflicts", {"customer_id": a.customer.id, "other_customer_id": b.customer.id}),
        ("GET", f"/api/availability?service_id={b.service.id}&day={day}", None),
        ("GET", f"/api/availability?service_id={a.service.id}&day={day}&barber_id={b.barber.id}", None),
        ("GET", f"/api/availability?service_id={a.service.id}&day={day}&customer_id={b.customer.id}", None),
        ("GET", f"/api/appointments/month?year=2026&month=10&barber_id={b.barber.id}", None),
        ("GET", f"/api/customer-conflicts?customer_id={b.customer.id}", None),
        ("GET", f"/api/customer-conflicts/day?day={day}&customer_id={b.customer.id}", None),
    ]


def test_cannot_create_or_query_with_other_shop_ids(two):
    from sqlalchemy import func, select
    count = lambda m: two.db.scalar(select(func.count()).select_from(m))  # noqa: E731
    before = {m: count(m) for m in (Appointment, Block, CommissionRule, CommissionSettlement, Expense, CustomerConflict)}
    for method, url, body in cross_cases(two):
        r = two.ca.request(method, url, json=body)
        assert r.status_code in (404, 422), f"{method} {url}: {r.status_code} {r.text[:200]}"
        assert no_leak(r.text, two.b)
    two.db.expire_all()
    assert {m: count(m) for m in before} == before


def test_barber_cannot_be_linked_to_other_shop_service(two):
    r = two.ca.post("/api/barbers", json={"name": "Novo", "service_ids": [two.b.service.id, two.a.service.id]})
    assert r.status_code == 200 and r.json()["service_ids"] == [two.a.service.id]
    r = two.ca.put(f"/api/barbers/{two.a.barber.id}", json={"name": "Barbeiro AAA", "service_ids": [two.b.service.id]})
    assert r.json()["service_ids"] == []


# ---------------------------------------------------------------- listas, relatórios e exportação

def list_urls(t):
    day = t.a.appt.start.date().isoformat()
    month = day[:7]
    return [
        "/api/me", "/api/shop", "/api/services", "/api/barbers", "/api/blocks",
        "/api/appointments?date_from=2026-01-01&date_to=2026-12-31&include_cancelled=true",
        f"/api/agenda/day?day={day}", f"/api/agenda/day?day={t.b.appt.start.date().isoformat()}",
        f"/api/appointments/month?year={day[:4]}&month={int(day[5:7])}", "/api/customers?limit=200",
        "/api/customers?q=ZZB", "/api/customers?q=1111", "/api/payments", "/api/payments?status=pending",
        "/api/reviews", "/api/reports/summary?date_from=2026-01-01&date_to=2026-12-31", "/api/commission-rules",
        "/api/finance/commissions?date_from=2026-01-01&date_to=2026-12-31", "/api/finance/settlements",
        f"/api/expenses?month={month}", "/api/expenses",
        "/api/finance/summary?date_from=2026-01-01&date_to=2026-12-31",
        "/api/finance/daily?date_from=2026-09-01&date_to=2026-12-31",
        "/api/finance/export.csv?date_from=2026-01-01&date_to=2026-12-31", "/api/approvals",
        "/api/customer-conflicts", "/api/ai/settings", "/api/ai/usage",
    ]


def test_lists_reports_and_exports_only_show_own_data(two):
    for url in list_urls(two):
        r = two.ca.get(url)
        assert r.status_code == 200, f"{url}: {r.status_code} {r.text[:200]}"
        assert no_leak(r.text, two.b), f"{url} vazou dados da barbearia B"
    # Controle: B enxerga os próprios dados nas mesmas rotas
    assert B_MARK in two.cb.get("/api/customers").text
    assert B_MARK in two.cb.get("/api/finance/export.csv?date_from=2026-01-01&date_to=2026-12-31").text


def test_agenda_of_a_day_has_only_own_professionals(two):
    day = two.b.appt.start.date().isoformat()
    names = [b["name"] for b in two.ca.get(f"/api/agenda/day?day={day}").json()["barbers"]]
    assert names and all(B_MARK not in n for n in names)
