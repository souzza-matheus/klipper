"""Popula a "Barbearia Demo" com dados de teste realistas.

Uso:
    python -m app.seed_mock           # gera os dados (só se ainda não houver dados mock)
    python -m app.seed_mock --reset   # apaga os dados mock da demo e gera de novo

Não mexe em serviços, barbeiros, expediente nem no usuário admin.
"""
import argparse
import random
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import now_local
from .db import SessionLocal
from .models import (
    Appointment, ApptStatus, Barber, Block, CommissionSettlement, Conversation, Customer, CustomerConflict, Expense,
    PayMethod, PayStatus, Payment, Review, Service, Shop,
)
from .seed import DEMO_PHONES, seed, seed_customers, seed_finance
from .services.payments import get_or_create_pix
from .services.scheduling import create_appointment, find_conflict, is_free

DAYS_BACK = 30
DAYS_AHEAD = 7
N_CUSTOMERS = 40
N_RECURRING = 10

FIRST_NAMES = [
    "Lucas", "Gabriel", "Rafael", "Matheus", "Gustavo", "Felipe", "Bruno", "Thiago", "Leonardo", "Rodrigo",
    "Diego", "Vinícius", "André", "Carlos", "Eduardo", "Marcelo", "Fernando", "Ricardo", "Daniel", "Igor",
    "Caio", "Henrique", "Otávio", "Samuel", "Davi", "Arthur", "Heitor", "Enzo", "Murilo", "Renan",
    "Wesley", "Júlio", "Sérgio", "Paulo", "Antônio", "José", "Wellington", "Cláudio", "Fábio", "Luan",
]
LAST_NAMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira", "Lima", "Gomes",
    "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes", "Soares", "Fernandes", "Vieira", "Barbosa",
    "Rocha", "Dias", "Nascimento", "Andrade", "Moreira", "Nunes", "Marques", "Machado", "Mendes", "Freitas",
]
CUSTOMER_NOTES = [
    "Prefere máquina 2 nas laterais e tesoura em cima.",
    "Gosta de degradê bem baixo. Não usar navalha no pescoço (pele sensível).",
    "Alérgico a pós-barba com álcool.",
    "Sempre chega uns 10 minutos atrasado.",
    "Prefere ser atendido pelo João.",
    "Cliente antigo, gosta de conversar sobre futebol (Atlético).",
    "Barba desenhada, manter o bigode mais cheio.",
    "Traz o filho junto às vezes; perguntar se quer agendar o corte dele.",
]
APPT_NOTES = [
    "Quer testar um corte novo, vai trazer foto.",
    "Só acertar o pezinho.",
    "Disfarçado na régua.",
    "Barba com toalha quente.",
]
COMMENTS_GOOD = [
    "Excelente atendimento, como sempre!",
    "Corte ficou top, recomendo.",
    "Muito caprichoso, voltarei com certeza.",
    "Ambiente agradável e pontual.",
    "Melhor barbearia da cidade.",
    "Barba ficou perfeita.",
    "Atendimento rápido e bem feito.",
]
COMMENTS_OK = [
    "Bom, mas demorou um pouco para começar.",
    "Corte ficou bom, só achei o preço um pouco alto.",
    "Gostei, mas a lateral ficou mais curta do que pedi.",
]
COMMENTS_BAD = [
    "Atrasou mais de 20 minutos.",
    "Corte ficou torto, tive que voltar para arrumar.",
    "Esperei muito e o atendimento foi apressado.",
    "Não gostei do resultado da barba.",
]


def _phone(used: set[str]) -> str:
    while True:
        p = f"55319{random.randint(0, 9999_9999):08d}"
        if p not in used:
            used.add(p)
            return p


def _pick_weighted(options: dict):
    return random.choices(list(options), weights=list(options.values()))[0]


def _rand_between(a: datetime, b: datetime) -> datetime:
    if b <= a:
        return a
    return a + timedelta(seconds=random.randint(0, int((b - a).total_seconds())))


def reset_mock(db: Session, shop: Shop) -> None:
    appt_ids = select(Appointment.id).where(Appointment.shop_id == shop.id)
    db.execute(delete(Review).where(Review.appointment_id.in_(appt_ids)))
    db.execute(delete(Payment).where(Payment.appointment_id.in_(appt_ids)))
    db.execute(delete(Appointment).where(Appointment.shop_id == shop.id))
    db.execute(delete(Block).where(Block.shop_id == shop.id))
    db.execute(delete(Conversation).where(Conversation.shop_id == shop.id))
    db.execute(delete(CustomerConflict).where(CustomerConflict.shop_id == shop.id))
    db.execute(delete(Customer).where(Customer.shop_id == shop.id))
    db.execute(delete(Expense).where(Expense.shop_id == shop.id))
    db.execute(delete(CommissionSettlement).where(CommissionSettlement.shop_id == shop.id))
    db.commit()
    print("Dados mock da Barbearia Demo apagados.")


