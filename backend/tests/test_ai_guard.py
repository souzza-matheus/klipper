"""Agente de IA: filtros antes do modelo, conversas fora do tema e limite de tokens (FakeProvider, sem rede)."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.ai import agent, usage
from app.ai.provider import ToolCall
from app.bot.context import conversation_for
from app.bot.router import handle_incoming
from app.config import now_local, settings
from app.models import AIUsage, Customer, Shop
from app.services.whatsapp import parse_webhook

INST = "barbearia-demo"
PHONE = "5531977776666"
OFF = ToolCall("mark_off_topic", {"category": "receita"})


@pytest.fixture()
def fake(monkeypatch):
    from app.ai.fake import FakeProvider
    f = FakeProvider()
    monkeypatch.setattr(settings, "gemini_api_key", "chave-de-teste")
    monkeypatch.setattr(settings, "ai_tier", "paid")
    monkeypatch.setattr(agent, "get_provider", lambda: f)
    return f


@pytest.fixture()
def env(db, fake):
    shop = db.scalar(select(Shop))
    shop.ai_enabled = True
    db.add(Customer(shop_id=shop.id, phone=PHONE, name="Carlos Silva"))
    db.commit()
    return db, shop


def say(db, text):
    return "\n---\n".join(handle_incoming(db, INST, PHONE, text, "Carlos"))


def blocked(db, category):
    return db.scalars(select(AIUsage).where(AIUsage.kind == "blocked", AIUsage.category == category)).all()


# ---------------------------------------------------------------- filtros antes do modelo

def test_sticker_reaction_and_empty_never_reach_the_model(env, fake):
    db, _ = env
    for kind in ("stickerMessage", "reactionMessage"):
        assert parse_webhook({"event": "messages.upsert", "instance": INST, "data": {
            "key": {"id": "S1", "fromMe": False, "remoteJid": f"{PHONE}@s.whatsapp.net"},
            "message": {kind: {}}}}) is None
    assert "Bem-vindo" in say(db, "[anexo]")  # imagem sem legenda: fluxo normal, sem IA
    assert "Bem-vindo" in say(db, "")
    assert "Bem-vindo" in say(db, "   ")
    assert fake.calls == []


def test_giant_text_is_refused_and_long_text_is_cut(env, fake):
    db, _ = env
    assert say(db, "a" * 1501) == agent.MSG_TOO_LONG
    assert fake.calls == [] and len(blocked(db, "too_long")) == 1
    fake.script = ["Certo!"]
    say(db, "x" * 499 + "FIM" + "y" * 400)
    sent = fake.calls[0]["messages"][-1].text
    assert sent.endswith("x" * 499 + "F") and "y" not in sent.split("MENSAGEM DO CLIENTE:")[1]


def test_repeated_message_answers_once_without_model(env, fake):
    db, _ = env
    fake.script = ["Oi! Como posso ajudar?", "Oi de novo!"]
    say(db, "oi tudo bem")
    say(db, "oi tudo bem")
    assert say(db, "oi tudo bem") == agent.MSG_REPEAT
    assert say(db, "oi tudo bem") == ""  # já avisado: silêncio, sem gastar IA
    assert len(fake.calls) == 2 and len(blocked(db, "repeat")) == 2
    fake.script = ["Claro, que dia?"]
    assert "que dia" in say(db, "quero agendar")  # mensagem diferente volta para a IA


def test_flood_answers_once_without_model(env, fake):
    db, _ = env
    fake.script = [f"resposta {i}" for i in range(5)]
    for i in range(5):
        say(db, f"mensagem {i}")
    assert say(db, "mensagem 5") == agent.MSG_FLOOD
    assert say(db, "mensagem 6") == ""
    assert len(fake.calls) == 5 and len(blocked(db, "flood")) == 2
    # Depois da janela, volta ao normal
    from app.models import ConversationMessage
    for m in db.scalars(select(ConversationMessage)):
        m.created_at -= timedelta(seconds=settings.ai_flood_seconds + 1)
    conversation_for(db, *_shop_phone(db)).data = {}
    db.commit()
    fake.script = ["Pode falar!"]
    assert say(db, "voltei") == "Pode falar!"


def _shop_phone(db):
    return db.scalar(select(Shop)), PHONE


def test_menu_numbers_still_bypass_filters(env, fake):
    db, _ = env
    assert "Qual serviço" in say(db, "1")
    assert fake.calls == []


# ---------------------------------------------------------------- fora do tema

def test_off_topic_streak_pause_and_cooldown(env, fake):
    db, shop = env
    fake.script = [("Aqui eu só ajudo com agendamentos. Quer marcar um horário?", OFF), OFF, OFF]
    assert "Quer marcar um horário?" in say(db, "me passa uma receita de bolo")  # 1ª: recusa do modelo
    r2 = say(db, "e de pudim?")
    assert r2 == agent.MSG_OFF_TOPIC_2.format(noun="barbearia") and "*menu*" in r2  # 2ª: texto fixo
    r3 = say(db, "e de brigadeiro?")
    assert "Bem-vindo" in r3  # 3ª: pausa a IA e mostra o menu
    assert len(fake.calls) == 3
    # Durante a pausa: texto livre recebe o menu, sem chamar o modelo; o menu numerado funciona
    assert "Bem-vindo" in say(db, "quero agendar amanhã")
    assert "Qual serviço" in say(db, "1")
    assert len(fake.calls) == 3
    assert len(blocked(db, "offtopic_pause")) == 1
    # Fim da pausa
    conv = conversation_for(db, shop, PHONE)
    conv.data = {**conv.data, "ai_pause_until": (now_local() - timedelta(minutes=1)).isoformat()}
    conv.state = "menu"
    db.commit()
    fake.script = ["Bora! Que dia?"]
    assert say(db, "quero agendar") == "Bora! Que dia?"
    assert conversation_for(db, shop, PHONE).data.get("ai_offtopic") == 0


def test_on_topic_message_resets_the_counter(env, fake):
    db, shop = env
    fake.script = [OFF, "Abrimos às 9h!", ("Só ajudo com agendamentos.", OFF)]
    say(db, "quem ganhou o jogo?")
    assert conversation_for(db, shop, PHONE).data["ai_offtopic"] == 1
    say(db, "que horas abre?")
    assert conversation_for(db, shop, PHONE).data["ai_offtopic"] == 0
    assert say(db, "e a política?") == "Só ajudo com agendamentos."  # de novo a 1ª: resposta do modelo


def test_cooldown_survives_menu_flows(env, fake):
    db, shop = env
    fake.script = [OFF, OFF, OFF]
    for t in ("piada", "outra piada", "mais uma"):
        say(db, t)
    say(db, "1")  # entra no fluxo do menu (reset do estado)
    say(db, "menu")
    assert conversation_for(db, shop, PHONE).data.get("ai_pause_until")
    assert "Bem-vindo" in say(db, "conta outra")
    assert len(fake.calls) == 3


def test_off_topic_is_logged_with_category_and_shown_in_usage(env, fake):
    db, shop = env
    fake.script = [OFF, ToolCall("mark_off_topic", {"category": "esporte"}), OFF]
    for t in ("receita", "futebol", "receita de novo"):
        say(db, t)
    say(db, "mais uma")  # pausa
    cats = [r.category for r in db.scalars(select(AIUsage).where(AIUsage.kind == "call").order_by(AIUsage.id))]
    assert cats == ["offtopic:receita", "offtopic:esporte", "offtopic:receita"]
    s = usage.summary(db, shop)
    assert s["offtopic_messages"] == 4 and s["paused_messages"] == 1 and s["blocked_messages"] == 1
    assert s["calls"] == 3 and s["tokens_saved_estimate"] > 0
    assert usage.month_calls(db, shop) == 3  # as barradas não contam no limite mensal


# ---------------------------------------------------------------- tokens

def test_output_token_limit_is_sent_on_every_call(env, fake, monkeypatch):
    db, _ = env
    monkeypatch.setattr(settings, "ai_max_output_tokens", 123)
    fake.script = [ToolCall("list_services", {}), "Temos corte e barba."]
    say(db, "o que vocês fazem?")
    assert [c["max_output_tokens"] for c in fake.calls] == [123, 123]
    row = db.scalars(select(AIUsage).order_by(AIUsage.id.desc())).first()
    assert row.thinking_tokens == 5  # tokens de raciocínio registrados


def test_history_is_short_and_clipped(env, fake, monkeypatch):
    db, _ = env
    monkeypatch.setattr(settings, "ai_history_messages", 4)
    for i in range(4):
        say(db, str(i + 1))  # respostas longas do menu entram no histórico
        say(db, "menu")
    fake.script = ["Ok"]
    say(db, "quero agendar")
    msgs = fake.calls[0]["messages"]
    assert len(msgs) <= 5 and all(len(m.text) <= agent.HISTORY_CHARS + 1 for m in msgs[:-1])


def test_usage_endpoint_shows_blocked_and_savings(env, fake):
    from fastapi.testclient import TestClient
    from app.main import app
    db, shop = env
    fake.script = [OFF, OFF, OFF]
    for t in ("a", "b", "c", "d"):
        say(db, f"receita {t}")
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + c.post(
        "/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()["token"]
    u = c.get("/api/ai/usage").json()
    assert u["offtopic_messages"] == 4 and u["tokens_saved_estimate"] > 0 and u["thinking_tokens"] >= 0


def test_fast_menu_navigation_is_not_flood(env, fake):
    db, _ = env
    for t in ("1", "menu", "3", "menu", "4", "menu", "5"):
        say(db, t)
    fake.script = ["Claro! Para qual dia?"]
    assert say(db, "quero agendar") == "Claro! Para qual dia?"
