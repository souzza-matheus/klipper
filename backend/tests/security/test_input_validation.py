"""Atribuição em massa, validação de entrada (números, datas, strings enormes, SQL injection) e BR Code do Pix."""
import pytest
from sqlalchemy import select

from app.models import Shop
from app.services.pix import build_brcode, crc16_ccitt, valid_pix_key

from .conftest import no_leak


def test_shop_update_cannot_change_internal_fields(two):
    shop = two.a.shop
    before = (shop.id, shop.evolution_instance, shop.ai_allow_free_tier, shop.ai_monthly_limit, shop.ai_enabled)
    r = two.ca.put("/api/shop", json={
        "id": two.b.shop.id, "evolution_instance": "bravo-zzb", "ai_allow_free_tier": True,
        "ai_monthly_limit": 10**9, "ai_enabled": True, "ai_limit_warned_month": "2099-01", "shop_id": two.b.shop.id,
        "name": "Barbearia Demo",
    })
    assert r.status_code == 200
    two.db.expire_all()
    shop = two.db.get(Shop, two.a.shop.id)
    assert (shop.id, shop.evolution_instance, shop.ai_allow_free_tier, shop.ai_monthly_limit, shop.ai_enabled) == before
    assert two.db.get(Shop, two.b.shop.id).evolution_instance == "bravo-zzb"
    # Configurações de IA: só ligar/desligar; o limite mensal não muda pela API
    two.ca.put("/api/ai/settings", json={"ai_enabled": True, "ai_monthly_limit": 10**9, "ai_allow_free_tier": True})
    two.db.expire_all()
    assert two.db.get(Shop, two.a.shop.id).ai_monthly_limit == before[3]


BAD_BODIES = [
    ("POST", "/api/services", {"name": "x", "duration_minutes": 30, "price": "-1"}),
    ("POST", "/api/services", {"name": "x", "duration_minutes": 30, "price": "1e12"}),
    ("POST", "/api/services", {"name": "x", "duration_minutes": 0, "price": "10"}),
    ("POST", "/api/services", {"name": "x", "duration_minutes": "trinta", "price": "10"}),
    ("POST", "/api/services", {"name": "x", "duration_minutes": 30, "price": "10", "sort_order": 10**12}),
    ("POST", "/api/services", {"name": "x" * 10_000, "duration_minutes": 30, "price": "10"}),
    ("POST", "/api/services", {"name": "", "duration_minutes": 30, "price": "10"}),
    ("POST", "/api/barbers", {"name": "x", "service_ids": [-1]}),
    ("POST", "/api/barbers", {"name": "x", "service_ids": [10**12]}),
    ("POST", "/api/barbers", {"name": "x", "phone": "9" * 40}),
    ("POST", "/api/barbers", {"name": "x", "working_hours": [{"weekday": 9, "start": "09:00", "end": "10:00"}]}),
    ("POST", "/api/barbers", {"name": "x", "working_hours": [{"weekday": 1, "start": "18:00", "end": "09:00"}]}),
    ("POST", "/api/blocks", {"start": "2026-11-10T12:00:00", "end": "2026-11-10T11:00:00"}),
    ("POST", "/api/blocks", {"start": "2026-13-45T12:00:00", "end": "2026-11-10T13:00:00"}),
    ("POST", "/api/blocks", {"start": "2026-11-10T12:00:00", "end": "2026-11-10T13:00:00", "reason": "r" * 5000}),
    ("POST", "/api/appointments", {"customer_phone": "1", "barber_id": 1, "service_id": 1, "start": "ontem"}),
    ("POST", "/api/appointments", {"customer_phone": "9" * 31, "barber_id": 1, "service_id": 1,
                                   "start": "2026-11-10T10:00:00"}),
    ("POST", "/api/expenses", {"description": "x", "amount": "0", "due_date": "2026-10-01"}),
    ("POST", "/api/expenses", {"description": "x", "amount": "-5", "due_date": "2026-10-01"}),
    ("POST", "/api/expenses", {"description": "x", "amount": "10", "due_date": "2026-02-30"}),
    ("POST", "/api/commission-rules", {"barber_id": 1, "beneficiary_type": "shop", "percentage": "150",
                                       "valid_from": "2026-01-01"}),
    ("POST", "/api/finance/settlements", {"payer_barber_id": 1, "beneficiary_type": "shop", "amount": "1e15",
                                          "period_start": "2026-09-01", "period_end": "2026-09-30"}),
    ("PUT", "/api/shop", {"slot_step_minutes": -5}),
    ("PUT", "/api/shop", {"booking_days_ahead": 10**6}),
    ("PUT", "/api/shop", {"welcome_text": "w" * 100_000}),
    ("PUT", "/api/shop", {"name": ""}),
    ("PUT", "/api/shop", {"owner_phone": "9" * 30}),
    ("PUT", "/api/shop", {"niche": "'; DROP TABLE shops; --"}),
    ("PUT", "/api/customers/{cid}", {"notes": "n" * 100_000}),
    ("PATCH", "/api/appointments/{aid}", {"price": "-1"}),
    ("PATCH", "/api/appointments/{aid}", {"status": "hackeado"}),
    ("POST", "/api/whatsapp/pairing-code", {"number": "9" * 40}),
    # ---- CRM fase 1
    ("PUT", "/api/shop", {"deposit_mode": "tudo"}),
    ("PUT", "/api/shop", {"deposit_value": "-10"}),
    ("PUT", "/api/shop", {"deposit_expire_minutes": 0}),
    ("POST", "/api/users", {"name": "x", "email": "nao-e-email", "role": "reception"}),
    ("POST", "/api/users", {"name": "x", "email": "a@b.com", "role": "admin"}),
    ("POST", "/api/products", {"name": "x", "price": "-1"}),
    ("POST", "/api/products", {"name": "x", "commission_pct": "500"}),
    ("POST", "/api/products/{pid}/movements", {"delta": "1e9", "reason": "purchase"}),
    ("POST", "/api/products/{pid}/movements", {"delta": "1", "reason": "sale"}),  # venda só pela comanda
    ("POST", "/api/products/{pid}/movements", {"delta": "0", "reason": "adjust"}),
    ("PUT", "/api/services/{sid}/consumption", [{"product_id": 1, "quantity": "-1"}]),
    ("POST", "/api/package-plans", {"name": "x", "service_id": 1, "sessions": 0, "price": "10"}),
    ("POST", "/api/package-plans", {"name": "x", "service_id": 1, "sessions": 4, "price": "0"}),
    ("POST", "/api/subscription-plans", {"name": "x", "price": "10", "items": []}),
    ("POST", "/api/subscription-plans", {"name": "x", "price": "10", "items": [{"service_id": 1,
                                                                                  "limit_per_period": 0}]}),
    ("POST", "/api/comandas/{coid}/items", {"kind": "gorjeta", "value": "1"}),
    ("POST", "/api/comandas/{coid}/items", {"kind": "discount", "percent": "150"}),
    ("POST", "/api/comandas/{coid}/items", {"kind": "discount", "value": "99999"}),
    ("POST", "/api/comandas/{coid}/items", {"kind": "product", "product_id": "{pid}", "quantity": 0}),
    ("POST", "/api/comandas/{coid}/items", {"kind": "tip", "value": "5"}),  # sem profissional
    ("POST", "/api/comandas/{coid}/payments", {"method": "bitcoin", "amount": "1"}),
    ("POST", "/api/comandas/{coid}/payments", {"method": "pix", "amount": "-1"}),
    ("POST", "/api/waitlist", {"customer_phone": "1", "service_id": 1, "day": "2026-10-10"}),
    ("POST", "/api/waitlist", {"customer_phone": "5531900000000", "service_id": 1, "day": "2020-01-01"}),
    ("POST", "/api/auth/change-password", {"current_password": "demo123", "new_password": "curta"}),
]