def _future_weekdays(today: date) -> list[date]:
    return [today + timedelta(days=i) for i in range(1, DAYS_AHEAD + 1) if (today + timedelta(days=i)).weekday() < 5]


def create_blocks(db: Session, shop: Shop, barbers: list[Barber], today: date) -> list[Block]:
    days = _future_weekdays(today)
    # Garante dias distintos mesmo se a janela tiver poucos dias úteis
    lunch_day, off_day, holiday = days[0], days[min(1, len(days) - 1)], days[min(3, len(days) - 1)]
    blocks = [
        Block(shop_id=shop.id, barber_id=barbers[0].id, reason="Almoço",
              start=datetime.combine(lunch_day, time(13)), end=datetime.combine(lunch_day, time(14))),
        Block(shop_id=shop.id, barber_id=barbers[1].id, reason="Folga",
              start=datetime.combine(off_day, time(0)), end=datetime.combine(off_day + timedelta(days=1), time(0))),
        Block(shop_id=shop.id, barber_id=None, reason="Feriado",
              start=datetime.combine(holiday, time(0)), end=datetime.combine(holiday + timedelta(days=1), time(0))),
    ]
    db.add_all(blocks)
    db.flush()
    return blocks


def create_access_demo(db: Session, shop: Shop, barbers: list[Barber], services: dict[str, Service],
                       today: date, now: datetime) -> None:
    """Agendamentos dos clientes de exemplo do controle de acesso: o bloqueado com um horário futuro (o app avisa),
    um pedido aguardando aprovação e um horário para um dos clientes em conflito."""
    demo = seed_customers(db, shop)
    days = _future_weekdays(today)
    plans = [("Marcos Teixeira", days[-1], ApptStatus.SCHEDULED),
             ("Paulo Duarte", days[0], ApptStatus.PENDING_APPROVAL),
             ("Alexandre Pinto", days[min(2, len(days) - 1)], ApptStatus.SCHEDULED)]
    service = services["Corte"]
    for name, day, status in plans:
        customer = demo[name]
        done = False
        for barber in barbers:
            for start in _candidate_starts(barber, day, service.duration_minutes, shop.slot_step_minutes):
                end = start + timedelta(minutes=service.duration_minutes)
                if start.hour >= 14 and is_free(db, shop, barber, start, end) \
                        and not find_conflict(db, shop, customer, start, end):
                    a = create_appointment(db, shop, customer, barber, service, start, status=status)
                    a.created_at = now - timedelta(hours=1)
                    if status == ApptStatus.PENDING_APPROVAL:
                        a.approval_requested_at = a.created_at
                    done = True
                    break
            if done:
                break
    db.commit()


def _candidate_starts(barber: Barber, day: date, duration: int, step: int) -> list[datetime]:
    starts = []
    for wh in barber.working_hours:
        if wh.weekday != day.weekday():
            continue
        cur = datetime.combine(day, wh.start)
        limit = datetime.combine(day, wh.end)
        while cur + timedelta(minutes=duration) <= limit:
            starts.append(cur)
            cur += timedelta(minutes=step)
    return starts


def _book(db: Session, shop: Shop, customer: Customer, barbers: list[Barber], services: dict[str, Service],
          day: date) -> Appointment | None:
    """Tenta marcar o cliente em um horário livre do dia, com qualquer barbeiro."""
    service = services[_pick_weighted({"Corte": 50, "Barba": 15, "Corte + Barba": 35})]
    for barber in random.sample(barbers, len(barbers)):
        starts = _candidate_starts(barber, day, service.duration_minutes, shop.slot_step_minutes)
        random.shuffle(starts)
        for start in starts:
            end = start + timedelta(minutes=service.duration_minutes)
            if is_free(db, shop, barber, start, end):
                notes = random.choice(APPT_NOTES) if random.random() < 0.08 else ""
                via = "bot" if random.random() < 0.7 else "app"
                return create_appointment(db, shop, customer, barber, service, start, created_via=via, notes=notes)
    return None


