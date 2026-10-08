import secrets
import uuid as _uuid
from datetime import datetime, time, date
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, LargeBinary,
    Numeric, String, Table, Text, Time, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from .db import Base
from .config import now_local


class ApptStatus:
    SCHEDULED = "scheduled"      # agendado
    CONFIRMED = "confirmed"      # cliente confirmou no lembrete
    COMPLETED = "completed"      # atendido
    CANCELLED = "cancelled"      # cancelado
    NO_SHOW = "no_show"          # faltou
    PENDING_APPROVAL = "pending_approval"  # pedido de cliente "precisa de aprovação", aguardando o dono
    AWAITING_DEPOSIT = "awaiting_deposit"  # reservado até o sinal ser confirmado (expira e libera o horário)
    HELD = "held"                          # oferecido a alguém da lista de espera (reserva de poucos minutos)
    ACTIVE = (SCHEDULED, CONFIRMED)
    # ocupam o horário na disponibilidade
    OCCUPYING = (SCHEDULED, CONFIRMED, PENDING_APPROVAL, AWAITING_DEPOSIT, HELD)


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


class Role:
    """Papel do usuário do app. O dono vê tudo; a recepção agenda, faz check-in e fecha comandas (sem o financeiro
    completo); o profissional vê só a própria agenda, os clientes que atendeu e as próprias comissões."""
    OWNER = "owner"
    RECEPTION = "reception"
    PROFESSIONAL = "professional"
    ALL = (OWNER, RECEPTION, PROFESSIONAL)
    STAFF = (OWNER, RECEPTION)
    LABELS = {OWNER: "Dono", RECEPTION: "Recepção", PROFESSIONAL: "Profissional"}


class DepositMode:
    """Sinal para garantir o horário. No serviço, "" = segue a regra do estabelecimento."""
    OFF = "off"
    FIXED = "fixed"
    PERCENT = "percent"
    ALL = (OFF, FIXED, PERCENT)


class DepositStatus:
    NONE = "none"
    PENDING = "pending"        # aguardando o Pix do sinal
    PAID = "paid"
    REFUND_DUE = "refund_due"  # cancelado no prazo: o sinal deve ser devolvido
    REFUNDED = "refunded"
    FORFEITED = "forfeited"    # cancelado fora do prazo (ou falta): o sinal fica com o estabelecimento


def new_uuid() -> str:
    return str(_uuid.uuid4())


class SyncMixin:
    """Colunas da sincronização offline. uuid é o id público (o app pode gerar ao criar offline); updated_at,
    version e sync_seq são escritos só pelo servidor (app/sync_events.py); deleted_at marca a exclusão (tombstone):
    a linha some das consultas normais, mas ainda vai para o app no /api/sync/pull."""
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Ordem das mudanças dentro da loja (contador em shops.sync_seq): o cursor do pull
    sync_seq: Mapped[int] = mapped_column(BigInteger, default=0)

    @declared_attr.directive
    def __table_args__(cls):
        extra = cls.__dict__.get("__extra_args__", ())
        return (*extra, Index(f"ix_{cls.__tablename__}_shop_seq", "shop_id", "sync_seq"))


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

    # Sinal (Pix antecipado que garante o horário)
    deposit_mode: Mapped[str] = mapped_column(String(10), default=DepositMode.OFF)
    deposit_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)  # R$ (fixed) ou % (percent)
    deposit_expire_minutes: Mapped[int] = mapped_column(Integer, default=30)  # sem sinal confirmado, libera o horário
    deposit_refund_hours: Mapped[int] = mapped_column(Integer, default=24)  # cancelou antes disso: devolve o sinal
    # Lista de espera: minutos que a vaga fica reservada para quem foi avisado
    waitlist_hold_minutes: Mapped[int] = mapped_column(Integer, default=10)
    # Contador das mudanças sincronizáveis desta loja (ver SyncMixin)
    sync_seq: Mapped[int] = mapped_column(BigInteger, default=0)

    # Aparência do app
    niche: Mapped[str] = mapped_column(String(20), default=Niche.BARBERSHOP)
    theme_mode: Mapped[str] = mapped_column(String(10), default=ThemeMode.AUTO)

    # Atendimento com IA (ver app/ai)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_audio_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_monthly_limit: Mapped[int] = mapped_column(Integer, default=3000)  # chamadas ao modelo por mês
    # Pode usar a IA quando o servidor está no plano gratuito do provedor (só a demo, com dados fictícios)
    ai_allow_free_tier: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_limit_warned_month: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "2026-10": aviso já enviado

    # WhatsApp (Evolution API)
    evolution_instance: Mapped[str] = mapped_column(String(60), unique=True)
    # Secret do webhook desta instância (vai no cabeçalho X-Webhook-Secret). Um por barbearia: se vazar, não vale
    # para as outras. Vazio = usa o WEBHOOK_SECRET global (instâncias antigas).
    webhook_secret: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(32))

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
    # Sobe a cada "sair de todos os aparelhos" ou troca de senha: tokens com versão antiga deixam de valer
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(15), default=Role.OWNER)
    # Profissional: a qual cadastro de profissional (agenda) este login pertence
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)  # convite com senha provisória
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=now_local, nullable=True)

    shop: Mapped[Shop] = relationship()
    barber: Mapped["Barber | None"] = relationship()


