"""Sincronização com o app offline.

PULL (GET /api/sync/pull?cursor=N): devolve, por entidade, o que mudou depois do cursor (sync_seq da loja), com
paginação, filtrado pelo papel do usuário e só da loja dele. Exclusões vêm em "deleted" (tombstones).

PUSH (POST /api/sync/push): operações em ordem, cada uma com operation_id único. Reenviar a mesma operação devolve o
mesmo resultado (idempotente). Resultado por operação: aplicado | rejeitado (motivo) | conflito (versão do servidor).

Regras de conflito:
- agendamento criado ou remarcado offline é validado como novo; horário ocupado = conflito (nada é gravado);
- lançamentos de comanda, pagamentos e movimentos de estoque só acrescentam: nunca conflitam;
- edição de cadastro com versão antiga: campos diferentes = merge campo a campo; mesmo campo = conflito;
- mensagens de WhatsApp só saem quando a operação foi aplicada e gravada.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import now_local
from ..models import (
    Appointment, ApptStatus, Barber, Block, Comanda, ComandaItem, ComandaPayment, Customer, CustomerPackage,
    PackagePlan, PackageUse, Product, Role, Service, Shop, StockMovement, StockReason, Subscription,
    SubscriptionPlan, SubscriptionUse, SyncOperation, User, WaitlistEntry,
)
from ..permissions import is_pro, own_barber_id, served_by
from . import whatsapp as wa

APPLIED, REJECTED, CONFLICT = "aplicado", "rejeitado", "conflito"
PAGE = 500
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
WINDOW_BACK, WINDOW_AHEAD = 30, 60  # dias da agenda que vão para o aparelho


def _u(obj) -> str | None:
    return obj.uuid if obj is not None else None


def _iso(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def _base(o) -> dict:
    return {"id": o.uuid, "server_id": o.id, "version": o.version, "updated_at": _iso(o.updated_at)}


# ---------------------------------------------------------------- serialização (o que vai para o aparelho)

def _service(o: Service, user: User) -> dict:
    return {**_base(o), "name": o.name, "duration_minutes": o.duration_minutes, "price": _iso(o.price),
            "active": o.active, "sort_order": o.sort_order}


def _barber(o: Barber, user: User) -> dict:
    return {**_base(o), "name": o.name, "active": o.active, "service_ids": [s.uuid for s in o.services],
            "working_hours": [{"weekday": w.weekday, "start": _iso(w.start), "end": _iso(w.end)}
                              for w in o.working_hours]}


def _block(o: Block, user: User) -> dict:
    return {**_base(o), "barber_id": _u(o.barber), "start": _iso(o.start), "end": _iso(o.end),
            "reason": o.reason if not is_pro(user) or o.barber_id == user.barber_id else ""}


def _customer(o: Customer, user: User) -> dict:
    out = {**_base(o), "name": o.name, "phone": o.phone, "notes": o.notes}
    if not is_pro(user):
        out["access_status"] = o.access_status
    return out


def _appointment(o: Appointment, user: User) -> dict:
    return {**_base(o), "customer_id": o.customer.uuid, "barber_id": o.barber.uuid, "service_id": o.service.uuid,
            "start": _iso(o.start), "end": _iso(o.end), "status": o.status, "price": _iso(o.price),
            "notes": o.notes, "payment_status": o.payment_status, "payment_method": o.payment_method,
            "checked_in_at": _iso(o.checked_in_at), "deposit_status": o.deposit_status,
            "deposit_amount": _iso(o.deposit_amount), "paid_with": "package" if o.customer_package_id
            else "subscription" if o.subscription_id else None}


def _product(o: Product, user: User) -> dict:
    out = {**_base(o), "name": o.name, "kind": o.kind, "unit": o.unit, "price": _iso(o.price),
           "min_stock": _iso(o.min_stock), "active": o.active}
    if user.role == Role.OWNER:
        out["cost"] = _iso(o.cost)
    return out


def _movement(o: StockMovement, user: User) -> dict:
    return {**_base(o), "product_id": o.product.uuid, "delta": _iso(o.delta), "reason": o.reason,
            "created_at": _iso(o.created_at)}


def _package_plan(o: PackagePlan, user: User) -> dict:
    return {**_base(o), "name": o.name, "service_id": o.service.uuid, "sessions": o.sessions,
            "price": _iso(o.price), "validity_days": o.validity_days, "active": o.active}


def _customer_package(o: CustomerPackage, user: User) -> dict:
    return {**_base(o), "customer_id": o.customer.uuid, "service_id": o.service.uuid, "name": o.name,
            "sessions": o.sessions, "session_value": _iso(o.session_value), "status": o.status,
            "expires_at": _iso(o.expires_at)}


def _package_use(o: PackageUse, user: User) -> dict:
    cp = o.__dict__.get("_cp")
    return {**_base(o), "customer_package_id": cp.uuid if cp else None, "delta": o.delta,
            "created_at": _iso(o.created_at)}


def _sub_plan(o: SubscriptionPlan, user: User) -> dict:
    return {**_base(o), "name": o.name, "price": _iso(o.price), "block_after_days": o.block_after_days,
            "active": o.active, "items": [{"service_id": i.service.uuid, "limit_per_period": i.limit_per_period}
                                          for i in o.items]}


def _subscription(o: Subscription, user: User) -> dict:
    return {**_base(o), "customer_id": o.customer.uuid, "plan_id": o.plan.uuid, "price": _iso(o.price),
            "status": o.status, "started_at": _iso(o.started_at), "next_due_date": _iso(o.next_due_date)}


def _sub_use(o: SubscriptionUse, user: User) -> dict:
    return {**_base(o), "subscription_id": o.__dict__["_sub"].uuid if o.__dict__.get("_sub") else None,
            "service_id": o.__dict__["_svc"].uuid if o.__dict__.get("_svc") else None,
            "period_start": _iso(o.period_start), "delta": o.delta}


def _comanda(o: Comanda, user: User) -> dict:
    return {**_base(o), "customer_id": _u(o.customer), "appointment_id": _u(o.appointment), "status": o.status,
            "opened_at": _iso(o.opened_at), "closed_at": _iso(o.closed_at), "notes": o.notes}


def _comanda_item(o: ComandaItem, user: User) -> dict:
    return {**_base(o), "comanda_id": o.comanda.uuid, "kind": o.kind, "description": o.description,
            "service_id": _u(o.service), "product_id": _u(o.product), "barber_id": _u(o.barber),
            "quantity": o.quantity, "unit_price": _iso(o.unit_price), "amount": _iso(o.amount),
            "covered_by": o.covered_by, "reverses_id": o.__dict__["_rev"] if "_rev" in o.__dict__ else None,
            "created_at": _iso(o.created_at)}


def _comanda_payment(o: ComandaPayment, user: User) -> dict:
    return {**_base(o), "comanda_id": o.comanda.uuid, "method": o.method, "amount": _iso(o.amount),
            "from_deposit": o.from_deposit, "reverses_id": o.__dict__.get("_rev"), "created_at": _iso(o.created_at)}


def _waitlist(o: WaitlistEntry, user: User) -> dict:
    return {**_base(o), "customer_id": o.customer.uuid, "service_id": o.service.uuid, "barber_id": _u(o.barber),
            "day": _iso(o.day), "after_time": _iso(o.after_time), "before_time": _iso(o.before_time),
            "status": o.status, "offer_expires_at": _iso(o.offer_expires_at)}


@dataclass
class Entity:
    model: type
    serialize: Callable
    roles: tuple[str, ...] = Role.ALL
    scope: Callable | None = None  # (query, user, today) -> query: filtro de papel e janela de dados


def _appt_scope(q, user: User, today: date):
    start = datetime.combine(today - timedelta(days=WINDOW_BACK), time())
    end = datetime.combine(today + timedelta(days=WINDOW_AHEAD + 1), time())
    q = q.where(Appointment.start >= start, Appointment.start < end)
    if is_pro(user):
        q = q.where(Appointment.barber_id == own_barber_id(user))
    return q


def _customer_scope(q, user: User, today: date):
    return q.where(served_by(own_barber_id(user))) if is_pro(user) else q


def _block_scope(q, user: User, today: date):
    q = q.where(Block.end >= datetime.combine(today - timedelta(days=WINDOW_BACK), time()))
    if is_pro(user):
        q = q.where(or_(Block.barber_id == own_barber_id(user), Block.barber_id.is_(None)))
    return q


def _comanda_scope(q, user: User, today: date):
    return q.where(Comanda.opened_at >= datetime.combine(today - timedelta(days=WINDOW_BACK), time()))


def _child_of_comanda(model):
    def scope(q, user: User, today: date):
        recent = select(Comanda.id).where(Comanda.opened_at >= datetime.combine(today - timedelta(days=WINDOW_BACK),
                                                                                time()))
        return q.where(model.comanda_id.in_(recent))
    return scope


STAFF = Role.STAFF
ENTITIES: dict[str, Entity] = {
    "services": Entity(Service, _service),
    "barbers": Entity(Barber, _barber),
    "blocks": Entity(Block, _block, scope=_block_scope),
    "customers": Entity(Customer, _customer, scope=_customer_scope),
    "appointments": Entity(Appointment, _appointment, scope=_appt_scope),
    "products": Entity(Product, _product, STAFF),
    "stock_movements": Entity(StockMovement, _movement, STAFF),
    "package_plans": Entity(PackagePlan, _package_plan, STAFF),
    "customer_packages": Entity(CustomerPackage, _customer_package, STAFF),
    "package_uses": Entity(PackageUse, _package_use, STAFF),
    "subscription_plans": Entity(SubscriptionPlan, _sub_plan, STAFF),
    "subscriptions": Entity(Subscription, _subscription, STAFF),
    "subscription_uses": Entity(SubscriptionUse, _sub_use, STAFF),
    "comandas": Entity(Comanda, _comanda, STAFF, _comanda_scope),
    "comanda_items": Entity(ComandaItem, _comanda_item, STAFF, _child_of_comanda(ComandaItem)),
    "comanda_payments": Entity(ComandaPayment, _comanda_payment, STAFF, _child_of_comanda(ComandaPayment)),
    "waitlist_entries": Entity(WaitlistEntry, _waitlist, STAFF),
}


def _attach_refs(db: Session, name: str, rows: list) -> None:
    """Uuids de referências sem relationship no modelo (evita uma consulta por linha)."""
    if name == "package_uses":
        ids = {r.customer_package_id for r in rows}
        cps = {c.id: c for c in db.scalars(select(CustomerPackage).where(CustomerPackage.id.in_(ids))
                                           .execution_options(include_deleted=True))}
        for r in rows:
            r.__dict__["_cp"] = cps.get(r.customer_package_id)
    elif name == "subscription_uses":
        subs = {s.id: s for s in db.scalars(select(Subscription).where(
            Subscription.id.in_({r.subscription_id for r in rows})).execution_options(include_deleted=True))}
        svcs = {s.id: s for s in db.scalars(select(Service).where(
            Service.id.in_({r.service_id for r in rows})).execution_options(include_deleted=True))}
        for r in rows:
            r.__dict__["_sub"], r.__dict__["_svc"] = subs.get(r.subscription_id), svcs.get(r.service_id)
    elif name in ("comanda_items", "comanda_payments"):
        model = ComandaItem if name == "comanda_items" else ComandaPayment
        ids = {r.reverses_id for r in rows if r.reverses_id}
        uuids = dict(db.execute(select(model.id, model.uuid).where(model.id.in_(ids))).all()) if ids else {}
        for r in rows:
            r.__dict__["_rev"] = uuids.get(r.reverses_id)


# ---------------------------------------------------------------- pull

def pull(db: Session, user: User, cursor: int, limit: int = PAGE) -> dict:
    shop = user.shop
    db.expire(shop, ["sync_seq"])
    top = shop.sync_seq or 0  # tudo até aqui já foi confirmado (ver app/sync_events.py)
    today = now_local().date()
    fetched: dict[str, list] = {}
    removed_other: list[str] = []
    horizon = top
    for name, ent in ENTITIES.items():
        if user.role not in ent.roles:
            continue
        m = ent.model
        q = select(m).where(m.shop_id == shop.id, m.sync_seq > cursor, m.sync_seq <= top)
        if ent.scope:
            q = ent.scope(q, user, today)
        rows = list(db.scalars(q.order_by(m.sync_seq).limit(limit + 1).execution_options(include_deleted=True)))
        if len(rows) > limit:
            rows = rows[:limit]
            horizon = min(horizon, rows[-1].sync_seq)
        fetched[name] = rows
    if is_pro(user):
        # Agendamento que saiu da agenda do profissional (trocou de profissional): some do aparelho dele
        removed_other = list(db.scalars(select(Appointment.uuid).where(
            Appointment.shop_id == shop.id, Appointment.sync_seq > cursor, Appointment.sync_seq <= horizon,
            Appointment.barber_id != own_barber_id(user)).execution_options(include_deleted=True)))
    changes: dict[str, list] = {}
    deleted: dict[str, list] = {}
    for name, rows in fetched.items():
        rows = [r for r in rows if r.sync_seq <= horizon]
        _attach_refs(db, name, rows)
        live = [r for r in rows if r.deleted_at is None]
        if live:
            changes[name] = [ENTITIES[name].serialize(r, user) for r in live]
        gone = [r.uuid for r in rows if r.deleted_at is not None]
        if gone:
            deleted[name] = gone
    if removed_other:
        deleted.setdefault("appointments", []).extend(removed_other)
    return {"cursor": str(horizon), "has_more": horizon < top, "server_time": _iso(now_local()),
            "changes": changes, "deleted": deleted}


# ---------------------------------------------------------------- push

class Reject(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class Conflict(Exception):
    def __init__(self, reason: str, message: str, server: dict | None = None, fields: list[str] | None = None):
        super().__init__(message)
        self.reason, self.message, self.server, self.fields = reason, message, server, fields or []


def _uuid(v, field: str = "id") -> str:
    if not isinstance(v, str) or not UUID_RE.match(v):
        raise Reject("dados_invalidos", f"{field} precisa ser um UUID.")
    return v.lower()


def _by_uuid(db: Session, shop: Shop, model, v, field: str, required: bool = True):
    if v in (None, "") and not required:
        return None
    obj = db.scalar(select(model).where(model.uuid == _uuid(v, field)))
    if obj is None or obj.shop_id != shop.id:
        raise Reject("nao_encontrado", f"{field}: registro não encontrado.")
    return obj


def _dt(v, field: str) -> datetime:
    try:
        return datetime.fromisoformat(str(v)).replace(tzinfo=None, second=0, microsecond=0)
    except ValueError:
        raise Reject("dados_invalidos", f"{field} inválido.")


def _money(v, field: str) -> Decimal:
    try:
        d = Decimal(str(v)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise Reject("dados_invalidos", f"{field} inválido.")
    if not Decimal(0) < d <= Decimal("99999999.99"):
        raise Reject("dados_invalidos", f"{field} inválido.")
    return d


def _text(v, n: int) -> str:
    return str(v or "")[:n]


def _need(user: User, roles: tuple[str, ...]) -> None:
    if user.role not in roles:
        raise Reject("sem_permissao", "Seu perfil não tem acesso a esta função.")


def _new_id(db: Session, model, op) -> str:
    uid = _uuid(op.id)
    if db.scalar(select(model.id).where(model.uuid == uid).execution_options(include_deleted=True)):
        raise Reject("id_em_uso", "Esse id já existe.")
    return uid


def _merge(obj, op, fields: tuple[str, ...], serialize) -> list[str]:
    """Edição de cadastro. Versão igual: aplica. Versão antiga: aplica os campos que o servidor não mudou desde a
    versão do app (base); campo mudado dos dois lados com valores diferentes = conflito (nada é aplicado)."""
    changes = {k: v for k, v in op.data.items() if k in fields}
    if not changes:
        raise Reject("dados_invalidos", "Nada para alterar.")
    if op.version is not None and op.version < obj.version:
        clash = [k for k, v in changes.items()
                 if k not in op.base or (getattr(obj, k) != op.base[k] and getattr(obj, k) != v)]
        if clash:
            raise Conflict("campo_alterado", "Outra pessoa alterou o mesmo campo.", serialize(obj), clash)
    for k, v in changes.items():
        setattr(obj, k, v)
    return list(changes)


# -------- agendamentos

def _appt_create(db: Session, user: User, op) -> Appointment:
    from ..api.admin import notify_new_appointment
    from . import scheduling as sch
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, Appointment, op)
    d = op.data
    barber = _by_uuid(db, shop, Barber, d.get("barber_id"), "barber_id")
    service = _by_uuid(db, shop, Service, d.get("service_id"), "service_id")
    if d.get("customer_id"):
        customer = _by_uuid(db, shop, Customer, d["customer_id"], "customer_id")
    else:
        phone = wa.normalize_phone(_text(d.get("customer_phone"), 30))
        if not 12 <= len(phone) <= 15:
            raise Reject("dados_invalidos", "Telefone inválido.")
        customer = sch.get_or_create_customer(db, shop, phone, _text(d.get("customer_name"), 120).strip().title())
    start = _dt(d.get("start"), "start")
    try:
        a = sch.create_appointment(db, shop, customer, barber, service, start, created_via="app",
                                   notes=_text(d.get("notes"), 2000), force=bool(d.get("force")))
    except sch.ConflictError:
        raise Conflict("cliente_em_conflito", "Esse horário fica perto de um cliente que não pode encontrar este.")
    except sch.SchedulingError:
        raise Conflict("horario_ocupado", "Esse horário foi ocupado enquanto você estava sem internet.")
    a.uuid = uid
    db.flush()
    notify_new_appointment(db, shop, a, use_balance=d.get("use_balance", True) is not False)
    return a


APPT_STATUS = {"confirmed", "completed", "cancelled", "no_show", "scheduled"}


def _appt_update(db: Session, user: User, op) -> Appointment:
    from ..api.admin import apply_patch
    from .. import schemas as S
    from . import scheduling as sch
    shop = user.shop
    a = _by_uuid(db, shop, Appointment, op.id, "id")
    d = op.data
    if is_pro(user):
        if a.barber_id != own_barber_id(user):
            raise Reject("nao_encontrado", "id: registro não encontrado.")
        if set(d) - {"status", "notes"} or d.get("status") not in (None, "confirmed", "completed", "no_show"):
            raise Reject("sem_permissao", "Seu perfil não tem acesso a esta função.")
    if "start" in d or "barber_id" in d:
        _need(user, Role.STAFF)
        if a.status not in ApptStatus.OCCUPYING:
            raise Conflict("status_alterado", "Esse agendamento já foi cancelado ou concluído.", _appointment(a, user))
        barber = _by_uuid(db, shop, Barber, d["barber_id"], "barber_id") if d.get("barber_id") else None
        try:  # remarcação offline: validada como um agendamento novo
            sch.reschedule_appointment(db, shop, a, _dt(d.get("start", a.start.isoformat()), "start"), barber,
                                       force=bool(d.get("force")))
        except sch.SchedulingError:
            raise Conflict("horario_ocupado", "Esse horário foi ocupado enquanto você estava sem internet.",
                           _appointment(a, user))
        if d.get("notify_customer", True):
            from .fmt import appt_summary
            wa.send_text(db, shop, a.customer.phone, f"🔁 Seu horário na *{shop.name}* foi remarcado:\n\n"
                                                     f"{appt_summary(a)}")
    status = d.get("status")
    if status is not None:
        if status not in APPT_STATUS:
            raise Reject("dados_invalidos", "Status inválido.")
        base = op.base.get("status")
        if op.version is not None and op.version < a.version and base is not None and a.status != base \
                and a.status != status:
            raise Conflict("status_alterado", "O status desse agendamento mudou no servidor.", _appointment(a, user),
                           ["status"])
        if a.status in (ApptStatus.CANCELLED,) and status != ApptStatus.CANCELLED:
            raise Conflict("status_alterado", "Esse agendamento já foi cancelado.", _appointment(a, user), ["status"])
    if status is not None or "notes" in d:
        if "notes" in d and op.version is not None and op.version < a.version and \
                op.base.get("notes", a.notes) != a.notes and a.notes != d["notes"]:
            raise Conflict("campo_alterado", "Outra pessoa alterou a observação.", _appointment(a, user), ["notes"])
        try:
            body = S.AppointmentPatch(status=status if status != a.status else None, notes=d.get("notes"),
                                      notify_customer=d.get("notify_customer", True))
        except ValueError:
            raise Reject("dados_invalidos", "Dados inválidos.")
        apply_patch(db, shop, a, body)
    return a


# -------- clientes

def _customer_create(db: Session, user: User, op) -> Customer:
    from . import scheduling as sch
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _uuid(op.id)
    phone = wa.normalize_phone(_text(op.data.get("phone"), 30))
    if not 12 <= len(phone) <= 15:
        raise Reject("dados_invalidos", "Telefone inválido.")
    existing = db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone))
    if existing:  # o mesmo telefone já existe: o cadastro do servidor vale (o app troca o id local)
        raise Conflict("cliente_ja_existe", "Já existe um cliente com esse telefone.", _customer(existing, user))
    _new_id(db, Customer, op)
    c = sch.get_or_create_customer(db, shop, phone, _text(op.data.get("name"), 120).strip())
    c.uuid, c.notes = uid, _text(op.data.get("notes"), 2000)
    return c


def _customer_update(db: Session, user: User, op) -> Customer:
    _need(user, Role.STAFF)
    c = _by_uuid(db, user.shop, Customer, op.id, "id")
    for k in ("name", "notes"):
        if k in op.data:
            op.data[k] = _text(op.data[k], 120 if k == "name" else 2000)
    _merge(c, op, ("name", "notes"), lambda o: _customer(o, user))
    return c


# -------- comandas (só acrescentam: não conflitam)

def _comanda_create(db: Session, user: User, op) -> Comanda:
    from . import comandas as cs
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, Comanda, op)
    appt = _by_uuid(db, shop, Appointment, op.data.get("appointment_id"), "appointment_id", required=False)
    customer = _by_uuid(db, shop, Customer, op.data.get("customer_id"), "customer_id", required=False)
    if appt is not None:
        existing = db.scalar(select(Comanda).where(Comanda.appointment_id == appt.id))
        if existing:  # outra pessoa abriu a comanda deste atendimento: o app passa a usar a do servidor
            raise Conflict("comanda_ja_aberta", "A comanda desse atendimento já foi aberta.",
                           _comanda(existing, user))
    try:
        return cs.open_comanda(db, shop, user, customer=customer, appointment=appt, uuid=uid)
    except cs.ComandaError as e:
        raise Reject("regra", str(e))


def _comanda_action(db: Session, user: User, op) -> Comanda:
    from . import comandas as cs
    _need(user, Role.STAFF)
    c = _by_uuid(db, user.shop, Comanda, op.id, "id")
    try:
        (cs.close if op.action == "close" else cs.cancel)(db, user.shop, user, c)
    except cs.ComandaError as e:
        raise Reject("regra", str(e))
    return c


def _item_create(db: Session, user: User, op) -> ComandaItem:
    from .. import schemas as S
    from ..api.sales import add_item
    from . import comandas as cs
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, ComandaItem, op)
    d = dict(op.data)
    c = _by_uuid(db, shop, Comanda, d.pop("comanda_id", None), "comanda_id")
    ids = {}
    for field, model in (("service_id", Service), ("product_id", Product), ("package_plan_id", PackagePlan),
                         ("barber_id", Barber)):
        obj = _by_uuid(db, shop, model, d.get(field), field, required=False)
        ids[field] = obj.id if obj else None
    try:
        fields = {k: v for k, v in d.items() if k in S.ComandaItemIn.model_fields}
        # venda feita offline já aconteceu no balcão: entra mesmo que o estoque fique negativo
        body = S.ComandaItemIn(**{**fields, **ids, "allow_negative_stock": True})
        return add_item(db, shop, user, c, body, uuid=uid)
    except cs.ComandaError as e:
        raise Reject("regra", str(e))
    except ValueError:
        raise Reject("dados_invalidos", "Dados inválidos.")


def _item_reverse(db: Session, user: User, op) -> ComandaItem:
    from . import comandas as cs
    _need(user, Role.STAFF)
    item = _by_uuid(db, user.shop, ComandaItem, op.id, "id")
    if item.comanda.status == "closed" and user.role != Role.OWNER:
        raise Reject("sem_permissao", "Estorno em comanda fechada: só o dono.")
    rid = _uuid(op.data.get("reversal_id"), "reversal_id")
    try:
        return cs.reverse_item(db, user.shop, user, item, uuid=rid)
    except cs.ComandaError as e:
        raise Reject("regra", str(e))


def _payment_create(db: Session, user: User, op) -> ComandaPayment:
    from . import comandas as cs
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, ComandaPayment, op)
    c = _by_uuid(db, shop, Comanda, op.data.get("comanda_id"), "comanda_id")
    try:
        return cs.add_payment(db, shop, user, c, str(op.data.get("method", "")),
                              _money(op.data.get("amount"), "amount"), uuid=uid)
    except cs.ComandaError as e:
        raise Reject("regra", str(e))


def _payment_reverse(db: Session, user: User, op) -> ComandaPayment:
    from . import comandas as cs
    _need(user, Role.STAFF)
    pay = _by_uuid(db, user.shop, ComandaPayment, op.id, "id")
    if pay.comanda.status == "closed" and user.role != Role.OWNER:
        raise Reject("sem_permissao", "Estorno em comanda fechada: só o dono.")
    try:
        return cs.reverse_payment(db, user.shop, user, pay, uuid=_uuid(op.data.get("reversal_id"), "reversal_id"))
    except cs.ComandaError as e:
        raise Reject("regra", str(e))


def _movement_create(db: Session, user: User, op) -> StockMovement:
    from . import stock
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, StockMovement, op)
    product = _by_uuid(db, shop, Product, op.data.get("product_id"), "product_id")
    reason = op.data.get("reason")
    if reason not in (StockReason.INTERNAL, StockReason.PURCHASE, StockReason.ADJUST):
        raise Reject("dados_invalidos", "Motivo inválido.")
    if reason != StockReason.INTERNAL:
        _need(user, (Role.OWNER,))
    try:
        delta = Decimal(str(op.data.get("delta"))).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        raise Reject("dados_invalidos", "Quantidade inválida.")
    if abs(delta) >= 100000:
        raise Reject("dados_invalidos", "Quantidade inválida.")
    delta = -abs(delta) if reason == StockReason.INTERNAL else abs(delta) if reason == StockReason.PURCHASE else delta
    try:
        return stock.move(db, shop, product, delta, reason, user, notes=_text(op.data.get("notes"), 200), uuid=uid)
    except stock.StockError as e:
        raise Reject("regra", str(e))


def _block_create(db: Session, user: User, op) -> Block:
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, Block, op)
    barber = _by_uuid(db, shop, Barber, op.data.get("barber_id"), "barber_id", required=False)
    start, end = _dt(op.data.get("start"), "start"), _dt(op.data.get("end"), "end")
    if end <= start:
        raise Reject("dados_invalidos", "O fim precisa ser depois do início.")
    b = Block(shop_id=shop.id, barber_id=barber.id if barber else None, start=start, end=end,
              reason=_text(op.data.get("reason"), 120), uuid=uid)
    db.add(b)
    db.flush()
    return b


def _block_delete(db: Session, user: User, op) -> Block:
    from ..sync_events import soft_delete
    _need(user, Role.STAFF)
    b = _by_uuid(db, user.shop, Block, op.id, "id")
    soft_delete(b)
    db.flush()
    return b


def _waitlist_create(db: Session, user: User, op) -> WaitlistEntry:
    from . import waitlist as wl
    _need(user, Role.STAFF)
    shop = user.shop
    uid = _new_id(db, WaitlistEntry, op)
    d = op.data
    customer = _by_uuid(db, shop, Customer, d.get("customer_id"), "customer_id")
    service = _by_uuid(db, shop, Service, d.get("service_id"), "service_id")
    barber = _by_uuid(db, shop, Barber, d.get("barber_id"), "barber_id", required=False)
    try:
        day = date.fromisoformat(str(d.get("day")))
    except ValueError:
        raise Reject("dados_invalidos", "Data inválida.")
    same = db.scalar(select(WaitlistEntry).where(
        WaitlistEntry.shop_id == shop.id, WaitlistEntry.customer_id == customer.id,
        WaitlistEntry.service_id == service.id, WaitlistEntry.day == day,
        WaitlistEntry.status.in_(("waiting", "offered"))))
    if same:
        raise Conflict("ja_na_lista", "Esse cliente já está na lista desse dia.", _waitlist(same, user))
    try:
        e = wl.join(db, shop, customer, service, day, barber, via="app")
    except wl.WaitlistError as err:
        raise Reject("regra", str(err))
    e.uuid = uid
    return e


HANDLERS: dict[tuple[str, str], tuple[Callable, Callable, str]] = {
    ("appointments", "create"): (_appt_create, _appointment, "appointments"),
    ("appointments", "update"): (_appt_update, _appointment, "appointments"),
    ("customers", "create"): (_customer_create, _customer, "customers"),
    ("customers", "update"): (_customer_update, _customer, "customers"),
    ("comandas", "create"): (_comanda_create, _comanda, "comandas"),
    ("comandas", "close"): (_comanda_action, _comanda, "comandas"),
    ("comandas", "cancel"): (_comanda_action, _comanda, "comandas"),
    ("comanda_items", "create"): (_item_create, _comanda_item, "comanda_items"),
    ("comanda_items", "reverse"): (_item_reverse, _comanda_item, "comanda_items"),
    ("comanda_payments", "create"): (_payment_create, _comanda_payment, "comanda_payments"),
    ("comanda_payments", "reverse"): (_payment_reverse, _comanda_payment, "comanda_payments"),
    ("stock_movements", "create"): (_movement_create, _movement, "stock_movements"),
    ("blocks", "create"): (_block_create, _block, "blocks"),
    ("blocks", "delete"): (_block_delete, _block, "blocks"),
    ("waitlist_entries", "create"): (_waitlist_create, _waitlist, "waitlist_entries"),
}


def _result(op, status: str, **extra) -> dict:
    return {"operation_id": op.operation_id, "entity": op.entity, "action": op.action, "id": op.id,
            "status": status, **extra}


def push(db: Session, user: User, operations: list) -> list[dict]:
    """Aplica as operações em ordem. Cada uma em um savepoint: uma rejeitada não desfaz as outras."""
    shop = user.shop
    results = []
    wa.start_queue(db)
    try:
        for op in operations:
            done = db.scalar(select(SyncOperation).where(SyncOperation.shop_id == shop.id,
                                                         SyncOperation.operation_id == op.operation_id))
            if done is not None:  # reenvio: devolve o mesmo resultado, sem executar de novo
                results.append({**done.result, "replayed": True})
                continue
            handler = HANDLERS.get((op.entity, op.action))
            mark = wa.queue_mark(db)
            sp = db.begin_nested()
            try:
                if handler is None:
                    raise Reject("operacao_desconhecida", f"Operação desconhecida: {op.entity}.{op.action}")
                fn, ser, _ = handler
                obj = fn(db, user, op)
                db.flush()
                res = _result(op, APPLIED, server=ser(obj, user))
                res["id"] = obj.uuid
            except Reject as e:
                sp.rollback()
                wa.queue_drop_from(db, mark)
                res = _result(op, REJECTED, reason=e.reason, message=e.message)
            except Conflict as e:
                sp.rollback()
                wa.queue_drop_from(db, mark)
                res = _result(op, CONFLICT, reason=e.reason, message=e.message, server=e.server, fields=e.fields)
            else:
                sp.commit()
            rec = SyncOperation(shop_id=shop.id, user_id=user.id, operation_id=op.operation_id,
                                entity=op.entity[:30], action=op.action[:20], status=res["status"], result=res)
            db.add(rec)
            db.flush()
            results.append(res)
        db.commit()
    except Exception:
        db.rollback()
        db.info.pop(wa.QUEUE_KEY, None)
        raise
    wa.send_queued(db)
    return results