def create_appointments(db: Session, shop: Shop, customers: list[Customer], barbers: list[Barber],
                        services: dict[str, Service], today: date) -> list[Appointment]:
    first_day = today - timedelta(days=DAYS_BACK)
    last_day = today + timedelta(days=DAYS_AHEAD)
    booked: dict[date, set[int]] = {}
    appts: list[Appointment] = []

    def book(customer: Customer, day: date) -> None:
        if customer.id in booked.setdefault(day, set()):
            return
        appt = _book(db, shop, customer, barbers, services, day)
        if appt:
            booked[day].add(customer.id)
            appts.append(appt)

    # Clientes recorrentes: voltam a cada 15 a 25 dias
    recurring, others = customers[:N_RECURRING], customers[N_RECURRING:]
    for c in recurring:
        day = first_day + timedelta(days=random.randint(0, 12))
        while day <= last_day:
            if day.weekday() == 6:
                day += timedelta(days=1)
            book(c, day)
            day += timedelta(days=random.randint(15, 25))

    # Demais clientes: alguns aparecem bastante, outros só uma ou duas vezes
    weights = [random.choice((1, 1, 2, 3, 5)) for _ in others]
    day = first_day
    while day <= last_day:
        wd = day.weekday()
        target = 0 if wd == 6 else random.randint(3, 6) if wd == 5 else random.randint(6, 12)
        tries = 0
        while len(booked.get(day, ())) < target and tries < 40:
            book(random.choices(others, weights=weights)[0], day)
            tries += 1
        day += timedelta(days=1)
    return appts


def apply_statuses(appts: list[Appointment], shop: Shop, now: datetime) -> None:
    reminder_delta = timedelta(minutes=shop.reminder_minutes_before)
    survey_delta = timedelta(minutes=shop.survey_delay_minutes)
    for a in appts:
        # Agendado entre algumas horas e alguns dias antes, sempre no passado
        a.created_at = min(a.start - timedelta(minutes=random.randint(60, 6 * 24 * 60)),
                           now - timedelta(minutes=random.randint(5, 600)))
        reminder_time = a.start - reminder_delta
        if a.end <= now:  # passado
            a.status = _pick_weighted({ApptStatus.COMPLETED: 80, ApptStatus.CANCELLED: 10, ApptStatus.NO_SHOW: 10})
        elif a.start <= now:  # em andamento
            a.status = ApptStatus.CONFIRMED
        else:  # futuro
            a.status = ApptStatus.SCHEDULED
            if reminder_time <= now:
                a.status = _pick_weighted({ApptStatus.CONFIRMED: 75, ApptStatus.SCHEDULED: 25})
            elif random.random() < 0.25:
                a.status = ApptStatus.CONFIRMED  # confirmado pelo dono no app

        if a.status == ApptStatus.CANCELLED:
            a.cancelled_at = _rand_between(a.created_at, a.start - timedelta(minutes=30))
            a.reminder_sent = a.cancelled_at > reminder_time
        else:
            a.reminder_sent = reminder_time <= now
        a.survey_sent = bool(shop.survey_enabled and a.status == ApptStatus.COMPLETED and a.end + survey_delta <= now)


def create_payments(db: Session, shop: Shop, appts: list[Appointment], now: datetime) -> None:
    for a in appts:
        if random.random() >= 0.30:
            continue
        pay = get_or_create_pix(db, shop, a)
        future = a.status in ApptStatus.ACTIVE
        if future:
            pay.created_at = _rand_between(a.created_at, now)
            kind = _pick_weighted({"pending": 45, "reported": 30, "expired": 25})
            if kind == "pending":
                # Ainda dentro do prazo: não expira na próxima rodada do job
                pay.created_at = max(pay.created_at, now - timedelta(hours=shop.pix_expire_hours - 1))
            elif kind == "reported":
                pay.customer_reported_at = _rand_between(pay.created_at, now)
            else:
                pay.status = PayStatus.EXPIRED
        else:
            pay.created_at = a.created_at + timedelta(minutes=random.randint(1, 10))
            if a.status == ApptStatus.COMPLETED:
                pay.status = PayStatus.PAID
                pay.customer_reported_at = pay.created_at + timedelta(minutes=random.randint(2, 60))
                pay.confirmed_at = min(pay.customer_reported_at + timedelta(minutes=random.randint(5, 240)), now)
            else:
                pay.status = PayStatus.EXPIRED
        a.payment_status = pay.status
    db.flush()


def set_payment_methods(appts: list[Appointment]) -> None:
    """Forma de pagamento dos atendimentos concluídos: Pix pago pelo bot vira "pix"; o resto é sorteado."""
    for a in appts:
        if a.status != ApptStatus.COMPLETED:
            continue
        if a.payment_status == PayStatus.PAID:
            a.payment_method = PayMethod.PIX
        else:
            a.payment_method = _pick_weighted({PayMethod.PIX: 30, PayMethod.CASH: 25, PayMethod.DEBIT: 30,
                                               PayMethod.CREDIT: 15})


