"""Conexão com a Evolution API 2.3 (QR Code, código de pareamento, desconectar) com respostas simuladas, sem rede."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.api import admin
from app.config import settings
from app.schemas import PairingCodeIn
from app.services import whatsapp as wa

QR = "data:image/png;base64,iVBORw0KGgo"
SHOP = SimpleNamespace(evolution_instance="barbearia-demo", webhook_secret="segredo-proprio-da-barbearia-0123456789")
MISSING = (404, {"status": 404, "error": "Not Found",
                 "response": {"message": ['The "barbearia-demo" instance does not exist']}})


def state(s):
    return 200, {"instance": {"instanceName": "barbearia-demo", "state": s}}


def qr(count=1, base64=QR, pairing=None):
    return 200, {"pairingCode": pairing, "code": "2@abc", "base64": base64, "count": count}


class FakeEvolution:
    """Responde cada rota com a próxima resposta da fila (a última se repete) e registra as chamadas."""

    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    def __call__(self, method, url, headers=None, timeout=None, json=None, params=None):
        path = url.removeprefix(settings.evolution_url)
        self.calls.append((method, path, params, json))
        key = f"{method} {path.split('/barbearia-demo')[0]}"
        if key not in self.routes:
            raise AssertionError(f"rota inesperada: {key}")
        queue = self.routes[key]
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(body, Exception):
            raise body
        return httpx.Response(status, json=body, request=httpx.Request(method, url))

    def called(self, key):
        return [c for c in self.calls if f"{c[0]} {c[1].split('/barbearia-demo')[0]}" == key]


@pytest.fixture()
def evo(monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "http://evolution:8080")
    monkeypatch.setattr(wa, "_sleep", lambda s: None)

    def install(routes):
        fake = FakeEvolution(routes)
        monkeypatch.setattr(wa.httpx, "request", fake)
        return fake
    return install


def test_modo_simulacao(monkeypatch):
    monkeypatch.setattr(settings, "evolution_url", "")
    r = admin.whatsapp_connect(SHOP)
    assert r["state"] == "simulacao" and r["qrcode"] is None and "simulação" in r["message"]
    assert wa.connection_state(SHOP) == "simulacao"


def test_instancia_inexistente_e_criada_com_webhook(evo):
    fake = evo({
        "GET /instance/connectionState": [MISSING],
        "POST /instance/create": [(201, {"instance": {"instanceName": "barbearia-demo", "status": "connecting"},
                                         "qrcode": {"pairingCode": None, "code": "2@abc", "base64": QR, "count": 1}})],
    })
    r = admin.whatsapp_connect(SHOP)
    assert r == {"state": "connecting", "qrcode": QR, "pairing_code": None, "message": None}
    body = fake.called("POST /instance/create")[0][3]
    assert body["instanceName"] == "barbearia-demo" and body["qrcode"] is True
    assert body["webhook"]["enabled"] and body["webhook"]["url"].endswith("/webhook/evolution")
    # O secret vai no cabeçalho, nunca na URL (que aparece em logs)
    assert body["webhook"]["headers"] == {"x-webhook-secret": SHOP.webhook_secret}  # o secret da própria barbearia
    assert SHOP.webhook_secret not in body["webhook"]["url"]


def test_criada_sem_qr_espera_o_connect(evo):
    evo({
        "GET /instance/connectionState": [MISSING],
        "POST /instance/create": [(201, {"instance": {}, "qrcode": {"count": 0}})],
        "GET /instance/connect": [(200, {"count": 0}), qr()],
    })
    assert admin.whatsapp_connect(SHOP)["qrcode"] == QR


def test_qr_gerado_sem_prefixo_ganha_prefixo(evo):
    evo({"GET /instance/connectionState": [state("connecting")], "GET /instance/connect": [qr(base64="iVBORw0KGgo")]})
    r = admin.whatsapp_connect(SHOP)
    assert r["qrcode"] == QR and r["state"] == "connecting"


def test_ja_conectada(evo):
    fake = evo({"GET /instance/connectionState": [state("open")]})
    r = admin.whatsapp_connect(SHOP)
    assert r["state"] == "open" and r["qrcode"] is None and "conectado" in r["message"]
    assert not fake.called("GET /instance/connect")


def test_fechada_gera_qr(evo):
    evo({"GET /instance/connectionState": [state("close")], "GET /instance/connect": [(200, {"count": 0}), qr()]})
    assert admin.whatsapp_connect(SHOP)["qrcode"] == QR


def test_travada_sem_qr_faz_logout_e_pede_outro(evo):
    fake = evo({
        "GET /instance/connectionState": [state("connecting")],
        "GET /instance/connect": [(200, {}), (200, {"count": 0}), qr()],
        "DELETE /instance/logout": [(200, {"status": "SUCCESS"})],
    })
    assert admin.whatsapp_connect(SHOP)["qrcode"] == QR
    assert len(fake.called("DELETE /instance/logout")) == 1


def test_qr_vencido_no_limite_faz_logout(evo):
    fake = evo({
        "GET /instance/connectionState": [state("connecting")],
        "GET /instance/connect": [qr(count=wa.QRCODE_LIMIT), qr(count=1)],
        "DELETE /instance/logout": [(200, {"status": "SUCCESS"})],
    })
    assert admin.whatsapp_connect(SHOP)["qrcode"] == QR
    assert fake.called("DELETE /instance/logout")


def test_qr_nao_gerado_a_tempo_explica(evo):
    evo({
        "GET /instance/connectionState": [state("connecting")],
        "GET /instance/connect": [(200, {"count": 0})],
        "DELETE /instance/logout": [(200, {"status": "SUCCESS"})],
    })
    r = admin.whatsapp_connect(SHOP)
    assert r["qrcode"] is None and "não gerou" in r["message"]


def test_erro_da_evolution_vira_502(evo):
    evo({"GET /instance/connectionState": [state("close")],
         "GET /instance/connect": [(200, {"error": True, "message": "Error: Connection Failure"})]})
    with pytest.raises(HTTPException) as e:
        admin.whatsapp_connect(SHOP)
    assert e.value.status_code == 502 and "Connection Failure" in e.value.detail


def test_evolution_fora_do_ar_vira_502(evo):
    evo({"GET /instance/connectionState": [(0, httpx.ConnectError("recusada"))]})
    with pytest.raises(HTTPException) as e:
        admin.whatsapp_connect(SHOP)
    assert e.value.status_code == 502 and "Evolution API" in e.value.detail
    assert wa.connection_state(SHOP) == "erro"


def test_apikey_errada_vira_502(evo):
    evo({"GET /instance/connectionState": [(401, {"status": 401, "error": "Unauthorized",
                                                  "response": {"message": "Unauthorized"}})]})
    with pytest.raises(HTTPException) as e:
        admin.whatsapp_connect(SHOP)
    assert e.value.status_code == 502 and "Unauthorized" in e.value.detail


def test_codigo_de_pareamento(evo):
    fake = evo({
        "GET /instance/connectionState": [state("connecting")],
        "DELETE /instance/logout": [(200, {"status": "SUCCESS"})],
        "GET /instance/connect": [qr(pairing=None), qr(pairing="WZYEH1YY")],
    })
    r = admin.whatsapp_pairing_code(PairingCodeIn(number="(31) 99999-8888"), SHOP)
    assert r["pairing_code"] == "WZYEH1YY" and r["state"] == "connecting"
    assert fake.called("GET /instance/connect")[0][2] == {"number": "5531999998888"}


def test_codigo_de_pareamento_cria_instancia_com_numero(evo):
    fake = evo({
        "GET /instance/connectionState": [MISSING],
        "POST /instance/create": [(201, {"qrcode": {"pairingCode": "ABCD1234", "base64": QR, "count": 1}})],
    })
    assert admin.whatsapp_pairing_code(PairingCodeIn(number="31999998888"), SHOP)["pairing_code"] == "ABCD1234"
    assert fake.called("POST /instance/create")[0][3]["number"] == "5531999998888"


def test_codigo_de_pareamento_numero_invalido(evo):
    with pytest.raises(HTTPException) as e:
        admin.whatsapp_pairing_code(PairingCodeIn(number="1234"), SHOP)
    assert e.value.status_code == 422


def test_desconectar(evo):
    fake = evo({"GET /instance/connectionState": [state("open"), state("close")],
                "DELETE /instance/logout": [(200, {"status": "SUCCESS"})]})
    r = admin.whatsapp_disconnect(SHOP)
    assert r["state"] == "close" and fake.called("DELETE /instance/logout")


def test_desconectar_ja_fechada_nao_e_erro(evo):
    evo({"GET /instance/connectionState": [state("close")],
         "DELETE /instance/logout": [(400, {"status": 400, "error": "Bad Request",
                                            "response": {"message": ['The "barbearia-demo" instance is not connected']}})]})
    assert admin.whatsapp_disconnect(SHOP)["state"] == "close"
