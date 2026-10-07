"""Sincronização do app offline (ver app/services/sync.py). Qualquer papel; o que cada um recebe e pode enviar
depende do papel."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import schemas as S
from ..db import get_db
from ..models import User
from ..permissions import team_user
from ..services import sync

router = APIRouter()


@router.get("/sync/pull", tags=["sync"])
def sync_pull(cursor: int = Query(0, ge=0, lt=2**62), limit: int = Query(sync.PAGE, ge=1, le=1000),
              user: User = Depends(team_user), db: Session = Depends(get_db)):
    """Mudanças depois do cursor. Repita com o cursor devolvido enquanto has_more for true."""
    return sync.pull(db, user, cursor, limit)


@router.post("/sync/push", tags=["sync"])
def sync_push(body: S.SyncPushIn, user: User = Depends(team_user), db: Session = Depends(get_db)):
    return {"results": sync.push(db, user, body.operations)}
