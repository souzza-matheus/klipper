"""Formatação de datas, valores e resumos em português."""
from datetime import date, datetime
from decimal import Decimal

from ..config import now_local

WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
WEEKDAYS_FULL = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def money(v: Decimal | float | int) -> str:
    s = f"{Decimal(v):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def day_label(d: date) -> str:
    today = now_local().date()
    base = f"{WEEKDAYS[d.weekday()]} {d:%d/%m}"
    if d == today:
        return f"Hoje ({base})"
    if (d - today).days == 1:
        return f"Amanhã ({base})"
    return base.capitalize()


def dt_label(dt: datetime) -> str:
    return f"{day_label(dt.date())} às {dt:%H:%M}"


def appt_summary(appt) -> str:
    return (
        f"✂️ *{appt.service.name}* com {appt.barber.name}\n"
        f"📅 {dt_label(appt.start)}\n"
        f"💰 {money(appt.price)}"
    )
