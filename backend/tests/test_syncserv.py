"""SyncServ: segmento e tema do negócio, agenda do dia, recusar Pix, comprovante e ação de conflito."""
import base64
from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import now_local, settings
from app.models import (
    Appointment, ApptStatus, Barber, Block, ConflictAction, Customer, CustomerConflict, OutboxMessage, PayStatus,
    Payment, Service, Shop,
)
from app.services import payments
from app.services import scheduling as sch
from app.services import whatsapp as wa
from app.services.whatsapp import parse_webhook

from test_customer_control import CLIENT, RIVAL, add_appt, book, last_appt, msgs_to, next_weekday

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture()
def api(db):
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()
    c.headers["Authorization"] = f"Bearer {r['token']}"
    c.login = r
    return c


@pytest.fixture()
def env(db):
    shop = db.scalar(select(Shop))
    barbers = {b.name: b for b in db.scalars(select(Barber))}
    services = {s.name: s for s in db.scalars(select(Service))}
    client = Customer(shop_id=shop.id, phone=CLIENT, name="Carlos Silva")
    rival = Customer(shop_id=shop.id, phone=RIVAL, name="Bruno Rival")
    db.add_all([client, rival])
    db.commit()
    return db, shop, barbers, services, client, rival


# ---------------------------------------------------------------- segmento e tema

def test_login_and_me_return_niche_and_theme(api):
    assert api.login["niche"] == "barbershop" and api.login["theme_mode"] == "auto"
    me = api.get("/api/me").json()
    assert me["niche"] == "barbershop" and me["theme_mode"] == "auto"


def test_update_niche_and_theme_mode(api):
    r = api.put("/api/shop", json={"niche": "petshop", "theme_mode": "dark"})
    assert r.status_code == 200 and r.json()["niche"] == "petshop" and r.json()["theme_mode"] == "dark"
    assert api.get("/api/shop").json()["niche"] == "petshop"
    login = TestClient(api.app).post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()
    assert login["niche"] == "petshop" and login["theme_mode"] == "dark"
    # Só altera o que veio no corpo
    assert api.put("/api/shop", json={"name": "Pet do Zé"}).json()["niche"] == "petshop"


@pytest.mark.parametrize("body", [{"niche": "padaria"}, {"theme_mode": "sepia"}])
def test_invalid_niche_or_theme_mode(api, body):
    assert api.put("/api/shop", json=body).status_code == 422


# ---------------------------------------------------------------- agenda do dia

def test_agenda_day_in_one_response(env, api):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    joao, pedro = barbers["João"], barbers["Pedro"]
    a = add_appt(db, shop, client, joao, services["Corte"], datetime.combine(day, time(10)))
    add_appt(db, shop, rival, joao, services["Corte"], datetime.combine(day, time(11)), status=ApptStatus.CANCELLED)
    db.add_all([
        Block(shop_id=shop.id, barber_id=pedro.id, start=datetime.combine(day, time(15)),
              end=datetime.combine(day, time(16)), reason="Dentista"),
        Block(shop_id=shop.id, barber_id=None, start=datetime.combine(day, time(18)),
              end=datetime.combine(day, time(19)), reason="Reunião"),
    ])
    db.commit()

    r = api.get("/api/agenda/day", params={"day": day.isoformat()})
    assert r.status_code == 200
    d = r.json()
    assert d["day"] == day.isoformat() and d["slot_step_minutes"] == shop.slot_step_minutes
    by = {b["name"]: b for b in d["barbers"]}
    j, p = by["João"], by["Pedro"]
    # Expediente das 9 às 12 e das 13 às 19
    assert [(w["start"][11:16], w["end"][11:16]) for w in j["working"]] == [("09:00", "12:00"), ("13:00", "19:00")]
    # Só o agendamento ativo; o cancelado não aparece
    assert [x["id"] for x in j["appointments"]] == [a.id]
    assert j["appointments"][0]["customer_name"] == "Carlos Silva"
    # O bloqueio da barbearia inteira vale para os dois; o do Pedro, só para ele
    assert [(k["reason"], k["whole_shop"]) for k in j["blocks"]] == [("Reunião", True)]
    assert [(k["reason"], k["whole_shop"]) for k in p["blocks"]] == [("Dentista", False), ("Reunião", True)]
    # Livre = expediente - agendamentos - bloqueios (o cancelado das 11h não ocupa)
    assert [(f["start"][11:16], f["end"][11:16]) for f in j["free"]] == [
        ("09:00", "10:00"), ("10:30", "12:00"), ("13:00", "18:00")]
    assert [(f["start"][11:16], f["end"][11:16]) for f in p["free"]] == [
        ("09:00", "12:00"), ("13:00", "15:00"), ("16:00", "18:00")]


