"""Comandas (dono e recepção) e lista de espera (dono e recepção).

Estorno em comanda já fechada: só o dono.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..db import get_db
from ..models import (
    Appointment, Barber, Comanda, ComandaItem, ComandaPayment, ComandaStatus, Customer, ItemKind, PackagePlan,
    Product, Role, Service, Shop, User, WaitlistEntry, WaitStatus,
)
from ..permissions import staff_shop, staff_user
from ..services import comandas as cs
from ..services import scheduling as sch
from ..services import waitlist as wl
from ..services import whatsapp as wa
from .admin import _own

router = APIRouter()


# ---------------------------------------------------------------- comandas

def comanda_out(c: Comanda) -> S.ComandaOut:
    t = cs.totals(c)
    rev_items = {i.reverses_id for i in c.items if i.reverses_id}
    rev_pays = {p.reverses_id for p in c.payments if p.reverses_id}
    return S.ComandaOut(
        id=c.id, uuid=c.uuid, version=c.version, status=c.status, customer_id=c.customer_id,
        customer_name=(c.customer.name or c.customer.phone) if c.customer else None, appointment_id=c.appointment_id,
        opened_at=c.opened_at, closed_at=c.closed_at, notes=c.notes,
        items=[S.ComandaItemOut(
            id=i.id, uuid=i.uuid, kind=i.kind, description=i.description, service_id=i.service_id,
            product_id=i.product_id, package_plan_id=i.package_plan_id, barber_id=i.barber_id,
            barber_name=i.barber.name if i.barber else None, quantity=i.quantity, unit_price=i.unit_price,
            amount=i.amount, percent=i.percent, covered_by=i.covered_by, commission_base=i.commission_base,
            reverses_id=i.reverses_id, reversed=i.id in rev_items, created_at=i.created_at) for i in c.items],
        payments=[S.ComandaPaymentOut(id=p.id, uuid=p.uuid, method=p.method, amount=p.amount,
                                      from_deposit=p.from_deposit, reverses_id=p.reverses_id,
                                      reversed=p.id in rev_pays, created_at=p.created_at) for p in c.payments],
        subtotal=t.subtotal, discount=t.discount, tips=t.tips, due=t.due, paid=t.paid, balance=t.balance,
        covered=t.covered,
    )


def _err(e: Exception) -> HTTPException:
    return HTTPException(409, str(e))


@router.get("/comandas", response_model=list[S.ComandaOut], tags=["comandas"])
def list_comandas(status: str | None = Query(None, pattern="^(open|closed|cancelled)$"), day: date | None = None,
                  shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    q = select(Comanda).where(Comanda.shop_id == shop.id)
    if status:
        q = q.where(Comanda.status == status)
    if day:
        start = datetime.combine(day, datetime.min.time())
        q = q.where(Comanda.opened_at >= start, Comanda.opened_at < start + timedelta(days=1))
    return [comanda_out(c) for c in db.scalars(q.order_by(Comanda.opened_at.desc()).limit(200))]


@router.post("/comandas", response_model=S.ComandaOut, tags=["comandas"])
def open_comanda(body: S.ComandaIn, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    appt = _own(db, Appointment, body.appointment_id, shop) if body.appointment_id else None
    customer = _own(db, Customer, body.customer_id, shop) if body.customer_id else None
    try:
        c = cs.open_comanda(db, shop, user, customer=customer, appointment=appt)
    except (cs.ComandaError, ValueError) as e:
        raise _err(e)
    db.commit()
    return comanda_out(c)


@router.get("/comandas/{cid}", response_model=S.ComandaOut, tags=["comandas"])
def get_comanda(cid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    return comanda_out(_own(db, Comanda, cid, shop))


def add_item(db: Session, shop: Shop, user: User, c: Comanda, body: S.ComandaItemIn, uuid: str | None = None):
    barber = _own(db, Barber, body.barber_id, shop) if body.barber_id else None
    if body.kind == ItemKind.SERVICE:
        if not body.service_id:
            raise cs.ComandaError("Escolha o serviço.")
        return cs.add_service(db, shop, user, c, _own(db, Service, body.service_id, shop), barber, body.quantity,
                              body.unit_price, body.cover, uuid=uuid)
    if body.kind == ItemKind.PRODUCT:
        if not body.product_id:
            raise cs.ComandaError("Escolha o produto.")
        return cs.add_product(db, shop, user, c, _own(db, Product, body.product_id, shop), body.quantity, barber,
                              body.unit_price, uuid=uuid, allow_negative=body.allow_negative_stock)
    if body.kind == ItemKind.PACKAGE:
        if not body.package_plan_id:
            raise cs.ComandaError("Escolha o pacote.")
        return cs.add_package_sale(db, shop, user, c, _own(db, PackagePlan, body.package_plan_id, shop), barber,
                                   uuid=uuid)
    if body.kind == ItemKind.DISCOUNT:
        return cs.add_discount(db, shop, user, c, body.value, body.percent, uuid=uuid)
    if barber is None or body.value is None:
        raise cs.ComandaError("Gorjeta: informe o valor e o profissional.")
    return cs.add_tip(db, shop, user, c, body.value, barber, uuid=uuid)


@router.post("/comandas/{cid}/items", response_model=S.ComandaOut, tags=["comandas"])
def post_item(cid: int, body: S.ComandaItemIn, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    try:
        add_item(db, shop, user, c, body)
    except (cs.ComandaError, ValueError) as e:
        db.rollback()
        raise _err(e)
    db.commit()
    db.refresh(c)
    return comanda_out(c)


def _closed_needs_owner(user: User, c: Comanda) -> None:
    if c.status == ComandaStatus.CLOSED and user.role != Role.OWNER:
        raise HTTPException(403, "Estorno em comanda fechada: só o dono.")


@router.post("/comandas/{cid}/items/{iid}/reverse", response_model=S.ComandaOut, tags=["comandas"])
def reverse_item(cid: int, iid: int, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    item = _own(db, ComandaItem, iid, shop)
    if item.comanda_id != c.id:
        raise HTTPException(404, "Não encontrado")
    _closed_needs_owner(user, c)
    try:
        cs.reverse_item(db, shop, user, item)
    except (cs.ComandaError, ValueError) as e:
        db.rollback()
        raise _err(e)
    db.commit()
    db.refresh(c)
    return comanda_out(c)


@router.post("/comandas/{cid}/payments", response_model=S.ComandaOut, tags=["comandas"])
def post_payment(cid: int, body: S.ComandaPaymentIn, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    try:
        cs.add_payment(db, shop, user, c, body.method, body.amount)
    except cs.ComandaError as e:
        raise _err(e)
    db.commit()
    db.refresh(c)
    return comanda_out(c)


@router.post("/comandas/{cid}/payments/{pid}/reverse", response_model=S.ComandaOut, tags=["comandas"])
def reverse_payment(cid: int, pid: int, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    pay = _own(db, ComandaPayment, pid, shop)
    if pay.comanda_id != c.id:
        raise HTTPException(404, "Não encontrado")
    _closed_needs_owner(user, c)
    try:
        cs.reverse_payment(db, shop, user, pay)
    except cs.ComandaError as e:
        raise _err(e)
    db.commit()
    db.refresh(c)
    return comanda_out(c)


@router.post("/comandas/{cid}/close", response_model=S.ComandaOut, tags=["comandas"])
def close_comanda(cid: int, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    try:
        cs.close(db, shop, user, c)
    except (cs.ComandaError, ValueError) as e:
        db.rollback()
        raise _err(e)
    db.commit()
    return comanda_out(c)


@router.post("/comandas/{cid}/cancel", response_model=S.ComandaOut, tags=["comandas"])
def cancel_comanda(cid: int, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Comanda, cid, shop)
    try:
        cs.cancel(db, shop, user, c)
    except cs.ComandaError as e:
        raise _err(e)
    db.commit()
    return comanda_out(c)


# ---------------------------------------------------------------- lista de espera

def wait_out(db: Session, e: WaitlistEntry) -> S.WaitlistOut:
    return S.WaitlistOut(
        id=e.id, uuid=e.uuid, customer_id=e.customer_id, customer_name=e.customer.name or e.customer.phone,
        customer_phone=e.customer.phone, service_id=e.service_id, service_name=e.service.name,
        barber_id=e.barber_id, barber_name=e.barber.name if e.barber else None, day=e.day,
        after_time=e.after_time, before_time=e.before_time, status=e.status,
        position=wl.position(db, e) if e.status == WaitStatus.WAITING else None,
        offer_expires_at=e.offer_expires_at, created_at=e.created_at)


@router.get("/waitlist", response_model=list[S.WaitlistOut], tags=["waitlist"])
def list_waitlist(day: date | None = None, include_closed: bool = False, shop: Shop = Depends(staff_shop),
                  db: Session = Depends(get_db)):
    q = select(WaitlistEntry).where(WaitlistEntry.shop_id == shop.id)
    if day:
        q = q.where(WaitlistEntry.day == day)
    if not include_closed:
        q = q.where(WaitlistEntry.status.in_(WaitStatus.OPEN))
    return [wait_out(db, e) for e in db.scalars(q.order_by(WaitlistEntry.day, WaitlistEntry.created_at).limit(300))]


@router.post("/waitlist", response_model=S.WaitlistOut, tags=["waitlist"])
def add_waitlist(body: S.WaitlistIn, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    svc = _own(db, Service, body.service_id, shop)
    barber = _own(db, Barber, body.barber_id, shop) if body.barber_id else None
    if body.customer_id:
        customer = _own(db, Customer, body.customer_id, shop)
    else:
        phone = wa.normalize_phone(body.customer_phone)
        if not 12 <= len(phone) <= 15:
            raise HTTPException(422, "Telefone inválido. Use DDD + número.")
        customer = sch.get_or_create_customer(db, shop, phone, body.customer_name.strip().title())
    try:
        e = wl.join(db, shop, customer, svc, body.day, barber, body.after_time, body.before_time, via="app")
    except wl.WaitlistError as err:
        raise HTTPException(422, str(err))
    db.commit()
    return wait_out(db, e)


@router.delete("/waitlist/{wid}", tags=["waitlist"])
def remove_waitlist(wid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    e = _own(db, WaitlistEntry, wid, shop)
    wl.cancel(db, shop, e)
    db.commit()
    return {"ok": True}
