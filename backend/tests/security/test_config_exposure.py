"""Configuração e exposição: modo de produção, documentação, CORS, cabeçalhos, tamanho do corpo, erros 500, logs e
arquivos de implantação."""
import logging
import os

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.main import app, create_app
from app.security import SECURITY_HEADERS

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def prod_settings(**over) -> Settings:
    base = dict(dev_mode=False, jwt_secret="j" * 40, webhook_secret="w" * 40, setup_token="s" * 40,
                cors_origins="https://app.syncserv.com.br", _env_file=None)
    return Settings(**{**base, **over})


def test_dev_routes_are_404_in_production(two, monkeypatch):
    monkeypatch.setattr(settings, "dev_mode", False)
    assert two.anon.post("/dev/simulate", json={"phone": "31999990000", "text": "painel"}).status_code == 404
    assert two.anon.post("/dev/run-jobs").status_code == 404


def test_docs_and_openapi_are_off_in_production():
    c = TestClient(create_app(prod_settings()))
    for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert c.get(path).status_code == 404, path
    dev = TestClient(create_app(Settings(dev_mode=True, _env_file=None)))
    assert dev.get("/openapi.json").status_code == 200


def test_cors_in_production_only_allows_configured_origins():
    c = TestClient(create_app(prod_settings()))
    pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    evil = c.options("/api/me", headers={"Origin": "https://malicioso.example", **pre})
    assert evil.headers.get("access-control-allow-origin") is None
    ok = c.options("/api/me", headers={"Origin": "https://app.syncserv.com.br", **pre})
    assert ok.headers.get("access-control-allow-origin") == "https://app.syncserv.com.br"
    # Sem origens configuradas: nenhuma (o app nativo não usa CORS)
    none = TestClient(create_app(prod_settings(cors_origins="")))
    assert none.get("/health", headers={"Origin": "https://malicioso.example"}).headers.get(
        "access-control-allow-origin") is None
    with pytest.raises(RuntimeError):
        create_app(prod_settings(cors_origins="*"))


def test_security_headers_on_every_response(two):
    for r in (two.anon.get("/health"), two.anon.get("/api/me"), two.ca.get("/api/shop"),
              two.anon.post("/webhook/evolution", json={})):
        for k, v in SECURITY_HEADERS.items():
            assert r.headers.get(k) == v, (r.url, k)
        assert "server" not in r.headers and "x-powered-by" not in r.headers
    assert two.ca.get("/api/shop").headers["cache-control"] == "no-store"


