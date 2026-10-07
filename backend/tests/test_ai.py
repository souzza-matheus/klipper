"""Agente de IA na conversa do cliente, com o FakeProvider (sem rede)."""
from datetime import datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.ai import agent, tools, usage
from app.ai.fake import FakeProvider, last_tool_result
from app.ai.provider import LLMError, ToolCall
from app.bot import customer as cb
from app.bot.router import handle_incoming
from app.config import now_local, settings
from app.models import (
    AccessStatus, AIUsage, Appointment, ApptStatus, Barber, ConversationMessage, Customer, OutboxMessage, Service, Shop,
)
from app.services.whatsapp import parse_webhook

from test_customer_control import add_appt, next_weekday

INST = "barbearia-demo"
PHONE = "5531977776666"
OTHER = "5531966665555"


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProvider()
    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "ai_tier", "paid")
    monkeypatch.setattr(agent, "get_provider", lambda: f)
    return f


@pytest.fixture()
def env(db, fake):
    shop = db.scalar(select(Shop))
    shop.ai_enabled = True
    me = Customer(shop_id=shop.id, phone=PHONE, name="Carlos Silva")
    other = Customer(shop_id=shop.id, phone=OTHER, name="Bruno Outro")
    db.add_all([me, other])
    db.commit()
    barbers = {b.name: b for b in db.scalars(select(Barber))}
    services = {s.name: s for s in db.scalars(select(Service))}
    return db, shop, barbers, services, me, other


def say(db, text, phone=PHONE):
    return "\n---\n".join(handle_incoming(db, INST, phone, text, "Carlos"))


def at(day, hh, mm=0):
    return datetime.combine(day, time(hh, mm)).strftime("%Y-%m-%dT%H:%M")


# ---------------------------------------------------------------- roteamento híbrido

def test_number_goes_to_menu_and_free_text_goes_to_ai(env, fake):
    db, *_ = env
    assert "Qual serviço" in say(db, "1")  # número: fluxo atual, sem IA
    assert fake.calls == []
    say(db, "menu")
    fake.script = [ToolCall("get_business_info", {}), "Abrimos de segunda a sábado! Quer agendar?"]
    r = say(db, "vcs abrem sábado?")
    assert "Abrimos de segunda a sábado" in r
    assert len(fake.calls) == 2 and "get_business_info" in fake.calls[0]["tools"]
    info = last_tool_result(fake.calls[1]["messages"], "get_business_info")
    assert info["name"] == "Barbearia Demo" and any("Sábado" in h for h in info["opening_hours"])
    # Instruções fixas (cacheáveis); data, dia da semana e cliente vão junto da mensagem
    assert now_local().strftime("%d/%m/%Y") not in fake.calls[0]["system"]
    turn = fake.calls[0]["messages"][-1].text
    assert now_local().strftime("%d/%m/%Y") in turn and "Carlos Silva" in turn and turn.endswith("vcs abrem sábado?")


def test_reminder_and_survey_answers_never_call_ai(env, fake):
    db, shop, barbers, services, me, _ = env
    a = add_appt(db, shop, me, barbers["João"], services["Corte"], datetime.combine(next_weekday(), time(10)))
    from app.bot.context import conversation_for
    c = conversation_for(db, shop, PHONE)
    c.state, c.data = "reminder", {"appt_id": a.id}
    db.commit()
    assert "Presença confirmada" in say(db, "sim")
    assert fake.calls == []


def test_paused_conversation_stays_silent(env, fake):
    db, shop, *_ = env
    from app.bot.context import conversation_for
    conversation_for(db, shop, PHONE).paused_until = now_local() + timedelta(hours=1)
    db.commit()
    assert say(db, "alguém aí?") == ""
    assert fake.calls == []


# ---------------------------------------------------------------- proposta + confirmação

