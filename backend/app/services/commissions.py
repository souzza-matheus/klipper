"""Comissões e repasses entre barbeiros: regras vigentes, validação dos 100% e cálculo por período."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Barber, Beneficiary, CommissionRule, CommissionSettlement, Shop

CENT = Decimal("0.01")
SHOP_LABEL = "Barbearia"

BenefKey = tuple[str, int | None]  # (beneficiary_type, beneficiary_barber_id)


def q2(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def key_of(obj) -> BenefKey:
    return obj.beneficiary_type, obj.beneficiary_barber_id if obj.beneficiary_type == Beneficiary.BARBER else None


def valid_on(rule: CommissionRule, day: date) -> bool:
    return rule.valid_from <= day and (rule.valid_to is None or day <= rule.valid_to)


def effective_rules(rules: list[CommissionRule], day: date, service_id: int | None) -> dict[BenefKey, CommissionRule]:
    """Regra que vale para cada beneficiário num dia e serviço. A de serviço substitui a geral;
    entre regras do mesmo tipo, vale a que começou por último."""
    best: dict[BenefKey, CommissionRule] = {}
    for r in rules:
        if not valid_on(r, day):
            continue
        specific = r.service_id is not None
        if specific and r.service_id != service_id:
            continue
        k = key_of(r)
        cur = best.get(k)
        rank = (specific, r.valid_from, r.id or 0)
        if cur is None or rank > (cur.service_id is not None, cur.valid_from, cur.id or 0):
            best[k] = r
    return best


def check_total(db: Session, candidate: CommissionRule) -> None:
    """Garante que, em nenhum dia de vigência da regra e para nenhum serviço, os repasses do barbeiro passem de 100%."""
    others = db.scalars(select(CommissionRule).where(
        CommissionRule.barber_id == candidate.barber_id,
        CommissionRule.id != (candidate.id or 0),
    )).all()
    rules = [*others, candidate]
    start, end = candidate.valid_from, candidate.valid_to
    # Os totais só mudam quando alguma regra começa ou termina
    days = {start}
    for r in others:
        for d in (r.valid_from, r.valid_to + timedelta(days=1) if r.valid_to else None):
            if d and start <= d and (end is None or d <= end):
                days.add(d)
    services = {None} | {r.service_id for r in rules if r.service_id}
    for d in days:
        for sid in services:
            total = sum((r.percentage for r in effective_rules(rules, d, sid).values()), Decimal(0))
            if total > 100:
                raise ValueError(f"Os repasses deste barbeiro somariam {total:.2f}% a partir de {d:%d/%m/%Y}. "
                                 "O máximo é 100%.")


def beneficiary_name(btype: str, barber: Barber | None) -> str:
    if btype == Beneficiary.SHOP:
        return SHOP_LABEL
    return barber.name if barber else "?"


def report(db: Session, shop: Shop, date_from: date, date_to: date, only_barber_id: int | None = None) -> dict:
    """Comissões do período. only_barber_id: visão do profissional (só a linha dele)."""
    from .revenue import commission_lines, extras_by_barber
    barbers = {b.id: b for b in db.scalars(select(Barber).where(Barber.shop_id == shop.id))}
    appts = commission_lines(db, shop, date_from, date_to)
    extras = extras_by_barber(db, shop, date_from, date_to)
    rules_by_barber: dict[int, list[CommissionRule]] = defaultdict(list)
    for r in db.scalars(select(CommissionRule).where(CommissionRule.shop_id == shop.id)):
        rules_by_barber[r.barber_id].append(r)
    # Acertos contam no período quando estão inteiramente dentro dele
    settlements = db.scalars(select(CommissionSettlement).where(
        CommissionSettlement.shop_id == shop.id,
        CommissionSettlement.period_start >= date_from, CommissionSettlement.period_end <= date_to,
    )).all()

    gross: dict[int, Decimal] = defaultdict(Decimal)
    count: dict[int, int] = defaultdict(int)
    dues: dict[int, dict[BenefKey, dict]] = defaultdict(dict)
    for a in appts:
        gross[a.barber_id] += a.base
        count[a.barber_id] += 1 if a.base >= 0 else -1  # estorno desconta o atendimento
        for k, r in effective_rules(rules_by_barber[a.barber_id], a.day, a.service_id).items():
            d = dues[a.barber_id].setdefault(k, {"base": Decimal(0), "amount": Decimal(0), "pcts": set()})
            d["base"] += a.base
            d["amount"] += a.base * r.percentage / 100
            d["pcts"].add(r.percentage)

    settled: dict[int, dict[BenefKey, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for st in settlements:
        settled[st.payer_barber_id][key_of(st)] += st.amount

    received: dict[int, Decimal] = defaultdict(Decimal)
    for payer_dues in dues.values():
        for (btype, bid), d in payer_dues.items():
            if btype == Beneficiary.BARBER and bid:
                received[bid] += q2(d["amount"])

    rows = []
    for bid, b in sorted(barbers.items(), key=lambda x: x[1].name):
        if only_barber_id is not None and bid != only_barber_id:
            continue
        ex = extras.get(bid, {"tips": Decimal("0.00"), "product_commission": Decimal("0.00")})
        if not (count[bid] or dues[bid] or settled[bid] or received[bid] or any(ex.values())):
            continue
        keys = list(dues[bid]) + [k for k in settled[bid] if k not in dues[bid]]
        due_rows = []
        for k in keys:
            d = dues[bid].get(k, {"base": Decimal(0), "amount": Decimal(0), "pcts": set()})
            amount, paid = q2(d["amount"]), q2(settled[bid][k])
            due_rows.append({
                "beneficiary_type": k[0], "beneficiary_barber_id": k[1],
                "beneficiary_name": beneficiary_name(k[0], barbers.get(k[1])),
                "percentages": sorted(d["pcts"]), "base": q2(d["base"]),
                "amount": amount, "settled": paid, "open": amount - paid,
            })
        due_rows.sort(key=lambda x: -x["amount"])
        total_due = sum((x["amount"] for x in due_rows), Decimal(0))
        total_paid = sum((x["settled"] for x in due_rows), Decimal(0))
        rows.append({
            "barber_id": bid, "barber_name": b.name, "gross": q2(gross[bid]), "appointments": count[bid],
            "dues": due_rows, "total_due": total_due, "net": q2(gross[bid]) - total_due,
            "received": received[bid], "settled": total_paid, "open": total_due - total_paid,
            "tips": ex["tips"], "product_commission": ex["product_commission"],
        })

    return {
        "date_from": date_from, "date_to": date_to, "barbers": rows,
        "total_gross": sum((r["gross"] for r in rows), Decimal(0)),
        "total_due": sum((r["total_due"] for r in rows), Decimal(0)),
        "total_open": sum((r["open"] for r in rows), Decimal(0)),
    }
