"""Loop do agente: filtra o que nem precisa de IA, monta o contexto, chama o modelo, executa as ferramentas e
devolve a resposta. Qualquer falha (erro, cota, tempo esgotado, resposta inválida) volta para o menu clássico.

Economia de tokens e fora do tema:
- antes do modelo: mensagem vazia/sticker/imagem sem legenda (fluxo normal), texto acima de AI_REJECT_INPUT_CHARS
  (texto fixo), a mesma mensagem AI_REPEAT_LIMIT vezes seguidas ou flood (texto fixo uma vez, depois silêncio) e
  número em pausa por fora do tema (menu clássico);
- o modelo marca a mensagem fora do tema com mark_off_topic; na 2ª seguida o código responde com texto fixo e, da 3ª
  em diante, a IA pausa para o número por AI_OFFTOPIC_COOLDOWN_MINUTES (o menu numerado continua funcionando).
"""
import logging
import re
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from ..bot import customer as cb
from ..bot.context import Ctx, norm
from ..config import now_local, settings
from ..models import ConversationMessage, Shop
from . import prompts, tools, usage
from .provider import LLMError, LLMProvider, Message

log = logging.getLogger("ai")

MAX_CHUNK = 600
HISTORY_CHARS = 400  # cada mensagem antiga entra resumida no contexto
NO_TEXT = {"", "[anexo]", "[áudio]"}  # sticker, reação, imagem sem legenda: nada para a IA interpretar

MSG_TOO_LONG = ("Sua mensagem ficou bem longa. 🙏 Pode me dizer em poucas palavras o que precisa? "
                "(ou mande *menu* para ver as opções)")
MSG_FLOOD = ("Recebi várias mensagens seguidas. 🙂 Me diga em uma mensagem só o que você precisa, "
             "ou mande *menu* para ver as opções.")
MSG_REPEAT = ("Já recebi essa mensagem. Se precisar, mande *menu* para ver as opções ou *atendente* para falar "
              "com uma pessoa.")
MSG_OFF_TOPIC_1 = "Aqui eu só consigo ajudar com agendamentos e informações da {noun}. Quer marcar um horário?"
MSG_OFF_TOPIC_2 = ("Aqui eu só consigo ajudar com agendamentos e informações da {noun}. Mande *menu* para ver as "
                   "opções ou me diga o que quer agendar.")

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.ai_provider == "gemini":
            from .gemini import GeminiProvider
            _provider = GeminiProvider(settings.gemini_api_key)
        else:
            raise LLMError("other", f"AI_PROVIDER desconhecido: {settings.ai_provider}")
    return _provider


# ---------------------------------------------------------------- histórico

def _save(ctx: Ctx, role: str, text: str, channel: str, tool_calls: list | None = None) -> None:
    ctx.db.add(ConversationMessage(shop_id=ctx.shop.id, phone=ctx.phone, role=role, channel=channel,
                                   text=(text or "")[:4000], tool_calls=tool_calls or None))


def record_menu_turn(ctx: Ctx) -> None:
    """Guarda as mensagens do fluxo de menu para a IA saber o que já aconteceu na conversa."""
    _save(ctx, "user", ctx.text, "menu")
    if ctx.replies:
        _save(ctx, "assistant", "\n\n".join(ctx.replies), "menu")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _history(ctx: Ctx) -> list[Message]:
    """Últimas AI_HISTORY_MESSAGES mensagens (sem as barradas), cada uma resumida."""
    rows = ctx.db.scalars(select(ConversationMessage).where(
        ConversationMessage.shop_id == ctx.shop.id, ConversationMessage.phone == ctx.phone,
        ConversationMessage.channel != "blocked",
    ).order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(settings.ai_history_messages)).all()
    msgs = [Message(role="user" if r.role == "user" else "model", text=_clip(r.text, HISTORY_CHARS))
            for r in reversed(rows) if r.text]
    while msgs and msgs[0].role != "user":  # o histórico começa sempre por uma mensagem do cliente
        msgs.pop(0)
    return msgs


