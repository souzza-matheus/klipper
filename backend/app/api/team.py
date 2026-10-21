"""Equipe: quem entra no negócio e com que papel (só o dono). Cada pessoa da equipe é um vínculo (Membership) da
conta dela com este negócio; desativar ou mudar o papel mexe só neste negócio. Convite com senha provisória, trocada
no primeiro acesso."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..auth import hash_password
from ..db import get_db
from ..models import Barber, Membership, Role, Shop, User
from ..permissions import owner_shop, owner_user
from .admin import _own

router = APIRouter()

# Sem caracteres que se confundem (0/O, 1/l/I)
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def provisional_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(12))


def user_out(m: Membership) -> S.UserOut:
    u = m.user
    return S.UserOut(id=u.id, name=u.name, email=u.email, role=m.role, role_label=Role.LABELS.get(m.role, m.role),
                     barber_id=m.barber_id, barber_name=m.barber.name if m.barber else None, active=m.active,
                     first_login=u.must_change_password, created_at=m.created_at or u.created_at)


def _member(db: Session, uid: int, shop: Shop) -> Membership:
    m = db.scalar(select(Membership).where(Membership.user_id == uid, Membership.shop_id == shop.id)) \
        if 0 < uid < 2**31 else None
    if m is None:
        raise HTTPException(404, "Não encontrado")
    return m


def _barber_for(db: Session, shop: Shop, role: str, barber_id: int | None) -> int | None:
    if barber_id is not None:
        _own(db, Barber, barber_id, shop)
    if role == Role.PROFESSIONAL and barber_id is None:
        raise HTTPException(422, "Escolha o cadastro de profissional (agenda) desta pessoa.")
    return barber_id


def _active_owners(db: Session, shop: Shop) -> int:
    return db.scalar(select(func.count()).select_from(Membership).where(
        Membership.shop_id == shop.id, Membership.role == Role.OWNER, Membership.active.is_(True))) or 0


@router.get("/users", response_model=list[S.UserOut], tags=["team"])
def list_users(shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    return [user_out(m) for m in db.scalars(select(Membership).join(User).where(Membership.shop_id == shop.id)
                                            .order_by(User.name))]


@router.post("/users", response_model=S.UserInviteOut, tags=["team"])
def invite_user(body: S.UserInviteIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "E-mail já cadastrado")
    barber_id = _barber_for(db, shop, body.role, body.barber_id)
    password = provisional_password()
    u = User(shop_id=shop.id, name=body.name.strip(), email=body.email, password_hash=hash_password(password),
             role=body.role, barber_id=barber_id, must_change_password=True)
    db.add(u)
    db.commit()
    return S.UserInviteOut(user=user_out(u.membership), provisional_password=password)


@router.put("/users/{uid}", response_model=S.UserOut, tags=["team"])
def update_user(uid: int, body: S.UserUpdateIn, me: User = Depends(owner_user), db: Session = Depends(get_db)):
    shop = me.shop
    m = _member(db, uid, shop)
    data = body.model_dump(exclude_unset=True)
    role = data.get("role", m.role)
    active = data.get("active", m.active)
    losing_owner = m.role == Role.OWNER and m.active and (role != Role.OWNER or not active)
    if losing_owner and _active_owners(db, shop) <= 1:
        raise HTTPException(409, "O estabelecimento precisa de pelo menos um dono ativo.")
    barber_id = _barber_for(db, shop, role, data["barber_id"] if "barber_id" in data else m.barber_id)
    changed_access = role != m.role or active != m.active or barber_id != m.barber_id
    if "name" in data:
        m.user.name = data["name"].strip()
    m.role, m.active, m.barber_id = role, active, barber_id
    if changed_access:
        m.version = (m.version or 0) + 1  # papel novo vale já: a pessoa entra de novo (só neste negócio)
    db.commit()
    return user_out(m)


@router.post("/users/{uid}/reset-password", response_model=S.UserInviteOut, tags=["team"])
def reset_password(uid: int, me: User = Depends(owner_user), db: Session = Depends(get_db)):
    m = _member(db, uid, me.shop)
    u = m.user
    if u.id == me.id:
        raise HTTPException(409, "Para trocar a sua senha, use Trocar senha.")
    # A senha é da conta: o dono de um negócio não pode trocar a senha de quem também entra em outro negócio
    if any(x.shop_id != m.shop_id for x in u.memberships):
        raise HTTPException(409, "Essa pessoa também entra em outro negócio. Ela mesma troca a senha, em "
                                 "Mais > Trocar senha.")
    password = provisional_password()
    u.password_hash, u.must_change_password = hash_password(password), True
    u.token_version = (u.token_version or 0) + 1
    db.commit()
    return S.UserInviteOut(user=user_out(m), provisional_password=password)