class Service(SyncMixin, Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # Sinal deste serviço: "" segue o estabelecimento; off, fixed ou percent sobrescrevem
    deposit_mode: Mapped[str] = mapped_column(String(10), default="")
    deposit_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)

    shop: Mapped[Shop] = relationship(back_populates="services")
    consumption: Mapped[list["ServiceProduct"]] = relationship(cascade="all, delete-orphan")


class Barber(SyncMixin, Base):
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


class Block(SyncMixin, Base):
    """Bloqueio de agenda: almoço, folga, feriado. barber_id nulo = barbearia inteira."""
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id", ondelete="CASCADE"), nullable=True)
    start: Mapped[datetime] = mapped_column(DateTime)
    end: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(120), default="")

    barber: Mapped[Barber | None] = relationship()


class Customer(SyncMixin, Base):
    __tablename__ = "customers"
    __extra_args__ = (UniqueConstraint("shop_id", "phone"),)

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


class Appointment(SyncMixin, Base):
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
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # cliente chegou (recepção)
    # Sinal
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    deposit_status: Mapped[str] = mapped_column(String(12), default=DepositStatus.NONE)
    # Pago com saldo: sessão de pacote ou uso da assinatura (consumido ao agendar, devolvido ao cancelar)
    customer_package_id: Mapped[int | None] = mapped_column(ForeignKey("customer_packages.id"), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)

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
    kind: Mapped[str] = mapped_column(String(10), default="full")  # full: atendimento | deposit: sinal
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


class ConversationMessage(Base):
    """Histórico da conversa do cliente usado como contexto pela IA (apagado depois de 30 dias).
    role: user | assistant. channel: ai (respondida pela IA) | menu (fluxo numerado)."""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    role: Mapped[str] = mapped_column(String(10))
    channel: Mapped[str] = mapped_column(String(10), default="menu")
    text: Mapped[str] = mapped_column(Text, default="")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{"name", "args", "ok"}] resumidas
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


class AIUsage(Base):
    """Cada chamada ao modelo de IA: para o limite mensal e o acompanhamento de custo."""
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    thinking_tokens: Mapped[int] = mapped_column(Integer, default=0)  # raciocínio, cobrado como saída
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)    # entrada servida pelo cache implícito
    # call: chamada ao modelo (conta no limite mensal); blocked: mensagem barrada sem chamar o modelo
    kind: Mapped[str] = mapped_column(String(10), default="call")
    # Motivo do bloqueio ou categoria fora do tema: offtopic:<categoria>, offtopic_pause, flood, repeat, too_long
    category: Mapped[str] = mapped_column(String(40), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str] = mapped_column(String(200), default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


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


# ================================================================ CRM fase 1

class ProductKind:
    SALE = "sale"          # só venda
    INTERNAL = "internal"  # só uso interno (consumido nos serviços)
    BOTH = "both"
    ALL = (SALE, INTERNAL, BOTH)


class StockReason:
    PURCHASE = "purchase"        # entrada (compra)
    SALE = "sale"                # venda na comanda
    CONSUMPTION = "consumption"  # consumo do serviço
    INTERNAL = "internal"        # uso interno avulso
    ADJUST = "adjust"            # ajuste de inventário (diferença, nunca o saldo)
    REVERSAL = "reversal"        # estorno de item da comanda
    ALL = (PURCHASE, SALE, CONSUMPTION, INTERNAL, ADJUST, REVERSAL)


class Product(SyncMixin, Base):
    """Produto de venda e/ou uso interno. O saldo NÃO é guardado aqui: é a soma das movimentações."""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10), default=ProductKind.BOTH)
    unit: Mapped[str] = mapped_column(String(10), default="un")
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    # Comissão do profissional que vendeu (opcional, % do valor vendido)
    commission_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class ServiceProduct(Base):
    """Quanto de cada produto um serviço consome (baixa automática do estoque ao lançar o serviço na comanda)."""
    __tablename__ = "service_products"

    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    product: Mapped[Product] = relationship()


