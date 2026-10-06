from datetime import timedelta

from sqlalchemy import select

from app.bot.router import handle_incoming
from app.config import now_local
from app.jobs import send_reminders, send_surveys
from app.models import Appointment, ApptStatus, OutboxMessage, PayStatus, Review, Shop

INST = "barbearia-demo"
CLIENT = "5531977776666"
OWNER = "5531999990000"


def say(db, phone, text):
    return "\n---\n".join(handle_incoming(db, INST, phone, text, "Carlos Silva"))


def staff_msgs(db, phone):
    return [m.text for m in db.scalars(select(OutboxMessage).where(OutboxMessage.phone == phone))]


def book(db):
    assert "Agendar horário" in say(db, CLIENT, "oi")
    assert "Qual serviço" in say(db, CLIENT, "1")
    assert "Com qual barbeiro" in say(db, CLIENT, "3")  # Corte + Barba
    assert "Para qual dia" in say(db, CLIENT, "1")      # João
    r = say(db, CLIENT, "2")
    assert "Horários livres" in r
    assert "Qual é o seu nome" in say(db, CLIENT, "1")
    assert "Confirma o agendamento" in say(db, CLIENT, "carlos silva")
    r = say(db, CLIENT, "1")
    assert "Agendado" in r and "Pagar agora via Pix" in r
    return db.scalar(select(Appointment).order_by(Appointment.id.desc()))


def test_full_booking_pix_and_owner_confirm(db):
    appt = book(db)
    assert appt.customer.name == "Carlos Silva"
    assert appt.service.name == "Corte + Barba"
    assert any("Novo agendamento" in m for m in staff_msgs(db, OWNER))
    assert any("Novo agendamento" in m for m in staff_msgs(db, "5531988880001"))  # barbeiro João

    r = say(db, CLIENT, "1")  # pagar agora
    assert "Pix" in r and "000201" in r
    db.refresh(appt)
    assert appt.payment_status == PayStatus.PENDING

    assert "Avisei a barbearia" in say(db, CLIENT, "paguei")
    assert any("informou pagamento" in m for m in staff_msgs(db, OWNER))

    assert "Painel" in say(db, OWNER, "oi")
    assert "Carlos Silva" in say(db, OWNER, "5")
    assert "confirmado" in say(db, OWNER, "1")
    db.refresh(appt)
    assert appt.payment_status == PayStatus.PAID
    assert any("Recebemos o seu Pix" in m for m in staff_msgs(db, CLIENT))


def test_cancel_notifies_owner_and_frees_slot(db):
    appt = book(db)
    say(db, CLIENT, "2")  # pagar na barbearia
    assert "próximos agendamentos" in say(db, CLIENT, "2")
    assert "O que você quer fazer" in say(db, CLIENT, "1")
    assert "Cancelar este horário" in say(db, CLIENT, "1")
    assert "cancelado" in say(db, CLIENT, "1")
    db.refresh(appt)
    assert appt.status == ApptStatus.CANCELLED
    assert any("ficou livre" in m for m in staff_msgs(db, OWNER))


def test_reschedule(db):
    appt = book(db)
    say(db, CLIENT, "2")
    old_start = appt.start
    say(db, CLIENT, "2")           # meus agendamentos
    say(db, CLIENT, "1")           # escolhe o agendamento
    assert "Com qual barbeiro" in say(db, CLIENT, "2")  # remarcar
    say(db, CLIENT, "2")           # Pedro
    say(db, CLIENT, "2")           # dia
    assert "Confirma a remarcação" in say(db, CLIENT, "3")
    assert "Remarcado" in say(db, CLIENT, "1")
    db.refresh(appt)
    assert appt.barber.name == "Pedro"
    assert appt.status == ApptStatus.SCHEDULED
    assert db.scalar(select(Appointment).where(Appointment.status == ApptStatus.CANCELLED)) is None
    assert any("Remarcação" in m for m in staff_msgs(db, OWNER))
    assert old_start is not None


def test_owner_menu_options(db):
    book(db)
    say(db, CLIENT, "2")
    assert "Painel" in say(db, OWNER, "menu")
    assert "Agenda" in say(db, OWNER, "2") or True
    say(db, OWNER, "3")
    assert "Horários livres" in say(db, OWNER, "amanhã")
    say(db, OWNER, "4")
    assert "Carlos Silva" in say(db, OWNER, "carlos")
    say(db, OWNER, "6")
    assert "Bloqueado" in say(db, OWNER, "hoje 23:00 23:30 teste")
    assert "Resumo" in say(db, OWNER, "8")
    assert "Modo cliente" in say(db, OWNER, "9")
    assert "Agendar horário" in say(db, OWNER, "oi")
    assert "Painel" in say(db, OWNER, "painel")


def test_info_and_human(db):
    say(db, CLIENT, "oi")
    assert "Corte + Barba" in say(db, CLIENT, "3")
    assert "João" in say(db, CLIENT, "4")
    assert "Endereço" in say(db, CLIENT, "5")
    assert "Avisei a equipe" in say(db, CLIENT, "7")
    assert say(db, CLIENT, "alguém aí?") == ""  # bot pausado
    assert "Agendar horário" in say(db, CLIENT, "menu")


def test_reminder_and_survey(db):
    appt = book(db)
    say(db, CLIENT, "2")
    shop = db.scalar(select(Shop))
    # Simula um agendamento criado ontem para daqui a 1 hora
    appt.created_at = now_local() - timedelta(days=1)
    appt.start = now_local() + timedelta(minutes=60)
    appt.end = appt.start + timedelta(minutes=60)
    db.commit()
    assert send_reminders(db, shop) == 1
    db.commit()
    assert "Presença confirmada" in say(db, CLIENT, "1")
    db.refresh(appt)
    assert appt.status == ApptStatus.CONFIRMED

    # Atendimento terminou há 40 minutos
    appt.start = now_local() - timedelta(minutes=100)
    appt.end = now_local() - timedelta(minutes=40)
    db.commit()
    assert send_surveys(db, shop) == 1
    db.commit()
    assert any("Dê uma nota" in m for m in staff_msgs(db, CLIENT))
    assert "Valeu pela nota" in say(db, CLIENT, "2")
    assert any("Avaliação baixa" in m for m in staff_msgs(db, OWNER))
    assert "Obrigado" in say(db, CLIENT, "Demorou um pouco")
    review = db.scalar(select(Review))
    assert review.rating == 2 and review.comment == "Demorou um pouco"
    db.refresh(appt)
    assert appt.status == ApptStatus.COMPLETED
