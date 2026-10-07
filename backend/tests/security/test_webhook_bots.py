"""Webhook do WhatsApp e bots: secret, payloads ruins, instância errada, menu do dono, estado da conversa e PII."""
import json

import pytest
from sqlalchemy import select

from app.bot.context import conversation_for
from app.bot.router import handle_incoming
from app.config import settings
from app.models import Appointment, ApptStatus, Conversation, Customer, OutboxMessage, Payment, PayStatus, Review

WEBHOOK = "/webhook/evolution"
STRANGER = "5531933334444"


def upsert(instance, phone, text):
    return {"event": "messages.upsert", "instance": instance, "data": {
        "key": {"id": "X1", "fromMe": False, "remoteJid": f"{phone}@s.whatsapp.net"}, "pushName": "Fulano",
        "message": {"conversation": text}}}


@pytest.mark.parametrize("query,headers", [
    ("", {}),
    ("?secret=errado", {}),
    ("?secret=", {}),
    ("?secret[]=x", {}),
    ("?SECRET={s}", {}),
    ("", {"x-webhook-secret": "errado"}),
    ("?secret={s}x", {}),
    ("?secret= {s}", {}),
])
def test_webhook_rejects_missing_or_wrong_secret(two, query, headers):
    r = two.anon.post(WEBHOOK + query.format(s=settings.webhook_secret), headers=headers,
                      json=upsert("barbearia-demo", STRANGER, "oi"))
    assert r.status_code == 403
    assert not two.db.scalar(select(Conversation).where(Conversation.phone == STRANGER))


def test_webhook_accepts_secret_in_header_or_query(two):
    body = upsert("barbearia-demo", STRANGER, "oi")
    assert two.anon.post(WEBHOOK, headers={"x-webhook-secret": settings.webhook_secret}, json=body).status_code == 200
    assert two.anon.post(f"{WEBHOOK}?secret={settings.webhook_secret}", json=body).status_code == 200


def test_secret_comparison_is_constant_time():
    import inspect
    from app.api import webhook
    from app import security
    assert "compare_digest" in inspect.getsource(security.same_secret)
    assert "same_secret" in inspect.getsource(webhook.evolution_webhook)


@pytest.mark.parametrize("raw", [
    b"{nao e json", b"[]", b"null", b"123", b'"texto"',
    json.dumps({"event": "messages.upsert", "data": "string"}).encode(),
    json.dumps({"event": "messages.upsert", "data": [None, 1]}).encode(),
    json.dumps({"event": "messages.upsert", "data": {"key": "x", "message": []}}).encode(),
    json.dumps({"event": "messages.upsert", "data": {"key": {"remoteJid": 123}, "message": {"conversation": 5}}}).encode(),
    json.dumps({"event": ["x"], "instance": {"a": 1}, "data": {}}).encode(),
    json.dumps({"event": "messages.upsert", "instance": "barbearia-demo", "data": {
        "key": {"remoteJid": f"{STRANGER}@s.whatsapp.net"}, "message": {"conversation": "x" * 100_000}}}).encode(),
    json.dumps({"a": [[[[[[[[[[[[[[[[[[[[[[]]]]]]]]]]]]]]]]]]]]]]}).encode(),
])
def test_malformed_payloads_never_crash(two, raw):
    r = two.anon.post(f"{WEBHOOK}?secret={settings.webhook_secret}", content=raw,
                      headers={"content-type": "application/json"})
    assert r.status_code == 200, r.text


