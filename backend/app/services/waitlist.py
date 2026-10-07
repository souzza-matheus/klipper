"""Lista de espera: quando não há horário, o cliente entra na lista do dia. Quando um horário abre (cancelamento,
sinal não pago, remarcação), a primeira pessoa da fila que cabe nele recebe o aviso no WhatsApp e a vaga fica
reservada para ela por alguns minutos (agendamento "held"). Sem resposta, a reserva cai e a próxima pessoa é avisada.
"""
import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, Barber, Customer, Service, Shop, WaitStatus, WaitlistEntry,
)
from .fmt import dt_label, money

log = logging.getLogger("waitlist")

OFFER_STATE = "wl_offer"


class WaitlistError(ValueError):
    pass


def join(db: Session, shop: Shop, customer: Customer, service: Service, day: date, barber: Barber | None = None,
         after: time | None = None, before: time | None = None, via: str = "bot") -> WaitlistEntry:
    if service.shop_id != shop.id or (barber and barber.shop_id != shop.id):
        raise WaitlistError("Não encontrado.")
    if day < now_local().date():
        raise WaitlistError("Essa data já passou.")
    same = db.scalar(select(WaitlistEntry).where(
        WaitlistEntry.shop_id == shop.id, WaitlistEntry.customer_id == customer.id,
        WaitlistEntry.service_id == service.id, WaitlistEntry.day == day,
        WaitlistEntry.status.in_(WaitStatus.OPEN)))
    if same:
        return same
    e = WaitlistEntry(shop_id=shop.id, customer_id=customer.id, service_id=service.id,
                      barber_id=barber.id if barber else None, day=day, after_time=after, before_time=before,
                      created_via=via)
    db.add(e)
    db.flush()
    return e


def position(db: Session, e: WaitlistEntry) -> int:
    """Lugar na fila do dia (por ordem de entrada; empate no horário, pela ordem de cadastro)."""
    ahead = db.scalars(select(WaitlistEntry.id).where(
        WaitlistEntry.shop_id == e.shop_id, WaitlistEntry.day == e.day, WaitlistEntry.status == WaitStatus.WAITING,
        or_(WaitlistEntry.created_at < e.created_at,
            and_(WaitlistEntry.created_at == e.created_at, WaitlistEntry.id <= e.id)))).all()
    return len(ahead)


def _fits(e: WaitlistEntry, start: datetime) -> bool:
    return (e.after_time is None or start.time() >= e.after_time) and \
        (e.before_time is None or start.time() <= e.before_time)


def _candidate_slot(db: Session, shop: Shop, e: WaitlistEntry, barber_id: int | None, start: datetime,
                    end: datetime) -> tuple[datetime, Barber] | None:
    """Primeiro horário livre (para esta pessoa) dentro do intervalo que abriu."""
    from . import scheduling as sch
    earliest = now_local() + timedelta(minutes=shop.min_advance_minutes)
    barbers = sch.active_barbers(db, shop, e.service)
    if e.barber_id:
        barbers = [b for b in barbers if b.id == e.barber_id]
    if barber_id:
        barbers = [b for b in barbers if b.id == barber_id]
    for b in barbers:
        for s in sch.free_slots(db, shop, e.service, b, e.day, customer=e.customer, only_blocking=True):
            s_end = s + timedelta(minutes=e.service.duration_minutes)
            if s >= earliest and s < end and s_end > start and _fits(e, s):
                return s, b
    return None


def on_slot_freed(db: Session, shop: Shop, barber_id: int | None, start: datetime, end: datetime) -> WaitlistEntry | None:
    """Chamado quando um horário abre. Avisa a primeira pessoa da fila do dia que cabe nele."""
    if end <= now_local():
        return None
    db.flush()
    entries = db.scalars(select(WaitlistEntry).where(
        WaitlistEntry.shop_id == shop.id, WaitlistEntry.day == start.date(),
        WaitlistEntry.status == WaitStatus.WAITING).order_by(WaitlistEntry.created_at, WaitlistEntry.id)).all()
    for e in entries:
        if e.customer.access_status == "blocked":
            continue
        slot = _candidate_slot(db, shop, e, barber_id, start, end)
        if slot:
            offer(db, shop, e, *slot)
            return e
    return None


