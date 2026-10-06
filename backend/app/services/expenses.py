"""Gastos da barbearia: meses, contas recorrentes e aviso de contas a pagar."""
import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Expense, ExpenseCategory, Shop
from .fmt import money

MAX_MONTHS = 24  # limite de meses gerados numa consulta de período longo


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def months_between(date_from: date, date_to: date) -> list[tuple[int, int]]:
    out = []
    y, m = date_from.year, date_from.month
    while (y, m) <= (date_to.year, date_to.month) and len(out) < MAX_MONTHS:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def same_day_in(year: int, month: int, day: int) -> date:
    """Mesmo dia em outro mês; 31 vira o último dia de meses mais curtos."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def ensure_recurring(db: Session, shop: Shop, year: int, month: int) -> int:
    """Gera, para o mês, as cópias dos gastos recorrentes que ainda não existem. Retorna quantas criou."""
    first, last = month_bounds(year, month)
    sources = db.scalars(select(Expense).where(
        Expense.shop_id == shop.id, Expense.recurring.is_(True), Expense.due_date < first,
    )).all()
    if not sources:
        return 0
    done = set(db.scalars(select(Expense.recurring_source_id).where(
        Expense.recurring_source_id.in_([s.id for s in sources]),
        Expense.due_date >= first, Expense.due_date <= last,
    )))
    created = 0
    for src in sources:
        if src.id in done:
            continue
        db.add(Expense(
            shop_id=shop.id, description=src.description, category=src.category, amount=src.amount,
            due_date=same_day_in(year, month, src.due_date.day), barber_id=src.barber_id,
            recurring=False, recurring_source_id=src.id, notes=src.notes,
        ))
        created += 1
    if created:
        db.flush()
    return created


def ensure_recurring_range(db: Session, shop: Shop, date_from: date, date_to: date) -> int:
    return sum(ensure_recurring(db, shop, y, m) for y, m in months_between(date_from, date_to))


def bills_due(db: Session, shop: Shop, today: date) -> list[Expense]:
    """Contas em aberto que vencem hoje ou já venceram."""
    return list(db.scalars(select(Expense).where(
        Expense.shop_id == shop.id, Expense.paid_at.is_(None), Expense.due_date <= today,
    ).order_by(Expense.due_date, Expense.description)).all())


def bills_text(db: Session, shop: Shop, today: date, limit: int = 10) -> str:
    """Trecho do resumo diário do dono. Vazio quando não há contas para avisar."""
    ensure_recurring(db, shop, today.year, today.month)
    bills = bills_due(db, shop, today)
    if not bills:
        return ""
    lines = ["💸 *Contas a pagar*"]
    for e in bills[:limit]:
        when = "vence hoje" if e.due_date == today else f"venceu {e.due_date:%d/%m}"
        lines.append(f"• {e.description} ({ExpenseCategory.LABELS.get(e.category, e.category)}) - "
                     f"{money(e.amount)} · {when}")
    if len(bills) > limit:
        lines.append(f"... e mais {len(bills) - limit}. Veja no app em Financeiro > Gastos.")
    total = sum((e.amount for e in bills), Decimal(0))
    lines.append(f"Total: *{money(total)}*")
    return "\n".join(lines)


def is_overdue(e: Expense, today: date) -> bool:
    return e.paid_at is None and e.due_date < today

