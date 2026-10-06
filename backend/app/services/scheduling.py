"""Regras de agenda: horários livres, criação, cancelamento, remarcação e visão do mês."""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, Barber, Block, Customer, PayMethod, PayStatus, Service, Shop,
)


class SchedulingError(Exception):
    pass


def active_barbers(db: Session, shop: Shop, service: Service | None = None) -> list[Barber]:
    barbers = db.scalars(
        select(Barber).where(Barber.shop_id == shop.id, Barber.active.is_(True)).order_by(Barber.name)
    ).all()
    if service is None:
        return list(barbers)
    # Barbeiro sem serviços cadastrados = faz todos
    return [b for b in barbers if not b.services or any(s.id == service.id for s in b.services)]


def active_services(db: Session, shop: Shop) -> list[Service]:
    return list(db.scalars(
        select(Service).where(Service.shop_id == shop.id, Service.active.is_(True))
        .order_by(Service.sort_order, Service.name)
    ).all())


def _busy_intervals(db: Session, shop: Shop, barber: Barber, day: date, ignore_appt_id: int | None = None):
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    appts = db.scalars(select(Appointment).where(
        Appointment.barber_id == barber.id,
        Appointment.status.in_(ApptStatus.ACTIVE),
        Appointment.start < day_end, Appointment.end > day_start,
    )).all()
    blocks = db.scalars(select(Block).where(
        Block.shop_id == shop.id,
        or_(Block.barber_id == barber.id, Block.barber_id.is_(None)),
        Block.start < day_end, Block.end > day_start,
    )).all()
    busy = [(a.start, a.end) for a in appts if a.id != ignore_appt_id]
    busy += [(b.start, b.end) for b in blocks]
    return busy


def is_free(db: Session, shop: Shop, barber: Barber, start: datetime, end: datetime,
            ignore_appt_id: int | None = None) -> bool:
    inside = False
    for wh in barber.working_hours:
        if wh.weekday == start.weekday():
            ws = datetime.combine(start.date(), wh.start)
            we = datetime.combine(start.date(), wh.end)
            if ws <= start and end <= we:
                inside = True
                break
    if not inside:
        return False
    for bs, be in _busy_intervals(db, shop, barber, start.date(), ignore_appt_id):
        if start < be and end > bs:
            return False
    return True


def free_slots(db: Session, shop: Shop, service: Service, barber: Barber, day: date,
               ignore_appt_id: int | None = None) -> list[datetime]:
    earliest = now_local() + timedelta(minutes=shop.min_advance_minutes)
    duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=shop.slot_step_minutes)
    busy = _busy_intervals(db, shop, barber, day, ignore_appt_id)
    slots: list[datetime] = []
    for wh in barber.working_hours:
        if wh.weekday != day.weekday():
            continue
        cur = datetime.combine(day, wh.start)
        limit = datetime.combine(day, wh.end)
        while cur + duration <= limit:
            end = cur + duration
            if cur >= earliest and not any(cur < be and end > bs for bs, be in busy):
                slots.append(cur)
            cur += step
    return sorted(set(slots))


def free_slots_any(db: Session, shop: Shop, service: Service, day: date) -> list[tuple[datetime, Barber]]:
    """Horários livres com qualquer barbeiro: para cada horário, o primeiro barbeiro disponível."""
    result: dict[datetime, Barber] = {}
    for barber in active_barbers(db, shop, service):
        for slot in free_slots(db, shop, service, barber, day):
            result.setdefault(slot, barber)
    return sorted(result.items(), key=lambda x: x[0])


def open_days(db: Session, shop: Shop, service: Service, barber: Barber | None) -> list[date]:
    barbers = [barber] if barber else active_barbers(db, shop, service)
    weekdays = {wh.weekday for b in barbers for wh in b.working_hours}
    today = now_local().date()
    days = []
    for i in range(shop.booking_days_ahead + 1):
        d = today + timedelta(days=i)
        if d.weekday() in weekdays:
            days.append(d)
    return days


def get_or_create_customer(db: Session, shop: Shop, phone: str, name: str = "") -> Customer:
    c = db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone))
    if c is None:
        c = Customer(shop_id=shop.id, phone=phone, name=name)
        db.add(c)
        db.flush()
    elif name and not c.name:
        c.name = name
    return c


def create_appointment(db: Session, shop: Shop, customer: Customer, barber: Barber, service: Service,
                       start: datetime, created_via: str = "bot", notes: str = "",
                       ignore_appt_id: int | None = None) -> Appointment:
    end = start + timedelta(minutes=service.duration_minutes)
    if not is_free(db, shop, barber, start, end, ignore_appt_id):
        raise SchedulingError("Esse horário não está mais disponível.")
    appt = Appointment(
        shop_id=shop.id, customer_id=customer.id, barber_id=barber.id, service_id=service.id,
        start=start, end=end, price=service.price, created_via=created_via, notes=notes,
        status=ApptStatus.SCHEDULED, payment_status=PayStatus.NONE,
    )
    db.add(appt)
    db.flush()
    return appt


def complete_appointment(appt: Appointment, payment_method: str | None = None) -> None:
    """Marca como atendido. Sem forma de pagamento informada, um Pix já pago pelo bot vira "pix"."""
    appt.status = ApptStatus.COMPLETED
    if payment_method:
        appt.payment_method = payment_method
    elif appt.payment_method is None and appt.payment_status == PayStatus.PAID:
        appt.payment_method = PayMethod.PIX


