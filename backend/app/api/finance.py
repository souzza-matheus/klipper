"""Financeiro do app admin: comissões e acertos, gastos e relatórios."""
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import now_local
from ..db import get_db
from ..models import Barber, Beneficiary, CommissionRule, CommissionSettlement, Expense, ExpenseCategory, Service, Shop
from ..services import commissions as com
from ..services import expenses as exp
from ..services import reports
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


# ---------------------------------------------------------------- gastos

def expense_out(e: Expense, today: date | None = None) -> S.ExpenseOut:
    return S.ExpenseOut(
        id=e.id, description=e.description, category=e.category,
        category_label=ExpenseCategory.LABELS.get(e.category, e.category), amount=e.amount, due_date=e.due_date,
        paid_at=e.paid_at, payment_method=e.payment_method, barber_id=e.barber_id,
        barber_name=e.barber.name if e.barber else None, recurring=e.recurring,
        recurring_source_id=e.recurring_source_id, notes=e.notes,
        overdue=exp.is_overdue(e, today or now_local().date()),
    )


def _parse_month(month: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", month)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise HTTPException(422, "Mês inválido. Use AAAA-MM, ex.: 2026-10")
    return int(m.group(1)), int(m.group(2))


@router.get("/expenses", response_model=list[S.ExpenseOut], tags=["expenses"])
def list_expenses(month: str | None = Query(None, description="AAAA-MM; gera as contas recorrentes do mês"),
                  category: str | None = None, status: str | None = Query(None, pattern="^(paid|open|overdue)$"),
                  barber_id: int | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    today = now_local().date()
    q = select(Expense).where(Expense.shop_id == shop.id)
    if month:
        year, mon = _parse_month(month)
        if exp.ensure_recurring(db, shop, year, mon):
            db.commit()
        first, last = exp.month_bounds(year, mon)
        q = q.where(Expense.due_date >= first, Expense.due_date <= last)
    if category:
        q = q.where(Expense.category == category)
    if status == "paid":
        q = q.where(Expense.paid_at.is_not(None))
    elif status == "open":
        q = q.where(Expense.paid_at.is_(None))
    elif status == "overdue":
        q = q.where(Expense.paid_at.is_(None), Expense.due_date < today)
    if barber_id:
        q = q.where(Expense.barber_id == barber_id)
    rows = db.scalars(q.order_by(Expense.due_date, Expense.description).limit(500))
    return [expense_out(e, today) for e in rows]


def _apply_expense(db: Session, shop: Shop, e: Expense, body: S.ExpenseIn) -> None:
    if body.barber_id:
        _own(db, Barber, body.barber_id, shop)
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    e.description = body.description.strip()
    if e.recurring_source_id:
        e.recurring = False  # a cópia de um mês não vira uma nova recorrência (duplicaria os meses seguintes)
    if e.paid_at is None:
        e.payment_method = None


@router.post("/expenses", response_model=S.ExpenseOut, tags=["expenses"])
def create_expense(body: S.ExpenseIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    e = Expense(shop_id=shop.id)
    _apply_expense(db, shop, e, body)
    db.add(e)
    db.commit()
    db.refresh(e)
    return expense_out(e)


@router.get("/expenses/{eid}", response_model=S.ExpenseOut, tags=["expenses"])
def get_expense(eid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    return expense_out(_own(db, Expense, eid, shop))


@router.put("/expenses/{eid}", response_model=S.ExpenseOut, tags=["expenses"])
def update_expense(eid: int, body: S.ExpenseIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    e = _own(db, Expense, eid, shop)
    _apply_expense(db, shop, e, body)
    db.commit()
    db.refresh(e)
    return expense_out(e)


@router.delete("/expenses/{eid}", tags=["expenses"])
def delete_expense(eid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    db.delete(_own(db, Expense, eid, shop))
    db.commit()
    return {"ok": True}


@router.post("/expenses/{eid}/pay", response_model=S.ExpenseOut, tags=["expenses"])
def pay_expense(eid: int, body: S.ExpensePayIn | None = None, shop: Shop = Depends(shop_of),
                db: Session = Depends(get_db)):
    e = _own(db, Expense, eid, shop)
    body = body or S.ExpensePayIn()
    e.paid_at = body.paid_at or now_local().date()
    if body.payment_method:
        e.payment_method = body.payment_method
    db.commit()
    return expense_out(e)


# ---------------------------------------------------------------- relatórios

MAX_DAYS = 366


def _check_period(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise HTTPException(422, "A data final precisa ser depois da inicial")
    if (date_to - date_from).days >= MAX_DAYS:
        raise HTTPException(422, "Período máximo de 1 ano")


@router.get("/finance/summary", response_model=S.FinanceSummaryOut, tags=["finance"])
def finance_summary(date_from: date, date_to: date, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    _check_period(date_from, date_to)
    out = reports.summary(db, shop, date_from, date_to)
    db.commit()  # contas recorrentes geradas para os meses do período
    return out


@router.get("/finance/daily", response_model=list[S.FinanceDayOut], tags=["finance"])
def finance_daily(date_from: date, date_to: date, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    _check_period(date_from, date_to)
    return reports.daily(db, shop, date_from, date_to)


@router.get("/finance/export.csv", tags=["finance"], response_class=Response)
def finance_export(date_from: date, date_to: date, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    _check_period(date_from, date_to)
    data = reports.export_csv(db, shop, date_from, date_to)
    db.commit()
    name = f"financeiro_{date_from:%Y-%m-%d}_{date_to:%Y-%m-%d}.csv"
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