def test_agenda_day_past_has_no_free_time_and_inactive_barber_only_with_appointments(env, api):
    db, shop, barbers, services, client, _ = env
    past = now_local().date() - timedelta(days=7)
    while past.weekday() > 4:
        past -= timedelta(days=1)
    barbers["Pedro"].active = False
    db.commit()
    d = api.get("/api/agenda/day", params={"day": past.isoformat()}).json()
    assert [b["name"] for b in d["barbers"]] == ["João"]
    assert d["barbers"][0]["free"] == []
    add_appt(db, shop, client, barbers["Pedro"], services["Corte"], datetime.combine(past, time(9)))
    d = api.get("/api/agenda/day", params={"day": past.isoformat()}).json()
    assert {b["name"] for b in d["barbers"]} == {"João", "Pedro"}


# ---------------------------------------------------------------- Pix: recusar e ordenar

def _pix(db, shop, customer, barber, service, start, reported=False):
    a = add_appt(db, shop, customer, barber, service, start)
    pay = payments.get_or_create_pix(db, shop, a)
    if reported:
        pay.customer_reported_at = now_local()
    db.commit()
    return pay


def test_reject_pix_expires_and_tells_customer_neutrally(env, api):
    db, shop, barbers, services, client, _ = env
    pay = _pix(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(), time(10)))
    r = api.post(f"/api/payments/{pay.id}/reject")
    assert r.status_code == 200 and r.json()["status"] == PayStatus.EXPIRED
    db.expire_all()
    assert db.get(Payment, pay.id).appointment.payment_status == PayStatus.EXPIRED
    assert db.get(Payment, pay.id).appointment.status == ApptStatus.SCHEDULED  # o horário continua
    msg = msgs_to(db, CLIENT)[-1]
    assert "Não localizamos o seu Pix de R$ 40,00" in msg and "continua marcado" in msg
    assert "recus" not in msg.lower() and "golpe" not in msg.lower()
    # Só pendentes podem ser recusados
    assert api.post(f"/api/payments/{pay.id}/reject").status_code == 409


def test_pending_payments_reported_first_then_by_time(env, api):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    early = _pix(db, shop, client, barbers["João"], services["Corte"], datetime.combine(day, time(9)))
    late_reported = _pix(db, shop, rival, barbers["João"], services["Corte"], datetime.combine(day, time(16)),
                         reported=True)
    mid = _pix(db, shop, client, barbers["Pedro"], services["Corte"], datetime.combine(day, time(11)))
    ids = [p["id"] for p in api.get("/api/payments", params={"status": "pending"}).json()]
    assert ids == [late_reported.id, early.id, mid.id]
    p = api.get("/api/payments", params={"status": "pending"}).json()[0]
    assert p["service_name"] == "Corte" and p["barber_name"] == "João" and p["has_receipt"] is False
    # A agenda do dia traz o Pix de cada agendamento, para confirmar direto do card
    appts = {x["id"]: x for b in api.get("/api/agenda/day", params={"day": day.isoformat()}).json()["barbers"]
             for x in b["appointments"]}
    assert appts[late_reported.appointment_id]["payment_id"] == late_reported.id
    assert appts[late_reported.appointment_id]["customer_reported_paid"] is True
    assert appts[early.appointment_id]["customer_reported_paid"] is False


# ---------------------------------------------------------------- comprovante

def _image_payload(caption=""):
    return {
        "event": "messages.upsert", "instance": "barbearia-demo",
        "data": {
            "key": {"id": "3EB0IMG", "fromMe": False, "remoteJid": f"{CLIENT}@s.whatsapp.net"},
            "pushName": "Carlos",
            "message": {"imageMessage": {"mimetype": "image/jpeg", "caption": caption, "url": "https://mmg/x"}},
            "messageType": "imageMessage",
        },
    }