class StockMovement(SyncMixin, Base):
    """Movimentação de estoque: sempre uma diferença (+ entra, - sai). Nunca é alterada nem apagada."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    delta: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(String(12))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    comanda_item_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_items.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)

    product: Mapped[Product] = relationship()


class PackagePlan(SyncMixin, Base):
    """Pacote à venda: N sessões de um serviço por um preço, com validade."""
    __tablename__ = "package_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    sessions: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    validity_days: Mapped[int] = mapped_column(Integer, default=90)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    service: Mapped[Service] = relationship()


class CustomerPackage(SyncMixin, Base):
    """Pacote comprado por um cliente. Saldo = sessions + soma de PackageUse.delta."""
    __tablename__ = "customer_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("package_plans.id"), nullable=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    name: Mapped[str] = mapped_column(String(80))
    sessions: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    session_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # preço / sessões: base da comissão
    # pending_payment (comprado pelo WhatsApp, aguardando o Pix) | active | cancelled
    status: Mapped[str] = mapped_column(String(16), default="active")
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    # use_alter: appointments -> customer_packages -> comandas -> appointments formam um ciclo
    comanda_id: Mapped[int | None] = mapped_column(
        ForeignKey("comandas.id", use_alter=True, name="fk_customer_packages_comanda_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    customer: Mapped[Customer] = relationship()
    service: Mapped[Service] = relationship()


class PackageUse(SyncMixin, Base):
    """Uso de sessão: -1 ao usar, +1 ao devolver (cancelamento ou estorno). Nunca é alterado."""
    __tablename__ = "package_uses"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_package_id: Mapped[int] = mapped_column(ForeignKey("customer_packages.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    comanda_item_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class SubStatus:
    ACTIVE = "ativa"
    LATE = "atrasada"
    CANCELLED = "cancelada"
    ALL = (ACTIVE, LATE, CANCELLED)


class SubscriptionPlan(SyncMixin, Base):
    """Clube de assinatura: mensalidade com serviços incluídos (com ou sem limite por período)."""
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Dias de atraso tolerados antes de bloquear os benefícios
    block_after_days: Mapped[int] = mapped_column(Integer, default=5)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    items: Mapped[list["SubscriptionPlanItem"]] = relationship(cascade="all, delete-orphan")


class SubscriptionPlanItem(Base):
    __tablename__ = "subscription_plan_items"

    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plans.id", ondelete="CASCADE"), primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="CASCADE"), primary_key=True)
    limit_per_period: Mapped[int | None] = mapped_column(Integer, nullable=True)  # nulo = sem limite

    service: Mapped[Service] = relationship()


class Subscription(SyncMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("subscription_plans.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # valor contratado (o plano pode mudar depois)
    status: Mapped[str] = mapped_column(String(10), default=SubStatus.ACTIVE, index=True)
    started_at: Mapped[date] = mapped_column(Date)
    next_due_date: Mapped[date] = mapped_column(Date)  # próxima cobrança a gerar
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    customer: Mapped[Customer] = relationship()
    plan: Mapped[SubscriptionPlan] = relationship()


class SubscriptionUse(SyncMixin, Base):
    """Uso de um serviço da assinatura no período (ciclo que começa no dia do mês em que a assinatura começou)."""
    __tablename__ = "subscription_uses"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    period_start: Mapped[date] = mapped_column(Date)
    delta: Mapped[int] = mapped_column(Integer)  # +1 usou, -1 devolveu
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    comanda_item_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)


class Charge(SyncMixin, Base):
    """Cobrança avulsa (fora de um agendamento): mensalidade da assinatura ou pacote comprado pelo WhatsApp.
    gateway = "manual_pix" (Pix da chave do estabelecimento, confirmado à mão); outro gateway entra por
    app/services/billing.py sem mudar o resto."""
    __tablename__ = "charges"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # subscription | package
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True, index=True)
    customer_package_id: Mapped[int | None] = mapped_column(ForeignKey("customer_packages.id"), nullable=True)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(10), default=PayStatus.PENDING, index=True)
    gateway: Mapped[str] = mapped_column(String(20), default="manual_pix")
    txid: Mapped[str] = mapped_column(String(35), default="")
    brcode: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    customer_reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    customer: Mapped[Customer] = relationship()
    subscription: Mapped[Subscription | None] = relationship()


class ComandaStatus:
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ItemKind:
    SERVICE = "service"
    PRODUCT = "product"
    PACKAGE = "package"    # venda de pacote
    DISCOUNT = "discount"  # valor negativo (R$ ou % do subtotal no momento)
    TIP = "tip"            # gorjeta: vai inteira para o profissional, não é faturamento
    ALL = (SERVICE, PRODUCT, PACKAGE, DISCOUNT, TIP)


class Comanda(SyncMixin, Base):
    """Conta do atendimento. Aberta ao concluir um agendamento ou avulsa (só produtos, encaixe). Itens e pagamentos
    são lançamentos imutáveis; estorno é um lançamento negativo que aponta para o original."""
    __tablename__ = "comandas"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(10), default=ComandaStatus.OPEN, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)
    opened_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    customer: Mapped[Customer | None] = relationship()
    appointment: Mapped[Appointment | None] = relationship()
    items: Mapped[list["ComandaItem"]] = relationship(order_by="ComandaItem.id", back_populates="comanda")
    payments: Mapped[list["ComandaPayment"]] = relationship(order_by="ComandaPayment.id", back_populates="comanda")


class ComandaItem(SyncMixin, Base):
    __tablename__ = "comanda_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(120), default="")
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    package_plan_id: Mapped[int | None] = mapped_column(ForeignKey("package_plans.id"), nullable=True)
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id"), nullable=True)  # quem fez/vendeu/recebe
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # valor a pagar (com sinal); coberto por saldo = 0
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # desconto em %
    # none | package | subscription: serviço pago com saldo de pacote ou assinatura
    covered_by: Mapped[str] = mapped_column(String(12), default="none")
    customer_package_id: Mapped[int | None] = mapped_column(ForeignKey("customer_packages.id"), nullable=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id"), nullable=True)
    commission_base: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)  # base da comissão (com sinal)
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_items.id"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    comanda: Mapped[Comanda] = relationship(back_populates="items")
    service: Mapped[Service | None] = relationship()
    product: Mapped[Product | None] = relationship()
    barber: Mapped[Barber | None] = relationship()
    package_plan: Mapped["PackagePlan | None"] = relationship()


class ComandaPayMethod:
    LABELS = {**PayMethod.LABELS}
    ALL = PayMethod.ALL


class ComandaPayment(SyncMixin, Base):
    __tablename__ = "comanda_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id"), index=True)
    method: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # negativo = estorno
    from_deposit: Mapped[bool] = mapped_column(Boolean, default=False)  # sinal pago antes pelo Pix
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_payments.id"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    comanda: Mapped[Comanda] = relationship(back_populates="payments")


class WaitStatus:
    WAITING = "waiting"
    OFFERED = "offered"      # vaga reservada para esta pessoa por alguns minutos
    BOOKED = "booked"
    EXPIRED = "expired"      # não respondeu a tempo (perde a vez)
    CANCELLED = "cancelled"  # recusou ou saiu da lista
    OPEN = (WAITING, OFFERED)


class WaitlistEntry(SyncMixin, Base):
    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    barber_id: Mapped[int | None] = mapped_column(ForeignKey("barbers.id"), nullable=True)  # nulo = qualquer um
    day: Mapped[date] = mapped_column(Date, index=True)
    after_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    before_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=WaitStatus.WAITING, index=True)
    offered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id"), nullable=True)
    created_via: Mapped[str] = mapped_column(String(10), default="bot")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)

    customer: Mapped[Customer] = relationship()
    service: Mapped[Service] = relationship()
    barber: Mapped[Barber | None] = relationship()


class SyncOperation(Base):
    """Operação recebida no /api/sync/push. operation_id único: reenviar a mesma operação devolve o mesmo resultado
    (idempotência) sem executar de novo."""
    __tablename__ = "sync_operations"
    __table_args__ = (UniqueConstraint("shop_id", "operation_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    entity: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


from . import sync_events  # noqa: E402,F401  (carimbos da sincronização e filtro de excluídos)
