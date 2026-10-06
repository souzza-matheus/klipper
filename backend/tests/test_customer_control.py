"""Controle de clientes: bloqueio, aprovação manual e clientes que não podem se encontrar."""
from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bot.router import handle_incoming
from app.config import now_local
from app.models import (
    AccessStatus, Appointment, ApptStatus, Barber, Customer, CustomerConflict, OutboxMessage, Service, Shop,
)
from app.services import approvals
from app.services import scheduling as sch

INST = "barbearia-demo"
CLIENT = "5531977776666"
RIVAL = "5531966665555"
RIVAL_NAME = "Bruno Rival"
OWNER = "5531999990000"


def say(db, phone, text):
    return "\n---\n".join(handle_incoming(db, INST, phone, text, "Carlos Silva"))


def msgs_to(db, phone):
    return [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == phone))]


def next_weekday(min_days=1):
    """Próximo dia de segunda a sexta (expediente das 9 às 12 e das 13 às 19)."""
    d = now_local().date() + timedelta(days=min_days)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


@pytest.fixture()
def env(db):
    shop = db.scalar(select(Shop))
    barbers = {b.name: b for b in db.scalars(select(Barber))}
    services = {s.name: s for s in db.scalars(select(Service))}
    client = Customer(shop_id=shop.id, phone=CLIENT, name="Carlos Silva")
    rival = Customer(shop_id=shop.id, phone=RIVAL, name=RIVAL_NAME)
    db.add_all([client, rival])
    db.commit()
    return db, shop, barbers, services, client, rival


def set_access(db, customer, status, reason=""):
    customer.access_status, customer.access_reason = status, reason
    db.commit()


def book(db, day_option="2", slot_option="1"):
    """Fluxo do cliente até a confirmação: Corte + Barba com o João."""
    say(db, CLIENT, "oi")
    assert "Qual serviço" in say(db, CLIENT, "1")
    assert "Com qual barbeiro" in say(db, CLIENT, "3")
    assert "Para qual dia" in say(db, CLIENT, "1")
    assert "Horários livres" in say(db, CLIENT, day_option)
    assert "Confirma o agendamento" in say(db, CLIENT, slot_option)
    return say(db, CLIENT, "1")


def last_appt(db):
    return db.scalar(select(Appointment).order_by(Appointment.id.desc()))


def add_appt(db, shop, customer, barber, service, start, status=ApptStatus.SCHEDULED):
    a = Appointment(shop_id=shop.id, customer_id=customer.id, barber_id=barber.id, service_id=service.id,
                    start=start, end=start + timedelta(minutes=service.duration_minutes), price=service.price,
                    status=status)
    db.add(a)
    db.commit()
    return a


def add_conflict(db, shop, x, y, gap=None, same_day=False):
    a, b = sorted((x.id, y.id))
    c = CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, min_gap_minutes=gap,
                         same_day_block=same_day, notes="Brigaram na barbearia")
    db.add(c)
    db.commit()
    return c


@pytest.fixture()
def api(db):
    from app.main import app
    c = TestClient(app)
    token = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


# ---------------------------------------------------------------- bloqueado

def test_blocked_customer_cannot_book_and_message_is_neutral(env):
    db, shop, barbers, services, client, rival = env
    future = add_appt(db, shop, client, barbers["João"], services["Corte"],
                      datetime.combine(next_weekday(2), time(15)))
    set_access(db, client, AccessStatus.BLOCKED, "Deu calote duas vezes")

    say(db, CLIENT, "oi")
    r = say(db, CLIENT, "1")
    assert "não conseguimos agendar por aqui" in r and "fale com a barbearia" in r
    # Remarcar também é bloqueado
    say(db, CLIENT, "2")
    assert "O que você quer fazer" in say(db, CLIENT, "1")
    assert "não conseguimos agendar por aqui" in say(db, CLIENT, "2")
    # Informações continuam funcionando
    assert "Corte + Barba" in say(db, CLIENT, "3")
    assert "Endereço" in say(db, CLIENT, "5")

    # O agendamento que ele já tinha não foi cancelado e nenhum novo foi criado
    db.refresh(future)
    assert future.status == ApptStatus.SCHEDULED
    assert db.scalar(select(Appointment).where(Appointment.id != future.id)) is None
    for text in msgs_to(db, CLIENT):
        low = text.lower()
        assert "bloque" not in low and "calote" not in low and "aprova" not in low


