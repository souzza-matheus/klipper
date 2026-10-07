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


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": str(user.id), "shop": user.shop_id, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login")
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"],
                             options={"require": ["exp", "sub"]})
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):  # token inválido nunca vira erro 500
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
    user = db.get(User, user_id) if 0 < user_id < 2**31 else None
    if user is None or payload.get("shop") not in (None, user.shop_id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
    return user