@pytest.mark.parametrize("method,path,body", BAD_BODIES)
def test_invalid_input_is_rejected_without_500(two, method, path, body):
    ids = dict(cid=two.a.customer.id, aid=two.a.appt.id, pid=two.a.extra["product"].id, sid=two.a.service.id,
               coid=two.a.extra["comanda"].id)
    url = path.format(**ids)
    if isinstance(body, dict) and body.get("product_id") == "{pid}":
        body = {**body, "product_id": ids["pid"]}
    r = two.ca.request(method, url, json=body)
    assert r.status_code in (400, 404, 409, 413, 422), f"{method} {url}: {r.status_code} {r.text[:200]}"


BAD_QUERIES = [
    "/api/appointments?date_from=2026-13-45",
    "/api/appointments?date_from=nao-e-data",
    "/api/agenda/day?day=0000-00-00",
    "/api/appointments/month?year=99999&month=1",
    "/api/appointments/month?year=2026&month=13",
    "/api/finance/summary?date_from=2026-12-31&date_to=2026-01-01",
    "/api/finance/summary?date_from=2000-01-01&date_to=2026-12-31",
    "/api/finance/export.csv?date_from=2026-12-31&date_to=2026-01-01",
    "/api/customers?limit=-1",
    "/api/customers?offset=-10",
    "/api/customers?limit=100000",
    "/api/customers?q=" + "a" * 101,
    "/api/ai/usage?month=2026-13",
    "/api/expenses?month=abc",
    "/api/customers/99999999999999999999999",
    "/api/customers/-1",
    "/api/payments/abc/receipt",
    "/api/comandas/99999999999999999999",
    "/api/comandas?status=aberta",
    "/api/comandas?day=2026-02-30",
    "/api/products/-5/movements",
    "/api/subscriptions?status=hackeada",
    "/api/charges?status=x",
    "/api/waitlist?day=ontem",
    "/api/sync/pull?cursor=abc",
    "/api/sync/pull?cursor=99999999999999999999999",
    "/api/sync/pull?limit=100000",
]


