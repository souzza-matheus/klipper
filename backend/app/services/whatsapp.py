"""Cliente da Evolution API (v2). Toda troca de provedor (ex.: API oficial da Meta) fica isolada aqui."""
import logging
import re

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import OutboxMessage, Shop

log = logging.getLogger("whatsapp")


def normalize_phone(raw: str) -> str:
    """Deixa só dígitos, com DDI 55. Aceita '5531999998888@s.whatsapp.net', '(31) 99999-8888' etc."""
    digits = re.sub(r"\D", "", raw.split("@")[0])
    if digits and not digits.startswith("55") and len(digits) in (10, 11):
        digits = "55" + digits
    return digits


def phones_match(a: str, b: str) -> bool:
    """Compara números ignorando o nono dígito (o WhatsApp às vezes entrega sem ele)."""
    a, b = normalize_phone(a), normalize_phone(b)
    if not a or not b:
        return False
    if a == b:
        return True

    def strip9(n: str) -> str:
        return n[:4] + n[5:] if len(n) == 13 and n[4] == "9" else n
    return strip9(a) == strip9(b)


def _headers() -> dict:
    return {"apikey": settings.evolution_api_key, "Content-Type": "application/json"}


def send_text(db: Session, shop: Shop, phone: str, text: str) -> bool:
    phone = normalize_phone(phone)
    msg = OutboxMessage(shop_id=shop.id, phone=phone, text=text)
    db.add(msg)
    if not settings.evolution_url:
        log.info("[SIMULAÇÃO] para %s:\n%s", phone, text)
        return True
    try:
        r = httpx.post(
            f"{settings.evolution_url}/message/sendText/{shop.evolution_instance}",
            json={"number": phone, "text": text}, headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as exc:  # não derruba o fluxo do bot por falha de envio
        log.exception("Falha ao enviar mensagem para %s", phone)
        msg.ok = False
        msg.error = str(exc)[:500]
        return False


def create_instance(shop: Shop) -> dict:
    """Cria a instância na Evolution API com o webhook já apontando para o backend."""
    body = {
        "instanceName": shop.evolution_instance,
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
        "webhook": {
            "enabled": True,
            "url": f"{settings.public_url}/webhook/evolution?secret={settings.webhook_secret}",
            "byEvents": False,
            "base64": False,
            "events": ["MESSAGES_UPSERT"],
        },
    }
    r = httpx.post(f"{settings.evolution_url}/instance/create", json=body, headers=_headers(), timeout=30)
    if r.status_code >= 400 and "already" not in r.text.lower():
        r.raise_for_status()
    return r.json()


def connect_qr(shop: Shop) -> dict:
    """Retorna o QR Code (base64) para conectar o celular da barbearia."""
    url = f"{settings.evolution_url}/instance/connect/{shop.evolution_instance}"
    r = httpx.get(url, headers=_headers(), timeout=30)
    if r.status_code == 404:
        created = create_instance(shop)
        # A criação (com qrcode=True) já devolve o QR; o /connect logo em seguida pode vir sem ele
        if (created.get("qrcode") or {}).get("base64"):
            return created["qrcode"]
        r = httpx.get(url, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def connection_state(shop: Shop) -> str:
    if not settings.evolution_url:
        return "simulacao"
    try:
        r = httpx.get(f"{settings.evolution_url}/instance/connectionState/{shop.evolution_instance}",
                      headers=_headers(), timeout=15)
        if r.status_code == 404:
            return "nao_criada"
        r.raise_for_status()
        return r.json().get("instance", {}).get("state", "desconhecido")
    except Exception:
        log.exception("Falha ao consultar estado da instância")
        return "erro"


def _phone_jid(data: dict) -> str:
    """Escolhe o jid com o número real. Em contas com LID, o remoteJid vem como '<id>@lid' e o número
    fica em remoteJidAlt (Evolution 2.3+ já troca o remoteJid por ele quando existe) ou senderPn (versões antigas)."""
    key = data.get("key") or {}
    candidates = [key.get("remoteJid"), key.get("remoteJidAlt"), key.get("senderPn"), data.get("senderPn")]
    for jid in candidates:
        if jid and jid.endswith("@s.whatsapp.net"):
            return jid
    return ""


def parse_webhook(payload: dict) -> dict | None:
    """Extrai (instância, telefone, texto, nome) de um evento messages.upsert. Ignora grupos e mensagens próprias."""
    event = (payload.get("event") or "").lower().replace("_", ".")
    if event and event != "messages.upsert":
        return None
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    key = data.get("key") or {}
    jid = key.get("remoteJid", "")
    if key.get("fromMe") or jid.endswith("@g.us") or "status@broadcast" in jid:
        return None
    message = data.get("message") or {}
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or (message.get("buttonsResponseMessage") or {}).get("selectedDisplayText")
        or (message.get("listResponseMessage") or {}).get("title")
        or ""
    )
    if not text and (message.get("imageMessage") or message.get("documentMessage")):
        text = (message.get("imageMessage") or message.get("documentMessage") or {}).get("caption") or "[anexo]"
    if not text:
        return None
    phone_jid = _phone_jid(data)
    if not phone_jid:
        # Só veio o LID: ele não é um telefone, então não dá para identificar o cliente
        log.warning("Mensagem ignorada: contato sem número real (jid %s)", jid)
        return None
    return {
        "instance": payload.get("instance", ""),
        "phone": normalize_phone(phone_jid),
        "text": text.strip(),
        "name": data.get("pushName", ""),
    }