def test_body_size_limit(two):
    big = b'{"email":"a@b.com","password":"' + b"x" * (settings.max_body_bytes + 1) + b'"}'
    r = two.anon.post("/api/auth/login", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_500_never_returns_stack_trace(two, monkeypatch):
    from app.services import whatsapp as wa

    def boom(shop):
        raise RuntimeError("detalhe interno SEGREDO-XYZ em /home/servidor/app.py linha 42")
    monkeypatch.setattr(wa, "connection_state", boom)
    c = TestClient(app, raise_server_exceptions=False)
    c.headers.update(two.ca.headers)
    r = c.get("/api/whatsapp/status")
    assert r.status_code == 500
    assert r.json() == {"detail": "Erro interno. Tente de novo em instantes."}
    assert "Traceback" not in r.text and "SEGREDO" not in r.text and ".py" not in r.text


def test_secrets_never_reach_the_logs(two, monkeypatch, caplog):
    s = {"webhook": "SENTINELA-WEBHOOK-7f3a9", "setup": "SENTINELA-SETUP-91bc2", "apikey": "SENTINELA-APIKEY-c0ffee",
         "gemini": "SENTINELA-GEMINI-5e5e5", "password": "SENTINELA-SENHA-a1b2"}
    monkeypatch.setattr(settings, "webhook_secret", s["webhook"])
    monkeypatch.setattr(settings, "setup_token", s["setup"])
    monkeypatch.setattr(settings, "evolution_api_key", s["apikey"])
    monkeypatch.setattr(settings, "evolution_url", "http://evolution:8080")
    monkeypatch.setattr(settings, "gemini_api_key", s["gemini"])

    def evolution(method, url, headers=None, timeout=None, json=None, params=None):
        assert headers["apikey"] == s["apikey"]
        return httpx.Response(401, json={"error": "Unauthorized"}, request=httpx.Request(method, url))
    monkeypatch.setattr(httpx, "request", evolution)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("recusada")))

    caplog.set_level(logging.DEBUG)
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/api/auth/login", json={"email": "admin@demo.com", "password": s["password"]})
    token = c.post("/api/auth/login", json={"email": "admin@demo.com", "password": "demo123"}).json()["token"]
    c.headers["Authorization"] = f"Bearer {token}"
    c.post("/api/auth/register", json={"setup_token": s["setup"] + "x", "shop_name": "x", "owner_name": "y",
                                       "email": "z@exemplo.com", "password": s["password"]})
    c.post("/api/whatsapp/connect")
    c.get("/api/whatsapp/status")
    c.post(f"/webhook/evolution?secret={s['webhook']}", json={
        "event": "messages.upsert", "instance": "barbearia-demo",
        "data": {"key": {"remoteJid": "5531955554444@s.whatsapp.net"}, "message": {"conversation": "oi"}}})
    # Linha de acesso do uvicorn com o secret na URL (instâncias antigas): o filtro apaga o valor
    logging.getLogger("uvicorn.access").info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "POST",
                                             f"/webhook/evolution?secret={s['webhook']}", "1.1", 200)
    text = caplog.text
    for name, value in {**s, "token": token, "jwt": settings.jwt_secret}.items():
        assert value not in text, f"{name} apareceu no log"
    assert "secret=***" in text


def test_dockerfile_hides_server_header_and_trusts_only_the_proxy():
    cmd = open(os.path.join(ROOT, "backend", "Dockerfile")).read()
    assert "--no-server-header" in cmd and "--forwarded-allow-ips" in cmd


def test_production_compose_publishes_only_the_backend_on_localhost():
    base = yaml.safe_load(open(os.path.join(ROOT, "docker-compose.yml")))
    for name in ("db", "evolution"):  # no compose de desenvolvimento, só no 127.0.0.1
        for p in base["services"][name].get("ports", []):
            assert str(p).startswith("127.0.0.1:"), (name, p)
    assert "ports" not in base["services"]["redis"]
    prod = open(os.path.join(ROOT, "docker-compose.prod.yml")).read()
    assert '"127.0.0.1:${BACKEND_PORT:-8002}:8000"' in prod and 'DEV_MODE: "false"' in prod
    assert prod.count("!reset []") == 2  # db e evolution sem porta publicada


def test_gitignore_covers_secrets_and_reports():
    ignore = open(os.path.join(ROOT, ".gitignore")).read().split()
    for entry in (".env", "qrcode.png", "CLAUDE-SECURITY-*/", "backend/.venv/"):
        assert entry in ignore, entry


def test_mobile_keeps_token_in_secure_store_and_has_no_api_keys():
    src = os.path.join(ROOT, "mobile", "src")
    code = ""
    for dirpath, _, files in os.walk(src):
        for f in files:
            if f.endswith(".js"):
                code += open(os.path.join(dirpath, f), encoding="utf-8").read()
    code += open(os.path.join(ROOT, "mobile", "App.js"), encoding="utf-8").read()
    assert "AsyncStorage" not in code and "SecureStore.setItemAsync('token'" in code
    import re
    for pattern in (r"AIza[0-9A-Za-z_-]{20,}", r"\bapikey\b", "GEMINI", "EVOLUTION_API_KEY", r"\bsk-[A-Za-z0-9]{20,}"):
        assert not re.search(pattern, code), pattern


def test_dev_mode_is_off_by_default(monkeypatch):
    """Sem DEV_MODE=true no ambiente, a API roda como produção (seguro por padrão)."""
    monkeypatch.delenv("DEV_MODE", raising=False)
    assert Settings(_env_file=None).dev_mode is False
