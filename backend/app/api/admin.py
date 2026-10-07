"""API REST do app admin. Todas as rotas exigem login e enxergam só a barbearia do usuário."""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, undefer

from .. import schemas as S
from ..auth import (
    check_password_or_dummy, current_user, hash_password, make_refresh_token, make_token, user_from_refresh,
)
from ..security import login_limiter, same_secret
from ..config import now_local, settings
from ..db import get_db
from ..models import (
    Appointment, ApptStatus, Barber, Block, Customer, DepositStatus, PayStatus, Payment, Review, Role, Service, Shop,
    User, WorkingHour,
)
from ..permissions import is_pro, own_barber_id, owner_shop, served_by, staff_shop, team_user
from ..sync_events import soft_delete
from ..services import scheduling as sch
from ..services import whatsapp as wa
from ..services.approvals import approval_deadline
from ..services.fmt import appt_summary, dt_label, money
from ..services.payments import confirm_payment, reject_payment
from ..services.pix import valid_pix_key

router = APIRouter()


# Padrão: só o dono. Rotas da recepção e do profissional usam staff_shop/team_user (app/permissions.py).
shop_of = owner_shop


def _phone_or_422(raw: str, label: str = "Telefone") -> str:
    """Telefone normalizado (só dígitos). Vazio é aceito; mais de 15 dígitos (limite internacional) não."""
    phone = wa.normalize_phone(raw)
    if len(phone) > 15:
        raise HTTPException(422, f"{label} inválido.")
    return phone


MAX_ID = 2**31 - 1  # ids fora do inteiro do banco: "não encontrado" (e não erro do banco)


def _own(db: Session, model, obj_id: int, shop: Shop):
    obj = db.get(model, obj_id) if 0 < obj_id <= MAX_ID else None
    if obj is None or obj.shop_id != shop.id:
        raise HTTPException(404, "Não encontrado")
    return obj


# ---------------------------------------------------------------- auth

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _throttle(email: str, ip: str) -> None:
    wait = login_limiter.retry_after(email, ip)
    if wait:
        raise HTTPException(429, f"Muitas tentativas. Tente de novo em {max(1, wait // 60)} min.",
                            headers={"Retry-After": str(wait)})


@router.post("/auth/login", response_model=S.TokenOut, tags=["auth"])
def login(body: S.LoginIn, request: Request, db: Session = Depends(get_db)):
    email, ip = body.email.lower(), _client_ip(request)
    _throttle(email, ip)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and not user.active:
        user = None  # login desativado: mesma resposta de senha errada
    if not check_password_or_dummy(body.password, user.password_hash if user else None):
        login_limiter.failed(email, ip)
        raise HTTPException(401, "E-mail ou senha incorretos")  # mesma mensagem para e-mail ou senha errados
    login_limiter.succeeded(email, ip)
    return _token_out(user, body.client)


def _token_out(user: User, client: str = "app") -> S.TokenOut:
    shop = user.shop
    web = client == "web"
    return S.TokenOut(token=make_token(user, client), user_name=user.name, shop_name=shop.name, niche=shop.niche,
                      theme_mode=shop.theme_mode, role=user.role, barber_id=user.barber_id,
                      first_login=user.must_change_password,
                      refresh_token=make_refresh_token(user) if web else None,
                      expires_in=settings.web_access_minutes * 60 if web else None)


@router.post("/auth/token", response_model=S.TokenOut, tags=["auth"])
def web_token(body: S.RefreshIn, request: Request, db: Session = Depends(get_db)):
    """Versão web: troca o refresh token por um token de acesso novo (e um refresh novo). Sair de todos os
    aparelhos, desativar a pessoa ou trocar a senha invalidam o refresh token."""
    ip = _client_ip(request)
    _throttle("refresh", ip)
    try:
        user = user_from_refresh(body.refresh_token, db)
    except HTTPException:
        login_limiter.failed("refresh", ip)
        raise
    return _token_out(user, "web")


