"""Geração de Pix "copia e cola" (BR Code estático, padrão EMV do Banco Central) a partir da chave do estabelecimento.

O dinheiro cai direto na conta do dono. Não há confirmação automática: o dono confirma o recebimento no bot ou no app.
"""
import re
import secrets
import string
import unicodedata
from decimal import Decimal


def _field(tag: str, value: str) -> str:
    """Campo EMV: tag + tamanho em 2 dígitos + valor. O valor precisa ser ASCII e ter até 99 caracteres."""
    if len(value) > 99 or not value.isascii():
        raise ValueError(f"Campo {tag} do Pix inválido")
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _clean(text: str, max_len: int) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9 ]", "", text).strip().upper()
    return text[:max_len] or "NA"


def normalize_key(key: str, key_type: str) -> str:
    key = key.strip()
    if key_type in ("cpf", "cnpj"):
        return re.sub(r"\D", "", key)
    if key_type == "phone":
        digits = re.sub(r"\D", "", key)
        if not digits.startswith("55"):
            digits = "55" + digits
        return "+" + digits
    if key_type == "email":
        return key.lower()
    return key  # chave aleatória (EVP)


# Formatos de chave aceitos pelo DICT (Banco Central)
_KEY_RULES = {
    "cpf": re.compile(r"\d{11}"),
    "cnpj": re.compile(r"\d{14}"),
    "phone": re.compile(r"\+55\d{10,11}"),
    "email": re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,63}\.[A-Za-z]{2,24}"),
    "random": re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"),
}


def valid_pix_key(key: str, key_type: str) -> bool:
    """A chave normalizada tem o formato do tipo e cabe no BR Code (e-mail até 77 caracteres)."""
    rule = _KEY_RULES.get(key_type)
    if not rule or not key:
        return False
    k = normalize_key(key, key_type)
    return bool(rule.fullmatch(k)) and len(k) <= 77


def new_txid() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "BB" + "".join(secrets.choice(alphabet) for _ in range(18))


def build_brcode(key: str, key_type: str, amount: Decimal, receiver_name: str, city: str,
                 txid: str, description: str = "") -> str:
    account = _field("00", "br.gov.bcb.pix") + _field("01", normalize_key(key, key_type))
    if description:
        account += _field("02", _clean(description, 40))
    payload = (
        _field("00", "01")
        + _field("26", account)
        + _field("52", "0000")
        + _field("53", "986")
        + _field("54", f"{Decimal(amount):.2f}")
        + _field("58", "BR")
        + _field("59", _clean(receiver_name, 25))
        + _field("60", _clean(city, 15))
        + _field("62", _field("05", re.sub(r"[^A-Za-z0-9]", "", txid)[:25] or "***"))
        + "6304"
    )
    return payload + crc16_ccitt(payload)
