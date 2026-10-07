"""Bot do cliente: agendar, consultar, cancelar, remarcar, pagar via Pix, informações e pesquisa de satisfação."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from ..config import now_local
from ..models import AccessStatus, Appointment, ApptStatus, Barber, ConflictAction, PayStatus, Review, Service
from ..services import approvals
from ..services import scheduling as sch
from ..services.fmt import WEEKDAYS_FULL, appt_summary, day_label, dt_label, money
from ..services.notify import notify_staff
from ..services.payments import get_or_create_pix, pix_messages, pix_ready
from .context import RESET_WORDS, Ctx, pick

FOOTER = "\n\nResponda com o número de outra opção ou *menu* para ver o menu."
# Cliente bloqueado: resposta neutra, sem dizer que houve bloqueio
MSG_BLOCKED = "No momento não conseguimos agendar por aqui. Por favor, fale com a barbearia."


# ---------------------------------------------------------------- entrada

# Estados em que a resposta é sempre do fluxo atual (não passa pela IA)
DETERMINISTIC_STATES = {"reminder", "survey_rating", "survey_comment", "book_name"}
HUMAN_WORDS = {"atendente", "humano", "falar com atendente", "falar com alguem", "pessoa"}
CONFIRM_WORDS = {"1", "sim", "s", "confirmar", "confirmo", "confirma", "pode", "ok", "isso", "fechado", "beleza"}
OTHER_WORDS = {"2", "outro", "outra", "outro horario", "escolher outro"}
GIVE_UP_WORDS = {"3", "nao", "n", "desistir", "desisto", "deixa", "deixa pra la"}


def _numeric(text: str) -> bool:
    return pick(text, 999) is not None


def handle(ctx: Ctx) -> None:
    _handle(ctx)
    if ctx.shop.ai_enabled and not ctx.via_ai:
        from ..ai import agent  # import tardio: app.ai importa este módulo
        agent.record_menu_turn(ctx)


def _handle(ctx: Ctx) -> None:
    conv = ctx.conv
    if conv.paused_until and conv.paused_until > now_local():
        if ctx.low in RESET_WORDS or ctx.low == "bot":
            conv.paused_until = None
            ctx.reset()
            show_menu(ctx)
        return  # atendimento humano em andamento: o bot fica em silêncio

    if ctx.low in RESET_WORDS:
        ctx.reset()
        show_menu(ctx)
        return

    if ctx.low in HUMAN_WORDS:
        talk_to_human(ctx)
        return

    if conv.state not in ("survey_rating", "survey_comment") and _looks_like_paid(ctx) and _report_paid(ctx):
        return

    # Modo híbrido: números, respostas de confirmação, lembrete e pesquisa seguem o fluxo atual (sem gastar IA);
    # texto livre vai para o agente de IA quando ele está disponível para a barbearia.
    handler = STATES.get(conv.state, st_menu)
    deterministic = (conv.state in DETERMINISTIC_STATES or _numeric(ctx.text)
                     or (conv.state == "ai_confirm" and ctx.low in CONFIRM_WORDS | OTHER_WORDS | GIVE_UP_WORDS))
    if not deterministic:
        from ..ai import agent
        outcome = agent.respond(ctx)
        if outcome == "ok":
            return
        if outcome == "failed":  # erro, cota, tempo esgotado: o cliente nunca fica sem resposta
            ctx.reset()
            show_menu(ctx)
            return
    handler(ctx)


def customer(ctx: Ctx):
    return sch.get_or_create_customer(ctx.db, ctx.shop, ctx.phone)


def show_menu(ctx: Ctx) -> None:
    c = customer(ctx)
    first = (c.name or ctx.push_name or "").split(" ")[0]
    hello = f"Olá, {first}! " if first else "Olá! "
    lines = [
        f"{hello}Bem-vindo à *{ctx.shop.name}* 💈",
    ]
    if ctx.shop.welcome_text:
        lines.append(ctx.shop.welcome_text)
    options = [
        "*1* - Agendar horário",
        "*2* - Meus agendamentos",
        "*3* - Serviços e preços",
        "*4* - Nossos barbeiros",
        "*5* - Horário de funcionamento e endereço",
        "*6* - Pagar agendamento via Pix" if pix_ready(ctx.shop) else None,
        "*7* - Falar com a barbearia",
    ]
    ctx.say("\n".join(lines) + "\n\n" + "\n".join(o for o in options if o) + "\n\nResponda com o número da opção.")
    ctx.reset()


def st_menu(ctx: Ctx) -> None:
    t = ctx.low
    actions = {
        "1": start_booking, "2": my_appointments, "3": info_services, "4": info_barbers,
        "5": info_hours, "6": pay_menu, "7": talk_to_human,
    }
    if t in ("agendar", "marcar", "horario"):
        t = "1"
    if t == "6" and not pix_ready(ctx.shop):
        t = ""
    fn = actions.get(t)
    if fn:
        fn(ctx)
    else:
        show_menu(ctx)


# ---------------------------------------------------------------- agendamento

def _blocked(ctx: Ctx) -> bool:
    if customer(ctx).access_status != AccessStatus.BLOCKED:
        return False
    ctx.say(MSG_BLOCKED + FOOTER)
    ctx.reset()
    return True


def start_booking(ctx: Ctx, reschedule_of: int | None = None, service_id: int | None = None) -> None:
    if _blocked(ctx):
        return
    services = sch.active_services(ctx.db, ctx.shop)
    if not services:
        ctx.say("No momento não há serviços disponíveis para agendamento. Fale com a barbearia (opção 7).")
        return
    ctx.reset()
    ctx.go("book_service", reschedule_of=reschedule_of)
    if service_id:
        ctx.go("book_service", service_id=service_id)
        _after_service(ctx)
        return
    if len(services) == 1:
        ctx.go("book_service", service_id=services[0].id)
        _after_service(ctx)
        return
    lines = [f"*{i}* - {s.name} ({s.duration_minutes} min) - {money(s.price)}" for i, s in enumerate(services, 1)]
    ctx.go("book_service", service_ids=[s.id for s in services])
    ctx.say("Qual serviço você quer?\n\n" + "\n".join(lines))


def st_book_service(ctx: Ctx) -> None:
    ids = ctx.get("service_ids", [])
    i = pick(ctx.text, len(ids))
    if i is None:
        ctx.say(f"Responda com um número de 1 a {len(ids)}, ou *menu* para voltar.")
        return
    ctx.go("book_service", service_id=ids[i])
    _after_service(ctx)


def _service(ctx: Ctx) -> Service:
    return ctx.db.get(Service, ctx.get("service_id"))


def _after_service(ctx: Ctx) -> None:
    barbers = sch.active_barbers(ctx.db, ctx.shop, _service(ctx))
    if not barbers:
        ctx.say("Nenhum barbeiro atende esse serviço no momento. Fale com a barbearia (opção 7).")
        ctx.reset()
        return
    if len(barbers) == 1:
        ctx.go("book_barber", barber_id=barbers[0].id)
        ask_day(ctx)
        return
    lines = [f"*{i}* - {b.name}" for i, b in enumerate(barbers, 1)]
    lines.append(f"*{len(barbers) + 1}* - Tanto faz (primeiro disponível)")
    ctx.go("book_barber", barber_ids=[b.id for b in barbers])
    ctx.say("Com qual barbeiro?\n\n" + "\n".join(lines))


def st_book_barber(ctx: Ctx) -> None:
    ids = ctx.get("barber_ids", [])
    i = pick(ctx.text, len(ids) + 1)
    if i is None:
        ctx.say(f"Responda com um número de 1 a {len(ids) + 1}, ou *menu* para voltar.")
        return
    ctx.go("book_barber", barber_id=ids[i] if i < len(ids) else None)
    ask_day(ctx)


def _barber(ctx: Ctx) -> Barber | None:
    bid = ctx.get("barber_id")
    return ctx.db.get(Barber, bid) if bid else None


def ask_day(ctx: Ctx, prefix: str = "") -> None:
    days = sch.open_days(ctx.db, ctx.shop, _service(ctx), _barber(ctx))
    if not days:
        ctx.say("Não encontrei dias com atendimento nos próximos dias. Fale com a barbearia (opção 7).")
        ctx.reset()
        return
    lines = [f"*{i}* - {day_label(d)}" for i, d in enumerate(days, 1)]
    ctx.go("book_day", days=[d.isoformat() for d in days])
    ctx.say((prefix + "\n\n" if prefix else "") + "Para qual dia?\n\n" + "\n".join(lines))


def st_book_day(ctx: Ctx) -> None:
    days = ctx.get("days", [])
    i = pick(ctx.text, len(days))
    if i is None:
        ctx.say(f"Responda com um número de 1 a {len(days)}, ou *menu* para voltar.")
        return
    show_times(ctx, date.fromisoformat(days[i]))


def bookable_slots(ctx: Ctx, service: Service, barber: Barber | None, day: date,
                   ignore_appt_id: int | None = None) -> list[tuple[datetime, int]]:
    """Horários que este cliente pode pedir pelo WhatsApp: (início, id do barbeiro). Usado pelo menu e pela IA.
    Com o cliente, some também o que fica perto demais de alguém em conflito com ele (sem explicar o motivo).
    Conflitos "approval" não escondem o horário: viram pedido para o dono aprovar."""
    c = customer(ctx)
    if barber:
        slots = [(s, barber.id) for s in sch.free_slots(ctx.db, ctx.shop, service, barber, day, ignore_appt_id,
                                                        customer=c, only_blocking=True)]
    else:
        slots = [(s, b.id) for s, b in sch.free_slots_any(ctx.db, ctx.shop, service, day, customer=c,
                                                          only_blocking=True)]
    earliest = now_local() + approvals.APPROVAL_MIN_LEAD  # o dono precisa de tempo para responder antes de expirar
    if c.access_status == AccessStatus.APPROVAL:
        return [x for x in slots if x[0] >= earliest]
    duration = timedelta(minutes=service.duration_minutes)
    needs_ok = [(ws, we) for ws, we, hit in sch.conflict_windows(ctx.db, ctx.shop, c, day)
                if hit.conflict.conflict_action == ConflictAction.APPROVAL]
    return [x for x in slots
            if x[0] >= earliest or not any(x[0] < we and x[0] + duration > ws for ws, we in needs_ok)]


def show_times(ctx: Ctx, day: date, prefix: str = "") -> None:
    slots = bookable_slots(ctx, _service(ctx), _barber(ctx), day, ctx.get("reschedule_of"))
    if not slots:
        ask_day(ctx, prefix=f"Não há horários livres em {day_label(day).lower()}. 😕")
        return
    slots = slots[:40]
    cells = [f"*{i}* - {s:%H:%M}" for i, (s, _) in enumerate(slots, 1)]
    rows = ["    ".join(cells[k:k + 3]) for k in range(0, len(cells), 3)]
    ctx.go("book_time", day=day.isoformat(), slots=[[s.isoformat(), b] for s, b in slots])
    head = (prefix + "\n\n" if prefix else "") + f"Horários livres em *{day_label(day)}*:"
    ctx.say(head + "\n\n" + "\n".join(rows) + "\n\nResponda com o número do horário.")


def st_book_time(ctx: Ctx) -> None:
    slots = ctx.get("slots", [])
    i = pick(ctx.text, len(slots))
    if i is None:
        ctx.say(f"Responda com um número de 1 a {len(slots)}, ou *menu* para voltar.")
        return
    start, barber_id = slots[i]
    ctx.go("book_time", start=start, slot_barber_id=barber_id)
    if not customer(ctx).name:
        ctx.go("book_name")
        ctx.say("Qual é o seu nome?")
        return
    show_confirm(ctx)


def st_book_name(ctx: Ctx) -> None:
    name = ctx.text.strip()[:120]
    if len(name) < 2:
        ctx.say("Me diga seu nome, por favor.")
        return
    customer(ctx).name = name.title()
    show_confirm(ctx)


def show_confirm(ctx: Ctx) -> None:
    service = _service(ctx)
    barber = ctx.db.get(Barber, ctx.get("slot_barber_id"))
    start = datetime.fromisoformat(ctx.get("start"))
    title = "Confirma a remarcação?" if ctx.get("reschedule_of") else "Confirma o agendamento?"
    ctx.go("book_confirm")
    ctx.say(
        f"{title}\n\n✂️ *{service.name}* com {barber.name}\n📅 {dt_label(start)}\n💰 {money(service.price)}\n\n"
        "*1* - Confirmar\n*2* - Escolher outro horário\n*3* - Desistir"
    )


def st_book_confirm(ctx: Ctx) -> None:
    t = ctx.low
    if t in ("1", "sim", "s", "confirmar", "confirmo"):
        _do_book(ctx)
    elif t == "2":
        show_times(ctx, date.fromisoformat(ctx.get("day")))
    elif t in ("3", "nao", "n", "desistir"):
        ctx.say("Tudo bem, não agendei nada. Quando quiser é só chamar! 👋")
        ctx.reset()
    else:
        ctx.say("Responda *1* para confirmar, *2* para outro horário ou *3* para desistir.")


def _do_book(ctx: Ctx) -> None:
    db, shop = ctx.db, ctx.shop
    service = _service(ctx)
    barber = db.get(Barber, ctx.get("slot_barber_id"))
    start = datetime.fromisoformat(ctx.get("start"))
    c = customer(ctx)
    if _blocked(ctx):  # o acesso pode ter mudado no meio da conversa
        return
    pending = c.access_status == AccessStatus.APPROVAL
    old_id = ctx.get("reschedule_of")
    old_label = dt_label(db.get(Appointment, old_id).start) if old_id else ""

    def book(force: bool = False):
        status = ApptStatus.PENDING_APPROVAL if pending else ApptStatus.SCHEDULED
        if old_id:
            return sch.reschedule_appointment(db, shop, db.get(Appointment, old_id), start, barber, status=status,
                                              force=force)
        return sch.create_appointment(db, shop, c, barber, service, start, status=status, force=force)

    try:
        try:
            appt = book()
        except sch.ConflictError as e:
            if e.hit.conflict.conflict_action != ConflictAction.APPROVAL:
                raise
            # Perto de um cliente em conflito com "exigir aprovação": vira pedido (o cliente não sabe o motivo)
            pending = True
            appt = book(force=True)
    except sch.SchedulingError:  # inclui conflito "block": a mensagem é a mesma de horário ocupado
        show_times(ctx, start.date(), prefix="Poxa, esse horário acabou de ser ocupado. 😕 Escolha outro:")
        return

    if pending:
        ctx.say(f"{approvals.MSG_RECEIVED}\n\n{appt_summary(appt)}")
        approvals.alert_owner(db, shop, appt, rescheduled_from=old_label if old_id else "")
        ctx.reset()
        return

    if old_id:
        ctx.say(f"✅ Remarcado!\n\n{appt_summary(appt)}\n\nTe mando um lembrete antes do horário.")
        notify_staff(db, shop, f"🔁 *Remarcação*\n{c.name} ({c.phone})\nDe: {old_label}\nPara:\n{appt_summary(appt)}",
                     appt.barber)
        ctx.reset()
        return

    notify_staff(db, shop, f"🆕 *Novo agendamento*\n{c.name} ({c.phone})\n{appt_summary(appt)}", appt.barber)
    if pix_ready(shop):
        ctx.go("book_pay", appt_id=appt.id)
        ctx.say(f"✅ Agendado!\n\n{appt_summary(appt)}\n\nQuer adiantar o pagamento?\n\n"
                "*1* - Pagar agora via Pix\n*2* - Pagar na barbearia")
    else:
        ctx.say(f"✅ Agendado!\n\n{appt_summary(appt)}\n\nTe mando um lembrete antes do horário. "
                "Para cancelar ou remarcar, é só mandar *menu* e escolher a opção 2.")
        ctx.reset()


def st_book_pay(ctx: Ctx) -> None:
    appt = ctx.db.get(Appointment, ctx.get("appt_id"))
    if ctx.low == "1":
        send_pix(ctx, appt)
        ctx.reset()
    elif ctx.low == "2":
        ctx.say("Combinado, pagamento na barbearia. Te mando um lembrete antes do horário! 👊")
        ctx.reset()
    else:
        ctx.say("Responda *1* para pagar agora via Pix ou *2* para pagar na barbearia.")


def send_pix(ctx: Ctx, appt: Appointment) -> None:
    if appt.payment_status == PayStatus.PAID:
        ctx.say("Esse agendamento já está pago. ✅")
        return
    pay = get_or_create_pix(ctx.db, ctx.shop, appt)
    ctx.say(*pix_messages(ctx.shop, appt, pay))


# ---------------------------------------------------------------- meus agendamentos

def my_appointments(ctx: Ctx) -> None:
    appts = sch.upcoming_for_customer(ctx.db, ctx.shop, customer(ctx))
    if not appts:
        ctx.say("Você não tem agendamentos futuros. Responda *1* para agendar." + FOOTER)
        ctx.reset()
        return
    lines = []
    for i, a in enumerate(appts, 1):
        paid = " (pago ✅)" if a.payment_status == PayStatus.PAID else ""
        if a.status == ApptStatus.PENDING_APPROVAL:
            paid = " (aguardando confirmação ⏳)"
        lines.append(f"*{i}* - {dt_label(a.start)} | {a.service.name} com {a.barber.name}{paid}")
    ctx.go("my_pick", appt_ids=[a.id for a in appts])
    ctx.say("Seus próximos agendamentos:\n\n" + "\n".join(lines) + "\n\nResponda com o número para cancelar, remarcar ou pagar.")


def st_my_pick(ctx: Ctx) -> None:
    ids = ctx.get("appt_ids", [])
    i = pick(ctx.text, len(ids))
    if i is None:
        st_menu(ctx)  # permite pular direto para outra opção do menu
        return
    appt = ctx.db.get(Appointment, ids[i])
    options = ["*1* - Cancelar", "*2* - Remarcar"]
    if pix_ready(ctx.shop) and appt.payment_status != PayStatus.PAID and appt.status in ApptStatus.ACTIVE:
        options.append("*3* - Pagar via Pix")
    options.append("*4* - Voltar ao menu")
    ctx.go("my_action", appt_id=appt.id)
    ctx.say(appt_summary(appt) + "\n\nO que você quer fazer?\n\n" + "\n".join(options))


def _my_appt(ctx: Ctx) -> Appointment | None:
    appt = ctx.db.get(Appointment, ctx.get("appt_id") or 0)
    if appt and appt.customer.phone == ctx.phone and appt.status in ApptStatus.OCCUPYING:
        return appt
    return None


def st_my_action(ctx: Ctx) -> None:
    appt = _my_appt(ctx)
    if appt is None:
        show_menu(ctx)
        return
    t = ctx.low
    if t == "1":
        if not sch.can_customer_cancel(ctx.shop, appt):
            ctx.say(f"O cancelamento pelo WhatsApp é só até {ctx.shop.cancel_min_hours}h antes do horário. "
                    "Responda *7* para falar com a barbearia.")
            ctx.reset()
            return
        ctx.go("my_cancel_confirm")
        ctx.say(f"Cancelar este horário?\n\n{appt_summary(appt)}\n\n*1* - Sim, cancelar\n*2* - Não")
    elif t == "2":
        if not sch.can_customer_cancel(ctx.shop, appt):
            ctx.say(f"A remarcação pelo WhatsApp é só até {ctx.shop.cancel_min_hours}h antes do horário. "
                    "Responda *7* para falar com a barbearia.")
            ctx.reset()
            return
        start_booking(ctx, reschedule_of=appt.id, service_id=appt.service_id)
    elif t == "3" and pix_ready(ctx.shop) and appt.status in ApptStatus.ACTIVE:
        send_pix(ctx, appt)
        ctx.reset()
    else:
        show_menu(ctx)


def st_my_cancel_confirm(ctx: Ctx) -> None:
    appt = _my_appt(ctx)
    if appt and ctx.low in ("1", "sim", "s"):
        _cancel(ctx, appt)
    else:
        ctx.say("Ok, mantive o seu horário. 👍" + FOOTER)
    ctx.reset()


def _cancel(ctx: Ctx, appt: Appointment) -> None:
    paid = appt.payment_status == PayStatus.PAID
    sch.cancel_appointment(ctx.db, appt)
    msg = "Agendamento cancelado. ❌"
    if paid:
        msg += "\nComo o pagamento já tinha sido feito, a barbearia vai entrar em contato sobre o valor."
    ctx.say(msg + "\nQuando quiser marcar de novo, é só mandar *1*.")
    c = appt.customer
    notify_staff(
        ctx.db, ctx.shop,
        f"❌ *Cancelamento*\n{c.name} ({c.phone})\n{appt_summary(appt)}\n\n"
        f"O horário de {dt_label(appt.start)} com {appt.barber.name} ficou livre."
        + ("\n⚠️ Esse cliente já tinha pago via Pix." if paid else ""),
        appt.barber,
    )


# ---------------------------------------------------------------- informações

def info_services(ctx: Ctx) -> None:
    services = sch.active_services(ctx.db, ctx.shop)
    lines = [f"• *{s.name}* - {money(s.price)} ({s.duration_minutes} min)" for s in services]
    ctx.say("💈 *Serviços e preços*\n\n" + ("\n".join(lines) or "Nenhum serviço cadastrado.") + FOOTER)
    ctx.reset()


def info_barbers(ctx: Ctx) -> None:
    lines = []
    for b in sch.active_barbers(ctx.db, ctx.shop):
        line = f"• *{b.name}*"
        if b.bio:
            line += f" - {b.bio}"
        if b.services:
            line += f"\n  Faz: {', '.join(s.name for s in b.services if s.active)}"
        lines.append(line)
    ctx.say("✂️ *Nossos barbeiros*\n\n" + ("\n".join(lines) or "Nenhum barbeiro cadastrado.") + FOOTER)
    ctx.reset()


def opening_hours(ctx: Ctx) -> list[str]:
    by_day: dict[int, list] = {}
    for b in sch.active_barbers(ctx.db, ctx.shop):
        for wh in b.working_hours:
            by_day.setdefault(wh.weekday, []).append(wh)
    lines = []
    for d in range(7):
        whs = by_day.get(d)
        if whs:
            lines.append(f"{WEEKDAYS_FULL[d].capitalize()}: {min(w.start for w in whs):%H:%M} às {max(w.end for w in whs):%H:%M}")
        else:
            lines.append(f"{WEEKDAYS_FULL[d].capitalize()}: fechado")
    return lines


def info_hours(ctx: Ctx) -> None:
    shop = ctx.shop
    parts = ["🕐 *Horário de funcionamento*\n" + "\n".join(opening_hours(ctx))]
    if shop.address:
        parts.append(f"📍 *Endereço*\n{shop.address}")
    if shop.phone:
        parts.append(f"📞 {shop.phone}")
    if shop.instagram:
        parts.append(f"📸 Instagram: {shop.instagram}")
    ctx.say("\n\n".join(parts) + FOOTER)
    ctx.reset()


# ---------------------------------------------------------------- Pix

def pay_menu(ctx: Ctx) -> None:
    # Pix só depois de aprovado: pedidos pendentes ficam de fora
    appts = [a for a in sch.upcoming_for_customer(ctx.db, ctx.shop, customer(ctx))
             if a.payment_status != PayStatus.PAID and a.status in ApptStatus.ACTIVE]
    if not appts:
        ctx.say("Você não tem agendamentos pendentes de pagamento." + FOOTER)
        ctx.reset()
        return
    if len(appts) == 1:
        send_pix(ctx, appts[0])
        ctx.reset()
        return
    lines = [f"*{i}* - {dt_label(a.start)} | {a.service.name} - {money(a.price)}" for i, a in enumerate(appts, 1)]
    ctx.go("pay_pick", appt_ids=[a.id for a in appts])
    ctx.say("Qual agendamento você quer pagar?\n\n" + "\n".join(lines))


def st_pay_pick(ctx: Ctx) -> None:
    ids = ctx.get("appt_ids", [])
    i = pick(ctx.text, len(ids))
    if i is None:
        ctx.say(f"Responda com um número de 1 a {len(ids)}, ou *menu* para voltar.")
        return
    send_pix(ctx, ctx.db.get(Appointment, ids[i]))
    ctx.reset()


def _looks_like_paid(ctx: Ctx) -> bool:
    t = ctx.low
    return "paguei" in t or "comprovante" in t or "pago" == t or ctx.text == "[anexo]"


def _report_paid(ctx: Ctx) -> bool:
    c = customer(ctx)
    pending = [a for a in sch.upcoming_for_customer(ctx.db, ctx.shop, c) if a.payment_status == PayStatus.PENDING]
    if not pending:
        return False
    for a in pending:
        a.payment.customer_reported_at = now_local()
    resumo = "\n\n".join(appt_summary(a) for a in pending)
    notify_staff(
        ctx.db, ctx.shop,
        f"💸 *Cliente informou pagamento via Pix*\n{c.name} ({c.phone})\n\n{resumo}\n\n"
        "Confira no extrato e confirme no app ou aqui (menu, opção *5*).",
    )
    ctx.say("Obrigado! 🙏 Avisei a barbearia. Assim que confirmarem o recebimento, te mando a confirmação.")
    ctx.reset()
    return True


# ---------------------------------------------------------------- humano

def talk_to_human(ctx: Ctx) -> None:
    c = customer(ctx)
    hours = ctx.shop.human_pause_hours
    ctx.conv.paused_until = now_local() + timedelta(hours=hours)
    notify_staff(ctx.db, ctx.shop, f"🙋 *{c.name or 'Cliente'}* pediu para falar com alguém.\nhttps://wa.me/{c.phone}")
    ctx.say("Avisei a equipe, já já alguém te responde por aqui. 🙂\n"
            "Se quiser voltar ao atendimento automático, mande *menu*.")
    ctx.reset()


# ---------------------------------------------------------------- lembrete e pesquisa

def st_reminder(ctx: Ctx) -> None:
    appt = _my_appt(ctx)
    if appt is None or appt.status not in ApptStatus.ACTIVE:
        ctx.reset()
        st_menu(ctx)
        return
    if ctx.low in ("1", "sim", "confirmo", "confirmar", "ok"):
        appt.status = ApptStatus.CONFIRMED
        ctx.say("Presença confirmada! ✅ Até já.")
        ctx.reset()
    elif ctx.low in ("2", "nao", "cancelar"):
        _cancel(ctx, appt)
        ctx.reset()
    else:
        ctx.reset()
        st_menu(ctx)


def st_survey_rating(ctx: Ctx) -> None:
    appt = ctx.db.get(Appointment, ctx.get("appt_id") or 0)
    i = pick(ctx.text, 5)
    if appt is None:
        ctx.reset()
        st_menu(ctx)
        return
    if i is None:
        ctx.say("Responda com uma nota de *1* a *5*, por favor. (ou *menu* para pular)")
        return
    rating = i + 1
    review = ctx.db.scalar(select(Review).where(Review.appointment_id == appt.id))
    if review is None:
        review = Review(shop_id=ctx.shop.id, appointment_id=appt.id, rating=rating)
        ctx.db.add(review)
    review.rating = rating
    ctx.db.flush()
    if rating <= 2:
        notify_staff(
            ctx.db, ctx.shop,
            f"⚠️ *Avaliação baixa: {rating}/5*\n{appt.customer.name} ({appt.customer.phone})\n"
            f"{appt.service.name} com {appt.barber.name} em {dt_label(appt.start)}",
        )
    ctx.go("survey_comment", review_id=review.id)
    ctx.say("Valeu pela nota! " + ("⭐" * rating) + "\nQuer deixar um comentário? Escreva aqui ou responda *pular*.")


def st_survey_comment(ctx: Ctx) -> None:
    review = ctx.db.get(Review, ctx.get("review_id") or 0)
    if review and ctx.low not in ("pular", "nao", "n", "nada", "-"):
        review.comment = ctx.text.strip()[:1000]
    ctx.say("Obrigado pelo retorno! 💈 Até a próxima.")
    if review and review.rating <= 2 and review.comment:
        notify_staff(ctx.db, ctx.shop, f"💬 Comentário de {review.appointment.customer.name} "
                                       f"(nota {review.rating}/5):\n{review.comment}")
    ctx.reset()


# ---------------------------------------------------------------- propostas da IA (confirmadas pelo fluxo atual)

def _proposal_text(ctx: Ctx, p: dict) -> str:
    if p["kind"] == "cancel":
        appt = ctx.db.get(Appointment, p["appointment_id"])
        return (f"Cancelar este horário?\n\n{appt_summary(appt)}\n\n"
                "*1* - Confirmar\n*2* - Escolher outro agendamento\n*3* - Desistir")
    service = ctx.db.get(Service, p["service_id"])
    barber = ctx.db.get(Barber, p["barber_id"])
    start = datetime.fromisoformat(p["start"])
    if p["kind"] == "reschedule":
        old = ctx.db.get(Appointment, p["appointment_id"])
        head = f"Confirma a remarcação?\n\nDe: {dt_label(old.start)}\nPara:"
    else:
        head = "Confirma o agendamento?"
    return (f"{head}\n\n✂️ *{service.name}* com {barber.name}\n📅 {dt_label(start)}\n💰 {money(service.price)}\n\n"
            "*1* - Confirmar\n*2* - Escolher outro horário\n*3* - Desistir")


def propose(ctx: Ctx, kind: str, **data) -> None:
    """Guarda a proposta da IA e envia o resumo padrão. Nada é gravado até o cliente responder 1."""
    p = {"kind": kind, **data}
    ctx.reset()
    ctx.go("ai_confirm", ai_proposal=p)
    ctx.say(_proposal_text(ctx, p))


def _own_active(ctx: Ctx, appt_id: int | None) -> Appointment | None:
    appt = ctx.db.get(Appointment, appt_id or 0)
    if appt and appt.shop_id == ctx.shop.id and appt.customer.phone == ctx.phone \
            and appt.status in ApptStatus.OCCUPYING:
        return appt
    return None


def st_ai_confirm(ctx: Ctx) -> None:
    p = ctx.get("ai_proposal")
    if not p:
        ctx.reset()
        st_menu(ctx)
        return
    t = ctx.low
    if t in CONFIRM_WORDS:
        if p["kind"] == "cancel":
            appt = _own_active(ctx, p["appointment_id"])
            ctx.reset()
            if appt is None:
                ctx.say("Não encontrei mais esse agendamento." + FOOTER)
            elif not sch.can_customer_cancel(ctx.shop, appt):
                ctx.say(f"O cancelamento pelo WhatsApp é só até {ctx.shop.cancel_min_hours}h antes do horário. "
                        "Responda *7* para falar com a barbearia.")
            else:
                _cancel(ctx, appt)
            return
        if p["kind"] == "reschedule":
            appt = _own_active(ctx, p["appointment_id"])
            if appt is None or not sch.can_customer_cancel(ctx.shop, appt):
                ctx.reset()
                ctx.say("Não dá mais para remarcar esse horário por aqui. Responda *7* para falar com a barbearia.")
                return
        # Mesmo caminho da confirmação do menu: regras, aprovação, conflitos, avisos e oferta de Pix
        ctx.reset()
        ctx.go("book_confirm", service_id=p["service_id"], barber_id=p["barber_id"], slot_barber_id=p["barber_id"],
               start=p["start"], day=p["start"][:10], reschedule_of=p.get("appointment_id"))
        _do_book(ctx)
    elif t in OTHER_WORDS:
        ctx.reset()
        if p["kind"] == "cancel":
            my_appointments(ctx)
        else:
            ctx.say("Sem problema! Me diga outro dia ou horário que eu procuro. (ou *menu* para ver as opções)")
    elif t in GIVE_UP_WORDS:
        ctx.reset()
        ctx.say("Tudo bem, não mudei nada. Quando quiser é só chamar! 👋")
    else:
        ctx.say("Responda *1* para confirmar, *2* para escolher outro ou *3* para desistir.")


STATES = {
    "ai_confirm": st_ai_confirm,
    "menu": st_menu,
    "book_service": st_book_service,
    "book_barber": st_book_barber,
    "book_day": st_book_day,
    "book_time": st_book_time,
    "book_name": st_book_name,
    "book_confirm": st_book_confirm,
    "book_pay": st_book_pay,
    "my_pick": st_my_pick,
    "my_action": st_my_action,
    "my_cancel_confirm": st_my_cancel_confirm,
    "pay_pick": st_pay_pick,
    "reminder": st_reminder,
    "survey_rating": st_survey_rating,
    "survey_comment": st_survey_comment,
}
