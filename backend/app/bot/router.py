"""Ponto de entrada das mensagens recebidas: decide entre bot do cliente e bot do estabelecimento."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Shop
from . import customer, owner
from .context import Ctx, norm

log = logging.getLogger("bot")


def handle_incoming(db: Session, instance: str, phone: str, text: str, push_name: str = "") -> list[str]:
    shop = db.scalar(select(Shop).where(Shop.evolution_instance == instance))
    if shop is None:
        log.warning("Mensagem para instância desconhecida: %s", instance)
        return []
    conv = db.scalar(select(Conversation).where(Conversation.shop_id == shop.id, Conversation.phone == phone))
    if conv is None:
        conv = Conversation(shop_id=shop.id, phone=phone, state="menu", data={})
        db.add(conv)
        db.flush()

    ctx = Ctx(db=db, shop=shop, conv=conv, phone=phone, text=text, push_name=push_name)
    staff = owner.is_staff(shop, phone)
    as_customer = bool((conv.data or {}).get("as_customer"))

    if staff and as_customer and norm(text) == "painel":
        conv.data = {}
        owner.show_menu(ctx)
    elif staff and not as_customer:
        owner.handle(ctx)
    else:
        if not staff and as_customer:
            conv.data = {}
        customer.handle(ctx)

    sent = list(ctx.replies)
    ctx.flush()
    db.commit()
    return sent
