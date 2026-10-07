"""Carimbos da sincronização offline, aplicados pelo servidor em toda gravação (API, bot, rotinas e /api/sync/push).

- Linhas novas ou alteradas de tabelas com SyncMixin recebem updated_at (relógio do servidor), version + 1 e um
  sync_seq tirado do contador da loja (shops.sync_seq). O UPDATE no contador trava a linha da loja até o commit, então
  as mudanças de uma loja são confirmadas na ordem do sync_seq: o cursor do pull nunca pula uma mudança que ainda
  estava em andamento.
- Consultas normais não enxergam linhas com deleted_at (tombstones). O pull usa include_deleted=True.
"""
from sqlalchemy import event, update
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from .config import now_local
from .models import Shop, SyncMixin


def _changed(session: Session, obj) -> bool:
    return session.is_modified(obj, include_collections=True)


@event.listens_for(Session, "before_flush")
def _stamp(session: Session, flush_context, instances) -> None:
    by_shop: dict[int, list] = {}
    for obj in session.new:
        if isinstance(obj, SyncMixin):
            by_shop.setdefault(obj.shop_id, []).append((obj, True))
    for obj in session.dirty:
        if isinstance(obj, SyncMixin) and _changed(session, obj):
            by_shop.setdefault(obj.shop_id, []).append((obj, False))
    if not by_shop:
        return
    now = now_local()
    conn = session.connection()
    for shop_id in sorted(k for k in by_shop if k is not None):  # sempre na mesma ordem: sem deadlock entre lojas
        rows = by_shop[shop_id]
        top = conn.execute(update(Shop).where(Shop.id == shop_id).values(sync_seq=Shop.sync_seq + len(rows))
                           .returning(Shop.sync_seq)).scalar_one()
        for i, (obj, is_new) in enumerate(rows):
            obj.sync_seq = top - len(rows) + 1 + i
            obj.updated_at = now
            if not is_new:
                obj.version = (obj.version or 1) + 1


@event.listens_for(Session, "do_orm_execute")
def _hide_deleted(state: ORMExecuteState) -> None:
    if state.is_select and not state.execution_options.get("include_deleted", False):
        state.statement = state.statement.options(
            with_loader_criteria(SyncMixin, lambda cls: cls.deleted_at.is_(None), include_aliases=True))


def soft_delete(obj) -> None:
    """Exclui uma linha sincronizável: some das consultas e vira tombstone no pull."""
    obj.deleted_at = now_local()
