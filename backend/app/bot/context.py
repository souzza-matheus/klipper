import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Conversation, Shop
from ..services.whatsapp import send_text

RESET_WORDS = {"0", "menu", "inicio", "voltar", "sair", "cancelar fluxo"}

# Estados em que a pessoa está no meio de um fluxo: avisos automáticos não mudam o estado da conversa
BUSY_STATES = {"book_service", "book_barber", "book_day", "book_time", "book_name", "book_confirm",
               "book_pay", "my_pick", "my_action", "my_cancel_confirm", "pay_pick", "survey_comment", "ai_confirm"}


def conversation_for(db: Session, shop: Shop, phone: str) -> Conversation:
    conv = db.scalar(select(Conversation).where(Conversation.shop_id == shop.id, Conversation.phone == phone))
    if conv is None:
        conv = Conversation(shop_id=shop.id, phone=phone, state="menu", data={})
        db.add(conv)
        db.flush()
    return conv


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def pick(text: str, n: int) -> int | None:
    """Converte a resposta '2' (ou '2.', '2)') em índice 0-based, se estiver entre 1 e n."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*[.)]?\s*", text)
    if not m:
        return None
    i = int(m.group(1))
    return i - 1 if 1 <= i <= n else None


@dataclass
class Ctx:
    db: Session
    shop: Shop
    conv: Conversation
    phone: str
    text: str
    push_name: str = ""
    replies: list[str] = field(default_factory=list)
    via_ai: bool = False  # a mensagem foi respondida pelo agente de IA (ele mesmo grava o histórico)

    @property
    def low(self) -> str:
        return norm(self.text)

    def say(self, *texts: str) -> None:
        self.replies.extend(t for t in texts if t)

    def go(self, state: str, **data) -> None:
        self.conv.state = state
        new = dict(self.conv.data or {})
        new.update(data)
        self.conv.data = new  # reatribui para o SQLAlchemy detectar a mudança no JSON

    def reset(self, keep: tuple[str, ...] = ("as_customer",)) -> None:
        self.conv.state = "menu"
        self.conv.data = {k: v for k, v in (self.conv.data or {}).items() if k in keep}

    def get(self, key: str, default=None):
        return (self.conv.data or {}).get(key, default)

    def flush(self) -> None:
        for r in self.replies:
            send_text(self.db, self.shop, self.phone, r)
        self.replies.clear()
