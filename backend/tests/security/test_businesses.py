"""Login só com e-mail e senha: o servidor descobre o negócio (vínculo usuário–negócio), a pessoa escolhe quando tem
mais de um, troca sem sair da conta, e o token de um negócio nunca abre outro."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.models import Membership, Role, User

DISABLED = "Seu acesso foi desativado. Fale com o responsável pelo negócio."


def _app():
    from app.main import app
    return TestClient(app)


def _login(email, password, **extra):
    return _app().post("/api/auth/login", json={"email": email, "password": password, **extra})


def _bearer(token):
    c = _app()
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def _second_business(two, role=Role.RECEPTION):
    """O dono de A passa a entrar também em B (com outro papel)."""
    owner_a = two.db.scalar(select(User).where(User.email == two.a.user_email))
    owner_a.memberships.append(Membership(shop_id=two.b.shop.id, role=role, active=True))
    two.db.commit()
    return owner_a


def test_one_business_goes_straight_in(two):
    r = _login(two.a.user_email, two.a.password)
    assert r.status_code == 200
    body = r.json()
    assert body["token"] and body["shop_id"] == two.a.shop.id and body["businesses_count"] == 1
    assert "choose" not in body


def test_two_businesses_return_the_list_and_the_choice_gives_the_right_token(two):
    _second_business(two)
    r = _login(two.a.user_email, two.a.password)
    assert r.status_code == 200
    body = r.json()
    assert body["choose"] is True and "token" not in body
    assert {(b["shop_id"], b["role"]) for b in body["businesses"]} == {(two.a.shop.id, "owner"),
                                                                       (two.b.shop.id, "reception")}
    names = {b["shop_id"]: b for b in body["businesses"]}
    assert names[two.b.shop.id]["name"] == two.b.shop.name and names[two.b.shop.id]["niche"] == "barbershop"
    assert names[two.b.shop.id]["role_label"] == "Recepção"

    sel = body["selection_token"]
    r = _app().post("/api/auth/select", json={"selection_token": sel, "shop_id": two.b.shop.id})
    assert r.status_code == 200
    tok = r.json()
    assert tok["shop_id"] == two.b.shop.id and tok["role"] == "reception" and tok["businesses_count"] == 2
    me = _bearer(tok["token"]).get("/api/me").json()
    assert me["shop_id"] == two.b.shop.id and me["role"] == "reception"
    # Recepção em B: o financeiro do dono não abre (o papel é o do vínculo, não o de A)
    assert _bearer(tok["token"]).get("/api/finance/summary").status_code == 403

    # O token de escolha não abre a API e não escolhe negócio de outra pessoa
    assert _bearer(sel).get("/api/me").status_code == 401
    other = two.db.scalar(select(Membership).where(Membership.shop_id != two.a.shop.id,
                                                   Membership.shop_id != two.b.shop.id))
    if other is not None:
        assert _app().post("/api/auth/select", json={"selection_token": sel,
                                                     "shop_id": other.shop_id}).status_code == 403
    assert _app().post("/api/auth/select", json={"selection_token": "x.y.z",
                                                 "shop_id": two.b.shop.id}).status_code == 401


def test_last_business_remembered_by_the_app_goes_straight_in(two):
    _second_business(two)
    r = _login(two.a.user_email, two.a.password, shop_id=two.b.shop.id)
    assert r.status_code == 200 and r.json()["shop_id"] == two.b.shop.id and r.json()["token"]
    # Negócio que a pessoa não tem (ou perdeu): volta a lista, sem token
    r = _login(two.a.user_email, two.a.password, shop_id=999999)
    assert r.json()["choose"] is True


def test_no_active_business_is_refused_with_a_clear_message(two):
    rec = two.a.extra["reception"]
    m = two.db.scalar(select(Membership).where(Membership.user_id == rec.id))
    m.active = False
    two.db.commit()
    r = _login(rec.email, two.a.extra["reception_password"])
    assert r.status_code == 403 and r.json()["detail"]["message"] == DISABLED and "token" not in r.text
    # Senha errada continua a mensagem genérica (não revela se o e-mail existe nem se está desativado)
    assert _login(rec.email, "errada-123").json()["detail"] == "E-mail ou senha incorretos"
    assert _login("ninguem@exemplo.com", "errada-123").json()["detail"] == "E-mail ou senha incorretos"


def test_suspended_business_blocks_its_team(two):
    two.b.shop.active = False
    two.db.commit()
    r = _login(two.b.user_email, two.b.password)
    assert r.status_code == 403 and r.json()["detail"]["message"] == DISABLED
    assert two.cb.get("/api/me").status_code == 401  # token já emitido também cai


def test_email_is_normalized_and_unique(two):
    r = _login("  " + two.a.user_email.upper() + "  ", two.a.password)
    assert r.status_code == 200 and r.json()["token"]
    r = two.ca.post("/api/users", json={"name": "Nova", "email": "  Nova.Pessoa@Exemplo.COM ", "role": "reception"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "nova.pessoa@exemplo.com"
    # O mesmo e-mail com outra caixa é o mesmo e-mail (único na plataforma)
    r = two.cb.post("/api/users", json={"name": "Copia", "email": "NOVA.pessoa@exemplo.com", "role": "reception"})
    assert r.status_code == 409


def test_token_of_business_a_never_opens_business_b(two):
    _second_business(two)
    tok_a = _login(two.a.user_email, two.a.password, shop_id=two.a.shop.id).json()["token"]
    c = _bearer(tok_a)
    assert c.get("/api/me").json()["shop_id"] == two.a.shop.id
    # Dados de B pelo token de A: não encontrados (a rota usa o negócio do token)
    assert c.get(f"/api/customers/{two.b.customer.id}").status_code == 404
    assert two.b.customer.phone not in c.get("/api/customers").text

    # Token de quem não tem vínculo com B, com o negócio trocado para B (mesmo assinado): recusado
    rec = two.a.extra["reception"]
    forged = jwt.encode({"sub": str(rec.id), "shop": two.b.shop.id, "ver": 0, "mv": 0,
                         "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, settings.jwt_secret,
                        algorithm="HS256")
    assert _bearer(forged).get("/api/me").status_code == 401


def test_switch_business_without_logging_out(two):
    _second_business(two)
    tok_a = _login(two.a.user_email, two.a.password, shop_id=two.a.shop.id).json()["token"]
    c = _bearer(tok_a)
    assert {b["shop_id"] for b in c.get("/api/auth/businesses").json()} == {two.a.shop.id, two.b.shop.id}
    r = c.post("/api/auth/switch", json={"shop_id": two.b.shop.id})
    assert r.status_code == 200
    me = _bearer(r.json()["token"]).get("/api/me").json()
    assert me["shop_id"] == two.b.shop.id and me["role"] == "reception"
    # Negócio sem vínculo: recusado
    rec = two.a.extra["reception"]
    c_rec = _bearer(_login(rec.email, two.a.extra["reception_password"]).json()["token"])
    assert c_rec.post("/api/auth/switch", json={"shop_id": two.b.shop.id}).status_code == 403


def test_leaving_one_business_keeps_the_other(two):
    """Desativado em B pelo dono de B: os tokens de B caem; os de A continuam."""
    owner_a = _second_business(two)
    tok_a = _login(two.a.user_email, two.a.password, shop_id=two.a.shop.id).json()["token"]
    tok_b = _login(two.a.user_email, two.a.password, shop_id=two.b.shop.id).json()["token"]
    assert two.cb.put(f"/api/users/{owner_a.id}", json={"active": False}).status_code == 200
    assert _bearer(tok_b).get("/api/me").status_code == 401
    assert _bearer(tok_a).get("/api/me").status_code == 200
    r = _login(two.a.user_email, two.a.password)  # só sobrou A: entra direto
    assert r.json()["shop_id"] == two.a.shop.id and r.json()["token"]


def test_owner_cannot_reset_the_password_of_someone_who_uses_another_business(two):
    owner_a = _second_business(two)
    r = two.cb.post(f"/api/users/{owner_a.id}/reset-password")
    assert r.status_code == 409
    assert _login(two.a.user_email, two.a.password).status_code == 200  # senha intacta