def test_block_from_app_can_cancel_future_appointments(env, api):
    db, shop, barbers, services, client, rival = env
    a = add_appt(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(2), time(15)))
    detail = api.get(f"/api/customers/{client.id}").json()
    assert detail["future_appointments"] == 1 and detail["access_status"] == "normal"

    r = api.put(f"/api/customers/{client.id}/access",
                json={"access_status": "blocked", "access_reason": "Calote", "cancel_future": True,
                      "notify_customer": True})
    assert r.status_code == 200, r.text
    assert r.json()["cancelled"] == 1 and r.json()["customer"]["access_status"] == "blocked"
    db.refresh(a)
    assert a.status == ApptStatus.CANCELLED
    sent = msgs_to(db, CLIENT)
    assert sent and all("Calote" not in m and "bloque" not in m.lower() for m in sent)
    # Filtro da lista de clientes
    blocked = api.get("/api/customers", params={"access_status": "blocked"}).json()
    assert [c["id"] for c in blocked] == [client.id]


# ---------------------------------------------------------------- precisa de aprovação

def test_approval_creates_pending_that_holds_the_slot_and_owner_approves(env):
    db, shop, barbers, services, client, rival = env
    set_access(db, client, AccessStatus.APPROVAL, "Cancela em cima da hora")
    r = book(db)
    assert "Recebemos seu pedido! A barbearia vai confirmar e te avisamos por aqui." in r
    assert "Pix" not in r  # Pix só depois da aprovação
    appt = last_appt(db)
    assert appt.status == ApptStatus.PENDING_APPROVAL and appt.approval_requested_at is not None
    alert = [m for m in msgs_to(db, OWNER) if "Pedido para aprovar" in m]
    assert alert and "Carlos Silva" in alert[0] and "Corte + Barba" in alert[0]

    # O horário fica ocupado enquanto aguarda
    assert appt.start not in sch.free_slots(db, shop, appt.service, appt.barber, appt.start.date())
    # Pix não aparece para o pedido pendente
    say(db, CLIENT, "menu")
    assert "aguardando confirmação" in say(db, CLIENT, "2")
    assert "Pagar via Pix" not in say(db, CLIENT, "1")
    say(db, CLIENT, "4")  # volta ao menu (no meio de um fluxo, a aprovação só indica o caminho do Pix)

    # Dono aprova pelo bot
    assert "*10* - Pedidos para aprovar (1)" in say(db, OWNER, "oi")
    assert "Carlos Silva" in say(db, OWNER, "10")
    r = say(db, OWNER, "1")
    assert "Cancela em cima da hora" in r and "*1* - Aprovar" in r
    assert "aprovado" in say(db, OWNER, "1")
    db.refresh(appt)
    assert appt.status == ApptStatus.SCHEDULED
    last = msgs_to(db, CLIENT)[-1]
    assert "confirmado" in last and "Pagar agora via Pix" in last
    assert "000201" in say(db, CLIENT, "1")  # aceita a oferta de Pix


def test_owner_refuses_pending_request(env):
    db, shop, barbers, services, client, rival = env
    set_access(db, client, AccessStatus.APPROVAL)
    book(db)
    appt = last_appt(db)
    say(db, OWNER, "oi")
    say(db, OWNER, "10")
    say(db, OWNER, "1")
    assert "recusado" in say(db, OWNER, "2")
    db.refresh(appt)
    assert appt.status == ApptStatus.CANCELLED
    assert approvals.MSG_REFUSED in msgs_to(db, CLIENT)[-1]
    assert appt.start in sch.free_slots(db, shop, appt.service, appt.barber, appt.start.date())
    assert "Nenhum pedido para aprovar" in say(db, OWNER, "10")


def test_pending_request_expires(env):
    db, shop, barbers, services, client, rival = env
    set_access(db, client, AccessStatus.APPROVAL)
    book(db)
    appt = last_appt(db)
    assert approvals.expire_pending(db, shop) == 0
    # Sem resposta por mais de 12 h (padrão da barbearia)
    appt.approval_requested_at = now_local() - timedelta(hours=12, minutes=1)
    db.commit()
    assert approvals.expire_pending(db, shop) == 1
    db.commit()
    db.refresh(appt)
    assert appt.status == ApptStatus.CANCELLED
    assert "Não conseguimos confirmar" in msgs_to(db, CLIENT)[-1]
    assert any("expiraram sem resposta" in m for m in msgs_to(db, OWNER))
    assert appt.start in sch.free_slots(db, shop, appt.service, appt.barber, appt.start.date())

    # Faltando menos de 1 h para o horário, expira mesmo dentro do prazo
    soon = add_appt(db, shop, client, barbers["Pedro"], services["Corte"],
                    now_local() + timedelta(minutes=50), status=ApptStatus.PENDING_APPROVAL)
    soon.approval_requested_at = now_local()
    shop.approval_expire_hours = 24
    db.commit()
    assert approvals.expire_pending(db, shop) == 1
    assert soon.status == ApptStatus.CANCELLED