def create_reviews(db: Session, shop: Shop, appts: list[Appointment], now: datetime) -> None:
    for a in appts:
        if not a.survey_sent or random.random() >= 0.6:
            continue
        rating = _pick_weighted({5: 50, 4: 30, 3: 12, 2: 5, 1: 3})
        comment = ""
        if random.random() < 0.5:
            pool = COMMENTS_GOOD if rating >= 4 else COMMENTS_OK if rating == 3 else COMMENTS_BAD
            comment = random.choice(pool)
        sent = a.end + timedelta(minutes=shop.survey_delay_minutes)
        created = min(sent + timedelta(minutes=random.randint(2, 180)), now)
        db.add(Review(shop_id=shop.id, appointment_id=a.id, rating=rating, comment=comment, created_at=created))
    db.flush()


def create_customers(db: Session, shop: Shop, now: datetime) -> list[Customer]:
    reserved = {shop.owner_phone, shop.phone} | {b.phone for b in shop.barbers} | DEMO_PHONES
    used = set(reserved)
    names = set()
    customers = []
    while len(customers) < N_CUSTOMERS:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name in names:
            continue
        names.add(name)
        customers.append(Customer(
            shop_id=shop.id, phone=_phone(used), name=name,
            created_at=now - timedelta(days=random.randint(DAYS_BACK + 5, 365)),
        ))
    for c, note in zip(random.sample(customers, len(CUSTOMER_NOTES)), CUSTOMER_NOTES):
        c.notes = note
    db.add_all(customers)
    db.flush()
    return customers


def summary(db: Session, shop: Shop) -> None:
    def count_by(col, model):
        return dict(db.execute(select(col, func.count()).where(model.shop_id == shop.id).group_by(col)).all())

    n_customers = db.scalar(select(func.count()).select_from(Customer).where(Customer.shop_id == shop.id))
    appts = count_by(Appointment.status, Appointment)
    pays = count_by(Payment.status, Payment)
    n_reviews, avg = db.execute(
        select(func.count(Review.id), func.avg(Review.rating)).where(Review.shop_id == shop.id)
    ).one()
    n_blocks = db.scalar(select(func.count()).select_from(Block).where(Block.shop_id == shop.id))
    n_expenses = db.scalar(select(func.count()).select_from(Expense).where(Expense.shop_id == shop.id))
    access = count_by(Customer.access_status, Customer)
    n_conflicts = db.scalar(select(func.count()).select_from(CustomerConflict).where(CustomerConflict.shop_id == shop.id))

    print("\nResumo da Barbearia Demo")
    print(f"  Clientes: {n_customers} (bloqueados: {access.get('blocked', 0)}, "
          f"precisam de aprovação: {access.get('approval', 0)}, pares em conflito: {n_conflicts})")
    print(f"  Agendamentos: {sum(appts.values())}")
    for status, n in sorted(appts.items()):
        print(f"    {status}: {n}")
    print(f"  Pagamentos Pix: {sum(pays.values())}")
    for status, n in sorted(pays.items()):
        print(f"    {status}: {n}")
    print(f"  Avaliações: {n_reviews} (nota média {float(avg or 0):.2f})")
    print(f"  Bloqueios: {n_blocks}")
    print(f"  Gastos: {n_expenses}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera dados de teste para a Barbearia Demo.")
    parser.add_argument("--reset", action="store_true", help="apaga os dados mock existentes antes de gerar")
    args = parser.parse_args()

    random.seed(42)
    shop_id = seed().id
    db = SessionLocal()
    try:
        shop = db.get(Shop, shop_id)
        if args.reset:
            reset_mock(db, shop)
        elif db.scalar(select(func.count()).select_from(Appointment).where(Appointment.shop_id == shop.id)):
            print("A Barbearia Demo já tem dados. Use --reset para apagar e gerar de novo.")
            summary(db, shop)
            return

        now = now_local()
        today = now.date()
        barbers = sorted((b for b in shop.barbers if b.active), key=lambda b: b.id)
        services = {s.name: s for s in shop.services}

        customers = create_customers(db, shop, now)
        create_blocks(db, shop, barbers, today)
        appts = create_appointments(db, shop, customers, barbers, services, today)
        apply_statuses(appts, shop, now)
        create_payments(db, shop, appts, now)
        set_payment_methods(appts)
        create_reviews(db, shop, appts, now)

        # Parte dos clientes é nova: cadastro feito no primeiro agendamento do período
        first_appt: dict[int, Appointment] = {}
        for a in sorted(appts, key=lambda a: a.created_at):
            first_appt.setdefault(a.customer_id, a)
        for c in customers:
            if c.id in first_appt and random.random() < 0.4:
                c.created_at = first_appt[c.id].created_at - timedelta(minutes=random.randint(1, 30))

        db.commit()
        create_access_demo(db, shop, barbers, services, today, now)
        seed_finance(db, shop, today)  # gastos de exemplo do mês (o --reset apaga os antigos)
        summary(db, shop)
    finally:
        db.close()


if __name__ == "__main__":
    main()
