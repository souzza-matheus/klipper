"""Regras de agenda: horários livres, criação, cancelamento, remarcação, conflitos entre clientes e visão do mês."""
import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, Barber, Block, ConflictAction, Customer, CustomerConflict, PayMethod, PayStatus,
    Service, Shop,
)


class SchedulingError(Exception):
    pass


@dataclass
class ConflictHit:
    """Agendamento de outro cliente que impede o horário. Só para o dono: nunca mostrar ao cliente."""
    conflict: CustomerConflict
    other: Appointment
    gap_minutes: int
    same_day_block: bool


class ConflictError(SchedulingError):
    """Horário livre na agenda, mas perto demais de um cliente em conflito."""
    def __init__(self, hit: ConflictHit):
        super().__init__("Esse horário não está mais disponível.")
        self.hit = hit


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
        Appointment.status.in_(ApptStatus.OCCUPYING),
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


# ---------------------------------------------------------------- conflitos entre clientes

def conflicts_of(db: Session, shop: Shop, customer_id: int) -> list[CustomerConflict]:
    return list(db.scalars(select(CustomerConflict).where(
        CustomerConflict.shop_id == shop.id,
        or_(CustomerConflict.customer_a_id == customer_id, CustomerConflict.customer_b_id == customer_id),
    )).all())


def conflict_gap(shop: Shop, conflict: CustomerConflict) -> int:
    return conflict.min_gap_minutes if conflict.min_gap_minutes is not None else shop.conflict_default_gap_minutes


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time())
    return start, start + timedelta(days=1)


def conflict_windows(db: Session, shop: Shop, customer: Customer | None, day: date,
                     ignore_appt_id: int | None = None) -> list[tuple[datetime, datetime, ConflictHit]]:
    """Intervalos do dia em que o cliente não pode começar/estar na barbearia por causa de clientes em conflito.
    Vale para qualquer barbeiro. Um atendimento [s, e) é proibido se cruzar algum intervalo."""
    if customer is None or customer.id is None:
        return []
    conflicts = conflicts_of(db, shop, customer.id)
    if not conflicts:
        return []
    day_start, day_end = _day_bounds(day)
    by_other = {c.other_id(customer.id): c for c in conflicts}
    # O intervalo pode passar da meia-noite: olha também o dia anterior e o seguinte
    others = db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.customer_id.in_(by_other),
        Appointment.status.in_(ApptStatus.OCCUPYING),
        Appointment.start < day_end + timedelta(days=1), Appointment.end > day_start - timedelta(days=1),
    ).order_by(Appointment.start)).all()
    windows = []
    for a in others:
        if a.id == ignore_appt_id:
            continue
        c = by_other[a.customer_id]
        gap = conflict_gap(shop, c)
        hit = ConflictHit(conflict=c, other=a, gap_minutes=gap, same_day_block=c.same_day_block)
        if c.same_day_block and a.start < day_end and a.end > day_start:
            windows.append((day_start, day_end, hit))
        g = timedelta(minutes=gap)
        if a.start - g < day_end and a.end + g > day_start:
            windows.append((a.start - g, a.end + g, hit))
    return windows


def find_conflict(db: Session, shop: Shop, customer: Customer | None, start: datetime, end: datetime,
                  ignore_appt_id: int | None = None) -> ConflictHit | None:
    """Agendamento de cliente em conflito que impede [start, end), considerando todos os barbeiros.
    Um conflito "block" tem preferência: só devolve um "approval" quando não há nenhum que bloqueie."""
    hits = [hit for ws, we, hit in conflict_windows(db, shop, customer, start.date(), ignore_appt_id)
            if start < we and end > ws]
    if end.date() != start.date():  # atendimento que passa da meia-noite
        hits += [hit for ws, we, hit in conflict_windows(db, shop, customer, end.date(), ignore_appt_id)
                 if start < we and end > ws]
    blocking = [h for h in hits if h.conflict.conflict_action != ConflictAction.APPROVAL]
    return (blocking or hits or [None])[0]