def _recent_user_texts(ctx: Ctx, since: datetime | None = None, limit: int = 10) -> list[str]:
    """Mensagens livres recentes do cliente (as que iriam para a IA). A navegação pelo menu numerado não conta
    para flood nem repetição."""
    q = select(ConversationMessage.text).where(
        ConversationMessage.shop_id == ctx.shop.id, ConversationMessage.phone == ctx.phone,
        ConversationMessage.role == "user", ConversationMessage.channel.in_(("ai", "blocked")))
    if since:
        q = q.where(ConversationMessage.created_at >= since)
    return list(ctx.db.scalars(q.order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
                               .limit(limit)))


# ---------------------------------------------------------------- chamadas ao modelo

# Falhas em que vale tentar o modelo reserva: cota (429), sobrecarga (5xx) e tempo esgotado do modelo principal
FALLBACK_KINDS = {"quota", "unavailable", "timeout"}


def _generate(ctx: Ctx, system: str, msgs: list[Message], tool_specs):
    """Chama o modelo principal; no 429 (cota), 5xx (sobrecarga) ou timeout, tenta uma vez o modelo reserva. Registra cada chamada.
    Se os dois estiverem sobrecarregados (5xx), espera um pouco e repete a rodada: o pico costuma passar em segundos
    e cair no menu no meio da conversa confunde o cliente. Devolve (resultado, linha de uso)."""
    models = [settings.ai_model]
    if settings.ai_fallback_model and settings.ai_fallback_model != settings.ai_model:
        models.append(settings.ai_fallback_model)
    rounds = 1 + max(0, settings.ai_unavailable_retries)
    for attempt in range(rounds):
        for i, model in enumerate(models):
            t0 = time.monotonic()
            try:
                r = get_provider().generate(system, msgs, tool_specs, model, settings.ai_timeout_seconds,
                                            settings.ai_max_output_tokens)
            except LLMError as e:
                usage.record(ctx.db, ctx.shop, ctx.phone, model, False, int((time.monotonic() - t0) * 1000),
                             error=str(e))
                if e.kind in FALLBACK_KINDS and i + 1 < len(models):
                    log.warning("IA: %s indisponível (%s); tentando %s", model, e.kind, models[i + 1])
                    continue
                if e.kind == "unavailable" and attempt + 1 < rounds:
                    log.warning("IA: modelos sobrecarregados; nova tentativa em %ss",
                                settings.ai_unavailable_retry_delay_seconds)
                    time.sleep(settings.ai_unavailable_retry_delay_seconds)
                    break
                raise
            row = usage.record(ctx.db, ctx.shop, ctx.phone, model, True, int((time.monotonic() - t0) * 1000),
                               r.input_tokens, r.output_tokens, thinking_tokens=r.thinking_tokens,
                               cached_tokens=r.cached_tokens)
            return r, row
    raise LLMError("quota", "sem modelo disponível")


def split_message(text: str, limit: int = MAX_CHUNK) -> list[str]:
    """Quebra respostas longas em mensagens de até ~600 caracteres: por parágrafo, depois por frase."""
    text = (text or "").strip()
    if len(text) <= limit:
        return [text] if text else []
    units: list[tuple[str, str]] = []  # (trecho, separador antes dele)
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        parts = [para] if len(para) <= limit else re.split(r"(?<=[.!?])\s+", para)
        for j, part in enumerate(parts):
            sep = "\n\n" if j == 0 else " "
            while len(part) > limit:  # frase gigante: corta no último espaço
                cut = part.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                units.append((part[:cut].strip(), sep))
                part, sep = part[cut:].strip(), " "
            units.append((part, sep))
    out, cur = [], ""
    for unit, sep in units:
        if cur and len(cur) + len(sep) + len(unit) > limit:
            out.append(cur)
            cur = unit
        else:
            cur = f"{cur}{sep}{unit}" if cur else unit
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------- fora do tema

