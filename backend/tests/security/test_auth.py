"""Autenticação, sessão, força bruta, segredos de produção e senhas."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy import select

from app.config import Settings, settings
from app.models import User
from app.security import check_production, login_limiter, production_problems

PUBLIC = {("POST", "/api/auth/login"), ("POST", "/api/auth/register")}


def _api_routes():
    import re
    from .test_isolation import all_routes
    for m, path in sorted(all_routes()):
        if path.startswith("/api/") and (m, path) not in PUBLIC:
            yield m, re.sub(r"\{[^}]+\}", "1", path)


def _token(**claims) -> str:
    payload = {"sub": "1", "shop": 1, "exp": datetime.now(timezone.utc) + timedelta(hours=1), **claims}
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, settings.jwt_secret, algorithm="HS256")


def test_every_api_route_requires_login(two):
    routes = list(_api_routes())
    assert len(routes) > 60
    for method, path in routes:
        r = two.anon.request(method, path, json={})
        assert r.status_code == 401, f"{method} {path} sem token: {r.status_code}"


BAD_TOKENS = {
    "malformado": "abc.def",
    "lixo": "x" * 500,
    "assinatura errada": jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                                    "outro-segredo", algorithm="HS256"),
    "expirado": None,  # preenchido no teste (precisa do segredo atual)
    "alg none": jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, None,
                           algorithm="none"),
}


@pytest.mark.parametrize("name", list(BAD_TOKENS) + ["usuario inexistente", "sub nao numerico", "sem sub",
                                                     "sem exp", "sub negativo", "shop trocado"])
def test_invalid_tokens_get_401(two, name):
    token = {
        "expirado": lambda: _token(exp=datetime.now(timezone.utc) - timedelta(minutes=1)),
        "usuario inexistente": lambda: _token(sub="999999"),
        "sub nao numerico": lambda: _token(sub="admin"),
        "sem sub": lambda: _token(sub=None),
        "sem exp": lambda: jwt.encode({"sub": "1"}, settings.jwt_secret, algorithm="HS256"),
        "sub negativo": lambda: _token(sub="-1"),
        "shop trocado": lambda: _token(sub=str(two.db.scalar(select(User.id).where(User.email == "admin@demo.com"))),
                                       shop=two.b.shop.id),
    }.get(name, lambda: BAD_TOKENS[name])()
    for path in ("/api/me", "/api/shop", f"/api/customers/{two.a.customer.id}"):
        r = two.anon.get(path, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, f"{name} em {path}: {r.status_code} {r.text}"


def test_login_error_does_not_reveal_which_emails_exist(two):
    wrong_email = two.anon.post("/api/auth/login", json={"email": "ninguem@exemplo.com", "password": "x" * 10})
    wrong_pass = two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "x" * 10})
    assert wrong_email.status_code == wrong_pass.status_code == 401
    assert wrong_email.json() == wrong_pass.json()


def test_brute_force_by_email_is_blocked(two):
    for _ in range(login_limiter.max_per_email):
        assert two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "errada!!"}).status_code == 401
    r = two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0  # bloqueado mesmo com a senha certa
    # Outro e-mail do mesmo IP ainda entra
    assert two.anon.post("/api/auth/login", json={"email": two.b.user_email, "password": two.b.password}).status_code == 200


def test_brute_force_by_ip_is_blocked(two):
    for i in range(login_limiter.max_per_ip):
        two.anon.post("/api/auth/login", json={"email": f"chute{i}@exemplo.com", "password": "errada!!"})
    r = two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"})
    assert r.status_code == 429


def test_successful_login_clears_email_failures(two):
    for _ in range(login_limiter.max_per_email - 1):
        two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "errada!!"})
    assert two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).status_code == 200
    assert two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "errada!!"}).status_code == 401


def test_register_requires_setup_token(two):
    body = {"setup_token": "errado", "shop_name": "X", "owner_name": "Y", "email": "novo@exemplo.com",
            "password": "senha-forte-1"}
    assert two.anon.post("/api/auth/register", json=body).status_code == 403
    assert two.anon.post("/api/auth/register", json={**body, "setup_token": ""}).status_code == 403
    assert two.anon.post("/api/auth/register", json={**body, "setup_token": settings.setup_token + " "}).status_code == 403
    for _ in range(login_limiter.max_per_ip):  # chutar o token de setup também é bloqueado
        two.anon.post("/api/auth/register", json=body)
    assert two.anon.post("/api/auth/register", json={**body, "setup_token": settings.setup_token}).status_code == 429


def test_register_password_policy(two):
    body = {"setup_token": settings.setup_token, "shop_name": "X", "owner_name": "Y", "email": "novo@exemplo.com"}
    assert two.anon.post("/api/auth/register", json={**body, "password": "1234567"}).status_code == 422
    assert two.anon.post("/api/auth/register", json={**body, "password": "a" * 129}).status_code == 422


@pytest.mark.parametrize("field", ["jwt_secret", "webhook_secret", "setup_token"])
def test_production_refuses_example_secrets(field):
    strong = {"jwt_secret": "j" * 40, "webhook_secret": "w" * 40, "setup_token": "s" * 40}
    cfg = SimpleNamespace(dev_mode=False, cors_origins="", **strong)
    check_production(cfg)  # forte: sobe
    for weak in (Settings.model_fields[field].default, "", "curto", "troque-isso-depois-xxxxxxxx"):
        bad = SimpleNamespace(**{**vars(cfg), field: weak})
        with pytest.raises(RuntimeError):
            check_production(bad)
    # Em desenvolvimento os valores de exemplo continuam aceitos
    check_production(SimpleNamespace(**{**vars(cfg), field: Settings.model_fields[field].default, "dev_mode": True}))


def test_production_app_does_not_start_with_defaults(monkeypatch):
    from app.main import create_app
    defaults = {k: Settings.model_fields[k].default for k in ("jwt_secret", "webhook_secret", "setup_token")}
    cfg = Settings(dev_mode=False, _env_file=None, **defaults)
    assert len(production_problems(cfg)) == 3
    with pytest.raises(RuntimeError):
        create_app(cfg)


def test_passwords_are_bcrypt_and_never_returned(two):
    hashes = list(two.db.scalars(select(User.password_hash)))
    assert hashes and all(h.startswith("$2b$") for h in hashes)
    from .test_isolation import list_urls
    for url in list_urls(two):
        body = two.ca.get(url).text
        assert "password" not in body.lower() and "$2b$" not in body, url
    login = two.anon.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).text
    assert "$2b$" not in login and "demo123" not in login
