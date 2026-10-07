"""Rotinas que rodam a cada minuto: lembretes, pesquisa de satisfação, expiração de Pix, de pedidos para aprovar, de
sinais não pagos e das reservas da lista de espera, cobrança do clube de assinatura e resumo diário."""
import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from .bot.owner import agenda_text, summary_text
from .bot.context import BUSY_STATES, Ctx, conversation_for
from .config import now_local, settings
from .db import SessionLocal
from .models import Appointment, ApptStatus, Shop
from .services.approvals import expire_pending
from .services.fmt import appt_summary
from .services.notify import notify_staff
from .services.expenses import bills_text
from .services.payments import expire_old
from .services.scheduling import complete_appointment
from .services.stock import low_stock_text
from .services.whatsapp import send_text

log = logging.getLogger("jobs")

_conv = conversation_for


def send_reminders(db, shop: Shop) -> int:
    now = now_local()
    appts = db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.status == ApptStatus.SCHEDULED,
        Appointment.reminder_sent.is_(False), Appointment.start > now,
        Appointment.start <= now + timedelta(minutes=shop.reminder_minutes_before),
    )).all()
    for a in appts:
        a.reminder_sent = True
        # Agendamento feito há poucos minutos dentro da janela do lembrete: não precisa lembrar
        if a.created_at and a.start - a.created_at < timedelta(minutes=shop.reminder_minutes_before):
            continue
        send_text(db, shop, a.customer.phone,
                  f"⏰ *Lembrete*, {a.customer.name.split(' ')[0] if a.customer.name else ''}!\n\n{appt_summary(a)}\n\n"
                  "*1* - Confirmo presença\n*2* - Preciso cancelar")
        conv = _conv(db, shop, a.customer.phone)
        if conv.state not in BUSY_STATES:
            Ctx(db, shop, conv, a.customer.phone, "").go("reminder", appt_id=a.id)
    return len(appts)


def send_surveys(db, shop: Shop) -> int:
    now = now_local()
    delay = timedelta(minutes=shop.survey_delay_minutes)
    appts = db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id,
        Appointment.status.in_((ApptStatus.SCHEDULED, ApptStatus.CONFIRMED, ApptStatus.COMPLETED)),
        Appointment.survey_sent.is_(False),
        Appointment.end <= now - delay, Appointment.end >= now - timedelta(days=1),
    )).all()
    count = 0
    for a in appts:
        a.survey_sent = True
        if a.status in ApptStatus.ACTIVE:
            complete_appointment(a)  # passou do horário sem ser marcado como falta: considera atendido
        if not shop.survey_enabled:
            continue
        conv = _conv(db, shop, a.customer.phone)
        if conv.state in BUSY_STATES:
            continue
        send_text(db, shop, a.customer.phone,
                  f"Oi! Como foi o seu atendimento de hoje com {a.barber.name} na *{shop.name}*? 💈\n\n"
                  "Dê uma nota de *1* a *5*:\n1 😞  2 🙁  3 😐  4 🙂  5 🤩")
        Ctx(db, shop, conv, a.customer.phone, "").go("survey_rating", appt_id=a.id)
        count += 1
    return count


def send_daily_summary(db, shop: Shop) -> bool:
    now = now_local()
    if not shop.owner_phone or now.hour < shop.daily_summary_hour or shop.last_summary_date == now.date():
        return False
    shop.last_summary_date = now.date()
    conv = _conv(db, shop, shop.owner_phone)
    ctx = Ctx(db, shop, conv, shop.owner_phone, "")
    parts = ["☀️ Bom dia! " + summary_text(ctx, now.date()), agenda_text(ctx, now.date())]
    bills = bills_text(db, shop, now.date())
    if bills:
        parts.append(bills)
    low = low_stock_text(db, shop)
    if low:
        parts.append(low)
    send_text(db, shop, shop.owner_phone, "\n\n".join(parts))
    return True


def run_crm(db, shop: Shop) -> None:
    """Sinal não confirmado no prazo libera o horário; reserva da lista de espera sem resposta passa a vez; clube de
    assinatura: cobra os vencimentos do dia e marca atraso."""
    from .services import billing, deposits, waitlist
    released = deposits.expire_unpaid(db, shop)
    if released:
        notify_staff(db, shop, f"⌛ {len(released)} horário(s) liberado(s): o sinal não foi pago a tempo.")
    waitlist.expire_offers(db, shop)
    billing.run_subscriptions(db, shop)


def run_all() -> None:
    db = SessionLocal()
    try:
        try:
            from .ai.usage import cleanup
            if cleanup(db):  # histórico da conversa usado pela IA: só os últimos 30 dias
                db.commit()
        except Exception:
            db.rollback()
            log.exception("Erro ao limpar o histórico das conversas")
        for shop in db.scalars(select(Shop)).all():
            try:
                send_reminders(db, shop)
                send_surveys(db, shop)
                expired = expire_old(db, shop)
                if expired:
                    notify_staff(db, shop, f"⌛ {expired} Pix pendente(s) expiraram sem confirmação.")
                expire_pending(db, shop)
                run_crm(db, shop)
                send_daily_summary(db, shop)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Erro nas rotinas da barbearia %s", shop.id)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    if not settings.run_scheduler:
        return None
    sched = BackgroundScheduler(timezone=settings.timezone)
    sched.add_job(run_all, "interval", minutes=1, id="rotinas", max_instances=1, coalesce=True)
    sched.start()
    return sched
