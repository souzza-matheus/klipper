"""Alertas para o dono e para os barbeiros."""
from sqlalchemy.orm import Session

from ..models import Barber, Shop
from .whatsapp import phones_match, send_text


def notify_staff(db: Session, shop: Shop, text: str, barber: Barber | None = None) -> None:
    """Envia para o dono e, se informado, para o barbeiro do atendimento (sem duplicar)."""
    targets = []
    if shop.owner_phone:
        targets.append(shop.owner_phone)
    if barber and barber.phone and not any(phones_match(barber.phone, t) for t in targets):
        targets.append(barber.phone)
    for phone in targets:
        send_text(db, shop, phone, text)
