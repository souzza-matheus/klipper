"""Relatórios financeiros: resumo do período com comparação, série diária e exportação CSV."""
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Barber, Expense, ExpenseCategory, PayMethod, Service, Shop
from .commissions import q2
from .expenses import ensure_recurring_range

NO_METHOD = "nao_informado"
NO_METHOD_LABEL = "Não informado"
NO_PRO_LABEL = "Sem profissional"
# "Serviço" no agrupamento por serviço para o que não é serviço (ids negativos não colidem com os do banco)
_KIND_IDS = {"product": 1, "package": 2, "subscription": 3, "deposit": 4}
_KIND_LABELS = {1: "Produtos", 2: "Pacotes", 3: "Assinaturas", 4: "Sinais retidos"}


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return datetime.combine(date_from, datetime.min.time()), datetime.combine(date_to + timedelta(days=1),
                                                                              datetime.min.time())


def _completed(db: Session, shop: Shop, date_from: date, date_to: date):
    """Linhas de faturamento: atendimentos sem comanda, comandas fechadas, cobranças pagas e sinais retidos."""
    from .revenue import lines
    return lines(db, shop, date_from, date_to)


def _paid_expenses(db: Session, shop: Shop, date_from: date, date_to: date) -> list[Expense]:
    """Regime de caixa: o gasto entra no dia em que foi pago."""
    return list(db.scalars(select(Expense).where(
        Expense.shop_id == shop.id, Expense.paid_at >= date_from, Expense.paid_at <= date_to,
    )).all())


def _open_expenses(db: Session, shop: Shop, date_from: date, date_to: date) -> list[Expense]:
    return list(db.scalars(select(Expense).where(
        Expense.shop_id == shop.id, Expense.paid_at.is_(None),
        Expense.due_date >= date_from, Expense.due_date <= date_to,
    )).all())


def _totals(db: Session, shop: Shop, date_from: date, date_to: date) -> dict:
    appts = _completed(db, shop, date_from, date_to)
    revenue = sum((a.price for a in appts), Decimal(0))
    visits = sum(a.visits for a in appts)
    paid = sum((e.amount for e in _paid_expenses(db, shop, date_from, date_to)), Decimal(0))
    return {
        "date_from": date_from, "date_to": date_to, "revenue": q2(revenue), "expenses_paid": q2(paid),
        "profit": q2(revenue - paid), "appointments": visits,
        "avg_ticket": q2(revenue / visits) if visits else Decimal("0.00"),
    }


