"""Bot do estabelecimento: o dono (ou barbeiro) consulta agenda, horários livres, clientes, Pix e avaliações pelo WhatsApp."""
import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select

from ..config import now_local
from ..models import Appointment, ApptStatus, Barber, Block, Customer, PayStatus, Review
from ..services import scheduling as sch
from ..services.fmt import day_label, dt_label, money
from ..services.payments import confirm_payment, pending_payments
from ..services.whatsapp import phones_match, send_text
from .context import RESET_WORDS, Ctx, pick

STATUS_ICON = {
    ApptStatus.SCHEDULED: "🕐", ApptStatus.CONFIRMED: "✅", ApptStatus.COMPLETED: "✔️",
    ApptStatus.NO_SHOW: "🚫", ApptStatus.CANCELLED: "❌",
}


def staff_barber(ctx: Ctx) -> Barber | None:
    """Retorna o barbeiro dono deste número, se não for o número do dono."""
    if ctx.shop.owner_phone and phones_match(ctx.shop.owner_phone, ctx.phone):
        return None
    for b in ctx.shop.barbers:
        if b.active and b.phone and phones_match(b.phone, ctx.phone):
            return b
    return None


def is_staff(shop, phone: str) -> bool:
    if shop.owner_phone and phones_match(shop.owner_phone, phone):
        return True
    return any(b.active and b.phone and phones_match(b.phone, phone) for b in shop.barbers)


def handle(ctx: Ctx) -> None:
    if ctx.low in RESET_WORDS or ctx.low in ("oi", "ola", "painel", "bom dia", "boa tarde", "boa noite"):
        show_menu(ctx)
        return
    STATES.get(ctx.conv.state, st_menu)(ctx)


def show_menu(ctx: Ctx) -> None:
    b = staff_barber(ctx)
    who = f"Olá, {b.name}! " if b else "Olá! "
    ctx.reset()
    ctx.go("o_menu")
    ctx.say(
        f"{who}Painel da *{ctx.shop.name}* 💈\n\n"
        "*1* - Agenda de hoje\n*2* - Agenda de amanhã\n*3* - Horários livres de um dia\n"
        "*4* - Buscar cliente\n*5* - Pix pendentes\n*6* - Bloquear horário\n"
        "*7* - Avaliações recentes\n*8* - Resumo do dia\n*9* - Testar o bot como cliente"
    )


def st_menu(ctx: Ctx) -> None:
    t = ctx.low
    today = now_local().date()
    if t == "1":
        ctx.say(agenda_text(ctx, today))
    elif t == "2":
        ctx.say(agenda_text(ctx, today + timedelta(days=1)))
    elif t == "3":
        ctx.go("o_free_day")
        ctx.say("Qual dia? Responda *hoje*, *amanhã* ou a data (ex.: 15/10).")
    elif t == "4":
        ctx.go("o_search")
        ctx.say("Digite o nome ou parte do telefone do cliente.")
    elif t == "5":
        list_pix(ctx)
    elif t == "6":
        ctx.go("o_block")
        ctx.say("Envie: *dia início fim motivo*\nEx.: _hoje 14:00 15:00 almoço_ ou _20/10 08:00 18:00 folga_")
    elif t == "7":
        ctx.say(reviews_text(ctx))
    elif t == "8":
        ctx.say(summary_text(ctx, today))
    elif t == "9":
        ctx.reset(keep=())
        ctx.go("menu", as_customer=True)
        ctx.say("Modo cliente ligado. Mande *oi* para ver o bot como seus clientes veem. Para voltar, mande *painel*.")
    else:
        show_menu(ctx)


# ---------------------------------------------------------------- agenda

def parse_day(text: str) -> date | None:
    t = text.strip().lower()
    today = now_local().date()
    if t in ("hoje", "hj"):
        return today
    if t in ("amanha", "amanhã"):
        return today + timedelta(days=1)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
        try:
            result = date(year, mo, d)
        except ValueError:
            return None
        if not y and result < today - timedelta(days=30):
            result = result.replace(year=year + 1)
        return result
    return None