def conflicts_on_day(db: Session, shop: Shop, customer: Customer, day: date) -> list[ConflictHit]:
    """Clientes em conflito com agendamento ativo no dia (para o aviso do dono no app)."""
    day_start, day_end = _day_bounds(day)
    seen, out = set(), []
    for _, _, hit in conflict_windows(db, shop, customer, day):
        a = hit.other
        if a.id not in seen and a.start < day_end and a.end > day_start:
            seen.add(a.id)
            out.append(hit)
    return out


# ---------------------------------------------------------------- horários livres

def free_slots(db: Session, shop: Shop, service: Service, barber: Barber, day: date,
               ignore_appt_id: int | None = None, customer: Customer | None = None,
               only_blocking: bool = False) -> list[datetime]:
    """Com customer, esconde também os horários perto demais de clientes em conflito com ele.
    only_blocking=True (bot) esconde só os conflitos "block": nos "approval" o horário aparece e vira pedido."""
    earliest = now_local() + timedelta(minutes=shop.min_advance_minutes)
    duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=shop.slot_step_minutes)
    busy = _busy_intervals(db, shop, barber, day, ignore_appt_id)
    busy += [(ws, we) for ws, we, hit in conflict_windows(db, shop, customer, day)
             if not (only_blocking and hit.conflict.conflict_action == ConflictAction.APPROVAL)]
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


