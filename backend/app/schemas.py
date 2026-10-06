from datetime import date, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(BaseModel):
    setup_token: str
    shop_name: str
    owner_name: str
    email: EmailStr
    password: str = Field(min_length=6)
    owner_phone: str = ""


class TokenOut(BaseModel):
    token: str
    user_name: str
    shop_name: str


# ---- shop
class ShopIn(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    owner_phone: str | None = None
    instagram: str | None = None
    pix_enabled: bool | None = None
    pix_key: str | None = None
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
    welcome_text: str | None = None
    human_pause_hours: int | None = Field(None, ge=1, le=48)


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
    evolution_instance: str


# ---- services
class ServiceIn(BaseModel):
    name: str
    duration_minutes: int = Field(ge=5, le=480)
    price: Decimal = Field(ge=0)
    active: bool = True
    sort_order: int = 0


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
    name: str
    phone: str = ""
    bio: str = ""
    active: bool = True
    service_ids: list[int] = []
    working_hours: list[WorkingHourIO] = []


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
    barber_id: int | None = None
    start: datetime
    end: datetime
    reason: str = ""


class BlockOut(ORM):
    id: int
    barber_id: int | None
    start: datetime
    end: datetime
    reason: str


# ---- customers
class CustomerIn(BaseModel):
    name: str | None = None
    notes: str | None = None


class CustomerOut(ORM):
    id: int
    name: str
    phone: str
    notes: str
    created_at: datetime


class CustomerDetail(CustomerOut):
    visits: int
    no_shows: int
    total_spent: Decimal
    appointments: list["AppointmentOut"]


# ---- appointments
class AppointmentIn(BaseModel):
    customer_phone: str
    customer_name: str = ""
    barber_id: int
    service_id: int
    start: datetime
    notes: str = ""


PAY_METHOD = "^(pix|dinheiro|debito|credito)$"


class AppointmentPatch(BaseModel):
    status: str | None = Field(None, pattern="^(scheduled|confirmed|completed|cancelled|no_show)$")
    notes: str | None = None
    payment_method: str | None = Field(None, pattern=PAY_METHOD)
    price: Decimal | None = Field(None, ge=0, decimal_places=2)  # valor final cobrado (desconto ou acréscimo)
    notify_customer: bool = True


class RescheduleIn(BaseModel):
    start: datetime
    barber_id: int | None = None
    notify_customer: bool = True


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
    barber_id: int
    beneficiary_type: str = Field(pattern="^(shop|barber)$")
    beneficiary_barber_id: int | None = None
    percentage: Decimal = Field(gt=0, le=100, decimal_places=2)
    service_id: int | None = None
    valid_from: date
    valid_to: date | None = None
    notes: str = ""


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
    payer_barber_id: int
    beneficiary_type: str = Field(pattern="^(shop|barber)$")
    beneficiary_barber_id: int | None = None
    period_start: date
    period_end: date
    amount: Decimal = Field(gt=0, decimal_places=2)
    paid_at: datetime | None = None
    notes: str = ""
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
    amount: Decimal = Field(gt=0, decimal_places=2)
    due_date: date
    paid_at: date | None = None
    payment_method: str | None = Field(None, pattern=PAY_METHOD)
    barber_id: int | None = None
    recurring: bool = False
    notes: str = ""


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