def test_parse_webhook_keeps_media_for_download():
    msg = parse_webhook(_image_payload())
    assert msg["text"] == "[anexo]"
    assert msg["media"]["key"]["id"] == "3EB0IMG" and "imageMessage" in msg["media"]["message"]


def test_receipt_from_whatsapp_is_stored_and_served(env, api, monkeypatch):
    db, shop, barbers, services, client, _ = env
    pay = _pix(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(), time(10)))
    calls = []

    def fake_media(shop_, media):
        calls.append(media["key"]["id"])
        return "image/jpeg", PNG
    monkeypatch.setattr(wa, "media_base64", fake_media)

    r = api.post(f"/webhook/evolution?secret={settings.webhook_secret}", json=_image_payload())
    assert r.status_code == 200 and calls == ["3EB0IMG"]
    db.expire_all()
    p = db.get(Payment, pay.id)
    assert p.receipt_mime == "image/jpeg" and p.receipt_at is not None
    assert p.customer_reported_at is not None  # a imagem sem legenda também conta como "paguei"
    listed = api.get("/api/payments", params={"status": "pending"}).json()[0]
    assert listed["has_receipt"] is True and listed["receipt_mime"] == "image/jpeg"
    got = api.get(f"/api/payments/{pay.id}/receipt")
    assert got.status_code == 200 and got.content == PNG and got.headers["content-type"] == "image/jpeg"
    # Rota autenticada
    assert TestClient(api.app).get(f"/api/payments/{pay.id}/receipt").status_code == 401


def test_receipt_limits(env, monkeypatch):
    db, shop, barbers, services, client, rival = env
    pay = _pix(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(), time(10)))
    media = {"key": {"id": "X"}, "message": {}}
    monkeypatch.setattr(wa, "media_base64", lambda s, m: ("audio/ogg", PNG))
    assert payments.save_receipt(db, shop, CLIENT, media) == 0
    monkeypatch.setattr(wa, "media_base64",
                        lambda s, m: ("image/png", b"0" * (payments.MAX_RECEIPT_BYTES + 1)))
    assert payments.save_receipt(db, shop, CLIENT, media) == 0
    monkeypatch.setattr(wa, "media_base64", lambda s, m: ("application/pdf", b"%PDF-1.4"))
    assert payments.save_receipt(db, shop, RIVAL, media) == 0  # rival não tem Pix pendente
    assert payments.save_receipt(db, shop, CLIENT, media) == 1
    assert db.get(Payment, pay.id).receipt_mime == "application/pdf"

    def boom(s, m):
        raise wa.EvolutionError("fora do ar")
    monkeypatch.setattr(wa, "media_base64", boom)
    assert payments.save_receipt(db, shop, CLIENT, media) == 0


def test_media_base64_calls_evolution(monkeypatch):
    import httpx
    from types import SimpleNamespace
    monkeypatch.setattr(settings, "evolution_url", "http://evolution:8080")
    seen = {}

    def fake_request(method, url, headers=None, timeout=None, json=None, params=None):
        seen.update(method=method, url=url, json=json)
        body = {"mimetype": "image/jpeg", "base64": base64.b64encode(PNG).decode(), "fileName": "x.jpeg"}
        return httpx.Response(201, json=body, request=httpx.Request(method, url))
    monkeypatch.setattr(wa.httpx, "request", fake_request)
    mime, data = wa.media_base64(SimpleNamespace(evolution_instance="barbearia-demo"),
                                 {"key": {"id": "K"}, "message": {"imageMessage": {}}})
    assert (mime, data) == ("image/jpeg", PNG)
    assert seen["method"] == "POST" and seen["url"].endswith("/chat/getBase64FromMediaMessage/barbearia-demo")
    assert seen["json"]["message"]["key"] == {"id": "K"} and seen["json"]["convertToMp4"] is False