def agenda_text(ctx: Ctx, day: date) -> str:
    me = staff_barber(ctx)
    appts = sch.appointments_on(ctx.db, ctx.shop, day, me.id if me else None)
    if not appts:
        return f"📅 *{day_label(day)}*\n\nNenhum agendamento."
    by_barber: dict[str, list[Appointment]] = {}
    for a in appts:
        by_barber.setdefault(a.barber.name, []).append(a)
    parts = [f"📅 *{day_label(day)}* - {len(appts)} atendimento(s)"]
    for name, items in by_barber.items():
        lines = [f"*{name}*"]
        for a in items:
            pay = " 💰pago" if a.payment_status == PayStatus.PAID else (" ⏳pix" if a.payment_status == PayStatus.PENDING else "")
            lines.append(f"{STATUS_ICON.get(a.status, '')} {a.start:%H:%M} {a.service.name} - {a.customer.name or a.customer.phone}{pay}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def st_free_day(ctx: Ctx) -> None:
    day = parse_day(ctx.text)
    if day is None:
        ctx.say("Não entendi a data. Responda *hoje*, *amanhã* ou dd/mm.")
        return
    services = sch.active_services(ctx.db, ctx.shop)
    if not services:
        ctx.say("Cadastre um serviço no app primeiro.")
        ctx.go("o_menu")
        return
    shortest = min(services, key=lambda s: s.duration_minutes)
    me = staff_barber(ctx)
    barbers = [me] if me else sch.active_barbers(ctx.db, ctx.shop)
    parts = [f"🟢 *Horários livres - {day_label(day)}*\n(considerando {shortest.duration_minutes} min)"]
    for b in barbers:
        slots = sch.free_slots(ctx.db, ctx.shop, shortest, b, day)
        parts.append(f"*{b.name}*: " + (", ".join(f"{s:%H:%M}" for s in slots) if slots else "sem horários livres"))
    ctx.say("\n\n".join(parts))
    ctx.go("o_menu")


# ---------------------------------------------------------------- clientes

def st_search(ctx: Ctx) -> None:
    q = ctx.text.strip()
    digits = re.sub(r"\D", "", q)
    cond = Customer.name.ilike(f"%{q}%")
    if len(digits) >= 4:
        cond = or_(cond, Customer.phone.contains(digits))
    found = ctx.db.scalars(select(Customer).where(Customer.shop_id == ctx.shop.id, cond).limit(5)).all()
    if not found:
        ctx.say("Nenhum cliente encontrado. Tente outro nome ou mande *menu*.")
        return
    parts = []
    now = now_local()
    for c in found:
        appts = ctx.db.scalars(select(Appointment).where(Appointment.customer_id == c.id)
                               .order_by(Appointment.start.desc())).all()
        nxt = [a for a in appts if a.start >= now and a.status in ApptStatus.ACTIVE]
        done = [a for a in appts if a.status == ApptStatus.COMPLETED]
        faltas = sum(1 for a in appts if a.status == ApptStatus.NO_SHOW)
        lines = [f"👤 *{c.name or 'Sem nome'}* - wa.me/{c.phone}",
                 f"Atendimentos: {len(done)} | Faltas: {faltas} | Total: {money(sum(a.price for a in done))}"]
        if done:
            lines.append(f"Último: {dt_label(done[0].start)} ({done[0].service.name})")
        for a in reversed(nxt):
            lines.append(f"Próximo: {dt_label(a.start)} - {a.service.name} com {a.barber.name}")
        parts.append("\n".join(lines))
    ctx.say("\n\n".join(parts))
    ctx.go("o_menu")


# ---------------------------------------------------------------- Pix

def list_pix(ctx: Ctx) -> None:
    pays = pending_payments(ctx.db, ctx.shop)
    if not pays:
        ctx.say("Nenhum Pix pendente. 👍")
        return
    lines = []
    for i, p in enumerate(pays, 1):
        a = p.appointment
        flag = " - 💸 cliente disse que pagou" if p.customer_reported_at else ""
        lines.append(f"*{i}* - {a.customer.name} | {money(p.amount)} | {dt_label(a.start)}{flag}")
    ctx.go("o_pix", payment_ids=[p.id for p in pays])
    ctx.say("⏳ *Pix pendentes*\n\n" + "\n".join(lines) + "\n\nResponda com o número para *confirmar o recebimento*.")


def st_pix(ctx: Ctx) -> None:
    from ..models import Payment
    ids = ctx.get("payment_ids", [])
    i = pick(ctx.text, len(ids))
    if i is None:
        st_menu(ctx)
        return
    pay = ctx.db.get(Payment, ids[i])
    if pay.status != PayStatus.PENDING:
        ctx.say("Esse pagamento não está mais pendente.")
        ctx.go("o_menu")
        return
    confirm_payment(ctx.db, pay)
    a = pay.appointment
    send_text(ctx.db, ctx.shop, a.customer.phone,
              f"✅ Recebemos o seu Pix de {money(pay.amount)}! Seu horário de {dt_label(a.start)} está pago. Até lá! 💈")
    ctx.say(f"Pagamento de {a.customer.name} confirmado e cliente avisado. ✅")
    ctx.go("o_menu")


# ---------------------------------------------------------------- bloqueio

def st_block(ctx: Ctx) -> None:
    m = re.fullmatch(r"\s*(\S+)\s+(\d{1,2}[:h]\d{2})\s+(\d{1,2}[:h]\d{2})\s*(.*)", ctx.text, re.I)
    day = parse_day(m.group(1)) if m else None
    if not m or day is None:
        ctx.say("Formato: *dia início fim motivo*\nEx.: _hoje 14:00 15:00 almoço_")
        return

    def hm(s: str):
        h, mi = re.split(r"[:h]", s.lower())
        return datetime.combine(day, datetime.min.time()).replace(hour=int(h), minute=int(mi))
    try:
        start, end = hm(m.group(2)), hm(m.group(3))
    except ValueError:
        ctx.say("Horário inválido. Use HH:MM, ex.: 14:00.")
        return
    if end <= start:
        ctx.say("O fim precisa ser depois do início.")
        return
    me = staff_barber(ctx)
    ctx.db.add(Block(shop_id=ctx.shop.id, barber_id=me.id if me else None, start=start, end=end,
                     reason=m.group(4).strip()[:120]))
    conflicts = [a for a in sch.appointments_on(ctx.db, ctx.shop, day, me.id if me else None)
                 if a.status in ApptStatus.ACTIVE and a.start < end and a.end > start]
    who = me.name if me else "a barbearia inteira"
    msg = f"🔒 Bloqueado {day_label(day)} das {start:%H:%M} às {end:%H:%M} para {who}."
    if conflicts:
        msg += "\n\n⚠️ Já existem agendamentos nesse intervalo (não foram cancelados):\n" + "\n".join(
            f"{a.start:%H:%M} {a.customer.name} - {a.service.name}" for a in conflicts)
    ctx.say(msg)
    ctx.go("o_menu")


# ---------------------------------------------------------------- avaliações e resumo

def reviews_text(ctx: Ctx) -> str:
    me = staff_barber(ctx)
    q = select(Review).join(Appointment).where(Review.shop_id == ctx.shop.id)
    if me:
        q = q.where(Appointment.barber_id == me.id)
    reviews = ctx.db.scalars(q.order_by(Review.created_at.desc()).limit(8)).all()
    if not reviews:
        return "Nenhuma avaliação ainda."
    avg = sum(r.rating for r in reviews) / len(reviews)
    lines = [f"⭐ *Avaliações recentes* (média {avg:.1f})"]
    for r in reviews:
        a = r.appointment
        lines.append(f"{'⭐' * r.rating} {a.customer.name} - {a.barber.name} ({a.start:%d/%m})"
                     + (f"\n   _{r.comment}_" if r.comment else ""))
    return "\n".join(lines)


def summary_text(ctx: Ctx, day: date) -> str:
    me = staff_barber(ctx)
    start = datetime.combine(day, datetime.min.time())
    q = select(Appointment).where(Appointment.shop_id == ctx.shop.id, Appointment.start >= start,
                                  Appointment.start < start + timedelta(days=1))
    if me:
        q = q.where(Appointment.barber_id == me.id)
    appts = ctx.db.scalars(q).all()
    valid = [a for a in appts if a.status not in (ApptStatus.CANCELLED, ApptStatus.NO_SHOW)]
    cancelled = sum(1 for a in appts if a.status == ApptStatus.CANCELLED)
    no_show = sum(1 for a in appts if a.status == ApptStatus.NO_SHOW)
    paid = sum(a.price for a in valid if a.payment_status == PayStatus.PAID)
    avg = ctx.db.scalar(select(func.avg(Review.rating)).where(
        Review.shop_id == ctx.shop.id, Review.created_at >= start - timedelta(days=6)))
    return (
        f"📊 *Resumo - {day_label(day)}*\n\n"
        f"Atendimentos: {len(valid)}\n"
        f"Cancelamentos: {cancelled}\n"
        f"Faltas: {no_show}\n"
        f"Faturamento previsto: {money(sum(a.price for a in valid))}\n"
        f"Já pago via Pix: {money(paid)}\n"
        f"Nota média (7 dias): {f'{avg:.1f}' if avg else '-'}"
    )


STATES = {
    "o_menu": st_menu,
    "o_free_day": st_free_day,
    "o_search": st_search,
    "o_pix": st_pix,
    "o_block": st_block,
}
