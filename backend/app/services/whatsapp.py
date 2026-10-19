"""Cliente da Evolution API (v2). Toda troca de provedor (ex.: API oficial da Meta) fica isolada aqui."""
import base64
import binascii
import logging
import re
import time

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


def mask_phone(phone: str) -> str:
    """Telefone para log: só os 4 últimos dígitos (dado pessoal não vai inteiro para o log)."""
    digits = re.sub(r"\D", "", str(phone or ""))
    return f"...{digits[-4:]}" if digits else "?"


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
    queue = db.info.get(QUEUE_KEY)
    if queue is not None:  # sync/push: só envia depois que a operação foi gravada (send_queued)
        queue.append((msg, shop, phone, text))
        return True
    return _deliver(msg, shop, phone, text)


QUEUE_KEY = "whatsapp_queue"


def start_queue(db: Session) -> None:
    db.info[QUEUE_KEY] = []


def queue_mark(db: Session) -> int:
    return len(db.info.get(QUEUE_KEY) or [])


def queue_drop_from(db: Session, mark: int) -> None:
    """Operação desfeita: as mensagens que ela geraria não saem."""
    del db.info[QUEUE_KEY][mark:]


def send_queued(db: Session) -> int:
    """Depois do commit: envia o que ficou na fila e registra falhas no histórico."""
    queue = db.info.pop(QUEUE_KEY, None) or []
    failed = 0
    for msg, shop, phone, text in queue:
        if not _deliver(msg, shop, phone, text):
            failed += 1
    if failed:
        db.commit()
    return len(queue)


def _deliver(msg: OutboxMessage, shop: Shop, phone: str, text: str) -> bool:
    if not settings.evolution_url:
        log.info("[SIMULAÇÃO] para %s:\n%s", mask_phone(phone), text)
        return True
    try:
        r = httpx.post(
            f"{settings.evolution_url}/message/sendText/{shop.evolution_instance}",
            json={"number": phone, "text": text}, headers=_headers(), timeout=15,
        )
        r.raise_for_status()
        return True
    except Exception as exc:  # não derruba o fluxo do bot por falha de envio
        log.exception("Falha ao enviar mensagem para %s", mask_phone(phone))
        msg.ok = False
        msg.error = str(exc)[:500]
        return False


class EvolutionError(Exception):
    """Falha ao falar com a Evolution API. A mensagem é para o usuário (português); o detalhe técnico vai para o log."""


# A Evolution 2.3 descarta a instância depois de QRCODE_LIMIT QR Codes sem leitura (padrão 30). Às vezes o
# descarte falha e a instância fica "connecting" para sempre, devolvendo o último QR Code (já vencido).
QRCODE_LIMIT = 30
_POLL_TRIES = 6
_POLL_INTERVAL = 1.5


def _sleep(seconds: float) -> None:  # separado para os testes não esperarem
    time.sleep(seconds)


def _call(method: str, path: str, timeout: float = 30, **kw) -> httpx.Response:
    try:
        return httpx.request(method, f"{settings.evolution_url}{path}", headers=_headers(), timeout=timeout, **kw)
    except httpx.HTTPError as exc:
        log.error("Evolution API inacessível (%s %s): %r", method, path, exc)
        raise EvolutionError("Não foi possível falar com a Evolution API. Confira se ela está rodando.") from exc


def _json(r: httpx.Response) -> dict:
    try:
        data = r.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error_text(r: httpx.Response) -> str:
    """Texto do erro no formato da Evolution: {"status":404,"response":{"message":["..."]}} ou {"error":true,"message":"..."}."""
    data = _json(r)
    msg = (data.get("response") or {}).get("message") if isinstance(data.get("response"), dict) else None
    msg = msg or data.get("message") or r.text
    return "; ".join(map(str, msg)) if isinstance(msg, list) else str(msg)


def _missing(r: httpx.Response) -> bool:
    return r.status_code == 404 or "does not exist" in r.text


