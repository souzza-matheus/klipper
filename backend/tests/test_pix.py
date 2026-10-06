from decimal import Decimal

from app.services.pix import build_brcode, crc16_ccitt, normalize_key


def test_crc_known_value():
    assert crc16_ccitt("123456789") == "29B1"


def test_brcode_structure_and_crc():
    code = build_brcode("contato@barbearia.com", "email", Decimal("65"), "Barbearia São João", "Conselheiro Lafaiete", "BB123")
    assert code.startswith("000201")
    assert "br.gov.bcb.pix" in code
    assert "540565.00" in code
    assert "5802BR" in code
    assert "BARBEARIA SAO JOAO" in code
    assert code[-8:-4] == "6304"
    assert crc16_ccitt(code[:-4]) == code[-4:]


def test_key_normalization():
    assert normalize_key("(31) 99999-8888", "phone") == "+5531999998888"
    assert normalize_key("123.456.789-09", "cpf") == "12345678909"
