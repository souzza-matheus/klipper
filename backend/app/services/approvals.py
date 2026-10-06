"""Pedidos de clientes com acesso "precisa de aprovação": alerta ao dono, aprovar, recusar e expiração.

As mensagens para o cliente são neutras: nunca dizem que ele precisa de aprovação nem o motivo."""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bot.context import BUSY_STATES, Ctx, conversation_for
from ..config import now_local
from ..models import Appointment, ApptStatus, Shop
from .fmt import appt_summary, dt_label
from .payments import pix_ready
from .scheduling import cancel_appointment
from .whatsapp import send_text

# Pedido pendente expira quando faltar menos que isso para o horário
APPROVAL_CUTOFF = timedelta(hours=1)
# Pelo bot, o cliente que precisa de aprovação só vê horários com pelo menos isso de antecedência,
# para o dono ter ao menos 1 h para responder antes do pedido expirar
APPROVAL_MIN_LEAD = timedelta(hours=2)

MSG_RECEIVED = "Recebemos seu pedido! A barbearia vai confirmar e te avisamos por aqui."
MSG_REFUSED = "Infelizmente não temos esse horário disponível. Fale com a barbearia para ver outras opções."


def pending_approvals(db: Session, shop: Shop) -> list[Appointment]:
    return list(db.scalars(select(Appointment).where(
        Appointment.shop_id == shop.id, Appointment.status == ApptStatus.PENDING_APPROVAL,
    ).order_by(Appointment.start)).all())


def approval_deadline(shop: Shop, appt: Appointment) -> datetime:
    """X horas sem resposta ou 1 h antes do horário, o que vier primeiro."""
    requested = appt.approval_requested_at or appt.created_at or now_local()
    return min(requested + timedelta(hours=shop.approval_expire_hours), appt.start - APPROVAL_CUTOFF)


def alert_owner(db: Session, shop: Shop, appt: Appointment, rescheduled_from: str = "") -> None:
    """Avisa o dono (só ele aprova) de um novo pedido pendente."""
    if not shop.owner_phone:
        return
    c = appt.customer
    head = "🟡 *Pedido de remarcação para aprovar*" if rescheduled_from else "🟡 *Pedido para aprovar*"
    extra = f"\nAntes: {rescheduled_from}" if rescheduled_from else ""
    send_text(db, shop, shop.owner_phone,
              f"{head}\n{c.name or 'Cliente'} ({c.phone}){extra}\n{appt_summary(appt)}\n\n"
              f"Expira {dt_label(approval_deadline(shop, appt)).lower()} se ninguém responder.\n"
              "Para aprovar ou recusar: mande *menu* e escolha *Pedidos para aprovar* (ou use o app).")


def approve(db: Session, shop: Shop, appt: Appointment) -> None:
    """Aprova o pedido: vira agendado, o cliente recebe o resumo e, com Pix ativo, a oferta de pagamento."""
    appt.status = ApptStatus.SCHEDULED
    appt.approval_requested_at = None
    phone = appt.customer.phone
    msg = f"✅ Seu horário na *{shop.name}* está confirmado!\n\n{appt_summary(appt)}"
    if not pix_ready(shop):
        send_text(db, shop, phone, msg + "\n\nTe mando um lembrete antes do horário. "
                                         "Para cancelar ou remarcar, é só mandar *menu* e escolher a opção 2.")
        return
    conv = conversation_for(db, shop, phone)
    if conv.state in BUSY_STATES:  # no meio de outro fluxo: não muda a conversa, indica o caminho
        send_text(db, shop, phone, msg + "\n\nSe quiser adiantar o pagamento via Pix, mande *menu* e escolha a opção 6.")
        return
    send_text(db, shop, phone, msg + "\n\nQuer adiantar o pagamento?\n\n"
                                     "*1* - Pagar agora via Pix\n*2* - Pagar na barbearia")
    Ctx(db, shop, conv, phone, "").go("book_pay", appt_id=appt.id)


def refuse(db: Session, shop: Shop, appt: Appointment) -> None:
    cancel_appointment(db, appt)
    appt.approval_requested_at = None
    send_text(db, shop, appt.customer.phone, f"{MSG_REFUSED}\n\n(Pedido: {dt_label(appt.start)})")


def expire_pending(db: Session, shop: Shop) -> int:
    """Cancela os pedidos sem resposta no prazo, libera o horário e avisa o cliente e o dono."""
    now = now_local()
    expired = [a for a in pending_approvals(db, shop) if approval_deadline(shop, a) <= now]
    for a in expired:
        cancel_appointment(db, a)
        a.approval_requested_at = None
        send_text(db, shop, a.customer.phone,
                  f"Não conseguimos confirmar o seu pedido para {dt_label(a.start).lower()} a tempo. 😕\n"
                  "Fale com a barbearia para ver outras opções.")
    if expired and shop.owner_phone:
        lines = "\n".join(f"• {a.customer.name or a.customer.phone} - {dt_label(a.start)}" for a in expired)
        send_text(db, shop, shop.owner_phone,
                  f"⌛ {len(expired)} pedido(s) para aprovar expiraram sem resposta e o horário foi liberado:\n{lines}")
    return len(expired)