def test_receipt_cleared_when_new_pix_is_generated(env):
    db, shop, barbers, services, client, _ = env
    pay = _pix(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(), time(10)))
    pay.receipt_mime, pay.receipt_data, pay.status = "image/png", PNG, PayStatus.EXPIRED
    db.commit()
    again = payments.get_or_create_pix(db, shop, pay.appointment)
    assert again.status == PayStatus.PENDING and again.receipt_mime is None and again.receipt_data is None


# ---------------------------------------------------------------- ação de conflito

def _conflict(db, shop, x, y, action, gap=120):
    a, b = sorted((x.id, y.id))
    c = CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, min_gap_minutes=gap,
                         conflict_action=action, notes="interno")
    db.add(c)
    db.commit()
    return c


def test_conflict_action_crud(env, api):
    db, shop, barbers, services, client, rival = env
    r = api.post("/api/customer-conflicts", json={"customer_id": client.id, "other_customer_id": rival.id,
                                                  "conflict_action": "approval"})
    assert r.status_code == 200 and r.json()["conflict_action"] == "approval"
    cid = r.json()["id"]
    assert api.get("/api/customer-conflicts", params={"customer_id": client.id}).json()[0]["conflict_action"] == "approval"
    r = api.put(f"/api/customer-conflicts/{cid}", json={"min_gap_minutes": 60, "conflict_action": "block"})
    assert r.json()["conflict_action"] == "block"
    assert api.put(f"/api/customer-conflicts/{cid}", json={"conflict_action": "talvez"}).status_code == 422
    # Padrão continua sendo bloquear
    db.query(CustomerConflict).delete()
    db.commit()
    r = api.post("/api/customer-conflicts", json={"customer_id": client.id, "other_customer_id": rival.id})
    assert r.json()["conflict_action"] == ConflictAction.BLOCK


def test_conflict_approval_shows_slot_to_bot_and_booking_becomes_pending(env, monkeypatch):
    db, shop, barbers, services, client, rival = env
    _conflict(db, shop, client, rival, ConflictAction.APPROVAL)
    # O rival ocupa a manhã inteira de todos os dias úteis com o Pedro, a partir das 9h
    days = sch.open_days(db, shop, services["Corte + Barba"], barbers["João"])
    for d in days:
        if d > now_local().date() and d.weekday() < 5:
            add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(d, time(9)))
    day = next(d for d in days if d > now_local().date() and d.weekday() < 5)

    # Para o app (sem only_blocking) o horário perto do rival some; para o bot, aparece
    joao, combo = barbers["João"], services["Corte + Barba"]
    assert time(9) not in [s.time() for s in sch.free_slots(db, shop, combo, joao, day, customer=client)]
    assert time(9) in [s.time() for s in sch.free_slots(db, shop, combo, joao, day, customer=client,
                                                       only_blocking=True)]

    r = book(db, day_option=str(days.index(day) + 1), slot_option="1")  # 09:00 com o João
    a = last_appt(db)
    assert a.customer_id == client.id and a.status == ApptStatus.PENDING_APPROVAL
    assert "Recebemos seu pedido" in r and "Bruno" not in r
    owner = [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == shop.owner_phone))]
    assert any("Pedido para aprovar" in m for m in owner)


def test_conflict_block_still_hides_slot_from_bot(env):
    db, shop, barbers, services, client, rival = env
    _conflict(db, shop, client, rival, ConflictAction.BLOCK)
    day = next_weekday()
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))
    slots = [s.time() for s in sch.free_slots(db, shop, services["Corte"], barbers["João"], day, customer=client,
                                              only_blocking=True)]
    assert time(14) not in slots and time(16, 30) in slots


def test_block_conflict_wins_over_approval(env):
    db, shop, barbers, services, client, rival = env
    third = Customer(shop_id=shop.id, phone="5531955554444", name="Terceiro")
    db.add(third)
    db.commit()
    _conflict(db, shop, client, rival, ConflictAction.APPROVAL)
    _conflict(db, shop, client, third, ConflictAction.BLOCK)
    day = next_weekday()
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))
    add_appt(db, shop, third, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14, 30)))
    start = datetime.combine(day, time(14))
    hit = sch.find_conflict(db, shop, client, start, start + timedelta(minutes=30))
    assert hit.conflict.conflict_action == ConflictAction.BLOCK
    assert not db.scalar(select(Appointment).where(Appointment.customer_id == client.id))
