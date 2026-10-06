from datetime import datetime, time, date
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
    Table, Text, Time, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .config import now_local


class ApptStatus:
    SCHEDULED = "scheduled"      # agendado
    CONFIRMED = "confirmed"      # cliente confirmou no lembrete
    COMPLETED = "completed"      # atendido
    CANCELLED = "cancelled"      # cancelado
    NO_SHOW = "no_show"          # faltou
    ACTIVE = (SCHEDULED, CONFIRMED)


class PayStatus:
    NONE = "none"        # vai pagar na barbearia
    PENDING = "pending"  # Pix gerado, aguardando confirmação do dono
    PAID = "paid"
    EXPIRED = "expired"


barber_services = Table(
    "barber_services",
    Base.metadata,
    Column("barber_id", ForeignKey("barbers.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    # Número pessoal do dono: recebe os alertas e acessa o menu do estabelecimento
    owner_phone: Mapped[str] = mapped_column(String(20), default="")
    instagram: Mapped[str] = mapped_column(String(80), default="")

    # Pix
    pix_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    pix_key: Mapped[str] = mapped_column(String(100), default="")
    pix_key_type: Mapped[str] = mapped_column(String(10), default="random")  # cpf, cnpj, email, phone, random
    pix_receiver_name: Mapped[str] = mapped_column(String(25), default="")
    pix_city: Mapped[str] = mapped_column(String(15), default="")
    pix_expire_hours: Mapped[int] = mapped_column(Integer, default=12)

    # Regras do bot
    slot_step_minutes: Mapped[int] = mapped_column(Integer, default=30)
    min_advance_minutes: Mapped[int] = mapped_column(Integer, default=30)
    booking_days_ahead: Mapped[int] = mapped_column(Integer, default=7)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=120)
    cancel_min_hours: Mapped[int] = mapped_column(Integer, default=2)
    survey_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    survey_delay_minutes: Mapped[int] = mapped_column(Integer, default=30)
    daily_summary_hour: Mapped[int] = mapped_column(Integer, default=8)
    last_summary_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    welcome_text: Mapped[str] = mapped_column(Text, default="")
    human_pause_hours: Mapped[int] = mapped_column(Integer, default=3)

    # WhatsApp (Evolution API)
    evolution_instance: Mapped[str] = mapped_column(String(60), unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    barbers: Mapped[list["Barber"]] = relationship(back_populates="shop")
    services: Mapped[list["Service"]] = relationship(back_populates="shop")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))

    shop: Mapped[Shop] = relationship()


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    shop: Mapped[Shop] = relationship(back_populates="services")


class Barber(Base):
    __tablename__ = "barbers"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(20), default="")  # recebe alertas da própria agenda
    bio: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    shop: Mapped[Shop] = relationship(back_populates="barbers")
    services: Mapped[list[Service]] = relationship(secondary=barber_services)
    working_hours: Mapped[list["WorkingHour"]] = relationship(
        back_populates="barber", cascade="all, delete-orphan", order_by="WorkingHour.weekday"
    )


class WorkingHour(Base):
    """Expediente do barbeiro. weekday: 0 = segunda ... 6 = domingo. Pode haver mais de um intervalo por dia."""
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start: Mapped[time] = mapped_column(Time)
    end: Mapped[time] = mapped_column(Time)

    barber: Mapped[Barber] = relationship(back_populates="working_hours")


class Block(Base):
    """Bloqueio de agenda: almoço, folga, feriado. barber_id nulo = barbearia inteira."""
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=True)
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(120), default="")

    barber: Mapped[Barber | None] = relationship()


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("shop_id", "phone"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    start: Mapped[datetime] = mapped_column(DateTime, index=True)
    end: Mapped[datetime] = mapped_column(DateTime)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default=ApptStatus.SCHEDULED, index=True)
    payment_status: Mapped[str] = mapped_column(String(20), default=PayStatus.NONE)
    created_via: Mapped[str] = mapped_column(String(10), default="bot")  # bot | app
    notes: Mapped[str] = mapped_column(Text, default="")
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    survey_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer: Mapped[Customer] = relationship()
    barber: Mapped[Barber] = relationship()
    service: Mapped[Service] = relationship()
    payment: Mapped["Payment | None"] = relationship(back_populates="appointment", uselist=False)
    review: Mapped["Review | None"] = relationship(back_populates="appointment", uselist=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    txid: Mapped[str] = mapped_column(String(25))
    brcode: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=PayStatus.PENDING, index=True)
    customer_reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # cliente disse "paguei"
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    appointment: Mapped[Appointment] = relationship(back_populates="payment")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), unique=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    appointment: Mapped[Appointment] = relationship(back_populates="review")


class Conversation(Base):
    """Estado do menu de cada número no WhatsApp."""
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("shop_id", "phone"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(40), default="menu")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, onupdate=now_local)


class OutboxMessage(Base):
    """Histórico de mensagens enviadas (útil para depuração e para o modo simulação)."""
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    text: Mapped[str] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