def _fail(r: httpx.Response, action: str) -> EvolutionError:
    log.error("Evolution API: falha ao %s (HTTP %s): %s", action, r.status_code, r.text[:500])
    return EvolutionError(f"A Evolution API recusou o pedido ao {action}: {_error_text(r)[:200]}")


def _qr_image(raw: str | None) -> str | None:
    """Imagem do QR Code sempre com o prefixo data:image/png;base64, (a v2 já manda com ele; versões antigas não)."""
    if not raw:
        return None
    return raw if raw.startswith("data:") else f"data:image/png;base64,{raw}"


def _qr_of(data: dict) -> dict:
    """Extrai o QR Code das respostas de /instance/create ({"qrcode": {...}}) e /instance/connect ({"base64": ...})."""
    qr = data.get("qrcode") if isinstance(data.get("qrcode"), dict) else data
    return {"qrcode": _qr_image(qr.get("base64")), "pairing_code": qr.get("pairingCode") or None,
            "count": qr.get("count") or 0}


def _instance_state(shop: Shop) -> str | None:
    """Estado da instância na Evolution (open, connecting, close) ou None se ela não existe."""
    r = _call("GET", f"/instance/connectionState/{shop.evolution_instance}", timeout=15)
    if _missing(r):
        return None
    if r.status_code >= 400:
        raise _fail(r, "consultar o status")
    return (_json(r).get("instance") or {}).get("state") or "close"


def create_instance(shop: Shop, number: str | None = None) -> dict:
    """Cria a instância na Evolution API com o webhook já apontando para o backend. Devolve o QR Code da criação."""
    body = {
        "instanceName": shop.evolution_instance,
        "integration": "WHATSAPP-BAILEYS",
        "qrcode": True,
        "webhook": {
            "enabled": True,
            # Secret no cabeçalho, não na URL: a URL aparece em logs (da Evolution, de proxies)
            "url": f"{settings.public_url}/webhook/evolution",
            "headers": {"x-webhook-secret": shop.webhook_secret or settings.webhook_secret},
            "byEvents": False,
            "base64": False,
            "events": ["MESSAGES_UPSERT"],
        },
    }
    if number:
        body["number"] = number
    r = _call("POST", "/instance/create", json=body, timeout=40)
    if r.status_code >= 400 and "already in use" not in r.text:
        raise _fail(r, "criar a instância")
    data = _json(r)
    if data.get("error"):
        raise _fail(r, "criar a instância")
    return _qr_of(data)


def _connect_once(shop: Shop, number: str | None = None) -> dict:
    r = _call("GET", f"/instance/connect/{shop.evolution_instance}", params={"number": number} if number else None)
    data = _json(r)
    # Em erros internos a Evolution responde 200 com {"error": true, "message": "..."}
    if r.status_code >= 400 or data.get("error"):
        raise _fail(r, "gerar o QR Code")
    return _qr_of(data)


def _logout(shop: Shop) -> None:
    """Derruba a sessão. Se a instância já estava fechada a Evolution responde erro, o que não é problema aqui."""
    r = _call("DELETE", f"/instance/logout/{shop.evolution_instance}")
    if r.status_code >= 400 and not _missing(r) and "not connected" not in r.text:
        raise _fail(r, "desconectar")


def _wait_for(shop: Shop, field: str, number: str | None = None) -> dict:
    """Pede /connect algumas vezes: logo depois de abrir a sessão o QR Code (ou o código) ainda não foi gerado."""
    qr = {"qrcode": None, "pairing_code": None, "count": 0}
    for i in range(_POLL_TRIES):
        qr = _connect_once(shop, number if i == 0 else None)
        if qr[field]:
            return qr
        _sleep(_POLL_INTERVAL)
    return qr


def _result(state: str, qr: dict | None = None, message: str | None = None) -> dict:
    qr = qr or {}
    return {"state": state, "qrcode": qr.get("qrcode"), "pairing_code": qr.get("pairing_code"), "message": message}