@router.post("/auth/register", response_model=S.TokenOut, tags=["auth"])
def register(body: S.RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Cadastra uma nova barbearia (feito por você na implantação, protegido pelo SETUP_TOKEN)."""
    ip = _client_ip(request)
    _throttle("setup", ip)
    if not same_secret(body.setup_token, settings.setup_token):
        login_limiter.failed("setup", ip)
        raise HTTPException(403, "Token de setup inválido")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    slug = re.sub(r"[^a-z0-9]+", "-", body.shop_name.lower()).strip("-")[:40] or "barbearia"
    instance = slug
    n = 1
    while db.scalar(select(Shop).where(Shop.evolution_instance == instance)):
        n += 1
        instance = f"{slug}-{n}"
    shop = Shop(name=body.shop_name, owner_phone=wa.normalize_phone(body.owner_phone), evolution_instance=instance)
    db.add(shop)
    db.flush()
    user = User(shop_id=shop.id, name=body.owner_name, email=body.email.lower(),
                password_hash=hash_password(body.password), role=Role.OWNER)
    db.add(user)
    db.commit()
    return _token_out(user)


@router.post("/auth/refresh", response_model=S.TokenOut, tags=["auth"])
def refresh(user: User = Depends(current_user)):
    """Token novo (validade renovada) para quem ainda tem um token válido. O app chama ao abrir. Token da versão
    web continua curto (não vira um token de 7 dias)."""
    return _token_out(user, getattr(user, "token_client", "app"))


@router.post("/auth/logout-all", tags=["auth"])
def logout_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Sai de todos os aparelhos: os tokens já emitidos para este usuário deixam de valer."""
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"ok": True}