def test_booking_proposal_then_confirmation_saves_and_notifies(env, fake):
    db, shop, barbers, services, me, _ = env
    day = next_weekday()
    joao, corte = barbers["João"], services["Corte"]

    def propose(system, messages, tools_, model):
        slots = last_tool_result(messages, "find_free_slots")["slots"]
        assert at(day, 14) in [s["start"] for s in slots]
        return ToolCall("propose_booking", {"service_id": corte.id, "professional_id": joao.id, "start": at(day, 14)})

    fake.script = [ToolCall("find_free_slots", {"service_id": corte.id, "professional_id": joao.id,
                                                "date": day.isoformat(), "after_time": "14:00"}),
                   propose]
    r = say(db, "quero cortar dia tal às 14h com o joão")
    assert "Confirma o agendamento?" in r and "*1* - Confirmar" in r and "*3* - Desistir" in r
    assert not db.scalar(select(Appointment).where(Appointment.customer_id == me.id))  # nada gravado ainda
    assert len(fake.calls) == 2  # a proposta encerra a rodada: o modelo não fala depois

    r = say(db, "1")
    a = db.scalar(select(Appointment).where(Appointment.customer_id == me.id))
    assert a and a.start == datetime.combine(day, time(14)) and a.barber_id == joao.id
    assert a.status == ApptStatus.SCHEDULED and "Agendado" in r
    owner = [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == shop.owner_phone))]
    assert any("Novo agendamento" in m for m in owner)
    assert len(fake.calls) == 2  # o "1" não passou pela IA


def test_booking_needs_customer_name(env, fake):
    db, shop, barbers, services, me, _ = env
    me.name = ""
    db.commit()
    day = next_weekday()
    args = {"service_id": services["Corte"].id, "start": at(day, 15)}
    fake.script = [ToolCall("propose_booking", args), "Qual é o seu nome?"]
    assert "Qual é o seu nome?" in say(db, "corte às 15h")
    assert "nome" in last_tool_result(fake.calls[1]["messages"], "propose_booking")["error"]
    fake.script = [ToolCall("set_customer_name", {"name": "carlos souza"}), ToolCall("propose_booking", args)]
    assert "Confirma o agendamento?" in say(db, "Carlos Souza")
    db.refresh(me)
    assert me.name == "Carlos Souza"


def test_give_up_and_other_option(env, fake):
    db, shop, barbers, services, me, _ = env
    day = next_weekday()
    call = ToolCall("propose_booking", {"service_id": services["Corte"].id, "start": at(day, 16)})
    fake.script = [call]
    say(db, "corte às 16h")
    assert "não mudei nada" in say(db, "3")
    fake.script = [call]
    say(db, "corte às 16h")
    assert "outro dia ou horário" in say(db, "2")
    assert not db.scalar(select(Appointment).where(Appointment.customer_id == me.id))


def test_cancel_through_ai(env, fake):
    db, shop, barbers, services, me, _ = env
    a = add_appt(db, shop, me, barbers["João"], services["Corte"], datetime.combine(next_weekday(min_days=2), time(10)))

    def propose(system, messages, tools_, model):
        mine = last_tool_result(messages, "get_my_appointments")["appointments"]
        assert [x["id"] for x in mine] == [a.id]
        return ToolCall("propose_cancel", {"appointment_id": a.id})

    fake.script = [ToolCall("get_my_appointments", {}), propose]
    assert "Cancelar este horário?" in say(db, "preciso desmarcar")
    assert db.get(Appointment, a.id).status == ApptStatus.SCHEDULED
    assert "cancelado" in say(db, "sim").lower()
    db.expire_all()
    assert db.get(Appointment, a.id).status == ApptStatus.CANCELLED


def test_reschedule_through_ai(env, fake):
    db, shop, barbers, services, me, _ = env
    day = next_weekday(min_days=2)
    a = add_appt(db, shop, me, barbers["João"], services["Corte"], datetime.combine(day, time(10)))
    fake.script = [ToolCall("propose_reschedule", {"appointment_id": a.id, "new_start": at(day, 17)})]
    r = say(db, "da pra passar pras 17h?")
    assert "Confirma a remarcação?" in r and "10:00" in r and "17:00" in r
    assert "Remarcado" in say(db, "1")
    db.expire_all()
    assert db.get(Appointment, a.id).start == datetime.combine(day, time(17))


# ---------------------------------------------------------------- regras e segurança