def connect(shop: Shop) -> dict:
    """Gera o QR Code para conectar o celular da barbearia. Sempre devolve state, qrcode, pairing_code e message."""
    if not settings.evolution_url:
        return _result("simulacao", message="O servidor está em modo simulação (EVOLUTION_URL não configurada): "
                                            "não há WhatsApp para conectar.")
    state = _instance_state(shop)
    if state == "open":
        return _result("open", message="O WhatsApp já está conectado.")
    if state is None:
        log.info("Criando a instância %s na Evolution API", shop.evolution_instance)
        qr = create_instance(shop)
        if not qr["qrcode"]:
            qr = _wait_for(shop, "qrcode")
    else:
        qr = _connect_once(shop) if state == "connecting" else _wait_for(shop, "qrcode")
        if not qr["qrcode"] or qr["count"] >= QRCODE_LIMIT:
            # Travada ou com QR Code vencido: derruba a sessão e pede outro
            log.warning("Instância %s sem QR Code válido (estado %s, count %s): reiniciando",
                        shop.evolution_instance, state, qr["count"])
            _logout(shop)
            qr = _wait_for(shop, "qrcode")
    if qr["qrcode"]:
        return _result("connecting", qr)
    state = _instance_state(shop) or "close"
    if state == "open":
        return _result("open", message="O WhatsApp já está conectado.")
    return _result(state, message="A Evolution API não gerou o QR Code a tempo. Tente de novo em alguns segundos.")


def pairing_code(shop: Shop, number: str) -> dict:
    """Pede o código de 8 dígitos para conectar digitando no celular (Conectar com número de telefone)."""
    if not settings.evolution_url:
        return _result("simulacao", message="O servidor está em modo simulação (EVOLUTION_URL não configurada): "
                                            "não há WhatsApp para conectar.")
    state = _instance_state(shop)
    if state == "open":
        return _result("open", message="O WhatsApp já está conectado.")
    if state is None:
        qr = create_instance(shop, number)
    else:
        # O número só é usado quando a sessão abre do zero, então derruba a que estiver aguardando o QR Code
        if state != "close":
            _logout(shop)
        qr = {"pairing_code": None}
    if not qr["pairing_code"]:
        qr = _wait_for(shop, "pairing_code", number)
    if qr["pairing_code"]:
        return _result("connecting", qr)
    return _result(_instance_state(shop) or "close",
                   message="A Evolution API não gerou o código a tempo. Tente de novo em alguns segundos.")


def disconnect(shop: Shop) -> dict:
    """Desconecta o WhatsApp da barbearia (o celular sai de Aparelhos conectados)."""
    if not settings.evolution_url:
        return _result("simulacao", message="O servidor está em modo simulação: não há WhatsApp conectado.")
    if _instance_state(shop) is None:
        return _result("nao_criada", message="O WhatsApp não estava conectado.")
    _logout(shop)
    return _result(_instance_state(shop) or "close", message="WhatsApp desconectado.")


def connection_state(shop: Shop) -> str:
    if not settings.evolution_url:
        return "simulacao"
    try:
        return _instance_state(shop) or "nao_criada"
    except EvolutionError:
        log.exception("Falha ao consultar estado da instância")
        return "erro"


