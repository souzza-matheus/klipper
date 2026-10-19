from app.services.whatsapp import parse_webhook


def _upsert(key: dict, message: dict | None = None, **data) -> dict:
    """Payload de messages.upsert no formato da Evolution API 2.3."""
    return {
        "event": "messages.upsert",
        "instance": "barbearia-demo",
        "data": {
            "key": {"id": "3EB0ABC", "fromMe": False, **key},
            "pushName": "Carlos",
            "message": message if message is not None else {"conversation": " oi "},
            "messageType": "conversation",
            **data,
        },
    }


def test_texto_simples():
    msg = parse_webhook(_upsert({"remoteJid": "5531977776666@s.whatsapp.net"}))
    assert msg == {"instance": "barbearia-demo", "phone": "5531977776666", "text": "oi", "name": "Carlos"}


def test_texto_estendido_e_evento_em_maiusculas():
    payload = _upsert({"remoteJid": "5531977776666@s.whatsapp.net"}, {"extendedTextMessage": {"text": "1"}})
    payload["event"] = "MESSAGES_UPSERT"
    assert parse_webhook(payload)["text"] == "1"


def test_lid_com_numero_em_remote_jid_alt():
    # Evolution 2.3.7 já troca o remoteJid pelo remoteJidAlt, mas versões anteriores mandam só o alt
    msg = parse_webhook(_upsert({"remoteJid": "123456789012345@lid", "remoteJidAlt": "5531977776666@s.whatsapp.net",
                                 "addressingMode": "lid"}))
    assert msg["phone"] == "5531977776666"


def test_lid_ja_trocado_pela_evolution():
    msg = parse_webhook(_upsert({"remoteJid": "5531977776666@s.whatsapp.net", "remoteJidAlt": "5531977776666@s.whatsapp.net",
                                 "addressingMode": "lid"}))
    assert msg["phone"] == "5531977776666"


def test_lid_com_sender_pn():
    msg = parse_webhook(_upsert({"remoteJid": "123456789012345@lid", "senderPn": "5531977776666@s.whatsapp.net"}))
    assert msg["phone"] == "5531977776666"


def test_lid_sem_numero_e_ignorado():
    assert parse_webhook(_upsert({"remoteJid": "123456789012345@lid"})) is None


def test_ignora_grupo_proprias_status_e_outros_eventos():
    assert parse_webhook(_upsert({"remoteJid": "120363000000000000@g.us"})) is None
    assert parse_webhook(_upsert({"remoteJid": "5531977776666@s.whatsapp.net", "fromMe": True})) is None
    assert parse_webhook(_upsert({"remoteJid": "status@broadcast"})) is None
    other = _upsert({"remoteJid": "5531977776666@s.whatsapp.net"})
    other["event"] = "messages.update"
    assert parse_webhook(other) is None


def test_anexo_sem_legenda():
    msg = parse_webhook(_upsert({"remoteJid": "5531977776666@s.whatsapp.net"}, {"imageMessage": {"mimetype": "image/jpeg"}}))
    assert msg["text"] == "[anexo]"


def test_ignora_mensagem_antiga_reenviada_ao_conectar():
    # Ao conectar, a Evolution reenvia as conversas anteriores: o bot não pode responder quem escreveu antes
    import time
    jid = {"remoteJid": "5531977776666@s.whatsapp.net"}
    assert parse_webhook(_upsert(jid, messageTimestamp=int(time.time()) - 3600)) is None
    assert parse_webhook(_upsert(jid, messageTimestamp=str(int(time.time()) - 3600))) is None
    assert parse_webhook(_upsert(jid, messageTimestamp={"low": int(time.time()) - 3600, "high": 0})) is None


def test_aceita_mensagem_recente_ou_sem_horario():
    import time
    jid = {"remoteJid": "5531977776666@s.whatsapp.net"}
    assert parse_webhook(_upsert(jid, messageTimestamp=int(time.time()) - 5))["text"] == "oi"
    assert parse_webhook(_upsert(jid, messageTimestamp="lixo"))["text"] == "oi"
    assert parse_webhook(_upsert(jid))["text"] == "oi"
