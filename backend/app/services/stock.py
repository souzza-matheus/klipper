"""Estoque: o saldo é sempre a soma das movimentações (diferenças). Nada sobrescreve o saldo, então duas baixas
feitas ao mesmo tempo (ou uma vinda do app offline) nunca se perdem."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ComandaItem, Product, Service, ServiceProduct, Shop, StockMovement, StockReason, User


class StockError(ValueError):
    pass


def balances(db: Session, shop: Shop, product_ids: list[int] | None = None) -> dict[int, Decimal]:
    q = select(StockMovement.product_id, func.coalesce(func.sum(StockMovement.delta), 0)).where(
        StockMovement.shop_id == shop.id).group_by(StockMovement.product_id)
    if product_ids is not None:
        q = q.where(StockMovement.product_id.in_(product_ids))
    return {pid: Decimal(total) for pid, total in db.execute(q)}


def balance(db: Session, shop: Shop, product: Product) -> Decimal:
    return balances(db, shop, [product.id]).get(product.id, Decimal(0))


def move(db: Session, shop: Shop, product: Product, delta: Decimal, reason: str, user: User | None = None,
         item: ComandaItem | None = None, unit_cost: Decimal | None = None, notes: str = "",
         uuid: str | None = None) -> StockMovement:
    if product.shop_id != shop.id:
        raise StockError("Produto não encontrado.")
    if reason not in StockReason.ALL:
        raise StockError("Motivo inválido.")
    delta = Decimal(delta)
    if delta == 0:
        raise StockError("A quantidade não pode ser zero.")
    m = StockMovement(shop_id=shop.id, product_id=product.id, delta=delta, reason=reason, unit_cost=unit_cost,
                      comanda_item_id=item.id if item else None, user_id=user.id if user else None, notes=notes[:200])
    if uuid:
        m.uuid = uuid
    db.add(m)
    db.flush()
    return m


def consume_for_service(db: Session, shop: Shop, service: Service, quantity: int, item: ComandaItem,
                        user: User | None) -> list[StockMovement]:
    """Baixa os produtos que o serviço consome (cadastro em service_products)."""
    out = []
    for sp in db.scalars(select(ServiceProduct).where(ServiceProduct.service_id == service.id)):
        if sp.product and sp.product.shop_id == shop.id:
            out.append(move(db, shop, sp.product, -sp.quantity * quantity, StockReason.CONSUMPTION, user, item))
    return out


def undo_for_item(db: Session, shop: Shop, item: ComandaItem, reversal: ComandaItem,
                  user: User | None) -> list[StockMovement]:
    """Estorno: devolve ao estoque exatamente o que o item original baixou (movimentos positivos novos)."""
    out = []
    for m in db.scalars(select(StockMovement).where(StockMovement.comanda_item_id == item.id)):
        out.append(move(db, shop, m.product, -m.delta, StockReason.REVERSAL, user, reversal))
    return out


def low_stock(db: Session, shop: Shop) -> list[tuple[Product, Decimal]]:
    products = db.scalars(select(Product).where(Product.shop_id == shop.id, Product.active.is_(True))
                          .order_by(Product.name)).all()
    bal = balances(db, shop, [p.id for p in products])
    return [(p, bal.get(p.id, Decimal(0))) for p in products
            if p.min_stock and bal.get(p.id, Decimal(0)) <= p.min_stock]


def fmt_qty(q: Decimal) -> str:
    q = Decimal(q).normalize()
    return f"{q:f}".replace(".", ",")


def low_stock_text(db: Session, shop: Shop) -> str:
    low = low_stock(db, shop)
    if not low:
        return ""
    lines = [f"• {p.name}: {fmt_qty(q)} {p.unit} (mínimo {fmt_qty(p.min_stock)})" for p, q in low[:15]]
    return "📦 *Estoque baixo*\n" + "\n".join(lines)