def _decode_b64(raw: str) -> bytes:
    raw = raw.split(",", 1)[-1]  # aceita com ou sem o prefixo data:...;base64,
    try:
        return base64.b64decode(raw, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise EvolutionError("A Evolution API devolveu uma mídia inválida.") from exc


def media_base64(shop: Shop, media: dict) -> tuple[str, bytes]:
    """Baixa a mídia de uma mensagem recebida. Devolve (mimetype, bytes).

    - Se o webhook já trouxe o arquivo (opção "base64" do webhook, nos dois modos), usa direto, sem outra chamada.
    - Senão, POST /chat/getBase64FromMediaMessage/{instância} com a mensagem inteira (key + message + messageType):
      no modo QR Code (Baileys) a Evolution baixa e decifra a mídia do WhatsApp sem procurar no banco dela; no modo
      oficial (WHATSAPP-BUSINESS / Cloud API) ela usa messageType para achar o id da mídia e baixa da Graph API
      (GET /{versão}/{media-id} e depois a URL devolvida). O tipo vem em "mimetype".
    O tipo devolvido é só o declarado: quem usa confere pelos bytes."""
    declared = (media.get("mimetype") or "application/octet-stream").split(";")[0].strip()
    inline = (media.get("message") or {}).get("base64") or media.get("base64")
    if isinstance(inline, str) and inline:
        return declared, _decode_b64(inline)
    if not settings.evolution_url:
        raise EvolutionError("Modo simulação: não há mídia para baixar.")
    body = {"key": media.get("key") or {}, "message": media.get("message") or {}}
    if media.get("messageType"):
        body["messageType"] = media["messageType"]
    r = _call("POST", f"/chat/getBase64FromMediaMessage/{shop.evolution_instance}", timeout=60,
              json={"message": body, "convertToMp4": False})
    data = _json(r)
    if r.status_code >= 400 or not data.get("base64"):
        raise _fail(r, "baixar a mídia")
    content = _decode_b64(data["base64"])
    return (data.get("mimetype") or declared).split(";")[0].strip(), content


def _phone_jid(data: dict) -> str:
    """Escolhe o jid com o número real. Em contas com LID, o remoteJid vem como '<id>@lid' e o número
    fica em remoteJidAlt (Evolution 2.3+ já troca o remoteJid por ele quando existe) ou senderPn (versões antigas)."""
    key = data.get("key") or {}
    candidates = [key.get("remoteJid"), key.get("remoteJidAlt"), key.get("senderPn"), data.get("senderPn")]
    for jid in candidates:
        if jid and jid.endswith("@s.whatsapp.net"):
            return jid
    return ""


def _timestamp(raw) -> int:
    """messageTimestamp em segundos. Vem como número, texto ou Long do protobuf ({"low": ..., "high": ...});
    0 quando falta ou é inválido (aí a mensagem é aceita)."""
    if isinstance(raw, dict):
        raw = (raw.get("high") or 0) * 2**32 + (raw.get("low") or 0)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


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
    sent_at = _timestamp(data.get("messageTimestamp"))
    if sent_at and time.time() - sent_at > settings.webhook_max_message_age_seconds:
        # Histórico reenviado ao conectar (ou fila de quando o servidor estava fora): não responde
        log.info("Mensagem antiga ignorada (%ds atrás) de %s", time.time() - sent_at, mask_phone(jid))
        return None
    message = data.get("message") or {}
    text = (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or (message.get("buttonsResponseMessage") or {}).get("selectedDisplayText")
        or (message.get("listResponseMessage") or {}).get("title")
        or ""
    )
    media_msg = message.get("imageMessage") or message.get("documentMessage") or (
        (message.get("documentWithCaptionMessage") or {}).get("message") or {}).get("documentMessage")
    if not text and media_msg:
        text = media_msg.get("caption") or "[anexo]"
    audio_msg = message.get("audioMessage")
    if not text and audio_msg:
        text = "[áudio]"
    if not text:
        return None
    phone_jid = _phone_jid(data)
    if not phone_jid:
        # Só veio o LID: ele não é um telefone, então não dá para identificar o cliente
        log.warning("Mensagem ignorada: contato sem número real (jid %s)", mask_phone(jid))
        return None
    out = {
        "instance": payload.get("instance", ""),
        "phone": normalize_phone(phone_jid),
        "text": text.strip(),
        "name": data.get("pushName", ""),
    }
    if media_msg:  # imagem ou documento: pode ser o comprovante do Pix (no modo oficial o tipo vem em mime_type)
        out["media"] = {"key": key, "message": message, "messageType": data.get("messageType", ""),
                        "mimetype": media_msg.get("mimetype") or media_msg.get("mime_type") or ""}
    if audio_msg and text == "[áudio]":  # transcrito pela IA, se estiver ligada (app.api.webhook)
        out["audio"] = {"key": key, "message": message, "mimetype": audio_msg.get("mimetype", "audio/ogg"),
                        "seconds": int(audio_msg.get("seconds") or 0)}
    return out
