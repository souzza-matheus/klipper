"""Produtos e estoque, pacotes, clube de assinatura e cobranças avulsas.

Leitura: dono e recepção (o custo do produto só aparece para o dono). Cadastro e ajuste de estoque: dono.
Recepção registra uso interno, assina clientes, confirma e reenvia cobranças.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import now_local
from ..db import get_db
from ..models import (
    Charge, Customer, CustomerPackage, PackagePlan, PayStatus, Product, Role, Service, ServiceProduct, Shop,
    StockMovement, StockReason, SubStatus, Subscription, SubscriptionPlan, SubscriptionPlanItem, User,
)
from ..permissions import owner_shop, staff_shop, staff_user
from ..services import benefits, billing, stock
from ..sync_events import soft_delete
from .admin import _own

router = APIRouter()


# ---------------------------------------------------------------- produtos

def product_out(p: Product, qty: Decimal, owner: bool) -> S.ProductOut:
    return S.ProductOut(id=p.id, uuid=p.uuid, name=p.name, kind=p.kind, unit=p.unit, cost=p.cost if owner else None,
                        price=p.price, min_stock=p.min_stock, commission_pct=p.commission_pct, active=p.active,
                        stock=qty, low_stock=stock.is_low(p, qty))


@router.get("/products", response_model=list[S.ProductOut], tags=["stock"])
def list_products(include_inactive: bool = False, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    q = select(Product).where(Product.shop_id == shop.id)
    if not include_inactive:
        q = q.where(Product.active.is_(True))
    products = db.scalars(q.order_by(Product.name)).all()
    bal = stock.balances(db, shop, [p.id for p in products])
    return [product_out(p, bal.get(p.id, Decimal(0)), user.role == Role.OWNER) for p in products]


@router.get("/products/low-stock", response_model=list[S.ProductOut], tags=["stock"])
def low_stock(user: User = Depends(staff_user), db: Session = Depends(get_db)):
    return [product_out(p, q, user.role == Role.OWNER) for p, q in stock.low_stock(db, user.shop)]


def _apply_product(p: Product, body: S.ProductIn) -> None:
    for k, v in body.model_dump().items():
        setattr(p, k, v)


@router.post("/products", response_model=S.ProductOut, tags=["stock"])
def create_product(body: S.ProductIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = Product(shop_id=shop.id)
    _apply_product(p, body)
    db.add(p)
    db.commit()
    return product_out(p, Decimal(0), True)


@router.put("/products/{pid}", response_model=S.ProductOut, tags=["stock"])
def update_product(pid: int, body: S.ProductIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = _own(db, Product, pid, shop)
    _apply_product(p, body)
    db.commit()
    return product_out(p, stock.balance(db, shop, p), True)


@router.delete("/products/{pid}", tags=["stock"])
def delete_product(pid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = _own(db, Product, pid, shop)
    used = db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == p.id))
    p.active = False
    if not used:
        soft_delete(p)
    db.commit()
    return {"ok": True, "deactivated": bool(used)}


@router.get("/products/{pid}/movements", response_model=list[S.StockMoveOut], tags=["stock"])
def list_movements(pid: int, limit: int = Query(100, ge=1, le=500), shop: Shop = Depends(owner_shop),
                   db: Session = Depends(get_db)):
    p = _own(db, Product, pid, shop)
    rows = db.scalars(select(StockMovement).where(StockMovement.product_id == p.id)
                      .order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(limit))
    return [S.StockMoveOut.model_validate(m, from_attributes=True) for m in rows]


@router.post("/products/{pid}/movements", response_model=S.StockMoveOut, tags=["stock"])
def add_movement(pid: int, body: S.StockMoveIn, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    """Entrada (compra) e ajuste de inventário: dono. Uso interno (saída): dono e recepção."""
    shop = user.shop
    p = _own(db, Product, pid, shop)
    if body.reason != StockReason.INTERNAL and user.role != Role.OWNER:
        raise HTTPException(403, "Seu perfil não tem acesso a esta função.")
    delta = body.delta
    if body.reason == StockReason.INTERNAL:
        delta = -abs(delta)
    elif body.reason == StockReason.PURCHASE:
        delta = abs(delta)
    try:
        m = stock.move(db, shop, p, delta, body.reason, user, unit_cost=body.unit_cost, notes=body.notes)
    except stock.StockError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return S.StockMoveOut.model_validate(m, from_attributes=True)


@router.put("/services/{sid}/consumption", response_model=list[S.ConsumptionIn], tags=["stock"])
def set_consumption(sid: int, body: list[S.ConsumptionIn], shop: Shop = Depends(owner_shop),
                    db: Session = Depends(get_db)):
    """Produtos que o serviço consome (baixa automática ao lançar o serviço na comanda)."""
    svc = _own(db, Service, sid, shop)
    if len(body) > 30:
        raise HTTPException(422, "No máximo 30 produtos por serviço.")
    for row in body:
        _own(db, Product, row.product_id, shop)
    svc.consumption = [ServiceProduct(product_id=r.product_id, quantity=r.quantity)
                       for r in {r.product_id: r for r in body}.values()]
    db.commit()
    return [S.ConsumptionIn(product_id=c.product_id, quantity=c.quantity) for c in svc.consumption]


@router.get("/services/{sid}/consumption", response_model=list[S.ConsumptionIn], tags=["stock"])
def get_consumption(sid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    svc = _own(db, Service, sid, shop)
    return [S.ConsumptionIn(product_id=c.product_id, quantity=c.quantity) for c in svc.consumption]


# ---------------------------------------------------------------- pacotes

@router.get("/package-plans", response_model=list[S.PackagePlanOut], tags=["packages"])
def list_package_plans(shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    return db.scalars(select(PackagePlan).where(PackagePlan.shop_id == shop.id).order_by(PackagePlan.name)).all()


def _apply_plan(db: Session, shop: Shop, p: PackagePlan, body: S.PackagePlanIn) -> None:
    _own(db, Service, body.service_id, shop)
    for k, v in body.model_dump().items():
        setattr(p, k, v)


@router.post("/package-plans", response_model=S.PackagePlanOut, tags=["packages"])
def create_package_plan(body: S.PackagePlanIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = PackagePlan(shop_id=shop.id)
    _apply_plan(db, shop, p, body)
    db.add(p)
    db.commit()
    return p


@router.put("/package-plans/{pid}", response_model=S.PackagePlanOut, tags=["packages"])
def update_package_plan(pid: int, body: S.PackagePlanIn, shop: Shop = Depends(owner_shop),
                        db: Session = Depends(get_db)):
    p = _own(db, PackagePlan, pid, shop)
    _apply_plan(db, shop, p, body)  # pacotes já vendidos guardam sessões e preço da venda
    db.commit()
    return p


@router.delete("/package-plans/{pid}", tags=["packages"])
def delete_package_plan(pid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = _own(db, PackagePlan, pid, shop)
    p.active = False
    if not db.scalar(select(func.count()).select_from(CustomerPackage).where(CustomerPackage.plan_id == p.id)):
        soft_delete(p)
    db.commit()
    return {"ok": True}


@router.get("/customers/{cid}/balance", tags=["packages"])
def customer_balance(cid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    """Pacotes (sessões, validade) e assinaturas (status, usos no período) do cliente."""
    c = _own(db, Customer, cid, shop)
    out = benefits.customer_balance(db, shop, c)
    db.commit()  # refresh_status pode ter atualizado o status da assinatura
    return out


@router.post("/customer-packages/{cpid}/cancel", tags=["packages"])
def cancel_customer_package(cpid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    cp = _own(db, CustomerPackage, cpid, shop)
    cp.status = "cancelled"
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- clube de assinatura

def plan_out(p: SubscriptionPlan) -> S.SubscriptionPlanOut:
    return S.SubscriptionPlanOut(id=p.id, uuid=p.uuid, name=p.name, price=p.price, block_after_days=p.block_after_days,
                                 active=p.active, items=[S.PlanItemIO(service_id=i.service_id,
                                                                      limit_per_period=i.limit_per_period)
                                                         for i in p.items])


@router.get("/subscription-plans", response_model=list[S.SubscriptionPlanOut], tags=["subscriptions"])
def list_sub_plans(shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    return [plan_out(p) for p in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.shop_id == shop.id)
                                            .order_by(SubscriptionPlan.name))]


def _apply_sub_plan(db: Session, shop: Shop, p: SubscriptionPlan, body: S.SubscriptionPlanIn) -> None:
    items = {i.service_id: i for i in body.items}
    for sid in items:
        _own(db, Service, sid, shop)
    p.name, p.price, p.block_after_days, p.active = body.name, body.price, body.block_after_days, body.active
    p.items = [SubscriptionPlanItem(service_id=i.service_id, limit_per_period=i.limit_per_period)
               for i in items.values()]


@router.post("/subscription-plans", response_model=S.SubscriptionPlanOut, tags=["subscriptions"])
def create_sub_plan(body: S.SubscriptionPlanIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = SubscriptionPlan(shop_id=shop.id)
    db.add(p)
    _apply_sub_plan(db, shop, p, body)
    db.commit()
    return plan_out(p)


@router.put("/subscription-plans/{pid}", response_model=S.SubscriptionPlanOut, tags=["subscriptions"])
def update_sub_plan(pid: int, body: S.SubscriptionPlanIn, shop: Shop = Depends(owner_shop),
                    db: Session = Depends(get_db)):
    p = _own(db, SubscriptionPlan, pid, shop)
    _apply_sub_plan(db, shop, p, body)  # assinantes atuais mantêm o valor contratado
    db.commit()
    return plan_out(p)


@router.delete("/subscription-plans/{pid}", tags=["subscriptions"])
def delete_sub_plan(pid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    p = _own(db, SubscriptionPlan, pid, shop)
    p.active = False
    if not db.scalar(select(func.count()).select_from(Subscription).where(Subscription.plan_id == p.id)):
        soft_delete(p)
    db.commit()
    return {"ok": True}


@router.get("/subscriptions", tags=["subscriptions"])
def list_subscriptions(status: str | None = Query(None, pattern="^(ativa|atrasada|cancelada)$"),
                       shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    rows = billing.subscriptions_report(db, shop)["subscribers"]
    db.commit()
    return [r for r in rows if status is None or r["status"] == status]


@router.get("/subscriptions/report", tags=["subscriptions"])
def subscriptions_report(shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    """Assinantes por status e receita recorrente mensal (MRR = soma das assinaturas não canceladas)."""
    out = billing.subscriptions_report(db, shop)
    db.commit()
    return out


@router.post("/subscriptions", tags=["subscriptions"])
def subscribe(body: S.SubscribeIn, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    shop = user.shop
    c = _own(db, Customer, body.customer_id, shop)
    plan = _own(db, SubscriptionPlan, body.plan_id, shop)
    if body.start and body.start < now_local().date():
        raise HTTPException(422, "A assinatura não pode começar no passado.")
    try:
        sub = billing.subscribe(db, shop, c, plan, body.start, charge_now=body.charge_now)
    except billing.BillingError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return {"id": sub.id, "uuid": sub.uuid, "status": sub.status, "next_due_date": sub.next_due_date}


@router.post("/subscriptions/{sid}/cancel", tags=["subscriptions"])
def cancel_subscription(sid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    sub = _own(db, Subscription, sid, shop)
    if sub.status == SubStatus.CANCELLED:
        raise HTTPException(409, "Essa assinatura já foi cancelada.")
    billing.cancel_subscription(db, sub)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- cobranças

def charge_out(ch: Charge, receipt=None, with_receipt: bool = True) -> S.ChargeOut:
    from sqlalchemy.orm import object_session
    from ..services import receipts
    if with_receipt and receipt is None:
        receipt = receipts.latest_for(object_session(ch), charge_id=ch.id)
    return S.ChargeOut(receipt=S.ReceiptOut.model_validate(receipt) if receipt else None,id=ch.id, uuid=ch.uuid, kind=ch.kind, customer_id=ch.customer_id,
                       customer_name=ch.customer.name or ch.customer.phone, subscription_id=ch.subscription_id,
                       customer_package_id=ch.customer_package_id, due_date=ch.due_date, amount=ch.amount,
                       status=ch.status, gateway=ch.gateway, brcode=ch.brcode, sent_at=ch.sent_at,
                       customer_reported_at=ch.customer_reported_at, confirmed_at=ch.confirmed_at)


@router.get("/charges", response_model=list[S.ChargeOut], tags=["subscriptions"])
def list_charges(status: str | None = Query(None, pattern="^(pending|paid|cancelled|expired)$"),
                 shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    q = select(Charge).where(Charge.shop_id == shop.id)
    if status:
        q = q.where(Charge.status == status)
    q = q.order_by(Charge.customer_reported_at.is_(None), Charge.due_date.desc()) if status == PayStatus.PENDING \
        else q.order_by(Charge.created_at.desc())
    from ..models import ReceiptResult
    from ..services import receipts
    rows = list(db.scalars(q.limit(200)))
    latest = receipts.latest_by_target(db, [c.id for c in rows], charges=True)
    out = [charge_out(c, latest.get(c.id), with_receipt=False) for c in rows]
    if status == PayStatus.PENDING:  # comprovante que confere no topo
        out.sort(key=lambda x: not (x.receipt and x.receipt.result == ReceiptResult.OK))
    return out


@router.post("/charges/{chid}/confirm", response_model=S.ChargeOut, tags=["subscriptions"])
def confirm_charge(chid: int, user: User = Depends(staff_user), db: Session = Depends(get_db)):
    from ..models import ReceiptDecision
    from ..services import receipts
    shop = user.shop
    ch = _own(db, Charge, chid, shop)
    try:
        billing.confirm_and_notify(db, shop, ch, user)
    except billing.BillingError as e:
        raise HTTPException(409, str(e))
    receipts.settle(db, ReceiptDecision.CONFIRMED, user, charge_id=ch.id)
    db.commit()
    return charge_out(ch)


@router.post("/charges/{chid}/cancel", response_model=S.ChargeOut, tags=["subscriptions"])
def cancel_charge(chid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    ch = _own(db, Charge, chid, shop)
    if ch.status != PayStatus.PENDING:
        raise HTTPException(409, "Essa cobrança não está mais pendente.")
    billing.cancel_charge(ch)
    if ch.subscription:
        db.flush()
        benefits.refresh_status(db, ch.subscription)
    db.commit()
    return charge_out(ch)


@router.post("/charges/{chid}/resend", response_model=S.ChargeOut, tags=["subscriptions"])
def resend_charge(chid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    ch = _own(db, Charge, chid, shop)
    if ch.status != PayStatus.PENDING:
        raise HTTPException(409, "Essa cobrança não está mais pendente.")
    if not ch.brcode:
        if not billing.pix_ready(shop):
            raise HTTPException(422, "Configure a chave Pix nas configurações")
        billing.GATEWAYS[ch.gateway].issue(shop, ch)
    billing.send_charge(db, shop, ch)
    db.commit()
    return charge_out(ch)