def test_app_approvals_endpoints(env, api):
    db, shop, barbers, services, client, rival = env
    a = add_appt(db, shop, client, barbers["João"], services["Corte"], datetime.combine(next_weekday(2), time(15)),
                 status=ApptStatus.PENDING_APPROVAL)
    a.approval_requested_at = now_local()
    db.commit()
    pending = api.get("/api/approvals").json()
    assert [p["id"] for p in pending] == [a.id] and pending[0]["approval_deadline"]
    assert api.post(f"/api/appointments/{a.id}/approve").json()["status"] == "scheduled"
    assert api.post(f"/api/appointments/{a.id}/refuse").status_code == 409


# ---------------------------------------------------------------- clientes que não podem se encontrar

def _slots(db, shop, services, barber, day, customer=None):
    return [s.time() for s in sch.free_slots(db, shop, services["Corte"], barber, day, customer=customer)]


def test_conflict_hides_slots_both_ways_and_across_barbers(env):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    add_conflict(db, shop, client, rival, gap=120)
    # O rival está com o Pedro das 14:00 às 14:30; o cliente vai consultar o João
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))

    free = _slots(db, shop, services, barbers["João"], day, client)
    # Antes: precisa terminar até 12:00 (2 h antes das 14:00)
    assert time(11, 30) in free
    # Entre 12:00 e 16:30 nada (o expediente da tarde começa às 13:00)
    assert not [t for t in free if time(12) <= t < time(16, 30)]
    # Depois: pode começar às 16:30 (2 h depois das 14:30)
    assert time(16, 30) in free
    # Sem o cliente (ou para outro cliente), a agenda do João está livre
    assert time(14) in _slots(db, shop, services, barbers["João"], day)
    # "Tanto faz" também respeita
    any_slots = [s.time() for s, _ in sch.free_slots_any(db, shop, services["Corte"], day, customer=client)]
    assert time(14) not in any_slots and time(16, 30) in any_slots


def test_same_day_block_hides_the_whole_day(env):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    add_conflict(db, shop, client, rival, same_day=True)
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(9)))
    assert _slots(db, shop, services, barbers["João"], day, client) == []
    assert sch.free_slots_any(db, shop, services["Corte"], day, customer=client) == []
    other_day = next_weekday((day - now_local().date()).days + 1)
    assert _slots(db, shop, services, barbers["João"], other_day, client)


def test_shop_default_gap_applies_when_null(env):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    add_conflict(db, shop, client, rival, gap=None)
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(15)))
    # Padrão 240 min: proibido de 11:00 (15:00 - 4 h) até 19:30
    free = _slots(db, shop, services, barbers["João"], day, client)
    assert time(10, 30) in free and time(11) not in free and not [t for t in free if t >= time(13)]
    shop.conflict_default_gap_minutes = 60
    db.commit()
    free = _slots(db, shop, services, barbers["João"], day, client)
    assert time(13, 30) in free and time(14) not in free and time(16) not in free and time(16, 30) in free


def test_create_appointment_rejects_conflict_and_app_can_force(env, api):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    add_conflict(db, shop, client, rival, gap=120)
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))
    start = datetime.combine(day, time(15))
    with pytest.raises(sch.ConflictError):
        sch.create_appointment(db, shop, client, barbers["João"], services["Corte"], start)
    db.rollback()

    body = {"customer_phone": CLIENT, "barber_id": barbers["João"].id, "service_id": services["Corte"].id,
            "start": start.isoformat()}
    r = api.post("/api/appointments", json=body)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "customer_conflict" and RIVAL_NAME in detail["message"]
    assert detail["conflict"]["gap_minutes"] == 120 and detail["conflict"]["other_customer_name"] == RIVAL_NAME
    assert "14:00" in detail["message"]

    r = api.post("/api/appointments", json={**body, "force": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"
    # A mensagem de confirmação para o cliente não fala do outro
    assert all(RIVAL_NAME not in m and "Bruno" not in m for m in msgs_to(db, CLIENT))

    # Disponibilidade no app com customer_id já vem filtrada
    q = {"service_id": services["Corte"].id, "day": day.isoformat(), "barber_id": barbers["João"].id}
    plain = [s["start"][11:16] for s in api.get("/api/availability", params=q).json()]
    filtered = [s["start"][11:16] for s in api.get("/api/availability", params={**q, "customer_id": client.id}).json()]
    assert "16:00" in plain and "16:00" not in filtered and "11:30" in filtered
    # Aviso do dia na tela de agendamento
    hits = api.get("/api/customer-conflicts/day", params={"day": day.isoformat(), "customer_phone": CLIENT}).json()
    assert [h["other_customer_name"] for h in hits] == [RIVAL_NAME]


def test_reschedule_rejects_conflict(env, api):
    db, shop, barbers, services, client, rival = env
    day = next_weekday()
    add_conflict(db, shop, client, rival, gap=60)
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))
    mine = add_appt(db, shop, client, barbers["João"], services["Corte"], datetime.combine(day, time(9)))
    body = {"start": datetime.combine(day, time(14, 30)).isoformat(), "barber_id": barbers["João"].id}
    assert api.post(f"/api/appointments/{mine.id}/reschedule", json=body).status_code == 409
    assert api.post(f"/api/appointments/{mine.id}/reschedule", json={**body, "force": True}).status_code == 200


