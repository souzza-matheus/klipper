from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Membership, User

bearer = HTTPBearer(auto_error=False)


def _pw_bytes(pw: str) -> bytes:
    return pw.encode()[:72]  # bcrypt só considera os primeiros 72 bytes (e recusa mais que isso)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(_pw_bytes(pw), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(pw), hashed.encode())
    except ValueError:
        return False


# Hash de uma senha qualquer: o login confere contra ele quando o e-mail não existe, para o tempo de resposta não
# revelar quais e-mails estão cadastrados
_DUMMY_HASH = bcrypt.hashpw(b"senha-que-nao-existe", bcrypt.gensalt()).decode()


def check_password_or_dummy(pw: str, hashed: str | None) -> bool:
    if hashed is None:
        check_password(pw, _DUMMY_HASH)
        return False
    return check_password(pw, hashed)


def _claims(user: User) -> dict:
    """Quem e em qual negócio: o token vale só para o vínculo (negócio ativo) e cai quando a conta ou o vínculo
    mudam (ver = conta, mv = vínculo)."""
    m = user.membership
    return {"sub": str(user.id), "shop": m.shop_id, "mv": m.version or 0, "ver": user.token_version or 0}


def make_token(user: User, client: str = "app") -> str:
    """Token de acesso do negócio ativo. App nativo: validade longa (guardado no SecureStore). Web: 15 minutos."""
    now = datetime.now(timezone.utc)
    exp = now + (timedelta(minutes=settings.web_access_minutes) if client == "web"
                 else timedelta(hours=settings.jwt_expire_hours))
    claims = {**_claims(user), "exp": exp}
    if client == "web":
        claims["cli"] = "web"  # /auth/refresh e a troca de senha devolvem de novo um token curto
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def make_refresh_token(user: User) -> str:
    """Refresh token da versão web: só serve em /auth/token (typ=refresh), nunca como token de acesso."""
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.web_refresh_hours)
    return jwt.encode({**_claims(user), "typ": "refresh", "exp": exp}, settings.jwt_secret, algorithm="HS256")


def make_selection_token(user: User) -> str:
    """Login de quem tem mais de um negócio: vale 5 minutos e só em /auth/select (escolher o negócio)."""
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({"sub": str(user.id), "ver": user.token_version or 0, "typ": "select", "exp": exp},
                      settings.jwt_secret, algorithm="HS256")


def active_memberships(user: User) -> list[Membership]:
    """Negócios em que a pessoa pode entrar agora: vínculo ativo e negócio não suspenso."""
    if not user.active:
        return []
    return [m for m in user.memberships if m.active and m.shop is not None and m.shop.active]


EXPIRED = "Sessão expirada, faça login de novo"


def _user_from(payload: dict, db: Session) -> User:
    user_id = int(payload["sub"])
    user = db.get(User, user_id) if 0 < user_id < 2**31 else None
    if user is None or not user.active or payload.get("ver", 0) != (user.token_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED)  # revogado por "sair de todos os aparelhos"
    shop_id = payload.get("shop")
    if not isinstance(shop_id, int):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED)
    m = next((x for x in active_memberships(user) if x.shop_id == shop_id), None)
    # Vínculo desativado, papel trocado (versão nova) ou negócio suspenso: o token deste negócio deixa de valer
    if m is None or payload.get("mv", 0) != (m.version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED)
    user.use_membership(m)
    return user


def user_from_token(raw: str, typ: str, db: Session) -> User:
    """Usuário de um token especial (refresh da web ou escolha de negócio). Escolha: o negócio ainda não existe."""
    try:
        payload = jwt.decode(raw, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        if payload.get("typ") != typ:
            raise ValueError
        if typ == "select":
            user = db.get(User, int(payload["sub"]))
            if user is None or not user.active or payload.get("ver", 0) != (user.token_version or 0):
                raise ValueError
            return user
        return _user_from(payload, db)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, EXPIRED)


def user_from_refresh(raw: str, db: Session) -> User:
    return user_from_token(raw, "refresh", db)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login")
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"],
                             options={"require": ["exp", "sub"]})
        if payload.get("typ"):  # refresh token e token de escolha de negócio não abrem a API
            raise ValueError
        int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):  # token inválido nunca vira erro 500
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
    try:
        user = _user_from(payload, db)
        user.token_client = "web" if payload.get("cli") == "web" else "app"
        return user
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
