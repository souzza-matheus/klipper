"""Papéis e permissões do app (dono, recepção e profissional).

Toda rota da API declara quem pode usá-la por uma destas dependências:
- owner_shop: só o dono (padrão de tudo que é configuração, financeiro completo, equipe, WhatsApp e IA);
- staff_shop: dono e recepção (agenda, check-in, comandas, clientes, Pix);
- team_user: qualquer papel; a rota filtra o que o profissional enxerga (só a própria agenda, os clientes que
  atendeu e as próprias comissões).
Fora do papel = 403 com a mesma mensagem, sem dizer o que existe.
"""
from fastapi import Depends, HTTPException
from sqlalchemy import exists, select

from .auth import current_user
from .models import Appointment, Role, Shop, User

FORBIDDEN = "Seu perfil não tem acesso a esta função."


PASSWORD_FIRST = "Troque a senha provisória antes de continuar."


def _require(user: User, roles: tuple[str, ...]) -> None:
    if user.must_change_password:  # convite: só /me, /auth/refresh e /auth/change-password até trocar a senha
        raise HTTPException(403, {"message": PASSWORD_FIRST, "code": "first_login"})
    if user.role not in roles:
        raise HTTPException(403, FORBIDDEN)


def owner_user(user: User = Depends(current_user)) -> User:
    _require(user, (Role.OWNER,))
    return user


def staff_user(user: User = Depends(current_user)) -> User:
    _require(user, Role.STAFF)
    return user


def team_user(user: User = Depends(current_user)) -> User:
    _require(user, Role.ALL)
    return user


def owner_or_pro_user(user: User = Depends(current_user)) -> User:
    """Comissões: o dono vê todas; o profissional, só as dele; a recepção não vê."""
    _require(user, (Role.OWNER, Role.PROFESSIONAL))
    return user


def owner_shop(user: User = Depends(owner_user)) -> Shop:
    return user.shop


def staff_shop(user: User = Depends(staff_user)) -> Shop:
    return user.shop


def is_pro(user: User) -> bool:
    return user.role == Role.PROFESSIONAL


def own_barber_id(user: User) -> int | None:
    """Profissional: o id do próprio cadastro de profissional (filtra agenda, clientes e comissões).
    Profissional sem cadastro vinculado não enxerga agenda nenhuma (id impossível)."""
    if not is_pro(user):
        return None
    return user.barber_id or -1


def served_by(barber_id: int):
    """Condição SQL: o cliente já teve agendamento com este profissional."""
    from .models import Customer
    return exists(select(Appointment.id).where(Appointment.customer_id == Customer.id,
                                               Appointment.barber_id == barber_id))