def change_pct(cur: Decimal | int, prev: Decimal | int) -> Decimal | None:
    """Variação percentual contra o período anterior; None quando não há base de comparação."""
    if not prev:
        return None
    return (Decimal(cur - prev) * 100 / abs(Decimal(prev))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def previous_period(date_from: date, date_to: date) -> tuple[date, date]:
    size = (date_to - date_from).days + 1
    return date_from - timedelta(days=size), date_from - timedelta(days=1)


def summary(db: Session, shop: Shop, date_from: date, date_to: date) -> dict:
    prev_from, prev_to = previous_period(date_from, date_to)
    ensure_recurring_range(db, shop, prev_from, date_to)

    appts = _completed(db, shop, date_from, date_to)
    barbers = dict(db.execute(select(Barber.id, Barber.name).where(Barber.shop_id == shop.id)).all())
    services = dict(db.execute(select(Service.id, Service.name).where(Service.shop_id == shop.id)).all())

    def group(key, name, label_key="name"):
        acc: dict = {}
        for a in appts:
            k = key(a)
            g = acc.setdefault(k, {"id": k, label_key: name(k), "appointments": 0, "revenue": Decimal(0)})
            g["appointments"] += a.visits
            g["revenue"] += a.price
        return sorted(({**g, "revenue": q2(g["revenue"])} for g in acc.values()),
                      key=lambda g: (-g["revenue"], -g["appointments"]))

    by_method = group(lambda a: a.payment_method or NO_METHOD,
                      lambda k: PayMethod.LABELS.get(k, NO_METHOD_LABEL), label_key="label")
    for g in by_method:
        g["method"] = g.pop("id")

    cats: dict[str, dict] = {}
    for kind, rows in (("paid", _paid_expenses(db, shop, date_from, date_to)),
                       ("open", _open_expenses(db, shop, date_from, date_to))):
        for e in rows:
            c = cats.setdefault(e.category, {"category": e.category, "paid": Decimal(0), "open": Decimal(0),
                                             "label": ExpenseCategory.LABELS.get(e.category, e.category)})
            c[kind] += e.amount

    cur = _totals(db, shop, date_from, date_to)
    prev = _totals(db, shop, prev_from, prev_to)
    keys = ("revenue", "expenses_paid", "profit", "avg_ticket", "appointments")
    by_service = group(lambda a: a.service_id if a.kind == "service" else -_KIND_IDS[a.kind],
                       lambda k: services.get(k, "?") if k and k > 0 else _KIND_LABELS[-k])
    for g in by_service:
        g["id"] = g["id"] if g["id"] and g["id"] > 0 else None
    return {
        **cur,
        "expenses_open": q2(sum((c["open"] for c in cats.values()), Decimal(0))),
        "by_barber": group(lambda a: a.barber_id, lambda k: barbers.get(k, NO_PRO_LABEL)),
        "by_service": by_service,
        "by_payment_method": by_method,
        "expenses_by_category": sorted(({**c, "paid": q2(c["paid"]), "open": q2(c["open"])} for c in cats.values()),
                                      key=lambda c: -(c["paid"] + c["open"])),
        "previous": prev,
        "change": {k: change_pct(cur[k], prev[k]) for k in keys},
    }


def daily(db: Session, shop: Shop, date_from: date, date_to: date) -> list[dict]:
    revenue: dict[date, Decimal] = defaultdict(Decimal)
    count: dict[date, int] = defaultdict(int)
    for a in _completed(db, shop, date_from, date_to):
        revenue[a.start.date()] += a.price
        count[a.start.date()] += a.visits
    expenses: dict[date, Decimal] = defaultdict(Decimal)
    for e in _paid_expenses(db, shop, date_from, date_to):
        expenses[e.paid_at] += e.amount
    out = []
    d = date_from
    while d <= date_to:
        out.append({"date": d, "revenue": q2(revenue[d]), "expenses": q2(expenses[d]), "appointments": count[d]})
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------- CSV (Excel em português)

def _br(v: Decimal | None) -> str:
    return "" if v is None else f"{q2(v):.2f}".replace(".", ",")


def _d(v: date | datetime | None) -> str:
    if v is None:
        return ""
    return f"{v:%d/%m/%Y %H:%M}" if isinstance(v, datetime) else f"{v:%d/%m/%Y}"


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Evita injeção de fórmula no Excel/Sheets: texto que começa com = + - @ (ex.: nome de cliente vindo do
    WhatsApp) ganha um apóstrofo na frente e é mostrado como texto."""
    if isinstance(value, str) and len(value) > 1 and value.startswith(_FORMULA_START):
        return "'" + value
    return value


class _SafeWriter:
    def __init__(self, writer):
        self._w = writer

    def writerow(self, row):
        self._w.writerow([csv_safe(v) for v in row])


def export_csv(db: Session, shop: Shop, date_from: date, date_to: date) -> bytes:
    """Atendimentos concluídos e gastos do período. Separador ;, vírgula decimal e BOM: abre direto no Excel."""
    ensure_recurring_range(db, shop, date_from, date_to)
    rows = _completed(db, shop, date_from, date_to)
    barbers = dict(db.execute(select(Barber.id, Barber.name).where(Barber.shop_id == shop.id)).all())
    expenses = db.scalars(select(Expense).where(
        Expense.shop_id == shop.id,
        ((Expense.due_date >= date_from) & (Expense.due_date <= date_to))
        | ((Expense.paid_at >= date_from) & (Expense.paid_at <= date_to)),
    ).order_by(Expense.due_date, Expense.description)).all()

    buf = io.StringIO()
    w = _SafeWriter(csv.writer(buf, delimiter=";", lineterminator="\r\n"))
    w.writerow([f"{shop.name} - financeiro de {_d(date_from)} a {_d(date_to)}"])
    w.writerow([])
    w.writerow(["ATENDIMENTOS E VENDAS"])
    w.writerow(["Data", "Cliente", "Profissional", "Item", "Forma de pagamento", "Valor (R$)"])
    for a in rows:
        w.writerow([_d(a.start), a.customer_name, barbers.get(a.barber_id, ""), a.label,
                    PayMethod.LABELS.get(a.payment_method or "", NO_METHOD_LABEL), _br(a.price)])
    w.writerow(["Total", "", "", "", "", _br(sum((r.price for r in rows), Decimal(0)))])
    w.writerow([])
    w.writerow(["GASTOS"])
    w.writerow(["Vencimento", "Descrição", "Categoria", "Barbeiro", "Situação", "Pago em", "Forma de pagamento",
                "Valor (R$)", "Observações"])
    for e in expenses:
        w.writerow([_d(e.due_date), e.description, ExpenseCategory.LABELS.get(e.category, e.category),
                    e.barber.name if e.barber else "", "Pago" if e.paid_at else "Em aberto", _d(e.paid_at),
                    PayMethod.LABELS.get(e.payment_method or "", ""), _br(e.amount), e.notes])
    w.writerow(["Total", "", "", "", "", "", "", _br(sum((e.amount for e in expenses), Decimal(0))), ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")