@pytest.mark.parametrize("url", BAD_QUERIES)
def test_invalid_query_and_path_values_never_500(two, url):
    r = two.ca.get(url)
    assert r.status_code in (400, 404, 422), f"{url}: {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("q", ["' OR 1=1 --", "%", "_", "\\", "'; DROP TABLE customers; --", "ZZB", "1111",
                               "\" OR \"\"=\"", "%' UNION SELECT password_hash FROM users --", "ç~´`^😀", "\x00"])
def test_customer_search_is_safe(two, q):
    r = two.ca.get("/api/customers", params={"q": q})
    assert r.status_code in (200, 422), f"{q!r}: {r.status_code}"
    if r.status_code == 200:
        assert no_leak(r.text, two.b) and "$2b$" not in r.text
        assert all(c["name"].endswith("AAA") or "AAA" not in q for c in r.json())
    assert two.db.scalar(select(Shop).where(Shop.id == two.b.shop.id)) is not None


# ---------------------------------------------------------------- Pix (BR Code)

def parse_emv(payload: str) -> list[tuple[str, str]]:
    """Lê o BR Code como TLV (tag 2 dígitos + tamanho 2 dígitos + valor). Falha se a estrutura estiver quebrada."""
    out, i = [], 0
    while i < len(payload):
        tag, size = payload[i:i + 2], int(payload[i + 2:i + 4])
        out.append((tag, payload[i + 4:i + 4 + size]))
        i += 4 + size
    assert i == len(payload)
    return out


@pytest.mark.parametrize("name,city,desc", [
    ("Zé da Navalha & Cia 6304ABCD", "São João del-Rei", "Agendamento 1"),
    ("A" * 200, "B" * 200, "C" * 200),
    ("😀💈 \"' <script>", "Cid@de\n5802US", "6304FFFF5303840"),
    ("", "", ""),
])
def test_brcode_fields_cannot_break_or_inject(name, city, desc):
    code = build_brcode("pix@exemplo.com", "email", "50.00", name, city, "TX123", desc)
    assert code.isascii()
    fields = parse_emv(code)
    tags = [t for t, _ in fields]
    assert tags == ["00", "26", "52", "53", "54", "58", "59", "60", "62", "63"]  # nenhum campo injetado
    assert dict(fields)["58"] == "BR" and dict(fields)["53"] == "986" and dict(fields)["54"] == "50.00"
    assert len(dict(fields)["59"]) <= 25 and len(dict(fields)["60"]) <= 15
    assert code[-4:] == crc16_ccitt(code[:-4])


@pytest.mark.parametrize("key,ktype,ok", [
    ("pix@exemplo.com", "email", True), ("x@y.com5802US", "email", False), ("a" * 70 + "@exemplo.com", "email", False),
    ("123.456.789-09", "cpf", True), ("123", "cpf", False), ("12.345.678/0001-90", "cnpj", True),
    ("(31) 99999-8888", "phone", True), ("31 9", "phone", False),
    ("123e4567-e89b-12d3-a456-426614174000", "random", True), ("qualquer coisa 5802US6304", "random", False),
    ("pix@exemplo.com", "invalido", False),
])
def test_pix_key_validation(key, ktype, ok):
    assert valid_pix_key(key, ktype) is ok


def test_invalid_pix_key_is_refused_by_api(two):
    for key, ktype in (("x@y.com5802US", "email"), ("a" * 100, "random"), ("123", "cpf")):
        r = two.ca.put("/api/shop", json={"pix_key": key, "pix_key_type": ktype})
        assert r.status_code == 422, (key, r.text)
    assert two.ca.put("/api/shop", json={"pix_key": "123e4567-e89b-12d3-a456-426614174000",
                                         "pix_key_type": "random"}).status_code == 200


@pytest.mark.parametrize("url", [
    "/api/appointments?date_from=2026-10-01&barber_id=999999999999999999999",
    "/api/appointments/month?year=2026&month=10&barber_id=999999999999999999999",
    "/api/availability?service_id=999999999999999999999&day=2026-10-10",
    "/api/reviews?barber_id=-3",
    "/api/commission-rules?barber_id=999999999999999999999",
    "/api/finance/settlements?barber_id=999999999999999999999",
    "/api/expenses?barber_id=999999999999999999999",
    "/api/customer-conflicts?customer_id=999999999999999999999",
    "/api/customer-conflicts/day?day=2026-10-10&customer_id=999999999999999999999",
])
def test_out_of_range_query_ids_never_500(two, url):
    r = two.ca.get(url)
    assert r.status_code in (404, 422), f"{url}: {r.status_code} {r.text[:200]}"