def test_tool_rejects_past_date_and_far_future(env, fake):
    db, shop, barbers, services, *_ = env
    yesterday = (now_local() - timedelta(days=1)).date().isoformat()
    far = (now_local() + timedelta(days=60)).date().isoformat()
    fake.script = [ToolCall("find_free_slots", {"service_id": services["Corte"].id, "date": yesterday}),
                   ToolCall("find_free_slots", {"service_id": services["Corte"].id, "date": far}),
                   "Essa data já passou. Quer ver amanhã?"]
    assert "já passou" in say(db, "quero ontem")
    tool_msgs = [r for m in fake.calls[-1]["messages"] for _, r in m.tool_results]
    assert "já passou" in tool_msgs[0]["error"] and "aberta só até" in tool_msgs[1]["error"]


def test_propose_rejects_slot_not_free(env, fake):
    db, shop, barbers, services, me, other = env
    day = next_weekday()
    add_appt(db, shop, other, barbers["João"], services["Corte"], datetime.combine(day, time(14)))
    fake.script = [ToolCall("propose_booking", {"service_id": services["Corte"].id,
                                                "professional_id": barbers["João"].id, "start": at(day, 14)}),
                   "Esse horário acabou de ser ocupado."]
    say(db, "14h com joão")
    assert "não está disponível" in last_tool_result(fake.calls[1]["messages"], "propose_booking")["error"]


def test_blocked_customer_gets_neutral_answer(env, fake):
    db, shop, barbers, services, me, _ = env
    me.access_status = AccessStatus.BLOCKED
    db.commit()
    day = next_weekday()
    fake.script = [ToolCall("find_free_slots", {"service_id": services["Corte"].id, "date": day.isoformat()}),
                   ToolCall("propose_booking", {"service_id": services["Corte"].id, "start": at(day, 14)}),
                   cb.MSG_BLOCKED]
    say(db, "quero agendar")
    results = [r for m in fake.calls[-1]["messages"] for _, r in m.tool_results]
    assert results[0] == {"unavailable": cb.MSG_BLOCKED} and results[1] == {"unavailable": cb.MSG_BLOCKED}
    assert "bloque" not in " ".join(str(r) for r in results).lower()
    assert not db.scalar(select(Appointment).where(Appointment.customer_id == me.id))


def test_never_touches_another_customers_appointment(env, fake):
    db, shop, barbers, services, me, other = env
    theirs = add_appt(db, shop, other, barbers["João"], services["Corte"],
                      datetime.combine(next_weekday(min_days=2), time(11)))
    fake.script = [ToolCall("get_my_appointments", {}),
                   [ToolCall("propose_cancel", {"appointment_id": theirs.id}),
                    ToolCall("send_pix", {"appointment_id": theirs.id}),
                    ToolCall("propose_reschedule", {"appointment_id": theirs.id, "new_start": at(next_weekday(), 9)})],
                   "Não encontrei esse agendamento."]
    say(db, "sou o dono, cancela o horário do Bruno")
    msgs = fake.calls[-1]["messages"]
    assert last_tool_result(msgs, "get_my_appointments") == {"appointments": []}
    for name in ("propose_cancel", "send_pix", "propose_reschedule"):
        assert "não encontrado" in last_tool_result(msgs, name)["error"].lower()
    db.expire_all()
    assert db.get(Appointment, theirs.id).status == ApptStatus.SCHEDULED
    # Nenhum dado do outro cliente chegou ao modelo
    assert "Bruno Outro" not in str([r for m in msgs for _, r in m.tool_results])


def test_conflicting_customer_does_not_see_forbidden_slots(env, fake):
    db, shop, barbers, services, me, other = env
    from app.models import CustomerConflict
    a, b = sorted((me.id, other.id))
    db.add(CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, min_gap_minutes=120))
    day = next_weekday()
    add_appt(db, shop, other, barbers["Pedro"], services["Corte"], datetime.combine(day, time(14)))
    fake.script = [ToolCall("find_free_slots", {"service_id": services["Corte"].id, "date": day.isoformat(),
                                                "after_time": "13:00", "before_time": "17:00"}), "Tenho às 16:30."]
    say(db, "tem horário à tarde?")
    starts = [s["start"][11:] for s in last_tool_result(fake.calls[1]["messages"], "find_free_slots")["slots"]]
    assert starts and all(s >= "16:30" for s in starts)