def test_giant_payload_is_refused_before_reading(two):
    big = b'{"x":"' + b"a" * (settings.max_body_bytes + 10) + b'"}'
    r = two.anon.post(f"{WEBHOOK}?secret={settings.webhook_secret}", content=big,
                      headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_message_to_other_instance_only_affects_that_shop(two):
    handle_incoming(two.db, "bravo-zzb", STRANGER, "oi", "Fulano")
    convs = two.db.scalars(select(Conversation).where(Conversation.phone == STRANGER)).all()
    assert [c.shop_id for c in convs] == [two.b.shop.id]
    assert handle_incoming(two.db, "instancia-que-nao-existe", STRANGER, "oi") == []
    # O dono de B não é dono de A: na instância de A ele é só um cliente
    replies = "\n".join(handle_incoming(two.db, "barbearia-demo", two.b.shop.owner_phone, "painel"))
    assert "Painel da" not in replies


@pytest.mark.parametrize("text", ["painel", "9", "menu", "oi", "0", "10", "5"])
def test_stranger_never_reaches_the_owner_menu(two, text):
    replies = "\n".join(handle_incoming(two.db, "barbearia-demo", STRANGER, text, "Fulano"))
    assert "Painel da" not in replies and "Pix pendentes" not in replies and "Agenda de hoje" not in replies
    for t in ("1", "2", "4", "5"):  # mesmo seguindo com números do menu do dono
        r = "\n".join(handle_incoming(two.db, "barbearia-demo", STRANGER, t, "Fulano"))
        assert "Agenda de hoje" not in r and two.a.customer.name not in r


def test_owner_still_gets_the_owner_menu(two):
    assert "Painel da" in "\n".join(handle_incoming(two.db, "barbearia-demo", two.a.shop.owner_phone, "painel"))


# ---------------------------------------------------------------- estado da conversa manipulado

@pytest.mark.parametrize("state,data,text", [
    ("my_action", {"appt_id": "OTHER"}, "1"),            # cancelar
    ("my_cancel_confirm", {"appt_id": "OTHER"}, "1"),
    ("my_action", {"appt_id": "OTHER"}, "3"),            # pagar via Pix
    ("reminder", {"appt_id": "OTHER"}, "2"),             # cancelar pelo lembrete
    ("book_pay", {"appt_id": "OTHER"}, "1"),             # Pix do agendamento de outro
    ("pay_pick", {"appt_ids": ["OTHER"]}, "1"),
    ("survey_rating", {"appt_id": "OTHER_DONE"}, "1"),   # avaliar o atendimento de outro
    ("ai_confirm", {"ai_proposal": {"kind": "cancel", "appointment_id": "OTHER"}}, "1"),
    ("ai_confirm", {"ai_proposal": {"kind": "reschedule", "appointment_id": "OTHER", "service_id": "SVC",
                                    "barber_id": "BARBER", "start": "START"}}, "1"),
])
def test_conversation_state_with_other_customer_ids_does_nothing(two, state, data, text):
    a = two.a
    victim = a.appt  # agendamento do "Cliente AAA"
    attacker = a.other_customer
    ids = {"OTHER": victim.id, "OTHER_DONE": a.done_appt.id, "SVC": a.service.id, "BARBER": a.barber.id,
           "START": victim.start.replace(hour=15).isoformat()}
    fill = lambda v: [fill(x) for x in v] if isinstance(v, list) else (  # noqa: E731
        {k: fill(x) for k, x in v.items()} if isinstance(v, dict) else ids.get(v, v))
    conv = conversation_for(two.db, a.shop, attacker.phone)
    conv.state, conv.data = state, fill(data)
    two.db.commit()
    before = (victim.status, victim.start, victim.payment_status)
    pays = two.db.scalar(select(Payment).where(Payment.appointment_id == victim.id)).created_at
    replies = "\n".join(handle_incoming(two.db, "barbearia-demo", attacker.phone, text, "Atacante"))
    two.db.expire_all()
    v = two.db.get(Appointment, victim.id)
    assert (v.status, v.start, v.payment_status) == before
    assert two.db.scalar(select(Payment).where(Payment.appointment_id == victim.id)).created_at == pays
    assert not two.db.scalar(select(Review).where(Review.appointment_id == a.done_appt.id, Review.rating == 1))
    assert a.customer.name not in replies and a.customer.phone not in replies
    brcode = two.db.scalar(select(Payment.brcode).where(Payment.appointment_id == victim.id))
    assert brcode not in replies  # o Pix do agendamento da vítima não vai para o atacante


def test_messages_to_customers_never_contain_other_customers_data(two):
    """Fluxos variados com vários clientes e, no fim, nenhuma mensagem a um cliente cita outro cliente."""
    a = two.a
    phones = [a.customer.phone, a.other_customer.phone, STRANGER]
    for phone in phones:
        for t in ("oi", "1", "1", "1", "2", "1", "1", "menu", "2", "1", "1", "menu", "3", "4", "5", "6", "paguei"):
            handle_incoming(two.db, "barbearia-demo", phone, t, "Fulano")
    customers = two.db.scalars(select(Customer)).all()
    for m in two.db.scalars(select(OutboxMessage)):
        target = next((c for c in customers if c.phone == m.phone), None)
        if target is None or m.phone in (a.shop.owner_phone, two.b.shop.owner_phone) or \
                m.phone in (a.barber.phone, two.b.barber.phone):
            continue  # mensagens para o dono e a equipe podem citar clientes
        for other in customers:
            if other.id == target.id:
                continue
            assert other.phone not in m.text, f"mensagem para {m.phone} cita o telefone de outro cliente"
            if other.name and len(other.name) > 3:
                assert other.name not in m.text, f"mensagem para {m.phone} cita {other.name}"


def test_paid_flow_does_not_confirm_payment_by_itself(two):
    a = two.a
    handle_incoming(two.db, "barbearia-demo", a.customer.phone, "paguei", "Cliente")
    two.db.expire_all()
    assert two.db.get(Payment, a.payment.id).status == PayStatus.PENDING  # só o dono confirma
    assert two.db.get(Appointment, a.appt.id).status == ApptStatus.SCHEDULED
