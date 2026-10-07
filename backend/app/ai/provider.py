"""Interface comum dos provedores de IA. Trocar de provedor = novo adaptador + AI_PROVIDER no .env."""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    """Ferramenta que o modelo pode pedir. parameters é um JSON Schema (type=object)."""
    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    name: str
    args: dict
    id: str = ""


@dataclass
class Message:
    """Uma mensagem do histórico, independente de provedor.
    role: user | model | tool. Em "model", raw guarda o conteúdo original do provedor (ex.: assinaturas de
    raciocínio do Gemini), que precisa voltar intacto na próxima chamada da mesma rodada."""
    role: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[tuple[ToolCall, dict]] = field(default_factory=list)
    raw: Any = None


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(Exception):
    """Falha do provedor. kind: quota (429), timeout, invalid (resposta sem texto nem ferramenta), other."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}"[:300])
        self.kind = kind
        self.detail = detail


class LLMProvider(Protocol):
    def generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                 timeout: float) -> LLMResult:
        """Uma chamada ao modelo. Devolve texto e/ou pedidos de ferramenta; levanta LLMError em falha."""
        ...

    def transcribe(self, audio: bytes, mime_type: str, model: str, timeout: float) -> LLMResult:
        """Transcreve um áudio (português) e devolve o texto em LLMResult.text."""
        ...
