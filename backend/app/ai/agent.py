"""Loop do agente: monta o contexto, chama o modelo, executa as ferramentas pedidas e devolve a resposta.
Qualquer falha (erro, cota, tempo esgotado, resposta inválida) volta para o menu clássico em customer.handle."""
import logging
import re
import time

from sqlalchemy import select

from ..bot import customer as cb
from ..bot.context import Ctx
from ..config import now_local, settings
from ..models import ConversationMessage, Shop
from . import prompts, tools, usage
from .provider import LLMError, LLMProvider, LLMResult, Message

log = logging.getLogger("ai")

MAX_CHUNK = 600
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


def _history(ctx: Ctx) -> list[Message]:
    rows = ctx.db.scalars(select(ConversationMessage).where(
        ConversationMessage.shop_id == ctx.shop.id, ConversationMessage.phone == ctx.phone,
    ).order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        .limit(settings.ai_history_messages)).all()
    msgs = [Message(role="user" if r.role == "user" else "model", text=r.text) for r in reversed(rows) if r.text]
    while msgs and msgs[0].role != "user":  # o histórico começa sempre por uma mensagem do cliente
        msgs.pop(0)
    return msgs


# ---------------------------------------------------------------- chamadas ao modelo

def _generate(ctx: Ctx, system: str, msgs: list[Message], tool_specs) -> LLMResult:
    """Chama o modelo principal; no 429 (cota), tenta uma vez o modelo reserva. Registra cada chamada."""
    models = [settings.ai_model]
    if settings.ai_fallback_model and settings.ai_fallback_model != settings.ai_model:
        models.append(settings.ai_fallback_model)
    for i, model in enumerate(models):
        t0 = time.monotonic()
        try:
            r = get_provider().generate(system, msgs, tool_specs, model, settings.ai_timeout_seconds)
        except LLMError as e:
            usage.record(ctx.db, ctx.shop, ctx.phone, model, False, int((time.monotonic() - t0) * 1000), error=str(e))
            if e.kind == "quota" and i + 1 < len(models):
                log.warning("IA: cota do %s esgotada (429); tentando %s", model, models[i + 1])
                continue
            raise
        usage.record(ctx.db, ctx.shop, ctx.phone, model, True, int((time.monotonic() - t0) * 1000),
                     r.input_tokens, r.output_tokens)
        return r
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


# ---------------------------------------------------------------- uma mensagem do cliente

def _run(ctx: Ctx) -> list[dict]:
    customer = cb.customer(ctx)
    msgs = _history(ctx) + [Message(role="user", text=ctx.text)]
    system = prompts.system_prompt(ctx.shop, now_local(), customer.name)
    tool_log: list[dict] = []
    used = 0
    while True:
        specs = tools.SPECS if used < settings.ai_max_tool_calls else []  # no limite: força a resposta em texto
        result = _generate(ctx, system, msgs, specs)
        if not result.tool_calls:
            ctx.say(*split_message(result.text))
            return tool_log
        if not specs:
            raise LLMError("invalid", "pediu ferramenta depois do limite")
        msgs.append(Message(role="model", text=result.text, tool_calls=result.tool_calls, raw=result.raw))
        before = len(ctx.replies)
        results, terminal = [], False
        for call in result.tool_calls:
            used += 1
            out = tools.run(ctx, call.name, call.args) if used <= settings.ai_max_tool_calls \
                else {"error": "Limite de consultas desta mensagem atingido. Responda ao cliente com o que já sabe."}
            ok = "error" not in out and "unavailable" not in out
            tool_log.append({"name": call.name, "args": call.args, "ok": ok})
            results.append((call, out))
            terminal = terminal or (call.name in tools.TERMINAL and ok and out.get("ok"))
        msgs.append(Message(role="tool", tool_results=results))
        if terminal:
            # O sistema já mandou o resumo (ou chamou a equipe): o texto que o modelo escreveu junto vem antes
            if result.text:
                ctx.replies[before:before] = split_message(result.text)
            return tool_log


def respond(ctx: Ctx) -> str:
    """"off": IA indisponível para esta conversa (usa o fluxo normal); "ok": respondida; "failed": usar o menu."""
    if not usage.available(ctx.db, ctx.shop, ctx.phone):
        return "off"
    ctx.via_ai = True
    start = len(ctx.replies)
    try:
        tool_log = _run(ctx)
    except LLMError as e:
        log.warning("IA falhou para a barbearia %s (%s); usando o menu", ctx.shop.id, e)
        del ctx.replies[start:]
        ctx.via_ai = False
        return "failed"
    except Exception:
        log.exception("Erro inesperado no agente de IA (barbearia %s); usando o menu", ctx.shop.id)
        del ctx.replies[start:]
        ctx.via_ai = False
        return "failed"
    if len(ctx.replies) == start:
        ctx.via_ai = False
        return "failed"
    _save(ctx, "user", ctx.text, "ai")
    _save(ctx, "assistant", "\n\n".join(ctx.replies[start:]), "ai", tool_log)
    return "ok"


def transcribe(db, shop: Shop, phone: str, audio: bytes, mime_type: str) -> str:
    """Transcreve um áudio com o mesmo provedor (e o modelo reserva no 429)."""
    models = [settings.ai_model] + ([settings.ai_fallback_model] if settings.ai_fallback_model else [])
    for i, model in enumerate(models):
        t0 = time.monotonic()
        try:
            r = get_provider().transcribe(audio, mime_type, model, settings.ai_timeout_seconds * 2)
        except LLMError as e:
            usage.record(db, shop, phone, model, False, int((time.monotonic() - t0) * 1000), error=str(e))
            if e.kind == "quota" and i + 1 < len(models):
                continue
            raise
        usage.record(db, shop, phone, model, True, int((time.monotonic() - t0) * 1000), r.input_tokens, r.output_tokens)
        return r.text
    raise LLMError("quota", "sem modelo disponível")