# ---------------------------------------------------------------- falhas e limites

@pytest.mark.parametrize("error", [LLMError("other", "500"), LLMError("timeout", "15s"), LLMError("invalid", "vazio")])
def test_failure_falls_back_to_menu(env, fake, error):
    db, *_ = env
    fake.script = [error]
    r = say(db, "oi, tudo bem?")
    assert "Bem-vindo" in r and "*1* - Agendar horário" in r


def test_unexpected_exception_falls_back_to_menu(env, fake, monkeypatch):
    db, *_ = env
    monkeypatch.setattr(tools, "run", lambda *a: 1 / 0)
    fake.script = [ToolCall("list_services", {})]
    assert "Bem-vindo" in say(db, "quanto tá o corte?")


def test_quota_retries_with_fallback_model(env, fake):
    db, shop, *_ = env
    fake.script = [LLMError("quota", "429"), "O corte custa R$ 40,00."]
    assert "R$ 40,00" in say(db, "quanto tá o corte?")
    assert [c["model"] for c in fake.calls] == [settings.ai_model, settings.ai_fallback_model]
    rows = db.scalars(select(AIUsage).order_by(AIUsage.id)).all()
    assert [(r.model, r.ok) for r in rows] == [(settings.ai_model, False), (settings.ai_fallback_model, True)]


def test_quota_on_both_models_goes_to_menu(env, fake):
    db, *_ = env
    fake.script = [LLMError("quota"), LLMError("quota")]
    assert "Bem-vindo" in say(db, "oi")


def test_tool_call_limit_forces_text_answer(env, fake, monkeypatch):
    db, shop, barbers, services, *_ = env
    monkeypatch.setattr(settings, "ai_max_tool_calls", 2)
    fake.script = [ToolCall("list_services", {}), ToolCall("list_professionals", {}), "Temos corte e barba."]
    assert "Temos corte e barba" in say(db, "o que vocês fazem?")
    assert fake.calls[-1]["tools"] == []  # a última chamada vai sem ferramentas


def test_monthly_limit_returns_to_menu_and_warns_owner_once(env, fake):
    db, shop, *_ = env
    shop.ai_monthly_limit = 1
    db.commit()
    fake.script = ["Oi! Em que posso ajudar?"]
    assert "Em que posso ajudar" in say(db, "oi")
    assert "Bem-vindo" in say(db, "quero agendar")  # limite atingido: menu
    assert "Bem-vindo" in say(db, "e agora?")
    warns = db.scalar(select(func.count()).select_from(OutboxMessage).where(
        OutboxMessage.phone == shop.owner_phone, OutboxMessage.text.contains("limite")))
    assert warns == 1
    assert len(fake.calls) == 1


def test_hourly_limit_per_customer(env, fake, monkeypatch):
    db, *_ = env
    monkeypatch.setattr(settings, "ai_hourly_limit_per_customer", 2)
    fake.script = ["Oi!", "Claro!"]
    say(db, "oi")
    say(db, "me ajuda?")
    assert "Bem-vindo" in say(db, "mais uma")
    assert len(fake.calls) == 2


def test_free_tier_only_for_allowed_shop(env, fake, monkeypatch):
    db, shop, *_ = env
    monkeypatch.setattr(settings, "ai_tier", "free")
    shop.ai_allow_free_tier = False
    db.commit()
    assert "Bem-vindo" in say(db, "quero cortar amanhã")
    assert fake.calls == []
    shop.ai_allow_free_tier = True
    db.commit()
    fake.script = ["Bora! Que horas?"]
    assert "Bora" in say(db, "quero cortar amanhã")


def test_ai_off_without_key_or_disabled(env, fake, monkeypatch):
    db, shop, *_ = env
    shop.ai_enabled = False
    db.commit()
    assert "Bem-vindo" in say(db, "oi")
    shop.ai_enabled = True
    db.commit()
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert "Bem-vindo" in say(db, "oi")
    assert fake.calls == []


