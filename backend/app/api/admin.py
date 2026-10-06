"""API REST do app admin. Todas as rotas exigem login e enxergam só a barbearia do usuário."""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..auth import check_password, current_user, hash_password, make_token
from ..config import now_local, settings
from ..db import get_db
from ..models import (
    Appointment, ApptStatus, Barber, Block, Customer, PayStatus, Payment, Review, Service, Shop, User,
    WorkingHour,
)
from ..services import scheduling as sch
from ..services import whatsapp as wa
from ..services.fmt import appt_summary, dt_label, money
from ..services.payments import confirm_payment

router = APIRouter()


def shop_of(user: User = Depends(current_user)) -> Shop:
    return user.shop


def _own(db: Session, model, obj_id: int, shop: Shop):
    obj = db.get(model, obj_id)
    if obj is None or obj.shop_id != shop.id:
        raise HTTPException(404, "Não encontrado")
    return obj


# ---------------------------------------------------------------- auth

@router.post("/auth/login", response_model=S.TokenOut, tags=["auth"])
def login(body: S.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "E-mail ou senha incorretos")
    return S.TokenOut(token=make_token(user), user_name=user.name, shop_name=user.shop.name)


@router.post("/auth/register", response_model=S.TokenOut, tags=["auth"])
def register(body: S.RegisterIn, db: Session = Depends(get_db)):
    """Cadastra uma nova barbearia (feito por você na implantação, protegido pelo SETUP_TOKEN)."""
    if body.setup_token != settings.setup_token:
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
    user = User(shop_id=shop.id, name=body.owner_name, email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return S.TokenOut(token=make_token(user), user_name=user.name, shop_name=shop.name)


@router.get("/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return {"name": user.name, "email": user.email, "shop_id": user.shop_id, "shop_name": user.shop.name}


# ---------------------------------------------------------------- barbearia

@router.get("/shop", response_model=S.ShopOut, tags=["shop"])
def get_shop(shop: Shop = Depends(shop_of)):
    return shop


@router.put("/shop", response_model=S.ShopOut, tags=["shop"])
def update_shop(body: S.ShopIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "owner_phone" in data:
        data["owner_phone"] = wa.normalize_phone(data["owner_phone"] or "")
    for k, v in data.items():
        setattr(shop, k, v)
    db.merge(shop)
    db.commit()
    return shop


# ---------------------------------------------------------------- WhatsApp

@router.get("/whatsapp/status", tags=["whatsapp"])
def whatsapp_status(shop: Shop = Depends(shop_of)):
    return {"instance": shop.evolution_instance, "state": wa.connection_state(shop)}


@router.post("/whatsapp/connect", tags=["whatsapp"])
def whatsapp_connect(shop: Shop = Depends(shop_of)):
    """Retorna o QR Code para ler com o WhatsApp da barbearia (Aparelhos conectados > Conectar aparelho)."""
    if not settings.evolution_url:
        return {"state": "simulacao", "qrcode": None, "message": "EVOLUTION_URL não configurada: rodando em modo simulação"}
    try:
        data = wa.connect_qr(shop)
    except Exception as exc:
        raise HTTPException(502, f"Falha ao falar com a Evolution API: {exc}")
    qr = data.get("base64") or (data.get("qrcode") or {}).get("base64")
    return {"state": wa.connection_state(shop), "qrcode": qr, "pairing_code": data.get("pairingCode")}


# ---------------------------------------------------------------- serviços

@router.get("/services", response_model=list[S.ServiceOut], tags=["services"])
def list_services(shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
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
    if used:
        svc.active = False  # mantém o histórico
    else:
        db.delete(svc)
    db.commit()
    return {"ok": True, "deactivated": bool(used)}


# ---------------------------------------------------------------- barbeiros

def _barber_out(b: Barber) -> S.BarberOut:
    return S.BarberOut(id=b.id, name=b.name, phone=b.phone, bio=b.bio, active=b.active,
                       service_ids=[s.id for s in b.services],
                       working_hours=[S.WorkingHourIO.model_validate(w) for w in b.working_hours])


def _apply_barber(db: Session, shop: Shop, b: Barber, body: S.BarberIn) -> None:
    b.name, b.bio, b.active = body.name, body.bio, body.active
    b.phone = wa.normalize_phone(body.phone)
    b.services = [s for s in (db.get(Service, i) for i in body.service_ids) if s and s.shop_id == shop.id]
    for w in body.working_hours:
        if w.end <= w.start:
            raise HTTPException(422, "No expediente, o fim precisa ser depois do início")
    b.working_hours = [WorkingHour(weekday=w.weekday, start=w.start, end=w.end) for w in body.working_hours]


@router.get("/barbers", response_model=list[S.BarberOut], tags=["barbers"])
def list_barbers(shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
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
    if used:
        b.active = False
    else:
        db.delete(b)
    db.commit()
    return {"ok": True, "deactivated": bool(used)}


# ---------------------------------------------------------------- bloqueios

@router.get("/blocks", response_model=list[S.BlockOut], tags=["blocks"])
def list_blocks(date_from: date | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    start = datetime.combine(date_from or now_local().date(), datetime.min.time())
    return db.scalars(select(Block).where(Block.shop_id == shop.id, Block.end >= start).order_by(Block.start)).all()


@router.post("/blocks", response_model=S.BlockOut, tags=["blocks"])
def create_block(body: S.BlockIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
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
def delete_block(bid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    db.delete(_own(db, Block, bid, shop))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- agendamentos

def appt_out(a: Appointment) -> S.AppointmentOut:
    return S.AppointmentOut(
        id=a.id, start=a.start, end=a.end, status=a.status, payment_status=a.payment_status, price=a.price,
        notes=a.notes, created_via=a.created_via, customer_id=a.customer_id, customer_name=a.customer.name,
        customer_phone=a.customer.phone, barber_id=a.barber_id, barber_name=a.barber.name,
        service_id=a.service_id, service_name=a.service.name, rating=a.review.rating if a.review else None,
    )


@router.get("/appointments", response_model=list[S.AppointmentOut], tags=["appointments"])
def list_appointments(date_from: date, date_to: date | None = None, barber_id: int | None = None,
                      include_cancelled: bool = False, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    start = datetime.combine(date_from, datetime.min.time())
    end = datetime.combine(date_to or date_from, datetime.min.time()) + timedelta(days=1)
    q = select(Appointment).where(Appointment.shop_id == shop.id, Appointment.start >= start, Appointment.start < end)
    if barber_id:
        q = q.where(Appointment.barber_id == barber_id)
    if not include_cancelled:
        q = q.where(Appointment.status != ApptStatus.CANCELLED)
    return [appt_out(a) for a in db.scalars(q.order_by(Appointment.start))]


@router.get("/availability", tags=["appointments"])
def availability(service_id: int, day: date, barber_id: int | None = None,
                 shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    svc = _own(db, Service, service_id, shop)
    if barber_id:
        b = _own(db, Barber, barber_id, shop)
        return [{"start": s, "barber_id": b.id, "barber_name": b.name} for s in sch.free_slots(db, shop, svc, b, day)]
    return [{"start": s, "barber_id": b.id, "barber_name": b.name} for s, b in sch.free_slots_any(db, shop, svc, day)]


@router.post("/appointments", response_model=S.AppointmentOut, tags=["appointments"])
def create_appt(body: S.AppointmentIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    barber = _own(db, Barber, body.barber_id, shop)
    svc = _own(db, Service, body.service_id, shop)
    phone = wa.normalize_phone(body.customer_phone)
    if len(phone) < 12:
        raise HTTPException(422, "Telefone inválido. Use DDD + número.")
    customer = sch.get_or_create_customer(db, shop, phone, body.customer_name.strip().title())
    try:
        a = sch.create_appointment(db, shop, customer, barber, svc, body.start.replace(tzinfo=None),
                                   created_via="app", notes=body.notes)
    except sch.SchedulingError as e:
        raise HTTPException(409, str(e))
    wa.send_text(db, shop, phone, f"✅ Seu horário na *{shop.name}* foi agendado:\n\n{appt_summary(a)}\n\n"
                                  "Te mando um lembrete antes. Para cancelar ou remarcar, mande *menu*.")
    db.commit()
    return appt_out(a)


@router.patch("/appointments/{aid}", response_model=S.AppointmentOut, tags=["appointments"])
def patch_appt(aid: int, body: S.AppointmentPatch, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    a = _own(db, Appointment, aid, shop)
    if body.notes is not None:
        a.notes = body.notes
    if body.status and body.status != a.status:
        if body.status == ApptStatus.CANCELLED:
            sch.cancel_appointment(db, a)
            if body.notify_customer:
                wa.send_text(db, shop, a.customer.phone,
                             f"❌ Seu horário na *{shop.name}* foi cancelado:\n\n{appt_summary(a)}\n\n"
                             "Para marcar outro, mande *menu*.")
        else:
            a.status = body.status
    db.commit()
    return appt_out(a)


@router.post("/appointments/{aid}/reschedule", response_model=S.AppointmentOut, tags=["appointments"])
def reschedule(aid: int, body: S.RescheduleIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    a = _own(db, Appointment, aid, shop)
    barber = _own(db, Barber, body.barber_id, shop) if body.barber_id else None
    try:
        sch.reschedule_appointment(db, shop, a, body.start.replace(tzinfo=None), barber)
    except sch.SchedulingError as e:
        raise HTTPException(409, str(e))
    if body.notify_customer:
        wa.send_text(db, shop, a.customer.phone, f"🔁 Seu horário na *{shop.name}* foi remarcado:\n\n{appt_summary(a)}")
    db.commit()
    return appt_out(a)


@router.post("/appointments/{aid}/send-pix", tags=["appointments"])
def send_pix(aid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
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


# ---------------------------------------------------------------- clientes

@router.get("/customers", response_model=list[S.CustomerOut], tags=["customers"])
def list_customers(q: str = "", limit: int = Query(50, le=200), offset: int = 0,
                   shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    query = select(Customer).where(Customer.shop_id == shop.id)
    if q:
        digits = re.sub(r"\D", "", q)
        cond = Customer.name.ilike(f"%{q}%")
        if len(digits) >= 3:
            cond = or_(cond, Customer.phone.contains(digits))
        query = query.where(cond)
    return db.scalars(query.order_by(Customer.name).limit(limit).offset(offset)).all()


@router.get("/customers/{cid}", response_model=S.CustomerDetail, tags=["customers"])
def get_customer(cid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    c = _own(db, Customer, cid, shop)
    appts = db.scalars(select(Appointment).where(Appointment.customer_id == c.id).order_by(Appointment.start.desc())).all()
    done = [a for a in appts if a.status == ApptStatus.COMPLETED]
    return S.CustomerDetail(
        id=c.id, name=c.name, phone=c.phone, notes=c.notes, created_at=c.created_at, visits=len(done),
        no_shows=sum(1 for a in appts if a.status == ApptStatus.NO_SHOW),
        total_spent=sum((a.price for a in done), Decimal(0)), appointments=[appt_out(a) for a in appts[:50]],
    )


@router.put("/customers/{cid}", response_model=S.CustomerOut, tags=["customers"])
def update_customer(cid: int, body: S.CustomerIn, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    c = _own(db, Customer, cid, shop)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    return c


# ---------------------------------------------------------------- pagamentos

def pay_out(p: Payment) -> S.PaymentOut:
    return S.PaymentOut(id=p.id, appointment_id=p.appointment_id, amount=p.amount, status=p.status, brcode=p.brcode,
                        created_at=p.created_at, customer_reported_at=p.customer_reported_at,
                        confirmed_at=p.confirmed_at, customer_name=p.appointment.customer.name,
                        appointment_start=p.appointment.start)


@router.get("/payments", response_model=list[S.PaymentOut], tags=["payments"])
def list_payments(status: str | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    q = select(Payment).where(Payment.shop_id == shop.id)
    if status:
        q = q.where(Payment.status == status)
    return [pay_out(p) for p in db.scalars(q.order_by(Payment.created_at.desc()).limit(200))]


@router.post("/payments/{pid}/confirm", response_model=S.PaymentOut, tags=["payments"])
def confirm(pid: int, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    p = _own(db, Payment, pid, shop)
    if p.status == PayStatus.PAID:
        return pay_out(p)
    confirm_payment(db, p)
    a = p.appointment
    wa.send_text(db, shop, a.customer.phone,
                 f"✅ Recebemos o seu Pix de {money(p.amount)}! Seu horário de {dt_label(a.start)} está pago. Até lá! 💈")
    db.commit()
    return pay_out(p)


# ---------------------------------------------------------------- avaliações e relatórios

@router.get("/reviews", response_model=list[S.ReviewOut], tags=["reviews"])
def list_reviews(barber_id: int | None = None, shop: Shop = Depends(shop_of), db: Session = Depends(get_db)):
    q = select(Review).join(Appointment).where(Review.shop_id == shop.id)
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
