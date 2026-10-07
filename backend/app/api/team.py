"""Equipe: usuários do app e seus papéis (só o dono). Convite com senha provisória, trocada no primeiro acesso."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..auth import hash_password
from ..db import get_db
from ..models import Barber, Role, Shop, User
from ..permissions import owner_shop, owner_user
from .admin import _own

router = APIRouter()

# Sem caracteres que se confundem (0/O, 1/l/I)
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def provisional_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(12))


def user_out(u: User) -> S.UserOut:
    return S.UserOut(id=u.id, name=u.name, email=u.email, role=u.role, role_label=Role.LABELS.get(u.role, u.role),
                     barber_id=u.barber_id, barber_name=u.barber.name if u.barber else None, active=u.active,
                     first_login=u.must_change_password, created_at=u.created_at)


def _barber_for(db: Session, shop: Shop, role: str, barber_id: int | None) -> int | None:
    if barber_id is not None:
        _own(db, Barber, barber_id, shop)
    if role == Role.PROFESSIONAL and barber_id is None:
        raise HTTPException(422, "Escolha o cadastro de profissional (agenda) desta pessoa.")
    return barber_id


def _active_owners(db: Session, shop: Shop) -> int:
    return db.scalar(select(func.count()).select_from(User).where(
        User.shop_id == shop.id, User.role == Role.OWNER, User.active.is_(True))) or 0


@router.get("/users", response_model=list[S.UserOut], tags=["team"])
def list_users(shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).where(User.shop_id == shop.id).order_by(User.name))]


@router.post("/users", response_model=S.UserInviteOut, tags=["team"])
def invite_user(body: S.UserInviteIn, shop: Shop = Depends(owner_shop), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "E-mail já cadastrado")
    barber_id = _barber_for(db, shop, body.role, body.barber_id)
    password = provisional_password()
    u = User(shop_id=shop.id, name=body.name.strip(), email=email, password_hash=hash_password(password),
             role=body.role, barber_id=barber_id, must_change_password=True)
    db.add(u)
    db.commit()
    return S.UserInviteOut(user=user_out(u), provisional_password=password)


@router.put("/users/{uid}", response_model=S.UserOut, tags=["team"])
def update_user(uid: int, body: S.UserUpdateIn, me: User = Depends(owner_user), db: Session = Depends(get_db)):
    shop = me.shop
    u = _own(db, User, uid, shop)
    data = body.model_dump(exclude_unset=True)
    role = data.get("role", u.role)
    active = data.get("active", u.active)
    losing_owner = u.role == Role.OWNER and u.active and (role != Role.OWNER or not active)
    if losing_owner and _active_owners(db, shop) <= 1:
        raise HTTPException(409, "O estabelecimento precisa de pelo menos um dono ativo.")
    barber_id = _barber_for(db, shop, role, data["barber_id"] if "barber_id" in data else u.barber_id)
    changed_access = role != u.role or active != u.active or barber_id != u.barber_id
    if "name" in data:
        u.name = data["name"].strip()
    u.role, u.active, u.barber_id = role, active, barber_id
    if changed_access:
        u.token_version = (u.token_version or 0) + 1  # papel novo vale já: a pessoa entra de novo
    db.commit()
    return user_out(u)


@router.post("/users/{uid}/reset-password", response_model=S.UserInviteOut, tags=["team"])
def reset_password(uid: int, me: User = Depends(owner_user), db: Session = Depends(get_db)):
    u = _own(db, User, uid, me.shop)
    if u.id == me.id:
        raise HTTPException(409, "Para trocar a sua senha, use Trocar senha.")
    password = provisional_password()
    u.password_hash, u.must_change_password = hash_password(password), True
    u.token_version = (u.token_version or 0) + 1
    db.commit()
    return S.UserInviteOut(user=user_out(u), provisional_password=password)