def _paused(ctx: Ctx) -> bool:
    until = ctx.get("ai_pause_until")
    if not until:
        return False
    if datetime.fromisoformat(until) > now_local():
        return True
    ctx.put(ai_pause_until=None, ai_offtopic=0)  # a pausa acabou
    return False


def _off_topic_reply(ctx: Ctx, model_text: str) -> None:
    """1ª fora do tema: a recusa do modelo; 2ª seguida: texto fixo; 3ª em diante: pausa a IA e mostra o menu."""
    noun = prompts.business_noun(ctx.shop)
    streak = int(ctx.get("ai_offtopic") or 0) + 1
    ctx.put(ai_offtopic=streak)
    if streak == 1:
        ctx.say(*(split_message(model_text) or [MSG_OFF_TOPIC_1.format(noun=noun)]))
    elif streak == 2:
        ctx.say(MSG_OFF_TOPIC_2.format(noun=noun))
    else:
        until = now_local() + timedelta(minutes=settings.ai_offtopic_cooldown_minutes)
        ctx.put(ai_pause_until=until.isoformat())
        log.info("IA pausada por %d min para ...%s (fora do tema)", settings.ai_offtopic_cooldown_minutes,
                 ctx.phone[-4:])
        cb.show_menu(ctx)


# ---------------------------------------------------------------- filtros antes do modelo

def _guard(ctx: Ctx) -> str | None:
    """Barra sem chamar o modelo. Devolve a categoria do bloqueio (e já responde, ou fica em silêncio) ou None."""
    now = now_local()
    if len(ctx.text) > settings.ai_reject_input_chars:
        ctx.say(MSG_TOO_LONG)
        return "too_long"

    current = norm(ctx.text)
    previous = _recent_user_texts(ctx, limit=settings.ai_repeat_limit - 1)
    if len(previous) == settings.ai_repeat_limit - 1 and all(norm(t) == current for t in previous):
        if ctx.get("ai_repeat_warned") != current:  # responde uma vez só por sequência
            ctx.put(ai_repeat_warned=current)
            ctx.say(MSG_REPEAT)
        return "repeat"
    if ctx.get("ai_repeat_warned") and ctx.get("ai_repeat_warned") != current:
        ctx.put(ai_repeat_warned=None)

    window = now - timedelta(seconds=settings.ai_flood_seconds)
    if len(_recent_user_texts(ctx, since=window, limit=settings.ai_flood_messages + 1)) + 1 > settings.ai_flood_messages:
        warned = ctx.get("ai_flood_warned_until")
        if not warned or datetime.fromisoformat(warned) < now:
            ctx.put(ai_flood_warned_until=(now + timedelta(seconds=settings.ai_flood_seconds)).isoformat())
            ctx.say(MSG_FLOOD)
        return "flood"
    return None


# ---------------------------------------------------------------- uma mensagem do cliente

def _run(ctx: Ctx) -> list[dict]:
    customer = cb.customer(ctx)
    text = ctx.text[:settings.ai_max_input_chars]  # o resto não vai para o modelo
    msgs = _history(ctx) + [Message(role="user",
                                    text=prompts.user_turn(ctx.shop, now_local(), customer.name, text))]
    system = prompts.system_prompt(ctx.shop)
    tool_log: list[dict] = []
    used = 0
    while True:
        specs = tools.SPECS if used < settings.ai_max_tool_calls else []  # no limite: força a resposta em texto
        result, row = _generate(ctx, system, msgs, specs)
        if not result.tool_calls:
            ctx.say(*split_message(result.text))
            if ctx.get("ai_offtopic"):
                ctx.put(ai_offtopic=0)  # mensagem dentro do tema zera o contador
            return tool_log
        if not specs:
            raise LLMError("invalid", "pediu ferramenta depois do limite")
        msgs.append(Message(role="model", text=result.text, tool_calls=result.tool_calls, raw=result.raw))
        before = len(ctx.replies)
        results, terminal, off_topic = [], False, None
        for call in result.tool_calls:
            used += 1
            out = tools.run(ctx, call.name, call.args) if used <= settings.ai_max_tool_calls \
                else {"error": "Limite de consultas desta mensagem atingido. Responda ao cliente com o que já sabe."}
            ok = "error" not in out and "unavailable" not in out
            tool_log.append({"name": call.name, "args": call.args, "ok": ok})
            results.append((call, out))
            if call.name == "mark_off_topic":
                off_topic = out.get("category", "outro")
            terminal = terminal or (call.name in tools.TERMINAL and ok and out.get("ok"))
        msgs.append(Message(role="tool", tool_results=results))
        if off_topic:
            row.category = f"offtopic:{off_topic}"[:40]
            del ctx.replies[before:]
            _off_topic_reply(ctx, result.text)
            return tool_log
        if terminal:
            # O sistema já mandou o resumo (ou chamou a equipe): o texto que o modelo escreveu junto vem antes
            if result.text:
                ctx.replies[before:before] = split_message(result.text)
            if ctx.get("ai_offtopic"):
                ctx.put(ai_offtopic=0)
            return tool_log