@router.post("/auth/change-password", response_model=S.TokenOut, tags=["auth"])
def change_password(body: S.ChangePasswordIn, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Troca a senha (obrigatório no primeiro acesso de quem foi convidado). Os outros aparelhos saem."""
    ip = _client_ip(request)
    _throttle(user.email, ip)
    if not check_password_or_dummy(body.current_password, user.password_hash):
        login_limiter.failed(user.email, ip)
        raise HTTPException(401, "Senha atual incorreta")
    if body.new_password == body.current_password:
        raise HTTPException(422, "A nova senha precisa ser diferente da atual.")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return _token_out(user, getattr(user, "token_client", "app"))


@router.get("/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return {"name": user.name, "email": user.email, "shop_id": user.shop_id, "shop_name": user.shop.name,
            "niche": user.shop.niche, "theme_mode": user.shop.theme_mode, "role": user.role,
            "role_label": Role.LABELS.get(user.role, user.role), "barber_id": user.barber_id,
            "first_login": user.must_change_password}


# ---------------------------------------------------------------- barbearia

@router.get("/shop", response_model=S.ShopOut, tags=["shop"])
def get_shop(user: User = Depends(team_user)):
    return user.shop


@router.put("/shop", response_model=S.ShopOut, tags=["shop"])
def update_shop(body: S.ShopIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "owner_phone" in data:
        data["owner_phone"] = _phone_or_422(data["owner_phone"] or "", "WhatsApp do dono")
    if "pix_key" in data or "pix_key_type" in data:
        key, ktype = data.get("pix_key", shop.pix_key), data.get("pix_key_type", shop.pix_key_type)
        if key and not valid_pix_key(key, ktype):
            raise HTTPException(422, "Chave Pix inválida para o tipo escolhido.")
    for k, v in data.items():
        setattr(shop, k, v)
    db.merge(shop)
    db.commit()
    return shop


# ---------------------------------------------------------------- WhatsApp

@router.get("/whatsapp/status", tags=["whatsapp"])
def whatsapp_status(shop: Shop = Depends(shop_of)):
    return {"instance": shop.evolution_instance, "state": wa.connection_state(shop)}


def _evolution(fn, *args) -> dict:
    """Erros da Evolution viram 502 com a mensagem em português; o detalhe técnico já foi para o log."""
    try:
        return fn(*args)
    except wa.EvolutionError as exc:
        raise HTTPException(502, str(exc))


@router.post("/whatsapp/connect", tags=["whatsapp"])
def whatsapp_connect(shop: Shop = Depends(shop_of)):
    """Gera o QR Code para ler com o WhatsApp da barbearia (Aparelhos conectados > Conectar aparelho).
    Sempre devolve state, qrcode (data:image/png;base64,... ou null), pairing_code e message (quando não há QR Code)."""
    return _evolution(wa.connect, shop)


@router.post("/whatsapp/pairing-code", tags=["whatsapp"])
def whatsapp_pairing_code(body: S.PairingCodeIn, shop: Shop = Depends(shop_of)):
    """Código de 8 dígitos para conectar sem ler QR Code (Conectar aparelho > Conectar com número de telefone)."""
    number = wa.normalize_phone(body.number)
    if not 12 <= len(number) <= 13:
        raise HTTPException(422, "Número inválido. Use o número do bot com DDD, ex.: (31) 99999-8888.")
    return _evolution(wa.pairing_code, shop, number)


@router.post("/whatsapp/disconnect", tags=["whatsapp"])
def whatsapp_disconnect(shop: Shop = Depends(shop_of)):
    return _evolution(wa.disconnect, shop)


# ---------------------------------------------------------------- serviços

@router.get("/services", response_model=list[S.ServiceOut], tags=["services"])
def list_services(user: User = Depends(team_user), db: Session = Depends(get_db)):
    shop = user.shop
    return db.scalars(select(Service).where(Service.shop_id == shop.id).order_by(Service.sort_order, Service.name)).all()


@router.post("/services", response_model=S.ServiceOut, tags=["services"])
def create_service(body: S.ServiceIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    svc = Service(shop_id=shop.id, **body.model_dump())
    db.add(svc)
    db.commit()
    return svc


@router.put("/services/{sid}", response_model=S.ServiceOut, tags=["services"])
def update_service(sid: int, body: S.ServiceIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    svc = _own(db, Service, sid, shop)
    for k, v in body.model_dump().items():
        setattr(svc, k, v)
    db.commit()
    return svc


@router.delete("/services/{sid}", tags=["services"])
def delete_service(sid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    svc = _own(db, Service, sid, shop)
    used = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.service_id == sid))
    svc.active = False  # mantém o histórico
    if not used:
        soft_delete(svc)  # some das listas; vira exclusão no sync do app
    db.commit()
    return {"ok": True, "deactivated": bool(used)}


# ---------------------------------------------------------------- barbeiros

def _barber_out(b: Barber) -> S.BarberOut:
    return S.BarberOut(id=b.id, name=b.name, phone=b.phone, bio=b.bio, active=b.active,
                       service_ids=[s.id for s in b.services],
                       working_hours=[S.WorkingHourIO.model_validate(w) for w in b.working_hours])


def _apply_barber(db: Session, shop: Shop, b: Barber, body: S.BarberIn) -> None:
    b.name, b.bio, b.active = body.name, body.bio, body.active
    b.phone = _phone_or_422(body.phone, "WhatsApp do profissional")
    b.services = [s for s in (db.get(Service, i) for i in body.service_ids) if s and s.shop_id == shop.id]
    for w in body.working_hours:
        if w.end <= w.start:
            raise HTTPException(422, "No expediente, o fim precisa ser depois do início")
    b.working_hours = [WorkingHour(weekday=w.weekday, start=w.start, end=w.end) for w in body.working_hours]


@router.get("/barbers", response_model=list[S.BarberOut], tags=["barbers"])
def list_barbers(user: User = Depends(team_user), db: Session = Depends(get_db)):
    shop = user.shop
    return [_barber_out(b) for b in db.scalars(select(Barber).where(Barber.shop_id == shop.id).order_by(Barber.name))]


@router.post("/barbers", response_model=S.BarberOut, tags=["barbers"])
def create_barber(body: S.BarberIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    b = Barber(shop_id=shop.id, name=body.name)
    db.add(b)
    _apply_barber(db, shop, b, body)
    db.commit()
    return _barber_out(b)


@router.put("/barbers/{bid}", response_model=S.BarberOut, tags=["barbers"])
def update_barber(bid: int, body: S.BarberIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    b = _own(db, Barber, bid, shop)
    _apply_barber(db, shop, b, body)
    db.commit()
    return _barber_out(b)


@router.delete("/barbers/{bid}", tags=["barbers"])
def delete_barber(bid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    b = _own(db, Barber, bid, shop)
    used = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.barber_id == bid))
    b.active = False
    if not used:
        soft_delete(b)
    db.commit()
    return {"ok": True, "deactivated": bool(used)}


# ---------------------------------------------------------------- bloqueios

@router.get("/blocks", response_model=list[S.BlockOut], tags=["blocks"])
def list_blocks(date_from: date | None = None, user: User = Depends(team_user), db: Session = Depends(get_db)):
    start = datetime.combine(date_from or now_local().date(), datetime.min.time())
    q = select(Block).where(Block.shop_id == user.shop_id, Block.end >= start)
    if is_pro(user):
        q = q.where(or_(Block.barber_id == own_barber_id(user), Block.barber_id.is_(None)))
    return db.scalars(q.order_by(Block.start)).all()


@router.post("/blocks", response_model=S.BlockOut, tags=["blocks"])
def create_block(body: S.BlockIn, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    if body.end <= body.start:
        raise HTTPException(422, "O fim precisa ser depois do início")
    if body.barber_id:
        _own(db, Barber, body.barber_id, shop)
    blk = Block(shop_id=shop.id, barber_id=body.barber_id, start=body.start.replace(tzinfo=None),
                end=body.end.replace(tzinfo=None), reason=body.reason)
    db.add(blk)
    db.commit()
    return blk


@router.delete("/blocks/{bid}", tags=["blocks"])
def delete_block(bid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    blk = _own(db, Block, bid, shop)
    soft_delete(blk)
    if blk.end > now_local():
        from ..services import waitlist
        db.flush()
        waitlist.on_slot_freed(db, shop, blk.barber_id, blk.start, blk.end)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- agendamentos

def appt_out(a: Appointment) -> S.AppointmentOut:
    deadline = approval_deadline(a.barber.shop, a) if a.status == ApptStatus.PENDING_APPROVAL else None
    return S.AppointmentOut(
        id=a.id, start=a.start, end=a.end, status=a.status, payment_status=a.payment_status,
        payment_method=a.payment_method, price=a.price,
        notes=a.notes, created_via=a.created_via, customer_id=a.customer_id, customer_name=a.customer.name,
        customer_phone=a.customer.phone, barber_id=a.barber_id, barber_name=a.barber.name,
        service_id=a.service_id, service_name=a.service.name, rating=a.review.rating if a.review else None,
        customer_access_status=a.customer.access_status, approval_deadline=deadline,
        payment_id=a.payment.id if a.payment else None,
        customer_reported_paid=bool(a.payment and a.payment.customer_reported_at),
        uuid=a.uuid, version=a.version, checked_in_at=a.checked_in_at, deposit_amount=a.deposit_amount,
        deposit_status=a.deposit_status, customer_package_id=a.customer_package_id, subscription_id=a.subscription_id,
    )


def conflict_hit_out(hit: sch.ConflictHit) -> S.ConflictHitOut:
    a = hit.other
    return S.ConflictHitOut(
        conflict_id=hit.conflict.id, other_customer_id=a.customer_id,
        other_customer_name=a.customer.name or a.customer.phone, appointment_id=a.id,
        start=a.start, end=a.end, barber_name=a.barber.name, gap_minutes=hit.gap_minutes,
        same_day_block=hit.same_day_block, conflict_action=hit.conflict.conflict_action,
    )


def conflict_409(e: sch.ConflictError) -> HTTPException:
    """Conflito entre clientes no agendamento manual: o app mostra o aviso e pode repetir com force=true."""
    hit = conflict_hit_out(e.hit)
    rule = ("os dois não podem vir no mesmo dia" if hit.same_day_block
            else f"a distância mínima entre os dois é de {_gap_label(hit.gap_minutes)}")
    msg = (f"{hit.other_customer_name} tem horário {dt_label(hit.start).lower()} até {hit.end:%H:%M} "
           f"com {hit.barber_name}, e {rule}.")
    return HTTPException(409, {"message": msg, "code": "customer_conflict", "conflict": hit.model_dump(mode="json")})


def _gap_label(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} h" + (f" {m} min" if m else "") if h else f"{m} min"


@router.get("/appointments", response_model=list[S.AppointmentOut], tags=["appointments"])
def list_appointments(date_from: date, date_to: date | None = None, barber_id: S.QId | None = None,
                      include_cancelled: bool = False, user: User = Depends(team_user), db: Session = Depends(get_db)):
    shop = user.shop
    barber_id = own_barber_id(user) or barber_id  # profissional: só a própria agenda
    start = datetime.combine(date_from, datetime.min.time())
    end = datetime.combine(date_to or date_from, datetime.min.time()) + timedelta(days=1)
    q = select(Appointment).where(Appointment.shop_id == shop.id, Appointment.start >= start, Appointment.start < end)
    if barber_id:
        q = q.where(Appointment.barber_id == barber_id)
    if not include_cancelled:
        q = q.where(Appointment.status != ApptStatus.CANCELLED)
    return [appt_out(a) for a in db.scalars(q.order_by(Appointment.start))]


@router.get("/agenda/day", response_model=S.AgendaDayOut, tags=["appointments"])
def agenda_day(day: date, user: User = Depends(team_user), db: Session = Depends(get_db)):
    """Tudo o que a agenda do dia precisa em uma resposta: expediente, bloqueios, agendamentos e horários livres
    de cada profissional ativo (ou com agendamento no dia). O profissional vê só a própria coluna."""
    shop = user.shop
    d = sch.day_agenda(db, shop, day)
    if is_pro(user):
        d.barbers = [b for b in d.barbers if b.barber.id == own_barber_id(user)]
    return S.AgendaDayOut(day=day, now=d.now, slot_step_minutes=shop.slot_step_minutes, barbers=[
        S.AgendaBarber(
            id=b.barber.id, name=b.barber.name,
            working=[S.Interval(start=a, end=z) for a, z in b.working],
            blocks=[S.AgendaBlock(id=k.id, start=k.start, end=k.end, reason=k.reason, whole_shop=k.barber_id is None)
                    for k in b.blocks],
            appointments=[appt_out(a) for a in b.appointments],
            free=[S.Interval(start=a, end=z) for a, z in b.free],
        ) for b in d.barbers
    ])


@router.get("/appointments/month", response_model=S.MonthOut, tags=["appointments"])
def appointments_month(year: int = Query(ge=2000, le=2100), month: int = Query(ge=1, le=12),
                       barber_id: S.QId | None = None, user: User = Depends(team_user),
                       db: Session = Depends(get_db)):
    """Visão do mês para o calendário: por dia, total, cancelados, faturamento previsto, ocupação e bloqueio."""
    shop = user.shop
    barber_id = own_barber_id(user) or barber_id
    if barber_id and barber_id > 0:
        _own(db, Barber, barber_id, shop)
    return S.MonthOut(year=year, month=month, days=sch.month_overview(db, shop, year, month, barber_id))


@router.get("/availability", tags=["appointments"])
def availability(service_id: S.QId, day: date, barber_id: S.QId | None = None, customer_id: S.QId | None = None,
                 shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    """Com customer_id, esconde os horários que ficam perto demais de clientes em conflito com ele."""
    svc = _own(db, Service, service_id, shop)
    customer = _own(db, Customer, customer_id, shop) if customer_id else None
    if barber_id:
        b = _own(db, Barber, barber_id, shop)
        return [{"start": s, "barber_id": b.id, "barber_name": b.name}
                for s in sch.free_slots(db, shop, svc, b, day, customer=customer)]
    return [{"start": s, "barber_id": b.id, "barber_name": b.name}
            for s, b in sch.free_slots_any(db, shop, svc, day, customer=customer)]


@router.post("/appointments", response_model=S.AppointmentOut, tags=["appointments"])
def create_appt(body: S.AppointmentIn, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    barber = _own(db, Barber, body.barber_id, shop)
    svc = _own(db, Service, body.service_id, shop)
    phone = wa.normalize_phone(body.customer_phone)
    if not 12 <= len(phone) <= 15:
        raise HTTPException(422, "Telefone inválido. Use DDD + número.")
    customer = sch.get_or_create_customer(db, shop, phone, body.customer_name.strip().title())
    try:
        a = sch.create_appointment(db, shop, customer, barber, svc, body.start.replace(tzinfo=None),
                                   created_via="app", notes=body.notes, force=body.force)
    except sch.ConflictError as e:
        err = conflict_409(e)
        db.rollback()  # desfaz o cliente criado agora, se for o caso
        raise err
    except sch.SchedulingError as e:
        raise HTTPException(409, str(e))
    notify_new_appointment(db, shop, a, use_balance=body.use_balance, require_deposit=body.require_deposit)
    db.commit()
    return appt_out(a)


def notify_new_appointment(db: Session, shop: Shop, a: Appointment, use_balance: bool = True,
                           require_deposit: bool = False) -> None:
    """Depois de criar pelo app (ou pelo sync): usa o saldo do cliente, pede o sinal se o dono quis e avisa o
    cliente no WhatsApp."""
    from ..services import benefits, deposits
    extra = benefits.apply_on_booking(db, shop, a) if use_balance else ""
    amount = deposits.needs_deposit(shop, a) if require_deposit else 0
    if amount:
        pay = deposits.request_deposit(db, shop, a, amount)
        for m in deposits.deposit_messages(shop, a, pay):
            wa.send_text(db, shop, a.customer.phone, m)
        return
    wa.send_text(db, shop, a.customer.phone, f"✅ Seu horário na *{shop.name}* foi agendado:\n\n{appt_summary(a)}\n\n"
                 + (extra + "\n\n" if extra else "")
                 + "Te mando um lembrete antes. Para cancelar ou remarcar, mande *menu*.")


@router.patch("/appointments/{aid}", response_model=S.AppointmentOut, tags=["appointments"])
def patch_appt(aid: int, body: S.AppointmentPatch, user: User = Depends(team_user), db: Session = Depends(get_db)):
    shop = user.shop
    a = _own(db, Appointment, aid, shop)
    if is_pro(user):
        # Profissional: só os próprios atendimentos, só presença/conclusão/falta e observação
        if a.barber_id != own_barber_id(user):
            raise HTTPException(404, "Não encontrado")
        if body.price is not None or body.payment_method is not None or \
                body.status not in (None, ApptStatus.CONFIRMED, ApptStatus.COMPLETED, ApptStatus.NO_SHOW):
            raise HTTPException(403, "Seu perfil não tem acesso a esta função.")
    apply_patch(db, shop, a, body)
    db.commit()
    return appt_out(a)


def apply_patch(db: Session, shop: Shop, a: Appointment, body: S.AppointmentPatch) -> None:
    from ..services import deposits
    if body.notes is not None:
        a.notes = body.notes
    if body.price is not None:
        a.price = body.price
    if body.payment_method is not None:
        a.payment_method = body.payment_method
    if body.status == ApptStatus.COMPLETED:
        sch.complete_appointment(a, body.payment_method)
    elif body.status and body.status != a.status:
        if body.status == ApptStatus.CANCELLED:
            sch.cancel_appointment(db, a)
            if body.notify_customer:
                wa.send_text(db, shop, a.customer.phone,
                             f"❌ Seu horário na *{shop.name}* foi cancelado:\n\n{appt_summary(a)}\n\n"
                             "Para marcar outro, mande *menu*.")
        else:
            if body.status == ApptStatus.NO_SHOW:
                deposits.on_no_show(a)
            a.status = body.status


@router.post("/appointments/{aid}/reschedule", response_model=S.AppointmentOut, tags=["appointments"])
def reschedule(aid: int, body: S.RescheduleIn, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    a = _own(db, Appointment, aid, shop)
    barber = _own(db, Barber, body.barber_id, shop) if body.barber_id else None
    try:
        sch.reschedule_appointment(db, shop, a, body.start.replace(tzinfo=None), barber, force=body.force)
    except sch.ConflictError as e:
        raise conflict_409(e)
    except sch.SchedulingError as e:
        raise HTTPException(409, str(e))
    if body.notify_customer:
        wa.send_text(db, shop, a.customer.phone, f"🔁 Seu horário na *{shop.name}* foi remarcado:\n\n{appt_summary(a)}")
    db.commit()
    return appt_out(a)


@router.post("/appointments/{aid}/send-pix", tags=["appointments"])
def send_pix(aid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    from ..services.payments import get_or_create_pix, pix_messages, pix_ready
    a = _own(db, Appointment, aid, shop)
    if not pix_ready(shop):
        raise HTTPException(422, "Configure a chave Pix nas configurações")
    if a.payment_status == PayStatus.PAID:
        raise HTTPException(409, "Já está pago")
    pay = get_or_create_pix(db, shop, a)
    for m in pix_messages(shop, a, pay):
        wa.send_text(db, shop, a.customer.phone, m)
    db.commit()
    return {"ok": True, "brcode": pay.brcode}


@router.post("/appointments/{aid}/check-in", response_model=S.AppointmentOut, tags=["appointments"])
def check_in(aid: int, user: User = Depends(team_user), db: Session = Depends(get_db)):
    """Cliente chegou. Recepção (qualquer agendamento) ou o próprio profissional."""
    a = _own(db, Appointment, aid, user.shop)
    if is_pro(user) and a.barber_id != own_barber_id(user):
        raise HTTPException(404, "Não encontrado")
    if a.status not in ApptStatus.ACTIVE:
        raise HTTPException(409, "Só dá para fazer check-in de um agendamento confirmado.")
    a.checked_in_at = a.checked_in_at or now_local()
    a.status = ApptStatus.CONFIRMED
    db.commit()
    return appt_out(a)


@router.post("/appointments/{aid}/deposit-refunded", response_model=S.AppointmentOut, tags=["appointments"])
def deposit_refunded(aid: int, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    """O dono devolveu o sinal (cancelamento no prazo)."""
    a = _own(db, Appointment, aid, shop)
    if a.deposit_status != DepositStatus.REFUND_DUE:
        raise HTTPException(409, "Esse sinal não está marcado para devolução.")
    a.deposit_status = DepositStatus.REFUNDED
    db.commit()
    return appt_out(a)


# ---------------------------------------------------------------- clientes

@router.get("/customers", response_model=list[S.CustomerOut], tags=["customers"])
def list_customers(q: str = Query("", max_length=100), access_status: str | None = Query(None, pattern=S.ACCESS_STATUS),
                   limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100_000),
                   user: User = Depends(team_user), db: Session = Depends(get_db)):
    query = select(Customer).where(Customer.shop_id == user.shop_id)
    if is_pro(user):  # profissional: só quem ele já atendeu
        query = query.where(served_by(own_barber_id(user)))
    if access_status:
        query = query.where(Customer.access_status == access_status)
    if q:
        digits = re.sub(r"\D", "", q)
        cond = Customer.name.ilike(f"%{q}%")
        if len(digits) >= 3:
            cond = or_(cond, Customer.phone.contains(digits))
        query = query.where(cond)
    return db.scalars(query.order_by(Customer.name).limit(limit).offset(offset)).all()


@router.get("/customers/{cid}", response_model=S.CustomerDetail, tags=["customers"])
def get_customer(cid: int, user: User = Depends(team_user), db: Session = Depends(get_db)):
    from ..services.benefits import customer_balance
    c = _own(db, Customer, cid, user.shop)
    q = select(Appointment).where(Appointment.customer_id == c.id)
    if is_pro(user):
        q = q.where(Appointment.barber_id == own_barber_id(user))
    appts = db.scalars(q.order_by(Appointment.start.desc())).all()
    if is_pro(user) and not appts:
        raise HTTPException(404, "Não encontrado")
    done = [a for a in appts if a.status == ApptStatus.COMPLETED]
    now = now_local()
    return S.CustomerDetail(
        **S.CustomerOut.model_validate(c).model_dump(), visits=len(done),
        no_shows=sum(1 for a in appts if a.status == ApptStatus.NO_SHOW),
        total_spent=sum((a.price for a in done), Decimal(0)),
        future_appointments=sum(1 for a in appts if a.start >= now and a.status in ApptStatus.OCCUPYING),
        appointments=[appt_out(a) for a in appts[:50]],
        balance=customer_balance(db, user.shop, c) if not is_pro(user) else None,
    )


@router.put("/customers/{cid}", response_model=S.CustomerOut, tags=["customers"])
def update_customer(cid: int, body: S.CustomerIn, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    c = _own(db, Customer, cid, shop)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return c


# ---------------------------------------------------------------- pagamentos

def pay_out(p: Payment) -> S.PaymentOut:
    a = p.appointment
    return S.PaymentOut(id=p.id, appointment_id=p.appointment_id, amount=p.amount, status=p.status, brcode=p.brcode,
                        created_at=p.created_at, customer_reported_at=p.customer_reported_at,
                        confirmed_at=p.confirmed_at, customer_name=a.customer.name, appointment_start=a.start,
                        customer_phone=a.customer.phone, service_name=a.service.name, barber_name=a.barber.name,
                        has_receipt=p.receipt_mime is not None, receipt_mime=p.receipt_mime, receipt_at=p.receipt_at)


@router.get("/payments", response_model=list[S.PaymentOut], tags=["payments"])
def list_payments(status: str | None = None, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    """Pendentes vêm primeiro os que o cliente disse que pagou, depois pelo horário do atendimento."""
    q = select(Payment).join(Appointment).where(Payment.shop_id == shop.id)
    if status:
        q = q.where(Payment.status == status)
    if status == PayStatus.PENDING:
        q = q.order_by(Payment.customer_reported_at.is_(None), Appointment.start)
    else:
        q = q.order_by(Payment.created_at.desc())
    return [pay_out(p) for p in db.scalars(q.limit(200))]


@router.post("/payments/{pid}/confirm", response_model=S.PaymentOut, tags=["payments"])
def confirm(pid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    p = _own(db, Payment, pid, shop)
    if p.status == PayStatus.PAID:
        return pay_out(p)
    deposit_ok = confirm_payment(db, p)
    a = p.appointment
    if p.kind == "deposit":
        msg = (f"✅ Recebemos o sinal de {money(p.amount)}! Seu horário de {dt_label(a.start)} está confirmado. "
               "O valor do sinal é descontado no atendimento." if deposit_ok else
               f"✅ Recebemos o sinal de {money(p.amount)} do horário de {dt_label(a.start)}.")
    else:
        msg = f"✅ Recebemos o seu Pix de {money(p.amount)}! Seu horário de {dt_label(a.start)} está pago. Até lá! 💈"
    wa.send_text(db, shop, a.customer.phone, msg)
    db.commit()
    return pay_out(p)


@router.post("/payments/{pid}/reject", response_model=S.PaymentOut, tags=["payments"])
def reject(pid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    """O Pix não caiu: marca como expirado e avisa o cliente com uma mensagem neutra. O horário continua marcado."""
    p = _own(db, Payment, pid, shop)
    if p.status != PayStatus.PENDING:
        raise HTTPException(409, "Esse pagamento não está mais pendente.")
    reject_payment(db, p)
    a = p.appointment
    wa.send_text(db, shop, a.customer.phone,
                 f"Não localizamos o seu Pix de {money(p.amount)} referente ao horário de {dt_label(a.start)}. "
                 "Seu horário continua marcado e você pode pagar no atendimento. Se já pagou, responda por aqui "
                 "que a gente confere.")
    db.commit()
    return pay_out(p)


@router.get("/payments/{pid}/receipt", tags=["payments"])
def payment_receipt(pid: int, shop: Shop = Depends(staff_shop), db: Session = Depends(get_db)):
    """Comprovante que o cliente mandou no WhatsApp (imagem ou PDF)."""
    p = db.scalar(select(Payment).options(undefer(Payment.receipt_data)).where(Payment.id == pid)) \
        if 0 < pid <= MAX_ID else None
    if p is None or p.shop_id != shop.id or not p.receipt_data:
        raise HTTPException(404, "Comprovante não encontrado")
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif",
           "application/pdf": "pdf"}.get(p.receipt_mime, "bin")
    return Response(p.receipt_data, media_type=p.receipt_mime or "application/octet-stream", headers={
        "Cache-Control": "private, max-age=3600",
        "Content-Disposition": f'inline; filename="comprovante-{p.id}.{ext}"',
        # nada dentro do arquivo roda no navegador (PDF com script, etc.)
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
    })


# ---------------------------------------------------------------- avaliações e relatórios

@router.get("/reviews", response_model=list[S.ReviewOut], tags=["reviews"])
def list_reviews(barber_id: S.QId | None = None, user: User = Depends(team_user), db: Session = Depends(get_db)):
    barber_id = own_barber_id(user) or barber_id
    q = select(Review).join(Appointment).where(Review.shop_id == user.shop_id)
    if barber_id:
        q = q.where(Appointment.barber_id == barber_id)
    out = []
    for r in db.scalars(q.order_by(Review.created_at.desc()).limit(200)):
        a = r.appointment
        out.append(S.ReviewOut(id=r.id, rating=r.rating, comment=r.comment, created_at=r.created_at,
                               customer_name=a.customer.name, barber_name=a.barber.name,
                               service_name=a.service.name, appointment_start=a.start))
    return out


@router.get("/reports/summary", response_model=S.ReportOut, tags=["reports"])
def report(date_from: date, date_to: date, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    start = datetime.combine(date_from, datetime.min.time())
    end = datetime.combine(date_to, datetime.min.time()) + timedelta(days=1)
    appts = db.scalars(select(Appointment).where(Appointment.shop_id == shop.id, Appointment.start >= start,
                                                 Appointment.start < end)).all()
    valid = [a for a in appts if a.status not in (ApptStatus.CANCELLED, ApptStatus.NO_SHOW)]
    done = [a for a in appts if a.status == ApptStatus.COMPLETED]
    ratings = [a.review.rating for a in appts if a.review]

    def group(key):
        acc: dict[str, dict] = {}
        for a in valid:
            k = key(a)
            g = acc.setdefault(k, {"name": k, "appointments": 0, "revenue": Decimal(0), "ratings": []})
            g["appointments"] += 1
            g["revenue"] += a.price
            if a.review:
                g["ratings"].append(a.review.rating)
        rows = []
        for g in acc.values():
            r = g.pop("ratings")
            g["avg_rating"] = round(sum(r) / len(r), 2) if r else None
            g["revenue"] = str(g["revenue"])
            rows.append(g)
        return sorted(rows, key=lambda x: -x["appointments"])

    return S.ReportOut(
        date_from=date_from, date_to=date_to, appointments=len(valid), completed=len(done),
        cancelled=sum(1 for a in appts if a.status == ApptStatus.CANCELLED),
        no_shows=sum(1 for a in appts if a.status == ApptStatus.NO_SHOW),
        revenue_expected=sum((a.price for a in valid), Decimal(0)),
        revenue_completed=sum((a.price for a in done), Decimal(0)),
        paid_pix=sum((a.price for a in valid if a.payment_status == PayStatus.PAID), Decimal(0)),
        avg_rating=round(sum(ratings) / len(ratings), 2) if ratings else None,
        by_barber=group(lambda a: a.barber.name), by_service=group(lambda a: a.service.name),
    )