def offer(db: Session, shop: Shop, e: WaitlistEntry, start: datetime, barber: Barber) -> Appointment:
    from ..bot.context import Ctx, conversation_for
    from . import scheduling as sch
    from .whatsapp import send_text
    hold = sch.create_appointment(db, shop, e.customer, barber, e.service, start, created_via="waitlist",
                                  status=ApptStatus.HELD, force=True)
    now = now_local()
    e.status, e.offered_at = WaitStatus.OFFERED, now
    e.offer_expires_at = now + timedelta(minutes=shop.waitlist_hold_minutes)
    e.offer_appointment_id = hold.id
    send_text(db, shop, e.customer.phone,
              f"🔔 Abriu um horário da lista de espera!\n\n✂️ *{e.service.name}* com {barber.name}\n"
              f"📅 {dt_label(start)}\n💰 {money(e.service.price)}\n\n"
              f"Ele fica reservado para você até {e.offer_expires_at:%H:%M}.\n\n*1* - Quero esse horário\n"
              "*2* - Não quero, sair da lista")
    conv = conversation_for(db, shop, e.customer.phone)
    Ctx(db, shop, conv, e.customer.phone, "").go(OFFER_STATE, wl_entry_id=e.id)
    return hold


def _open_offer(db: Session, shop: Shop, entry_id: int, phone: str) -> WaitlistEntry | None:
    e = db.get(WaitlistEntry, entry_id or 0)
    if e and e.shop_id == shop.id and e.customer.phone == phone and e.status == WaitStatus.OFFERED \
            and e.offer_expires_at and e.offer_expires_at > now_local():
        return e
    return None


def accept(db: Session, shop: Shop, entry_id: int, phone: str) -> Appointment | None:
    """O cliente aceitou: a reserva vira agendamento (ou "aguardando sinal", se o estabelecimento cobra sinal)."""
    e = _open_offer(db, shop, entry_id, phone)
    if e is None:
        return None
    hold = db.get(Appointment, e.offer_appointment_id)
    if hold is None or hold.status != ApptStatus.HELD:
        return None
    hold.status = ApptStatus.SCHEDULED
    e.status = WaitStatus.BOOKED
    return hold


def decline(db: Session, shop: Shop, entry_id: int, phone: str) -> bool:
    e = _open_offer(db, shop, entry_id, phone)
    if e is None:
        return False
    _drop_offer(db, shop, e, WaitStatus.CANCELLED)
    return True


def _drop_offer(db: Session, shop: Shop, e: WaitlistEntry, status: str) -> None:
    from . import scheduling as sch
    e.status = status
    hold = db.get(Appointment, e.offer_appointment_id) if e.offer_appointment_id else None
    if hold and hold.status == ApptStatus.HELD:
        sch.cancel_appointment(db, hold)  # libera e avisa a próxima pessoa da fila


def expire_offers(db: Session, shop: Shop) -> int:
    now = now_local()
    n = 0
    for e in db.scalars(select(WaitlistEntry).where(WaitlistEntry.shop_id == shop.id,
                                                    WaitlistEntry.status == WaitStatus.OFFERED,
                                                    WaitlistEntry.offer_expires_at <= now)
                        .order_by(WaitlistEntry.offer_expires_at)):
        _drop_offer(db, shop, e, WaitStatus.EXPIRED)
        n += 1
    # Entradas de dias que já passaram saem da fila
    for e in db.scalars(select(WaitlistEntry).where(WaitlistEntry.shop_id == shop.id,
                                                    WaitlistEntry.status == WaitStatus.WAITING,
                                                    WaitlistEntry.day < now.date())):
        e.status = WaitStatus.EXPIRED
    return n


def cancel(db: Session, shop: Shop, e: WaitlistEntry) -> None:
    if e.status == WaitStatus.OFFERED:
        _drop_offer(db, shop, e, WaitStatus.CANCELLED)
    elif e.status == WaitStatus.WAITING:
        e.status = WaitStatus.CANCELLED
