from datetime import datetime, time, date
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String,
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
    PENDING_APPROVAL = "pending_approval"  # pedido de cliente "precisa de aprovação", aguardando o dono
    ACTIVE = (SCHEDULED, CONFIRMED)
    OCCUPYING = (SCHEDULED, CONFIRMED, PENDING_APPROVAL)  # ocupam o horário na disponibilidade


class AccessStatus:
    """Acesso do cliente ao agendamento pelo bot. O motivo é interno e nunca aparece para o cliente."""
    NORMAL = "normal"
    APPROVAL = "approval"  # agendamento pelo bot fica pendente até o dono aprovar
    BLOCKED = "blocked"    # não agenda nem remarca pelo bot
    ALL = (NORMAL, APPROVAL, BLOCKED)


class PayMethod:
    """Forma de pagamento do atendimento (preenchida ao concluir)."""
    PIX = "pix"
    CASH = "dinheiro"
    DEBIT = "debito"
    CREDIT = "credito"
    ALL = (PIX, CASH, DEBIT, CREDIT)
    LABELS = {PIX: "Pix", CASH: "Dinheiro", DEBIT: "Débito", CREDIT: "Crédito"}


class Niche:
    """Segmento do negócio: define o tema e o vocabulário do app."""
    BARBERSHOP = "barbershop"
    BEAUTY = "beauty"
    PETSHOP = "petshop"
    CLINIC = "clinic"
    FITNESS = "fitness"
    ALL = (BARBERSHOP, BEAUTY, PETSHOP, CLINIC, FITNESS)


class ThemeMode:
    AUTO = "auto"  # usa o modo (claro ou escuro) do segmento
    DARK = "dark"
    LIGHT = "light"
    ALL = (AUTO, DARK, LIGHT)


class ConflictAction:
    """O que o bot faz quando o horário fica perto de um cliente em conflito."""
    BLOCK = "block"        # esconde o horário (o cliente não vê o motivo)
    APPROVAL = "approval"  # deixa agendar, mas o pedido fica aguardando a aprovação do dono
    ALL = (BLOCK, APPROVAL)


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
    # Pedido de cliente "precisa de aprovação" expira sem resposta do dono
    approval_expire_hours: Mapped[int] = mapped_column(Integer, default=12)
    # Distância mínima entre clientes em conflito quando o conflito não define a sua
    conflict_default_gap_minutes: Mapped[int] = mapped_column(Integer, default=240)

    # Aparência do app
    niche: Mapped[str] = mapped_column(String(20), default=Niche.BARBERSHOP)
    theme_mode: Mapped[str] = mapped_column(String(10), default=ThemeMode.AUTO)

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
    access_status: Mapped[str] = mapped_column(String(10), default=AccessStatus.NORMAL)
    access_reason: Mapped[str] = mapped_column(Text, default="")  # interno, só para o dono
    access_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class CustomerConflict(Base):
    """Dois clientes que não devem estar na barbearia ao mesmo tempo. O par é guardado com customer_a_id <
    customer_b_id, então A-B e B-A são o mesmo registro. min_gap_minutes nulo = padrão da barbearia."""
    __tablename__ = "customer_conflicts"
    __table_args__ = (
        UniqueConstraint("shop_id", "customer_a_id", "customer_b_id"),
        CheckConstraint("customer_a_id < customer_b_id", name="ck_customer_conflicts_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_a_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    customer_b_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    min_gap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    same_day_block: Mapped[bool] = mapped_column(Boolean, default=False)  # nunca os dois no mesmo dia
    conflict_action: Mapped[str] = mapped_column(String(10), default=ConflictAction.BLOCK)
    notes: Mapped[str] = mapped_column(Text, default="")  # motivo interno
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    customer_a: Mapped["Customer"] = relationship(foreign_keys=[customer_a_id])
    customer_b: Mapped["Customer"] = relationship(foreign_keys=[customer_b_id])

    def other_id(self, customer_id: int) -> int:
        return self.customer_b_id if customer_id == self.customer_a_id else self.customer_a_id


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
    payment_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # PayMethod; nulo = não informado
    created_via: Mapped[str] = mapped_column(String(10), default="bot")  # bot | app
    notes: Mapped[str] = mapped_column(Text, default="")
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    survey_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Quando o pedido entrou em pending_approval (conta o prazo de expiração)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    # Comprovante mandado pelo cliente no WhatsApp (imagem ou PDF, baixado da Evolution API)
    receipt_mime: Mapped[str | None] = mapped_column(String(60), nullable=True)
    receipt_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    receipt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class Beneficiary:
    SHOP = "shop"      # dono da barbearia
    BARBER = "barber"  # outro barbeiro (padrinho/mentor)


class CommissionRule(Base):
    """Repasse de uma porcentagem do que o barbeiro fatura. service_id nulo = todos os serviços;
    uma regra de serviço substitui a geral para o mesmo beneficiário."""
    __tablename__ = "commission_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), index=True)  # quem paga
    beneficiary_type: Mapped[str] = mapped_column(String(10), default=Beneficiary.SHOP)
    beneficiary_barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=True)
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    barber: Mapped[Barber] = relationship(foreign_keys=[barber_id])
    beneficiary_barber: Mapped[Barber | None] = relationship(foreign_keys=[beneficiary_barber_id])
    service: Mapped[Service | None] = relationship()


class CommissionSettlement(Base):
    """Acerto: registra que o repasse de um período foi pago ao beneficiário."""
    __tablename__ = "commission_settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    payer_barber_id: Mapped[int] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), index=True)
    beneficiary_type: Mapped[str] = mapped_column(String(10), default=Beneficiary.SHOP)
    beneficiary_barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    payer: Mapped[Barber] = relationship(foreign_keys=[payer_barber_id])
    beneficiary_barber: Mapped[Barber | None] = relationship(foreign_keys=[beneficiary_barber_id])


class ExpenseCategory:
    LABELS = {
        "aluguel": "Aluguel", "energia": "Energia", "agua": "Água", "internet": "Internet",
        "produtos": "Produtos", "equipamentos": "Equipamentos", "manutencao": "Manutenção",
        "marketing": "Marketing", "salarios": "Salários", "impostos": "Impostos", "outros": "Outros",
    }
    ALL = tuple(LABELS)


class Expense(Base):
    """Gasto da barbearia. paid_at nulo = em aberto. Um gasto com recurring=True é o original de uma conta mensal:
    as cópias dos meses seguintes apontam para ele em recurring_source_id."""
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(20), default="outros", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    paid_at: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="SET NULL"), nullable=True)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurring_source_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    barber: Mapped[Barber | None] = relationship()