def test_conflicts_crud(env, api):
    db, shop, barbers, services, client, rival = env
    body = {"customer_id": rival.id, "other_customer_id": client.id, "min_gap_minutes": 120, "notes": "Briga"}
    r = api.post("/api/customer-conflicts", json=body)
    assert r.status_code == 200, r.text
    conf = r.json()
    assert conf["customer_a_id"] == min(client.id, rival.id)  # par sem ordem
    assert conf["other_customer_name"] == "Carlos Silva"
    # B-A é o mesmo par
    dup = {"customer_id": client.id, "other_customer_id": rival.id}
    assert api.post("/api/customer-conflicts", json=dup).status_code == 409
    assert api.post("/api/customer-conflicts", json={"customer_id": client.id, "other_customer_id": client.id}).status_code == 422

    mine = api.get("/api/customer-conflicts", params={"customer_id": client.id}).json()
    assert len(mine) == 1 and mine[0]["other_customer_name"] == RIVAL_NAME and mine[0]["effective_gap_minutes"] == 120
    r = api.put(f"/api/customer-conflicts/{conf['id']}", json={"min_gap_minutes": None, "same_day_block": True})
    assert r.json()["effective_gap_minutes"] == 240 and r.json()["same_day_block"] is True
    assert api.delete(f"/api/customer-conflicts/{conf['id']}").status_code == 200
    assert api.get("/api/customer-conflicts", params={"customer_id": client.id}).json() == []

    # Outra barbearia não enxerga nem usa clientes desta
    other = TestClient(api.app).post("/api/auth/register", json={
        "setup_token": "troque-este-token-de-setup", "shop_name": "Outra", "owner_name": "Zé",
        "email": "ze@outra.com", "password": "123456"}).json()["token"]
    h = {"Authorization": f"Bearer {other}"}
    assert api.get("/api/customer-conflicts", params={"customer_id": client.id}, headers=h).status_code == 404
    assert api.post("/api/customer-conflicts", json=body, headers=h).status_code == 404


def test_bot_never_reveals_the_other_customer(env):
    db, shop, barbers, services, client, rival = env
    add_conflict(db, shop, client, rival, same_day=True)
    say(db, CLIENT, "oi")
    say(db, CLIENT, "1")
    say(db, CLIENT, "3")
    days = sch.open_days(db, shop, services["Corte + Barba"], barbers["João"])
    day = next(d for d in days if d > now_local().date() and d.weekday() < 5)
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(day, time(9)))
    say(db, CLIENT, "1")  # João
    r = say(db, CLIENT, str(days.index(day) + 1))
    assert "Não há horários livres" in r  # o dia inteiro some, sem explicar

    # Corrida: o cliente vê o horário, o rival agenda antes, e a confirmação falha sem citar ninguém
    rival_day = next(d for d in days if d > day and d.weekday() < 5)
    shop.conflict_default_gap_minutes = 120
    db.query(CustomerConflict).update({"same_day_block": False})
    db.commit()
    say(db, CLIENT, "menu")
    say(db, CLIENT, "1")
    say(db, CLIENT, "3")
    say(db, CLIENT, "1")
    say(db, CLIENT, str(days.index(rival_day) + 1))
    assert "Confirma o agendamento" in say(db, CLIENT, "1")  # 09:00 com o João
    add_appt(db, shop, rival, barbers["Pedro"], services["Corte"], datetime.combine(rival_day, time(9, 30)))
    assert "acabou de ser ocupado" in say(db, CLIENT, "1")
    assert not db.scalar(select(Appointment).where(Appointment.customer_id == client.id))

    for text in msgs_to(db, CLIENT):
        assert RIVAL_NAME not in text and "Bruno" not in text and "conflito" not in text.lower()
