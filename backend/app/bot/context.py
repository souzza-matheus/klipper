import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Conversation, Shop
from ..services.whatsapp import send_text

RESET_WORDS = {"0", "menu", "inicio", "voltar", "sair", "cancelar fluxo"}


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
