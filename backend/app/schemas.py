from datetime import date, datetime, time
from decimal import Decimal

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Limites de entrada: nenhum valor pode passar do que o banco aceita (sem isso o Postgres devolve erro)
Id = Annotated[int, Field(gt=0, lt=2**31)]
# Ids em query string (?barber_id=): mesma faixa, e um valor fora dela é 422 (não erro do banco)
QId = Annotated[int, Query(gt=0, lt=2**31)]
Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999.99"), decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, le=Decimal("99999999.99"), decimal_places=2)]
Phone = Annotated[str, Field(max_length=30)]
Note = Annotated[str, Field(max_length=2000)]


def Text(n: int):  # noqa: N802 - tipo: texto com tamanho máximo
    return Annotated[str, Field(max_length=n)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class RegisterIn(BaseModel):
    setup_token: str = Field(max_length=200)
    shop_name: str = Field(min_length=1, max_length=120)
    owner_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    owner_phone: Phone = ""


NICHE = "^(barbershop|beauty|petshop|clinic|fitness)$"
THEME_MODE = "^(auto|dark|light)$"
CONFLICT_ACTION = "^(block|approval)$"


class TokenOut(BaseModel):
    token: str
    user_name: str
    shop_name: str
    niche: str = "barbershop"
    theme_mode: str = "auto"


# ---- shop
class ShopIn(BaseModel):
    """Só o que o dono pode mudar. evolution_instance, id e os controles internos da IA não estão aqui (e campos
    desconhecidos são ignorados)."""
    name: Text(120) | None = Field(None, min_length=1)
    address: Text(255) | None = None
    phone: Text(20) | None = None
    owner_phone: Phone | None = None
    instagram: Text(80) | None = None
    pix_enabled: bool | None = None
    pix_key: Text(100) | None = None
    pix_key_type: str | None = Field(None, pattern="^(cpf|cnpj|email|phone|random)$")
    pix_receiver_name: str | None = Field(None, max_length=25)
    pix_city: str | None = Field(None, max_length=15)
    pix_expire_hours: int | None = Field(None, ge=1, le=72)
    slot_step_minutes: int | None = Field(None, ge=5, le=120)
    min_advance_minutes: int | None = Field(None, ge=0, le=1440)
    booking_days_ahead: int | None = Field(None, ge=1, le=60)
    reminder_minutes_before: int | None = Field(None, ge=10, le=2880)
    cancel_min_hours: int | None = Field(None, ge=0, le=72)
    survey_enabled: bool | None = None
    survey_delay_minutes: int | None = Field(None, ge=0, le=1440)
    daily_summary_hour: int | None = Field(None, ge=0, le=23)
    welcome_text: Note | None = None
    human_pause_hours: int | None = Field(None, ge=1, le=48)
    approval_expire_hours: int | None = Field(None, ge=1, le=72)
    conflict_default_gap_minutes: int | None = Field(None, ge=0, le=1440)
    niche: str | None = Field(None, pattern=NICHE)
    theme_mode: str | None = Field(None, pattern=THEME_MODE)


class ShopOut(ORM):
    id: int
    name: str
    address: str
    phone: str
    owner_phone: str
    instagram: str
    pix_enabled: bool
    pix_key: str
    pix_key_type: str
    pix_receiver_name: str
    pix_city: str
    pix_expire_hours: int
    slot_step_minutes: int
    min_advance_minutes: int
    booking_days_ahead: int
    reminder_minutes_before: int
    cancel_min_hours: int
    survey_enabled: bool
    survey_delay_minutes: int
    daily_summary_hour: int
    welcome_text: str
    human_pause_hours: int
    approval_expire_hours: int
    conflict_default_gap_minutes: int
    niche: str
    theme_mode: str
    evolution_instance: str


# ---- services
class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    duration_minutes: int = Field(ge=5, le=480)
    price: Money
    active: bool = True
    sort_order: int = Field(0, ge=-1000, le=1000)


class ServiceOut(ORM):
    id: int
    name: str
    duration_minutes: int
    price: Decimal
    active: bool
    sort_order: int


# ---- barbers
class WorkingHourIO(ORM):
    weekday: int = Field(ge=0, le=6)
    start: time
    end: time


class BarberIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: Phone = ""
    bio: Text(200) = ""
    active: bool = True
    service_ids: list[Id] = Field([], max_length=200)
    working_hours: list[WorkingHourIO] = Field([], max_length=50)


class BarberOut(ORM):
    id: int
    name: str
    phone: str
    bio: str
    active: bool
    service_ids: list[int]
    working_hours: list[WorkingHourIO]


# ---- blocks
class BlockIn(BaseModel):
    barber_id: Id | None = None
    start: datetime
    end: datetime
    reason: Text(120) = ""


class BlockOut(ORM):
    id: int
    barber_id: int | None
    start: datetime
    end: datetime
    reason: str


# ---- customers
class CustomerIn(BaseModel):
    name: Text(120) | None = None
    notes: Note | None = None


ACCESS_STATUS = "^(normal|approval|blocked)$"


class CustomerOut(ORM):
    id: int
    name: str
    phone: str
    notes: str
    access_status: str
    access_reason: str
    access_changed_at: datetime | None
    created_at: datetime


class CustomerDetail(CustomerOut):
    visits: int
    no_shows: int
    total_spent: Decimal
    future_appointments: int  # agendamentos futuros ativos (inclui pedidos aguardando aprovação)
    appointments: list["AppointmentOut"]


class CustomerAccessIn(BaseModel):
    access_status: str = Field(pattern=ACCESS_STATUS)
    access_reason: str = Field("", max_length=1000)
    cancel_future: bool = False      # ao bloquear: cancela os agendamentos futuros
    notify_customer: bool = False    # ...e avisa o cliente (mensagem neutra)


class CustomerAccessOut(BaseModel):
    customer: CustomerOut
    cancelled: int


# ---- clientes que não podem se encontrar
class ConflictIn(BaseModel):
    customer_id: Id
    other_customer_id: Id
    min_gap_minutes: int | None = Field(None, ge=0, le=1440)  # nulo = padrão da barbearia
    same_day_block: bool = False
    conflict_action: str = Field("block", pattern=CONFLICT_ACTION)
    notes: str = Field("", max_length=1000)


class ConflictUpdate(BaseModel):
    min_gap_minutes: int | None = Field(None, ge=0, le=1440)
    same_day_block: bool = False
    conflict_action: str = Field("block", pattern=CONFLICT_ACTION)
    notes: str = Field("", max_length=1000)


class ConflictOut(BaseModel):
    id: int
    customer_a_id: int
    customer_a_name: str
    customer_b_id: int
    customer_b_name: str
    # Preenchidos quando a listagem é de um cliente: o "outro" do par
    other_customer_id: int | None = None
    other_customer_name: str | None = None
    other_customer_phone: str | None = None
    min_gap_minutes: int | None
    effective_gap_minutes: int  # o que vale de fato (padrão da barbearia quando min_gap_minutes é nulo)
    same_day_block: bool
    conflict_action: str = "block"  # block: esconde o horário; approval: o pedido fica aguardando aprovação
    notes: str
    created_at: datetime


class ConflictHitOut(BaseModel):
    """Agendamento de um cliente em conflito (só para o dono)."""
    conflict_id: int
    other_customer_id: int
    other_customer_name: str
    appointment_id: int
    start: datetime
    end: datetime
    barber_name: str
    gap_minutes: int
    same_day_block: bool
    conflict_action: str = "block"


# ---- appointments
class AppointmentIn(BaseModel):
    customer_phone: Phone
    customer_name: Text(120) = ""
    barber_id: Id
    service_id: Id
    start: datetime
    notes: Note = ""
    force: bool = False  # agenda mesmo com conflito entre clientes


PAY_METHOD = "^(pix|dinheiro|debito|credito)$"


class AppointmentPatch(BaseModel):
    status: str | None = Field(None, pattern="^(scheduled|confirmed|completed|cancelled|no_show)$")
    notes: Note | None = None
    payment_method: str | None = Field(None, pattern=PAY_METHOD)
    price: Money | None = None  # valor final cobrado (desconto ou acréscimo)
    notify_customer: bool = True


class RescheduleIn(BaseModel):
    start: datetime
    barber_id: Id | None = None
    notify_customer: bool = True
    force: bool = False


class AppointmentOut(ORM):
    id: int
    start: datetime
    end: datetime
    status: str
    payment_status: str
    payment_method: str | None = None
    price: Decimal
    notes: str
    created_via: str
    customer_id: int
    customer_name: str
    customer_phone: str
    barber_id: int
    barber_name: str
    service_id: int
    service_name: str
    rating: int | None = None
    customer_access_status: str = "normal"
    approval_deadline: datetime | None = None  # só em pending_approval
    payment_id: int | None = None  # Pix gerado para o atendimento (para confirmar direto do card)
    customer_reported_paid: bool = False  # o cliente disse que pagou o Pix


# ---- payments / reviews
class PaymentOut(ORM):
    id: int
    appointment_id: int
    amount: Decimal
    status: str
    brcode: str
    created_at: datetime
    customer_reported_at: datetime | None
    confirmed_at: datetime | None
    customer_name: str
    appointment_start: datetime
    customer_phone: str = ""
    service_name: str = ""
    barber_name: str = ""
    has_receipt: bool = False
    receipt_mime: str | None = None
    receipt_at: datetime | None = None


class ReviewOut(ORM):
    id: int
    rating: int
    comment: str
    created_at: datetime
    customer_name: str
    barber_name: str
    service_name: str
    appointment_start: datetime


class ReportOut(BaseModel):
    date_from: date
    date_to: date
    appointments: int
    completed: int
    cancelled: int
    no_shows: int
    revenue_expected: Decimal
    revenue_completed: Decimal
    paid_pix: Decimal
    avg_rating: float | None
    by_barber: list[dict]
    by_service: list[dict]


# ---- comissões e repasses
class CommissionRuleIn(BaseModel):
    barber_id: Id
    beneficiary_type: str = Field(pattern="^(shop|barber)$")
    beneficiary_barber_id: Id | None = None
    percentage: Decimal = Field(gt=0, le=100, decimal_places=2)
    service_id: Id | None = None
    valid_from: date
    valid_to: date | None = None
    notes: Note = ""


class CommissionRuleOut(ORM):
    id: int
    barber_id: int
    barber_name: str
    beneficiary_type: str
    beneficiary_barber_id: int | None
    beneficiary_name: str
    percentage: Decimal
    service_id: int | None
    service_name: str | None
    valid_from: date
    valid_to: date | None
    notes: str


class CommissionDueOut(BaseModel):
    beneficiary_type: str
    beneficiary_barber_id: int | None
    beneficiary_name: str
    percentages: list[Decimal]  # mais de uma quando a regra muda no período ou há regra por serviço
    base: Decimal               # faturamento sobre o qual o repasse incidiu
    amount: Decimal
    settled: Decimal
    open: Decimal


class BarberCommissionOut(BaseModel):
    barber_id: int
    barber_name: str
    gross: Decimal
    appointments: int
    dues: list[CommissionDueOut]
    total_due: Decimal
    net: Decimal       # faturamento bruto menos os repasses
    received: Decimal  # repasses que recebe de outros barbeiros (padrinho)
    settled: Decimal
    open: Decimal


class CommissionReportOut(BaseModel):
    date_from: date
    date_to: date
    barbers: list[BarberCommissionOut]
    total_gross: Decimal
    total_due: Decimal
    total_open: Decimal


class SettlementIn(BaseModel):
    payer_barber_id: Id
    beneficiary_type: str = Field(pattern="^(shop|barber)$")
    beneficiary_barber_id: Id | None = None
    period_start: date
    period_end: date
    amount: PositiveMoney
    paid_at: datetime | None = None
    notes: Note = ""
    notify: bool = True


class SettlementOut(ORM):
    id: int
    payer_barber_id: int
    payer_name: str
    beneficiary_type: str
    beneficiary_barber_id: int | None
    beneficiary_name: str
    period_start: date
    period_end: date
    amount: Decimal
    paid_at: datetime
    notes: str


# ---- agenda do mês
class MonthDayOut(BaseModel):
    date: date
    total: int              # atendimentos não cancelados
    cancelled: int
    revenue_expected: Decimal
    capacity: float         # quantos atendimentos cabem no dia (expediente livre / duração média)
    occupancy: float        # 0 a 1
    working: bool           # algum barbeiro tem expediente neste dia da semana
    has_block: bool


class MonthOut(BaseModel):
    year: int
    month: int
    days: list[MonthDayOut]


# ---- gastos
EXPENSE_CATEGORY = "^(aluguel|energia|agua|internet|produtos|equipamentos|manutencao|marketing|salarios|impostos|outros)$"


class ExpenseIn(BaseModel):
    description: str = Field(min_length=1, max_length=120)
    category: str = Field("outros", pattern=EXPENSE_CATEGORY)
    amount: PositiveMoney
    due_date: date
    paid_at: date | None = None
    payment_method: str | None = Field(None, pattern=PAY_METHOD)
    barber_id: Id | None = None
    recurring: bool = False
    notes: Note = ""


class ExpensePayIn(BaseModel):
    paid_at: date | None = None  # padrão: hoje
    payment_method: str | None = Field(None, pattern=PAY_METHOD)


class ExpenseOut(BaseModel):
    id: int
    description: str
    category: str
    category_label: str
    amount: Decimal
    due_date: date
    paid_at: date | None
    payment_method: str | None
    barber_id: int | None
    barber_name: str | None
    recurring: bool
    recurring_source_id: int | None
    notes: str
    overdue: bool


# ---- relatórios financeiros
class FinanceGroupOut(BaseModel):
    id: int | None = None
    name: str
    appointments: int
    revenue: Decimal


class PaymentMethodGroupOut(BaseModel):
    method: str
    label: str
    appointments: int
    revenue: Decimal


class ExpenseCategoryGroupOut(BaseModel):
    category: str
    label: str
    paid: Decimal
    open: Decimal


class FinanceTotalsOut(BaseModel):
    date_from: date
    date_to: date
    revenue: Decimal
    expenses_paid: Decimal
    profit: Decimal
    avg_ticket: Decimal
    appointments: int


class FinanceChangeOut(BaseModel):
    """Variação em % contra o período anterior de mesmo tamanho (nulo quando o anterior é zero)."""
    revenue: Decimal | None
    expenses_paid: Decimal | None
    profit: Decimal | None
    avg_ticket: Decimal | None
    appointments: Decimal | None


class FinanceSummaryOut(FinanceTotalsOut):
    expenses_open: Decimal
    by_barber: list[FinanceGroupOut]
    by_service: list[FinanceGroupOut]
    by_payment_method: list[PaymentMethodGroupOut]
    expenses_by_category: list[ExpenseCategoryGroupOut]
    previous: FinanceTotalsOut
    change: FinanceChangeOut


class FinanceDayOut(BaseModel):
    date: date
    revenue: Decimal
    expenses: Decimal
    appointments: int


CustomerDetail.model_rebuild()


# ---- whatsapp
class PairingCodeIn(BaseModel):
    number: Phone


# ---- agenda do dia
class Interval(BaseModel):
    start: datetime
    end: datetime


class AgendaBlock(BaseModel):
    id: int
    start: datetime
    end: datetime
    reason: str
    whole_shop: bool  # bloqueio da barbearia inteira (vale para todos os profissionais)


class AgendaBarber(BaseModel):
    id: int
    name: str
    working: list[Interval]
    blocks: list[AgendaBlock]
    appointments: list["AppointmentOut"]
    free: list[Interval]  # expediente menos bloqueios e agendamentos (a partir de agora, se for hoje)


class AgendaDayOut(BaseModel):
    day: date
    now: datetime
    slot_step_minutes: int
    barbers: list[AgendaBarber]
