"""Quem verifica se um Pix foi pago. Hoje só existe o ReceiptVerifier (comprovante mandado pelo cliente), que é
PRÉ-CONFERÊNCIA: não acessa o extrato, então o resultado nunca é prova (definitive=False) e quem confirma é o dono
(ou a confirmação automática opcional, só para valores baixos).

Próximos passos (só a interface, nada implementado; ver ROADMAP-CRM.md, "Confirmação real do Pix"):
- BankPixVerifier: API Pix do banco do dono (Pix com QR Code dinâmico, cobrança imediata com txid e webhook de
  pagamento recebido). Aí o resultado é definitivo e a confirmação passa a ser automática de verdade.
- Gateway (Mercado Pago, Asaas, Efí...): o mesmo papel, pela API do gateway; para cobranças avulsas ele entra também
  em app/services/billing.py (PaymentGateway).
"""
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session

from ..models import PaymentReceipt, ReceiptResult, Shop
from .receipts import Target, evaluate


@dataclass
class Verification:
    result: str                      # confere | divergente | ilegivel (ReceiptResult)
    definitive: bool                 # True só quando a fonte é o próprio banco (o dinheiro caiu)
    checks: list[dict] = field(default_factory=list)


class PaymentVerifier(Protocol):
    name: str
    definitive: bool

    def verify(self, db: Session, shop: Shop, target: Target, evidence) -> Verification:
        """Confere um pagamento pendente com a evidência da fonte (comprovante, notificação do banco...)."""


class ReceiptVerifier:
    """Comprovante lido pela IA + conferências no código (app/services/receipts.py)."""
    name = "receipt"
    definitive = False

    def verify(self, db: Session, shop: Shop, target: Target, evidence: PaymentReceipt) -> Verification:
        result = evaluate(db, shop, evidence, target)
        return Verification(result=result, definitive=False, checks=list(evidence.checks or []))


class BankPixVerifier:
    """API Pix do banco do dono (a implementar): consulta GET /pix/{e2eid} ou recebe o webhook do Pix recebido no
    txid da cobrança dinâmica. Precisa de conta PJ, credenciais (client_id/secret), certificado mTLS do banco e
    URL pública para o webhook."""
    name = "bank_pix"
    definitive = True

    def verify(self, db: Session, shop: Shop, target: Target, evidence) -> Verification:
        raise NotImplementedError("Confirmação pelo banco ainda não implementada (ver ROADMAP-CRM.md).")


VERIFIERS: dict[str, PaymentVerifier] = {"receipt": ReceiptVerifier()}

__all__ = ["BankPixVerifier", "PaymentVerifier", "ReceiptResult", "ReceiptVerifier", "VERIFIERS", "Verification"]