def can_customer_cancel(shop: Shop, appt: Appointment) -> bool:
    return appt.start - now_local() >= timedelta(hours=shop.cancel_min_hours)


def cancel_appointment(db: Session, appt: Appointment) -> None:
    appt.status = ApptStatus.CANCELLED
    appt.cancelled_at = now_local()
    if appt.payment and appt.payment.status == PayStatus.PENDING:
        appt.payment.status = PayStatus.EXPIRED
        appt.payment_status = PayStatus.EXPIRED


def reschedule_appointment(db: Session, shop: Shop, appt: Appointment, new_start: datetime,
                           new_barber: Barber | None = None) -> Appointment:
    barber = new_barber or appt.barber
    end = new_start + timedelta(minutes=appt.service.duration_minutes)
    if not is_free(db, shop, barber, new_start, end, ignore_appt_id=appt.id):
        raise SchedulingError("Esse horário não está mais disponível.")
    appt.barber_id = barber.id
    appt.barber = barber
    appt.start = new_start
    appt.end = end
    appt.reminder_sent = False
    appt.status = ApptStatus.SCHEDULED
    db.flush()
    return appt


def upcoming_for_customer(db: Session, shop: Shop, customer: Customer) -> list[Appointment]:
    return list(db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.customer_id == customer.id,
        Appointment.status.in_(ApptStatus.ACTIVE), Appointment.start >= now_local() - timedelta(minutes=30),
    ).order_by(Appointment.start)).all())


def appointments_on(db: Session, shop: Shop, day: date, barber_id: int | None = None) -> list[Appointment]:
    start = datetime.combine(day, datetime.min.time())
    q = select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.start >= start, Appointment.start < start + timedelta(days=1),
        Appointment.status != ApptStatus.CANCELLED,
    )
    if barber_id:
        q = q.where(Appointment.barber_id == barber_id)
    return list(db.scalars(q.order_by(Appointment.start)).all())


def _merged_minutes(intervals: list[tuple[datetime, datetime]]) -> float:
    total, cur_s, cur_e = 0.0, None, None
    for a, b in sorted(intervals):
        if cur_e is None or a > cur_e:
            if cur_e is not None:
                total += (cur_e - cur_s).total_seconds() / 60
            cur_s, cur_e = a, b
        else:
            cur_e = max(cur_e, b)
    if cur_e is not None:
        total += (cur_e - cur_s).total_seconds() / 60
    return total


def month_overview(db: Session, shop: Shop, year: int, month: int, barber_id: int | None = None) -> list[dict]:
    """Resumo de cada dia do mês para o calendário: atendimentos, cancelados, faturamento previsto, ocupação e bloqueios.
    Ocupação = atendimentos / capacidade do dia, onde capacidade = minutos de expediente livres de bloqueio
    divididos pela duração média dos serviços ativos. Usa 4 consultas, não uma por dia."""
    n_days = calendar.monthrange(year, month)[1]
    first = date(year, month, 1)
    start = datetime.combine(first, datetime.min.time())
    end = start + timedelta(days=n_days)

    bq = select(Barber).options(selectinload(Barber.working_hours)).where(Barber.shop_id == shop.id)
    bq = bq.where(Barber.id == barber_id) if barber_id else bq.where(Barber.active.is_(True))
    barbers = db.scalars(bq).all()

    aq = select(Appointment.start, Appointment.status, Appointment.price).where(
        Appointment.shop_id == shop.id, Appointment.start >= start, Appointment.start < end)
    kq = select(Block).where(Block.shop_id == shop.id, Block.start < end, Block.end > start)
    if barber_id:
        aq = aq.where(Appointment.barber_id == barber_id)
        kq = kq.where(or_(Block.barber_id == barber_id, Block.barber_id.is_(None)))
    appts = db.execute(aq).all()
    blocks = db.scalars(kq).all()
    avg_duration = db.scalar(select(func.avg(Service.duration_minutes)).where(
        Service.shop_id == shop.id, Service.active.is_(True))) or shop.slot_step_minutes or 30

    days = []
    for i in range(n_days):
        d = first + timedelta(days=i)
        d_start = datetime.combine(d, datetime.min.time())
        d_end = d_start + timedelta(days=1)
        day_blocks = [b for b in blocks if b.start < d_end and b.end > d_start]
        work = free = 0.0
        for b in barbers:
            mine = [(k.start, k.end) for k in day_blocks if k.barber_id in (None, b.id)]
            for wh in b.working_hours:
                if wh.weekday != d.weekday():
                    continue
                ws, we = datetime.combine(d, wh.start), datetime.combine(d, wh.end)
                minutes = (we - ws).total_seconds() / 60
                work += minutes
                free += minutes - _merged_minutes([(max(a, ws), min(z, we)) for a, z in mine if a < we and z > ws])
        days.append({"date": d, "total": 0, "cancelled": 0, "revenue_expected": Decimal(0),
                     "capacity": round(free / float(avg_duration), 1), "working": work > 0,
                     "has_block": bool(day_blocks), "occupancy": 0.0})

    for a in appts:
        row = days[a.start.day - 1]
        if a.status == ApptStatus.CANCELLED:
            row["cancelled"] += 1
            continue
        row["total"] += 1
        if a.status != ApptStatus.NO_SHOW:
            row["revenue_expected"] += a.price
    for row in days:
        row["revenue_expected"] = row["revenue_expected"].quantize(Decimal("0.01"))
        if row["capacity"] > 0:
            row["occupancy"] = round(min(1.0, row["total"] / row["capacity"]), 2)
        elif row["total"]:
            row["occupancy"] = 1.0
    return days
