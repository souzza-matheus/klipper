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


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": str(user.id), "shop": user.shop_id, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login")
    try:
        payload = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, faça login de novo")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário não encontrado")
    return user
