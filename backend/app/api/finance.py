"""Financeiro do app admin: regras de comissão/repasse entre barbeiros e acertos."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import now_local
from ..db import get_db
from ..models import Barber, Beneficiary, CommissionRule, CommissionSettlement, Service, Shop
from ..services import commissions as com
from ..services import whatsapp as wa
from ..services.fmt import money
from .admin import _own, shop_of

router = APIRouter()


def _check_beneficiary(db: Session, shop: Shop, payer_id: int, btype: str, bid: int | None) -> int | None:
    if btype == Beneficiary.SHOP:
        return None
    if not bid:
        raise HTTPException(422, "Informe o barbeiro que recebe o repasse")
    if bid == payer_id:
        raise HTTPException(422, "O barbeiro não pode repassar para ele mesmo")
    _own(db, Barber, bid, shop)
    return bid


# ---------------------------------------------------------------- regras de comissão

def rule_out(r: CommissionRule) -> S.CommissionRuleOut:
    return S.CommissionRuleOut(
        id=r.id, barber_id=r.barber_id, barber_name=r.barber.name, beneficiary_type=r.beneficiary_type,
        beneficiary_barber_id=r.beneficiary_barber_id,
        beneficiary_name=com.beneficiary_name(r.beneficiary_type, r.beneficiary_barber),
        percentage=r.percentage, service_id=r.service_id, service_name=r.service.name if r.service else None,
        valid_from=r.valid_from, valid_to=r.valid_to, notes=r.notes,
    )


def _apply_rule(db: Session, shop: Shop, r: CommissionRule, body: S.CommissionRuleIn) -> None:
    _own(db, Barber, body.barber_id, shop)
    if body.service_id:
        _own(db, Service, body.service_id, shop)
    if body.valid_to and body.valid_to < body.valid_from:
        raise HTTPException(422, "O fim da vigência precisa ser depois do início")
    r.barber_id = body.barber_id
    r.beneficiary_type = body.beneficiary_type
    r.beneficiary_barber_id = _check_beneficiary(db, shop, body.barber_id, body.beneficiary_type, body.beneficiary_barber_id)
    r.percentage, r.service_id = body.percentage, body.service_id
    r.valid_from, r.valid_to, r.notes = body.valid_from, body.valid_to, body.notes
    try:
        com.check_total(db, r)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/commission-rules", response_model=list[S.CommissionRuleOut], tags=["finance"])
def list_rules(barber_id: int | None = None, active_on: date | None = None,
               shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    q = select(CommissionRule).where(CommissionRule.shop_id == shop.id)
    if barber_id:
        q = q.where(CommissionRule.barber_id == barber_id)
    rules = db.scalars(q.order_by(CommissionRule.barber_id, CommissionRule.valid_from.desc())).all()
    if active_on:
        rules = [r for r in rules if com.valid_on(r, active_on)]
    return [rule_out(r) for r in rules]


@router.post("/commission-rules", response_model=S.CommissionRuleOut, tags=["finance"])
def create_rule(body: S.CommissionRuleIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    r = CommissionRule(shop_id=shop.id)
    _apply_rule(db, shop, r, body)
    db.add(r)
    db.commit()
    return rule_out(r)


@router.get("/commission-rules/{rid}", response_model=S.CommissionRuleOut, tags=["finance"])
def get_rule(rid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    return rule_out(_own(db, CommissionRule, rid, shop))


@router.put("/commission-rules/{rid}", response_model=S.CommissionRuleOut, tags=["finance"])
def update_rule(rid: int, body: S.CommissionRuleIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    r = _own(db, CommissionRule, rid, shop)
    try:
        _apply_rule(db, shop, r, body)
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    db.refresh(r)  # recarrega barbeiro/serviço se mudaram
    return rule_out(r)


@router.delete("/commission-rules/{rid}", tags=["finance"])
def delete_rule(rid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    db.delete(_own(db, CommissionRule, rid, shop))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- repasses e acertos

@router.get("/finance/commissions", response_model=S.CommissionReportOut, tags=["finance"])
def commissions(date_from: date, date_to: date, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    if date_to < date_from:
        raise HTTPException(422, "A data final precisa ser depois da inicial")
    return com.report(db, shop, date_from, date_to)


def settlement_out(st: CommissionSettlement, shop: Shop) -> S.SettlementOut:
    return S.SettlementOut(
        id=st.id, payer_barber_id=st.payer_barber_id, payer_name=st.payer.name, beneficiary_type=st.beneficiary_type,
        beneficiary_barber_id=st.beneficiary_barber_id,
        beneficiary_name=com.beneficiary_name(st.beneficiary_type, st.beneficiary_barber),
        period_start=st.period_start, period_end=st.period_end, amount=st.amount, paid_at=st.paid_at, notes=st.notes,
    )


@router.get("/finance/settlements", response_model=list[S.SettlementOut], tags=["finance"])
def list_settlements(barber_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                     shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    q = select(CommissionSettlement).where(CommissionSettlement.shop_id == shop.id)
    if barber_id:
        q = q.where((CommissionSettlement.payer_barber_id == barber_id)
                    | (CommissionSettlement.beneficiary_barber_id == barber_id))
    if date_from:
        q = q.where(CommissionSettlement.period_end >= date_from)
    if date_to:
        q = q.where(CommissionSettlement.period_start <= date_to)
    rows = db.scalars(q.order_by(CommissionSettlement.paid_at.desc()).limit(200))
    return [settlement_out(st, shop) for st in rows]


@router.post("/finance/settlements", response_model=S.SettlementOut, tags=["finance"])
def create_settlement(body: S.SettlementIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    payer = _own(db, Barber, body.payer_barber_id, shop)
    if body.period_end < body.period_start:
        raise HTTPException(422, "O fim do período precisa ser depois do início")
    bid = _check_beneficiary(db, shop, payer.id, body.beneficiary_type, body.beneficiary_barber_id)
    st = CommissionSettlement(
        shop_id=shop.id, payer_barber_id=payer.id, beneficiary_type=body.beneficiary_type, beneficiary_barber_id=bid,
        period_start=body.period_start, period_end=body.period_end, amount=body.amount,
        paid_at=body.paid_at.replace(tzinfo=None) if body.paid_at else now_local(), notes=body.notes,
    )
    db.add(st)
    db.flush()
    if body.notify:
        period = f"{st.period_start:%d/%m} a {st.period_end:%d/%m/%Y}"
        to = com.beneficiary_name(st.beneficiary_type, st.beneficiary_barber)
        if payer.phone:
            wa.send_text(db, shop, payer.phone, f"💈 Acerto registrado: repasse de *{money(st.amount)}* para {to}, "
                                                f"referente a {period}.")
        if st.beneficiary_barber and st.beneficiary_barber.phone:
            wa.send_text(db, shop, st.beneficiary_barber.phone,
                         f"💈 Acerto registrado: {payer.name} te repassou *{money(st.amount)}*, referente a {period}.")
    db.commit()
    return settlement_out(st, shop)


@router.delete("/finance/settlements/{sid}", tags=["finance"])
def delete_settlement(sid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    db.delete(_own(db, CommissionSettlement, sid, shop))
    db.commit()
    return {"ok": True}
