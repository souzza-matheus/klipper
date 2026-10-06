import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bot.router import handle_incoming
from ..config import settings
from ..db import get_db
from ..jobs import run_all
from ..models import Shop
from ..services.whatsapp import normalize_phone, parse_webhook

router = APIRouter()
log = logging.getLogger("webhook")


@router.post("/webhook/evolution", tags=["webhook"])
@router.post("/webhook/evolution/{event}", tags=["webhook"])
async def evolution_webhook(request: Request, secret: str = "", event: str = "", db: Session = Depends(get_db)):
    if secret != settings.webhook_secret:
        raise HTTPException(403, "secret inválido")
    payload = await request.json()
    msg = parse_webhook(payload)
    if not msg or not msg["phone"]:
        return {"ignored": True}
    try:
        handle_incoming(db, msg["instance"], msg["phone"], msg["text"], msg["name"])
    except Exception:
        db.rollback()
        log.exception("Erro ao processar mensagem de %s", msg["phone"])
    return {"ok": True}


class SimIn(BaseModel):
    phone: str
    text: str
    instance: str | None = None
    name: str = ""


@router.post("/dev/simulate", tags=["dev"])
def simulate(body: SimIn, db: Session = Depends(get_db)):
    """Simula uma mensagem recebida no WhatsApp e devolve as respostas do bot (só com DEV_MODE=true)."""
    if not settings.dev_mode:
        raise HTTPException(404)
    instance = body.instance or db.scalar(select(Shop.evolution_instance).order_by(Shop.id))
    return {"replies": handle_incoming(db, instance, normalize_phone(body.phone), body.text, body.name)}


@router.post("/dev/run-jobs", tags=["dev"])
def dev_run_jobs():
    if not settings.dev_mode:
        raise HTTPException(404)
    run_all()
    return {"ok": True}