def test_talk_to_human_pauses_bot(env, fake):
    db, shop, *_ = env
    fake.script = [ToolCall("talk_to_human", {})]
    assert "Avisei a equipe" in say(db, "quero falar com uma pessoa de verdade")
    assert say(db, "alô?") == ""  # pausado: o robô fica em silêncio
    assert "Bem-vindo" in say(db, "menu")  # "menu" religa o robô, como hoje


def test_atendente_keyword_without_ai(env, fake):
    db, shop, *_ = env
    shop.ai_enabled = False
    db.commit()
    assert "Avisei a equipe" in say(db, "atendente")


# ---------------------------------------------------------------- histórico, mensagens longas, limpeza

def test_history_is_saved_used_and_cleaned(env, fake):
    db, shop, *_ = env
    say(db, "1")  # menu: também entra no histórico
    say(db, "menu")
    fake.script = ["Claro, me diga o dia."]
    say(db, "quero agendar")
    sent = [m.text for m in fake.calls[0]["messages"] if m.role in ("user", "model")]
    assert sent[0] == "1" and sent[-1].endswith("MENSAGEM DO CLIENTE:\nquero agendar")
    rows = db.scalars(select(ConversationMessage).where(ConversationMessage.phone == PHONE)).all()
    assert {(r.role, r.channel) for r in rows} >= {("user", "ai"), ("assistant", "ai"), ("user", "menu")}
    for r in rows:
        r.created_at = now_local() - timedelta(days=31)
    db.commit()
    assert usage.cleanup(db) == len(rows)


def test_long_answers_are_split(env, fake):
    db, *_ = env
    fake.script = [("Parágrafo. " * 80).strip()]
    replies = handle_incoming(db, INST, PHONE, "me explica tudo", "Carlos")
    assert len(replies) > 1 and all(len(r) <= 600 for r in replies)


# ---------------------------------------------------------------- áudio

def test_parse_audio_message():
    msg = parse_webhook({"event": "messages.upsert", "instance": INST, "data": {
        "key": {"id": "A1", "fromMe": False, "remoteJid": f"{PHONE}@s.whatsapp.net"}, "pushName": "Carlos",
        "message": {"audioMessage": {"mimetype": "audio/ogg; codecs=opus", "seconds": 7}}}})
    assert msg["text"] == "[áudio]" and msg["audio"]["seconds"] == 7


def test_audio_is_transcribed_and_answered(env, fake, monkeypatch):
    db, shop, *_ = env
    from app.api import webhook
    shop.ai_audio_enabled = True
    db.commit()
    monkeypatch.setattr(webhook, "media_base64", lambda s, m: ("audio/ogg", b"OggS..."))
    fake.transcript = "quanto custa o corte?"
    fake.script = ["O corte custa R$ 40,00."]
    webhook.process_audio(INST, PHONE, "Carlos", {"key": {"id": "A1"}, "message": {}, "seconds": 7})
    db.expire_all()
    out = [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == PHONE))]
    assert "O corte custa R$ 40,00." in out
    assert fake.calls[0]["mime"] == "audio/ogg"
    assert fake.calls[1]["messages"][-1].text.endswith("quanto custa o corte?")


def test_long_audio_asks_to_write(env, fake, monkeypatch):
    db, shop, *_ = env
    from app.api import webhook
    shop.ai_audio_enabled = True
    db.commit()
    webhook.process_audio(INST, PHONE, "Carlos", {"key": {"id": "A2"}, "message": {}, "seconds": 300})
    db.expire_all()
    out = [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == PHONE))]
    assert out == [webhook.MSG_AUDIO_LONG] and fake.calls == []


def test_audio_ignored_when_disabled(env, fake, monkeypatch):
    db, shop, *_ = env
    from app.api import webhook
    webhook.process_audio(INST, PHONE, "Carlos", {"key": {"id": "A3"}, "message": {}, "seconds": 5})
    db.expire_all()
    assert not db.scalars(select(OutboxMessage).where(OutboxMessage.phone == PHONE)).all()