def free_slots_any(db: Session, shop: Shop, service: Service, day: date,
                   customer: Customer | None = None, only_blocking: bool = False) -> list[tuple[datetime, Barber]]:
    """Horários livres com qualquer barbeiro: para cada horário, o primeiro barbeiro disponível."""
    result: dict[datetime, Barber] = {}
    for barber in active_barbers(db, shop, service):
        for slot in free_slots(db, shop, service, barber, day, customer=customer, only_blocking=only_blocking):
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
                       ignore_appt_id: int | None = None, status: str = ApptStatus.SCHEDULED,
                       force: bool = False) -> Appointment:
    """force=True ignora só o conflito entre clientes (o dono decidiu agendar mesmo assim), nunca a agenda ocupada."""
    end = start + timedelta(minutes=service.duration_minutes)
    if not is_free(db, shop, barber, start, end, ignore_appt_id):
        raise SchedulingError("Esse horário não está mais disponível.")
    if not force:
        hit = find_conflict(db, shop, customer, start, end, ignore_appt_id)
        if hit:
            raise ConflictError(hit)
    appt = Appointment(
        shop_id=shop.id, customer_id=customer.id, barber_id=barber.id, service_id=service.id,
        start=start, end=end, price=service.price, created_via=created_via, notes=notes,
        status=status, payment_status=PayStatus.NONE,
        approval_requested_at=now_local() if status == ApptStatus.PENDING_APPROVAL else None,
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


def cancel_appointment(db: Session, appt: Appointment, offer_waitlist: bool = True) -> None:
    """Cancela, devolve a sessão do pacote ou o uso da assinatura, aplica a regra do sinal e oferece o horário à
    lista de espera."""
    from . import benefits, deposits, waitlist
    was_occupying = appt.status in ApptStatus.OCCUPYING
    shop = appt.barber.shop
    appt.status = ApptStatus.CANCELLED
    appt.cancelled_at = now_local()
    if appt.payment and appt.payment.status == PayStatus.PENDING:
        appt.payment.status = PayStatus.EXPIRED
        if appt.payment.kind != "deposit":
            appt.payment_status = PayStatus.EXPIRED
    deposits.on_cancel(shop, appt)
    benefits.release_on_cancel(db, shop, appt)
    if was_occupying and offer_waitlist:
        waitlist.on_slot_freed(db, shop, appt.barber_id, appt.start, appt.end)


def reschedule_appointment(db: Session, shop: Shop, appt: Appointment, new_start: datetime,
                           new_barber: Barber | None = None, status: str = ApptStatus.SCHEDULED,
                           force: bool = False) -> Appointment:
    barber = new_barber or appt.barber
    old = (appt.barber_id, appt.start, appt.end)
    end = new_start + timedelta(minutes=appt.service.duration_minutes)
    if not is_free(db, shop, barber, new_start, end, ignore_appt_id=appt.id):
        raise SchedulingError("Esse horário não está mais disponível.")
    if not force:
        hit = find_conflict(db, shop, appt.customer, new_start, end, ignore_appt_id=appt.id)
        if hit:
            raise ConflictError(hit)
    appt.barber_id = barber.id
    appt.barber = barber
    appt.start = new_start
    appt.end = end
    appt.reminder_sent = False
    if not (appt.status == ApptStatus.AWAITING_DEPOSIT and status == ApptStatus.SCHEDULED):
        appt.status = status  # quem ainda deve o sinal continua devendo depois de remarcar
    appt.approval_requested_at = now_local() if status == ApptStatus.PENDING_APPROVAL else None
    db.flush()
    if old != (appt.barber_id, appt.start, appt.end):
        from . import waitlist
        waitlist.on_slot_freed(db, shop, *old)  # o horário antigo abriu
    return appt


def upcoming_for_customer(db: Session, shop: Shop, customer: Customer) -> list[Appointment]:
    """Próximos agendamentos do cliente, incluindo pedidos aguardando aprovação."""
    return list(db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.customer_id == customer.id,
        Appointment.status.in_(ApptStatus.OCCUPYING), Appointment.start >= now_local() - timedelta(minutes=30),
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


# ---------------------------------------------------------------- agenda do dia

@dataclass
class BarberDay:
    barber: Barber
    working: list[tuple[datetime, datetime]]
    blocks: list[Block]
    appointments: list[Appointment]
    free: list[tuple[datetime, datetime]]


@dataclass
class DayAgenda:
    now: datetime
    barbers: list[BarberDay]


def _subtract(intervals: list[tuple[datetime, datetime]], busy: list[tuple[datetime, datetime]]):
    """Partes dos intervalos que não cruzam nenhum ocupado."""
    out = []
    for s, e in intervals:
        cur = s
        for bs, be in sorted(busy):
            if be <= cur or bs >= e:
                continue
            if bs > cur:
                out.append((cur, bs))
            cur = max(cur, be)
            if cur >= e:
                break
        if cur < e:
            out.append((cur, e))
    return out


def day_agenda(db: Session, shop: Shop, day: date) -> DayAgenda:
    """Expediente, bloqueios, agendamentos (sem os cancelados) e intervalos livres de cada profissional no dia.
    Entra quem está ativo ou tem agendamento no dia. Livre só a partir de agora (dias passados não têm livre).
    Usa 3 consultas principais, mais os carregamentos em lote das relações dos agendamentos."""
    day_start, day_end = _day_bounds(day)
    now = now_local()
    barbers = db.scalars(select(Barber).options(selectinload(Barber.working_hours))
                         .where(Barber.shop_id == shop.id).order_by(Barber.name)).all()
    blocks = db.scalars(select(Block).where(Block.shop_id == shop.id, Block.start < day_end, Block.end > day_start)
                        .order_by(Block.start)).all()
    appts = db.scalars(select(Appointment).options(
        selectinload(Appointment.customer), selectinload(Appointment.service),
        selectinload(Appointment.review), selectinload(Appointment.payment),
    ).where(
        Appointment.shop_id == shop.id, Appointment.start >= day_start, Appointment.start < day_end,
        Appointment.status != ApptStatus.CANCELLED,
    ).order_by(Appointment.start)).all()

    out = []
    for b in barbers:
        mine = [a for a in appts if a.barber_id == b.id]
        if not b.active and not mine:
            continue
        working = sorted((datetime.combine(day, wh.start), datetime.combine(day, wh.end))
                         for wh in b.working_hours if wh.weekday == day.weekday())
        own_blocks = [k for k in blocks if k.barber_id in (None, b.id)]
        busy = [(k.start, k.end) for k in own_blocks]
        busy += [(a.start, a.end) for a in mine if a.status in ApptStatus.OCCUPYING]
        free = _subtract(working, busy) if day >= now.date() else []
        if day == now.date():
            free = [(max(s, now), e) for s, e in free if e > now]
        out.append(BarberDay(barber=b, working=working, blocks=own_blocks, appointments=mine,
                             free=[(s, e) for s, e in free if (e - s) >= timedelta(minutes=5)]))
    return DayAgenda(now=now, barbers=out)
