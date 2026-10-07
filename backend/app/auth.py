from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

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


def make_token(user: User, client: str = "app") -> str:
    """Token de acesso. App nativo: validade longa (guardado no SecureStore). Web: 15 minutos."""
    now = datetime.now(timezone.utc)
    exp = now + (timedelta(minutes=settings.web_access_minutes) if client == "web"
                 else timedelta(hours=settings.jwt_expire_hours))
    claims = {"sub": str(user.id), "shop": user.shop_id, "ver": user.token_version or 0, "exp": exp}
    if client == "web":
        claims["cli"] = "web"  # /auth/refresh e a troca de senha devolvem de novo um token curto
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def make_refresh_token(user: User) -> str:
    """Refresh token da versão web: só serve em /auth/token (typ=refresh), nunca como token de acesso."""
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.web_refresh_hours)
    return jwt.encode({"sub": str(user.id), "shop": user.shop_id, "ver": user.token_version or 0, "typ": "refresh",
                       "exp": exp}, settings.jwt_secret, algorithm="HS256")


def _user_from(payload: dict, db: Session) -> User:
    user_id = int(payload["sub"])
    user = db.get(User, user_id) if 0 < user_id < 2**31 else None
    if user is None or not user.active or payload.get("shop") not in (None, user.shop_id) \
            or payload.get("ver", 0) != (user.token_version or 0):  # revogado por "sair de todos os aparelhos"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
    return user


def user_from_refresh(raw: str, db: Session) -> User:
    try:
        payload = jwt.decode(raw, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        if payload.get("typ") != "refresh":
            raise ValueError
        return _user_from(payload, db)
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login")
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"],
                             options={"require": ["exp", "sub"]})
        if payload.get("typ") == "refresh":  # refresh token não abre a API
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