# ---------------------------------------------------------------- app e simulador

@pytest.fixture()
def api(db):
    from app.main import app
    c = TestClient(app)
    token = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def test_settings_and_usage_endpoints(env, fake, api, monkeypatch):
    db, shop, *_ = env
    monkeypatch.setattr(settings, "ai_tier", "free")
    s = api.get("/api/ai/settings").json()
    assert s["ai_enabled"] is True and s["tier"] == "free" and s["free_tier_allowed"] is True
    assert "dados fictícios" in s["test_mode_warning"] and s["monthly_limit"] == 3000
    s = api.put("/api/ai/settings", json={"ai_enabled": False, "ai_audio_enabled": True}).json()
    assert s["ai_enabled"] is False and s["ai_audio_enabled"] is True and s["available"] is False
    usage.record(db, shop, PHONE, "m", True, 120, 1000, 50)
    usage.record(db, shop, PHONE, "m", False, 15000, error="timeout")
    db.commit()
    u = api.get("/api/ai/usage", params={"month": now_local().strftime("%Y-%m")}).json()
    assert u["calls"] == 2 and u["errors"] == 1 and u["input_tokens"] == 1000 and u["limit"] == 3000
    assert api.get("/api/ai/usage", params={"month": "2026-13"}).status_code == 422


def test_dev_simulate_uses_ai(env, fake, api):
    fake.script = ["Oi! Quer marcar um horário?"]
    r = api.post("/dev/simulate", json={"phone": "31977776666", "text": "oi, boa tarde"},
                 headers={"x-setup-token": settings.setup_token})
    assert r.json()["replies"] == ["Oi! Quer marcar um horário?"]


# ---------------------------------------------------------------- adaptador do Gemini (SDK simulado, sem rede)

def test_gemini_adapter_builds_requests_and_parses_responses(monkeypatch):
    from google.genai import errors, types
    from app.ai.gemini import GeminiProvider
    from app.ai.provider import Message
    p = GeminiProvider("chave-falsa")
    sent = []
    replies = [
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[
                types.Part(function_call=types.FunctionCall(id="c1", name="list_services", args={}))]))],
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=120, candidates_token_count=8)),
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="Corte: R$ 40,00")]))],
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=150, candidates_token_count=6)),
    ]

    def fake_generate(model, contents, config):
        sent.append((model, contents, config))
        return replies.pop(0)
    monkeypatch.setattr(p._client.models, "generate_content", fake_generate)

    msgs = [Message(role="user", text="quanto custa?")]
    r1 = p.generate("instruções", msgs, tools.SPECS, "gemini-teste", 15, 300)
    assert r1.tool_calls[0].name == "list_services" and r1.input_tokens == 120
    model, contents, config = sent[0]
    assert config.system_instruction == "instruções" and config.automatic_function_calling.disable is True
    assert config.http_options.timeout == 15000 and config.max_output_tokens == 300
    assert config.thinking_config.thinking_level.value == settings.ai_thinking_budget.upper()
    names = [f.name for f in config.tools[0].function_declarations]
    assert names == [s.name for s in tools.SPECS]

    msgs += [Message(role="model", tool_calls=r1.tool_calls, raw=r1.raw),
             Message(role="tool", tool_results=[(r1.tool_calls[0], {"services": []})])]
    r2 = p.generate("instruções", msgs, tools.SPECS, "gemini-teste", 15, 300)
    assert r2.text == "Corte: R$ 40,00" and not r2.tool_calls
    _, contents, _ = sent[1]
    assert [c.role for c in contents] == ["user", "model", "tool"]
    assert contents[1] is r1.raw  # conteúdo original volta intacto (assinaturas de raciocínio)
    assert contents[2].parts[0].function_response.name == "list_services"

    def quota(model, contents, config):
        raise errors.ClientError(429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    monkeypatch.setattr(p._client.models, "generate_content", quota)
    with pytest.raises(LLMError) as e:
        p.generate("x", [Message(role="user", text="oi")], [], "gemini-teste", 15, 300)
    assert e.value.kind == "quota"
