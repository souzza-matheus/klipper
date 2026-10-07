import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bot.router import handle_incoming
from ..config import settings
from ..db import SessionLocal, get_db
from ..jobs import run_all
from ..models import Shop
from ..security import same_secret
from ..services.payments import save_receipt
from ..services.whatsapp import (
    EvolutionError, mask_phone, media_base64, normalize_phone, parse_webhook, send_text,
)

router = APIRouter()
log = logging.getLogger("webhook")


@router.post("/webhook/evolution", tags=["webhook"])
@router.post("/webhook/evolution/{event}", tags=["webhook"])
async def evolution_webhook(request: Request, background: BackgroundTasks, event: str = "",
                            db: Session = Depends(get_db)):
    # Secret só no cabeçalho X-Webhook-Secret (nunca na URL, que aparece em logs). Cada barbearia tem o seu.
    given = request.headers.get("x-webhook-secret")
    if not given:
        raise HTTPException(403, "secret inválido")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "payload inválido")
    instance = payload.get("instance") if isinstance(payload, dict) else None
    shop = db.scalar(select(Shop).where(Shop.evolution_instance == instance)) if isinstance(instance, str) else None
    expected = (shop.webhook_secret if shop and shop.webhook_secret else settings.webhook_secret)
    if not same_secret(given, expected):
        raise HTTPException(403, "secret inválido")
    try:
        msg = parse_webhook(payload)
    except Exception:  # tipos inesperados: ignora, nunca derruba
        log.warning("Webhook com payload inválido ignorado")
        return {"ignored": True}
    if not msg or not msg["phone"]:
        return {"ignored": True}
    if msg.get("audio"):
        # Áudio: só com a transcrição por IA ligada; baixar e transcrever leva alguns segundos
        background.add_task(process_audio, msg["instance"], msg["phone"], msg["name"], msg["audio"])
        return {"ok": True, "audio": True}
    try:
        # Em uma thread: a resposta da IA pode levar alguns segundos e não pode travar a API
        await run_in_threadpool(handle_incoming, db, msg["instance"], msg["phone"], msg["text"], msg["name"])
    except Exception:
        db.rollback()
        log.exception("Erro ao processar mensagem de %s", mask_phone(msg["phone"]))
    if msg.get("media"):
        # Baixar a mídia leva alguns segundos: fica para depois da resposta do bot
        background.add_task(store_receipt, msg["instance"], msg["phone"], msg["media"])
    return {"ok": True}


MSG_AUDIO_LONG = "Seu áudio é um pouco longo para eu ouvir. 🙏 Consegue escrever ou mandar um áudio de até 2 minutos?"
MSG_AUDIO_FAIL = "Não consegui ouvir o seu áudio. Pode escrever, por favor? (ou mande *menu* para ver as opções)"


def process_audio(instance: str, phone: str, name: str, audio: dict) -> None:
    """Áudio do cliente: com a IA e a transcrição ligadas, transcreve e segue o fluxo normal com o texto.
    Sem elas, o áudio é ignorado (como antes)."""
    from ..ai import agent, usage
    db = SessionLocal()
    try:
        shop = db.scalar(select(Shop).where(Shop.evolution_instance == instance))
        if shop is None or not shop.ai_audio_enabled or not usage.available(db, shop, phone):
            db.commit()  # guarda o aviso de limite, se houve
            return
        if audio.get("seconds", 0) > settings.ai_audio_max_seconds:
            send_text(db, shop, phone, MSG_AUDIO_LONG)
            db.commit()
            return
        try:
            mime, data = media_base64(shop, audio)
            text = agent.transcribe(db, shop, phone, data, mime or audio.get("mimetype") or "audio/ogg")
        except (EvolutionError, agent.LLMError):
            log.exception("Falha ao transcrever o áudio de %s", phone[-4:])
            send_text(db, shop, phone, MSG_AUDIO_FAIL)
            db.commit()
            return
        db.commit()
        if text.strip() == "[inaudível]":
            send_text(db, shop, phone, MSG_AUDIO_FAIL)
            db.commit()
            return
        handle_incoming(db, instance, phone, text, name)
    except Exception:
        db.rollback()
        log.exception("Erro ao processar o áudio de %s", phone[-4:])
    finally:
        db.close()


def store_receipt(instance: str, phone: str, media: dict) -> None:
    """Guarda imagem/PDF mandado pelo cliente como comprovante dos Pix pendentes dele (se houver)."""
    db = SessionLocal()
    try:
        shop = db.scalar(select(Shop).where(Shop.evolution_instance == instance))
        if shop and save_receipt(db, shop, phone, media):
            db.commit()
    except Exception:
        db.rollback()
        log.exception("Erro ao guardar o comprovante de %s", mask_phone(phone))
    finally:
        db.close()


class SimIn(BaseModel):
    phone: str
    text: str
    instance: str | None = None
    name: str = ""


def dev_only(x_setup_token: str = Header("", description="SETUP_TOKEN do .env")) -> None:
    """Rotas de desenvolvimento: 404 em produção e, mesmo em desenvolvimento, só com o SETUP_TOKEN (quem alcança a
    porta do backend na rede não consegue se passar pelo dono no bot)."""
    if not settings.dev_mode:
        raise HTTPException(404)
    if not same_secret(x_setup_token, settings.setup_token):
        raise HTTPException(403, "Informe o SETUP_TOKEN no cabeçalho X-Setup-Token")


@router.post("/dev/simulate", tags=["dev"], dependencies=[Depends(dev_only)])
def simulate(body: SimIn, db: Session = Depends(get_db)):
    """Simula uma mensagem recebida no WhatsApp e devolve as respostas do bot (só com DEV_MODE=true e o cabeçalho
    X-Setup-Token)."""
    instance = body.instance or db.scalar(select(Shop.evolution_instance).order_by(Shop.id))
    return {"replies": handle_incoming(db, instance, normalize_phone(body.phone), body.text, body.name)}


@router.post("/dev/run-jobs", tags=["dev"], dependencies=[Depends(dev_only)])
def dev_run_jobs():
    run_all()
    return {"ok": True}
