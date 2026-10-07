"""Quem pode usar a IA, registro de uso e limites (mensal por barbearia e por cliente por hora)."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import now_local, settings
from ..models import AIUsage, ConversationMessage, Shop
from ..services.whatsapp import send_text

log = logging.getLogger("ai")


def provider_configured() -> bool:
    return settings.ai_provider == "gemini" and bool(settings.gemini_api_key)


def month_bounds(month: str | None = None) -> tuple[datetime, datetime]:
    """"AAAA-MM" (padrão: mês atual) -> [início, início do mês seguinte)."""
    now = now_local()
    y, m = (int(x) for x in month.split("-")) if month else (now.year, now.month)
    start = datetime(y, m, 1)
    end = datetime(y + (m == 12), m % 12 + 1, 1)
    return start, end


def month_calls(db: Session, shop: Shop, month: str | None = None) -> int:
    """Chamadas ao modelo no mês (as mensagens barradas antes do modelo não contam)."""
    start, end = month_bounds(month)
    return db.scalar(select(func.count()).select_from(AIUsage).where(
        AIUsage.shop_id == shop.id, AIUsage.kind == "call", AIUsage.created_at >= start,
        AIUsage.created_at < end)) or 0


def tier_allows(shop: Shop) -> bool:
    """No plano gratuito do provedor o conteúdo pode ser usado para treinar: só barbearias liberadas (a demo)."""
    if settings.ai_tier == "paid":
        return True
    return bool(shop.ai_allow_free_tier)


def status(db: Session, shop: Shop) -> tuple[bool, str]:
    """(disponível, motivo) para a barbearia, sem olhar o cliente."""
    if not provider_configured():
        return False, "IA não configurada no servidor (GEMINI_API_KEY)."
    if not tier_allows(shop):
        return False, "IA em modo de teste no servidor: liberada só para a barbearia de demonstração."
    if not shop.ai_enabled:
        return False, "IA desligada nas configurações."
    if month_calls(db, shop) >= shop.ai_monthly_limit:
        return False, "Limite mensal de uso da IA atingido."
    return True, ""


def available(db: Session, shop: Shop, phone: str) -> bool:
    ok, reason = status(db, shop)
    if not ok:
        if reason.startswith("Limite"):
            warn_limit(db, shop)
        return False
    since = now_local() - timedelta(hours=1)
    recent = db.scalar(select(func.count()).select_from(ConversationMessage).where(
        ConversationMessage.shop_id == shop.id, ConversationMessage.phone == phone,
        ConversationMessage.role == "user", ConversationMessage.channel == "ai",
        ConversationMessage.created_at >= since)) or 0
    if recent >= settings.ai_hourly_limit_per_customer:
        log.warning("IA: cliente %s passou de %d mensagens por hora; usando o menu", phone[-4:],
                    settings.ai_hourly_limit_per_customer)
        return False
    return True


def warn_limit(db: Session, shop: Shop) -> None:
    """Avisa o dono uma vez por mês que a IA atingiu o limite e o bot voltou para o menu."""
    month = now_local().strftime("%Y-%m")
    if shop.ai_limit_warned_month == month:
        return
    shop.ai_limit_warned_month = month
    log.warning("IA: barbearia %s atingiu o limite mensal (%d chamadas)", shop.id, shop.ai_monthly_limit)
    if shop.owner_phone:
        send_text(db, shop, shop.owner_phone,
                  f"⚠️ O atendimento com IA atingiu o limite de {shop.ai_monthly_limit} usos deste mês. "
                  "Até o mês que vem, o bot responde com o menu de opções (tudo continua funcionando).")


def record(db: Session, shop: Shop, phone: str, model: str, ok: bool, latency_ms: int,
           input_tokens: int = 0, output_tokens: int = 0, error: str = "", thinking_tokens: int = 0,
           cached_tokens: int = 0, category: str = "") -> AIUsage:
    """Uma chamada ao modelo."""
    row = AIUsage(shop_id=shop.id, phone=phone, model=model, ok=ok, latency_ms=latency_ms, kind="call",
                  input_tokens=input_tokens, output_tokens=output_tokens, thinking_tokens=thinking_tokens,
                  cached_tokens=cached_tokens, error=error[:200], category=category)
    db.add(row)
    db.flush()
    return row


def record_blocked(db: Session, shop: Shop, phone: str, category: str) -> None:
    """Mensagem barrada antes do modelo (pausa por fora do tema, flood, repetição, texto longo): 0 tokens."""
    db.add(AIUsage(shop_id=shop.id, phone=phone, model="", ok=True, latency_ms=0, kind="blocked", category=category))
    db.flush()


def summary(db: Session, shop: Shop, month: str | None = None) -> dict:
    """Uso do mês: chamadas, erros, tokens, mensagens fora do tema e estimativa de tokens economizados pelos
    bloqueios (mensagens barradas x média de tokens por chamada no mês)."""
    start, end = month_bounds(month)
    in_month = (AIUsage.shop_id == shop.id, AIUsage.created_at >= start, AIUsage.created_at < end)
    is_call = AIUsage.kind == "call"
    total = lambda col: func.coalesce(func.sum(case((is_call, col), else_=0)), 0)  # noqa: E731
    count_if = lambda cond: func.coalesce(func.sum(case((cond, 1), else_=0)), 0)  # noqa: E731
    calls, errors, tin, tout, tthink, tcache, offtopic, blocked, paused = db.execute(select(
        count_if(is_call), count_if(is_call & AIUsage.ok.is_(False)),
        total(AIUsage.input_tokens), total(AIUsage.output_tokens), total(AIUsage.thinking_tokens),
        total(AIUsage.cached_tokens),
        count_if(AIUsage.category.like("offtopic%")), count_if(AIUsage.kind == "blocked"),
        count_if(AIUsage.category == "offtopic_pause"),
    ).where(*in_month)).one()
    per_call = (tin + tout + tthink) / calls if calls else 0
    return {
        "month": start.strftime("%Y-%m"), "calls": int(calls), "limit": shop.ai_monthly_limit,
        "errors": int(errors), "input_tokens": int(tin), "output_tokens": int(tout),
        "thinking_tokens": int(tthink), "cached_tokens": int(tcache),
        "offtopic_messages": int(offtopic), "blocked_messages": int(blocked), "paused_messages": int(paused),
        "tokens_saved_estimate": int(round(blocked * per_call)),
    }


def cleanup(db: Session, days: int = 30) -> int:
    """Apaga o histórico de conversa com mais de N dias."""
    limit = now_local() - timedelta(days=days)
    rows = db.query(ConversationMessage).filter(ConversationMessage.created_at < limit).delete(synchronize_session=False)
    return rows


def startup_notice() -> None:
    if provider_configured() and settings.ai_tier != "paid":
        log.warning("IA no plano GRATUITO (AI_TIER=free): o Google pode usar o conteúdo das conversas para melhorar "
                    "os produtos dele. Ligada só para barbearias com ai_allow_free_tier (use dados fictícios).")
