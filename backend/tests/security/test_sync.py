"""Sincronização offline: /api/sync/pull e /api/sync/push."""
import uuid
from datetime import datetime, time, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Appointment, Comanda, ComandaItem, Customer, OutboxMessage, StockMovement

from .conftest import B_MARK, _future_weekday, no_leak


def uid() -> str:
    return str(uuid.uuid4())


def op(entity, action, id=None, data=None, version=None, base=None):
    return {"operation_id": uid(), "entity": entity, "action": action, "id": id, "data": data or {},
            "version": version, "base": base or {}}


def pull_all(client, cursor="0", limit=500):
    """Puxa até has_more=false; devolve (mudanças por entidade, excluídos por entidade, cursor final, páginas)."""
    changes, deleted, pages = {}, {}, 0
    while True:
        r = client.get("/api/sync/pull", params={"cursor": cursor, "limit": limit})
        assert r.status_code == 200, r.text
        body = r.json()
        pages += 1
        for k, rows in body["changes"].items():
            changes.setdefault(k, []).extend(rows)
        for k, ids in body["deleted"].items():
            deleted.setdefault(k, []).extend(ids)
        cursor = body["cursor"]
        if not body["has_more"]:
            return changes, deleted, cursor, pages


def _login(email, password) -> TestClient:
    from app.main import app
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer " + c.post("/api/auth/login", json={"email": email, "password": password}
                                                    ).json()["token"]
    return c


def test_pull_returns_everything_once_and_then_only_changes(two):
    changes, deleted, cursor, _ = pull_all(two.ca)
    assert {"services", "barbers", "customers", "appointments", "products", "comandas", "comanda_items"} <= set(changes)
    appt = next(a for a in changes["appointments"] if a["server_id"] == two.a.appt.id)
    assert appt["id"] == two.a.appt.uuid and appt["customer_id"] == two.a.customer.uuid
    assert appt["barber_id"] == two.a.barber.uuid and appt["version"] >= 1
    # Nada mudou: o próximo pull vem vazio
    again = two.ca.get("/api/sync/pull", params={"cursor": cursor}).json()
    assert again["changes"] == {} and again["deleted"] == {} and again["cursor"] == cursor
    # Muda um cliente: só ele volta, com versão nova
    two.ca.put(f"/api/customers/{two.a.customer.id}", json={"notes": "prefere tesoura"})
    body = two.ca.get("/api/sync/pull", params={"cursor": cursor}).json()
    assert list(body["changes"]) == ["customers"]
    row = body["changes"]["customers"][0]
    assert row["id"] == two.a.customer.uuid and row["notes"] == "prefere tesoura" and row["version"] == 2


def test_pull_pagination_has_no_gaps_or_duplicates(two):
    full, _, _, _ = pull_all(two.ca)
    paged, _, _, pages = pull_all(two.ca, limit=2)
    assert pages > 3
    for entity, rows in full.items():
        ids = [r["id"] for r in paged.get(entity, [])]
        assert sorted(ids) == sorted(r["id"] for r in rows), entity
        assert len(ids) == len(set(ids)), entity


def test_deletions_come_as_tombstones(two):
    _, _, cursor, _ = pull_all(two.ca)
    block = two.a.block
    assert two.ca.delete(f"/api/blocks/{block.id}").status_code == 200
    body = two.ca.get("/api/sync/pull", params={"cursor": cursor}).json()
    assert body["deleted"] == {"blocks": [block.uuid]}
    # Some das telas normais
    assert block.id not in [b["id"] for b in two.ca.get("/api/blocks", params={"date_from": "2026-01-01"}).json()]


def test_pull_never_mixes_shops(two):
    changes, _, _, _ = pull_all(two.ca)
    import json
    assert no_leak(json.dumps(changes), two.b)
    changes_b, _, _, _ = pull_all(two.cb)
    assert B_MARK in json.dumps(changes_b)