def respond(ctx: Ctx) -> str:
    """"off": IA indisponível ou nada para interpretar (usa o fluxo normal); "ok": respondida; "silent": barrada
    sem resposta (flood ou repetição já avisados); "paused" e "failed": usar o menu clássico."""
    if norm(ctx.text) in NO_TEXT or ctx.text.strip() in NO_TEXT:
        return "off"
    if not usage.available(ctx.db, ctx.shop, ctx.phone):
        return "off"
    ctx.via_ai = True  # daqui em diante o agente grava o histórico desta mensagem
    if _paused(ctx):
        usage.record_blocked(ctx.db, ctx.shop, ctx.phone, "offtopic_pause")
        _save(ctx, "user", ctx.text, "blocked")
        return "paused"
    start = len(ctx.replies)
    blocked = _guard(ctx)
    if blocked:
        usage.record_blocked(ctx.db, ctx.shop, ctx.phone, blocked)
        _save(ctx, "user", ctx.text, "blocked")
        if len(ctx.replies) > start:
            _save(ctx, "assistant", "\n\n".join(ctx.replies[start:]), "blocked")
            return "ok"
        return "silent"
    try:
        tool_log = _run(ctx)
    except LLMError as e:
        log.warning("IA falhou para a barbearia %s (%s); usando o menu", ctx.shop.id, e)
        return _failed(ctx, start)
    except Exception:
        log.exception("Erro inesperado no agente de IA (barbearia %s); usando o menu", ctx.shop.id)
        return _failed(ctx, start)
    if len(ctx.replies) == start:
        return _failed(ctx, start)
    _save(ctx, "user", ctx.text, "ai")
    _save(ctx, "assistant", "\n\n".join(ctx.replies[start:]), "ai", tool_log)
    return "ok"


def _failed(ctx: Ctx, start: int) -> str:
    del ctx.replies[start:]
    ctx.via_ai = False  # o menu clássico responde e o histórico é gravado como menu
    return "failed"


def transcribe(db, shop: Shop, phone: str, audio: bytes, mime_type: str) -> str:
    """Transcreve um áudio com o mesmo provedor (e o modelo reserva no 429, 5xx ou timeout)."""
    models = [settings.ai_model] + ([settings.ai_fallback_model] if settings.ai_fallback_model else [])
    for i, model in enumerate(models):
        t0 = time.monotonic()
        try:
            r = get_provider().transcribe(audio, mime_type, model, settings.ai_timeout_seconds * 2)
        except LLMError as e:
            usage.record(db, shop, phone, model, False, int((time.monotonic() - t0) * 1000), error=str(e))
            if e.kind in FALLBACK_KINDS and i + 1 < len(models):
                continue
            raise
        usage.record(db, shop, phone, model, True, int((time.monotonic() - t0) * 1000), r.input_tokens,
                     r.output_tokens, thinking_tokens=r.thinking_tokens, cached_tokens=r.cached_tokens,
                     category="audio")
        return r.text
    raise LLMError("quota", "sem modelo disponível")
