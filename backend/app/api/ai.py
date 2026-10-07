"""Configurações e uso do atendimento com IA (seção "Atendimento com IA" do app)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai import usage
from ..config import settings
from ..db import get_db
from ..models import Shop
from .admin import shop_of

router = APIRouter()


class AISettingsIn(BaseModel):
    ai_enabled: bool | None = None
    ai_audio_enabled: bool | None = None


def _settings_out(db: Session, shop: Shop) -> dict:
    available, reason = usage.status(db, shop)
    return {
        "ai_enabled": shop.ai_enabled, "ai_audio_enabled": shop.ai_audio_enabled,
        "monthly_limit": shop.ai_monthly_limit, "calls_this_month": usage.month_calls(db, shop),
        "configured": usage.provider_configured(), "tier": settings.ai_tier,
        "free_tier_allowed": usage.tier_allows(shop), "available": available, "reason": reason,
        "test_mode_warning": "IA em modo de teste: use apenas com dados fictícios."
        if settings.ai_tier != "paid" else "",
    }


@router.get("/ai/settings", tags=["ai"])
def get_ai_settings(shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    return _settings_out(db, shop)


@router.put("/ai/settings", tags=["ai"])
def put_ai_settings(body: AISettingsIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    if body.ai_enabled is not None:
        shop.ai_enabled = body.ai_enabled
    if body.ai_audio_enabled is not None:
        shop.ai_audio_enabled = body.ai_audio_enabled
    db.commit()
    return _settings_out(db, shop)


@router.get("/ai/usage", tags=["ai"])
def get_ai_usage(month: str | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "Use month=AAAA-MM")
    return usage.summary(db, shop, month)