def test_pull_is_filtered_by_role(two):
    pro = _login(two.a.extra["pro"].email, two.a.extra["pro_password"])
    changes, _, _, _ = pull_all(pro)
    assert set(changes) <= {"services", "barbers", "blocks", "customers", "appointments"}
    assert {a["barber_id"] for a in changes["appointments"]} == {two.a.barber.uuid}
    assert all("access_status" not in c for c in changes["customers"])
    rec = _login(two.a.extra["reception"].email, two.a.extra["reception_password"])
    changes, _, _, _ = pull_all(rec)
    assert "products" in changes and all("cost" not in p for p in changes["products"])
    owner, _, _, _ = pull_all(two.ca)
    assert all("cost" in p for p in owner["products"])


def _slot(days=8, hour=15):
    return datetime.combine(_future_weekday(days), time(hour)).isoformat()


def test_push_is_idempotent_and_whatsapp_goes_out_once(two):
    a = two.a
    o = op("appointments", "create", uid(), {"customer_phone": "5531955554444", "customer_name": "Offline",
                                             "barber_id": a.barber.uuid, "service_id": a.service.uuid,
                                             "start": _slot()})
    first = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert first["status"] == "aplicado" and first["id"] == o["id"]
    again = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert again["status"] == "aplicado" and again["replayed"] is True
    db = two.db
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Appointment).where(Appointment.uuid == o["id"])) == 1
    sent = db.scalars(select(OutboxMessage).where(OutboxMessage.phone == "5531955554444")).all()
    assert len(sent) == 1 and "agendado" in sent[0].text


def test_push_offline_booking_on_taken_slot_is_a_conflict(two):
    a = two.a
    start = _slot(hour=16)
    two.ca.post("/api/appointments", json={"customer_phone": "5531955550001", "barber_id": a.barber.id,
                                           "service_id": a.service.id, "start": start})
    o = op("appointments", "create", uid(), {"customer_phone": "5531955550002", "customer_name": "Atrasado",
                                             "barber_id": a.barber.uuid, "service_id": a.service.uuid,
                                             "start": start})
    res = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert res["status"] == "conflito" and res["reason"] == "horario_ocupado"
    two.db.expire_all()
    assert not two.db.scalar(select(Appointment).where(Appointment.uuid == o["id"]))
    assert not two.db.scalars(select(OutboxMessage).where(OutboxMessage.phone == "5531955550002")).all()
    # Remarcação offline para horário ocupado: também conflito, o agendamento fica onde estava
    before = two.db.get(Appointment, a.appt.id).start
    o = op("appointments", "update", a.appt.uuid, {"start": start}, version=1)
    res = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert res["status"] == "conflito" and res["server"]["start"] == before.isoformat()


def test_operations_run_in_order_and_one_failure_does_not_undo_the_others(two):
    a = two.a
    com_id, item_id = uid(), uid()
    ops = [
        op("comandas", "create", com_id, {"customer_id": a.customer.uuid}),
        op("comanda_items", "create", item_id, {"comanda_id": com_id, "kind": "product",
                                                "product_id": a.extra["product"].uuid, "quantity": 2}),
        op("comanda_items", "create", uid(), {"comanda_id": com_id, "kind": "product",
                                              "product_id": two.b.extra["product"].uuid}),  # de outra loja
        op("comanda_payments", "create", uid(), {"comanda_id": com_id, "method": "pix", "amount": "80"}),
        op("comandas", "close", com_id),
        op("inexistente", "create", uid()),
    ]
    res = two.ca.post("/api/sync/push", json={"operations": ops}).json()["results"]
    assert [r["status"] for r in res] == ["aplicado", "aplicado", "rejeitado", "aplicado", "aplicado", "rejeitado"]
    assert res[2]["reason"] == "nao_encontrado" and no_leak(str(res), two.b)
    two.db.expire_all()
    c = two.db.scalar(select(Comanda).where(Comanda.uuid == com_id))
    assert c.status == "closed"
    assert two.db.scalar(select(StockMovement.delta).join(ComandaItem).where(ComandaItem.uuid == item_id)) == -2


