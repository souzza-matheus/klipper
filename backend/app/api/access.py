"""Controle de clientes: acesso ao agendamento (normal, precisa de aprovação, bloqueado), pedidos para aprovar
e clientes que não podem se encontrar. Tudo isolado pela barbearia do usuário."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import now_local
from ..db import get_db
from ..models import Appointment, ApptStatus, Customer, CustomerConflict, Shop
from ..services import approvals
from ..services import scheduling as sch
from ..services import whatsapp as wa
from ..services.fmt import appt_summary
from .admin import _own, appt_out, conflict_hit_out, shop_of

router = APIRouter()


# ---------------------------------------------------------------- acesso ao agendamento

@router.put("/customers/{cid}/access", response_model=S.CustomerAccessOut, tags=["customers"])
def set_access(cid: int, body: S.CustomerAccessIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    """Muda o acesso do cliente. Ao bloquear, cancel_future=true cancela os agendamentos futuros
    (notify_customer=true avisa o cliente com uma mensagem neutra)."""
    c = _own(db, Customer, cid, shop)
    if body.access_status != c.access_status:
        c.access_changed_at = now_local()
    c.access_status = body.access_status
    c.access_reason = body.access_reason.strip()
    cancelled = 0
    if body.cancel_future:
        future = db.scalars(select(Appointment).where(
            Appointment.shop_id == shop.id, Appointment.customer_id == c.id,
            Appointment.status.in_(ApptStatus.OCCUPYING), Appointment.start >= now_local(),
        ).order_by(Appointment.start)).all()
        for a in future:
            sch.cancel_appointment(db, a)
            if body.notify_customer:
                wa.send_text(db, shop, c.phone, f"❌ Seu horário na *{shop.name}* foi cancelado:\n\n{appt_summary(a)}\n\n"
                                                "Qualquer dúvida, fale com a barbearia.")
        cancelled = len(future)
    db.commit()
    return S.CustomerAccessOut(customer=S.CustomerOut.model_validate(c), cancelled=cancelled)


# ---------------------------------------------------------------- pedidos para aprovar

@router.get("/approvals", response_model=list[S.AppointmentOut], tags=["approvals"])
def list_approvals(shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    return [appt_out(a) for a in approvals.pending_approvals(db, shop)]


def _pending(db: Session, aid: int, shop: Shop) -> Appointment:
    a = _own(db, Appointment, aid, shop)
    if a.status != ApptStatus.PENDING_APPROVAL:
        raise HTTPException(409, "Esse pedido não está mais pendente (já foi respondido ou expirou).")
    return a


@router.post("/appointments/{aid}/approve", response_model=S.AppointmentOut, tags=["approvals"])
def approve(aid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    a = _pending(db, aid, shop)
    approvals.approve(db, shop, a)
    db.commit()
    return appt_out(a)


@router.post("/appointments/{aid}/refuse", response_model=S.AppointmentOut, tags=["approvals"])
def refuse(aid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    a = _pending(db, aid, shop)
    approvals.refuse(db, shop, a)
    db.commit()
    return appt_out(a)


# ---------------------------------------------------------------- clientes que não podem se encontrar

def conflict_out(shop: Shop, c: CustomerConflict, customer_id: int | None = None) -> S.ConflictOut:
    out = S.ConflictOut(
        id=c.id, customer_a_id=c.customer_a_id, customer_a_name=c.customer_a.name,
        customer_b_id=c.customer_b_id, customer_b_name=c.customer_b.name, min_gap_minutes=c.min_gap_minutes,
        effective_gap_minutes=sch.conflict_gap(shop, c), same_day_block=c.same_day_block,
        conflict_action=c.conflict_action, notes=c.notes,
        created_at=c.created_at,
    )
    if customer_id in (c.customer_a_id, c.customer_b_id):
        other = c.customer_b if customer_id == c.customer_a_id else c.customer_a
        out.other_customer_id, out.other_customer_name, out.other_customer_phone = other.id, other.name, other.phone
    return out


@router.get("/customer-conflicts", response_model=list[S.ConflictOut], tags=["conflicts"])
def list_conflicts(customer_id: int | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    q = select(CustomerConflict).where(CustomerConflict.shop_id == shop.id)
    if customer_id:
        _own(db, Customer, customer_id, shop)
        q = q.where(or_(CustomerConflict.customer_a_id == customer_id, CustomerConflict.customer_b_id == customer_id))
    return [conflict_out(shop, c, customer_id) for c in db.scalars(q.order_by(CustomerConflict.created_at.desc()))]


@router.get("/customer-conflicts/day", response_model=list[S.ConflictHitOut], tags=["conflicts"])
def conflicts_on_day(day: date, customer_id: int | None = None, customer_phone: str = "",
                     shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    """Clientes em conflito com este cliente que têm horário no dia (aviso na tela de agendamento)."""
    if customer_id:
        c = _own(db, Customer, customer_id, shop)
    else:
        phone = wa.normalize_phone(customer_phone)
        c = db.scalar(select(Customer).where(Customer.shop_id == shop.id, Customer.phone == phone)) if phone else None
    if c is None:
        return []
    return [conflict_hit_out(h) for h in sch.conflicts_on_day(db, shop, c, day)]


@router.get("/customer-conflicts/{conf_id}", response_model=S.ConflictOut, tags=["conflicts"])
def get_conflict(conf_id: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    return conflict_out(shop, _own(db, CustomerConflict, conf_id, shop))


@router.post("/customer-conflicts", response_model=S.ConflictOut, tags=["conflicts"])
def create_conflict(body: S.ConflictIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    if body.customer_id == body.other_customer_id:
        raise HTTPException(422, "Escolha dois clientes diferentes")
    _own(db, Customer, body.customer_id, shop)
    _own(db, Customer, body.other_customer_id, shop)
    a, b = sorted((body.customer_id, body.other_customer_id))  # A-B e B-A são o mesmo par
    exists = db.scalar(select(CustomerConflict).where(
        CustomerConflict.shop_id == shop.id, CustomerConflict.customer_a_id == a, CustomerConflict.customer_b_id == b))
    if exists:
        raise HTTPException(409, "Esses dois clientes já estão marcados para não agendar juntos")
    c = CustomerConflict(shop_id=shop.id, customer_a_id=a, customer_b_id=b, min_gap_minutes=body.min_gap_minutes,
                         same_day_block=body.same_day_block, conflict_action=body.conflict_action,
                         notes=body.notes.strip())
    db.add(c)
    try:
        db.commit()
    except IntegrityError:  # dois cadastros do mesmo par ao mesmo tempo
        db.rollback()
        raise HTTPException(409, "Esses dois clientes já estão marcados para não agendar juntos")
    return conflict_out(shop, c, body.customer_id)


@router.put("/customer-conflicts/{conf_id}", response_model=S.ConflictOut, tags=["conflicts"])
def update_conflict(conf_id: int, body: S.ConflictUpdate, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    c = _own(db, CustomerConflict, conf_id, shop)
    c.min_gap_minutes, c.same_day_block, c.notes = body.min_gap_minutes, body.same_day_block, body.notes.strip()
    c.conflict_action = body.conflict_action
    db.commit()
    return conflict_out(shop, c)


@router.delete("/customer-conflicts/{conf_id}", tags=["conflicts"])
def delete_conflict(conf_id: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    db.delete(_own(db, CustomerConflict, conf_id, shop))
    db.commit()
    return {"ok": True}