def test_append_only_entries_never_conflict(two):
    """Dois aparelhos lançando na mesma comanda ao mesmo tempo, cada um com a versão antiga: os dois entram."""
    cid = two.a.extra["comanda"].uuid
    pid = two.a.extra["product"].uuid
    d1 = op("comanda_items", "create", uid(), {"comanda_id": cid, "kind": "product", "product_id": pid}, version=1)
    d2 = op("comanda_items", "create", uid(), {"comanda_id": cid, "kind": "product", "product_id": pid}, version=1)
    m1 = op("stock_movements", "create", uid(), {"product_id": pid, "delta": "1", "reason": "internal"}, version=1)
    res = two.ca.post("/api/sync/push", json={"operations": [d1, d2, m1]}).json()["results"]
    assert [r["status"] for r in res] == ["aplicado"] * 3


def test_profile_edit_merges_different_fields_and_conflicts_on_same_field(two):
    c = two.a.customer
    two.db.expire_all()
    v = two.db.get(Customer, c.id).version
    # No servidor alguém mudou o nome
    two.ca.put(f"/api/customers/{c.id}", json={"name": "Nome Novo"})
    # Offline, outro aparelho (na versão antiga) mudou só a observação: merge
    o = op("customers", "update", c.uuid, {"notes": "alérgico a lâmina"}, version=v, base={"notes": c.notes})
    res = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert res["status"] == "aplicado"
    assert res["server"]["name"] == "Nome Novo" and res["server"]["notes"] == "alérgico a lâmina"
    # O mesmo campo mudado dos dois lados: conflito, nada é gravado
    o = op("customers", "update", c.uuid, {"name": "Outro Nome"}, version=v, base={"name": c.name})
    res = two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert res["status"] == "conflito" and res["fields"] == ["name"] and res["server"]["name"] == "Nome Novo"
    two.db.expire_all()
    assert two.db.get(Customer, c.id).name == "Nome Novo"


def test_push_respects_role_and_shop(two):
    pro = _login(two.a.extra["pro"].email, two.a.extra["pro_password"])
    res = pro.post("/api/sync/push", json={"operations": [
        op("comandas", "create", uid(), {"customer_id": two.a.customer.uuid}),
        op("appointments", "update", two.a.appt.uuid, {"status": "confirmed"}),
        op("appointments", "update", two.a.appt.uuid, {"status": "cancelled"}),
        op("appointments", "update", two.b.appt.uuid, {"status": "confirmed"}),
    ]}).json()["results"]
    assert [r["status"] for r in res] == ["rejeitado", "aplicado", "rejeitado", "rejeitado"]
    assert res[0]["reason"] == "sem_permissao" and res[3]["reason"] == "nao_encontrado"
    # O id de operação é por loja: B pode usar o mesmo sem receber o resultado de A
    o = op("blocks", "delete", two.b.block.uuid)
    assert two.ca.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]["status"] == "rejeitado"
    r = two.cb.post("/api/sync/push", json={"operations": [o]}).json()["results"][0]
    assert r["status"] == "aplicado" and "replayed" not in r


def test_push_input_limits(two):
    big = {"operations": [op("blocks", "delete", uid()) for _ in range(201)]}
    assert two.ca.post("/api/sync/push", json=big).status_code == 422
    bad = {"operations": [{**op("blocks", "delete", uid()), "operation_id": "x' OR 1=1 --"}]}
    assert two.ca.post("/api/sync/push", json=bad).status_code == 422
    res = two.ca.post("/api/sync/push", json={"operations": [op("blocks", "delete", "nao-e-uuid")]}).json()
    assert res["results"][0]["reason"] == "dados_invalidos"
    assert two.ca.get("/api/sync/pull", params={"cursor": -1}).status_code == 422


def test_pull_window_keeps_old_agenda_off_the_device(two):
    a = two.a
    old = datetime.combine(_future_weekday(0) - timedelta(days=60), time(10))
    ap = Appointment(shop_id=a.shop.id, customer_id=a.customer.id, barber_id=a.barber.id, service_id=a.service.id,
                     start=old, end=old + timedelta(minutes=30), price=a.service.price, status="completed")
    two.db.add(ap)
    two.db.commit()
    changes, _, _, _ = pull_all(two.ca)
    assert ap.uuid not in {x["id"] for x in changes["appointments"]}
