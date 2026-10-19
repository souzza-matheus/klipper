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
    output_tokens: int = 0     # resposta visível
    thinking_tokens: int = 0   # raciocínio (cobrado como saída)
    cached_tokens: int = 0     # parte da entrada servida pelo cache implícito


class LLMError(Exception):
    """Falha do provedor. kind: quota (429), unavailable (5xx), timeout, invalid (resposta sem texto nem ferramenta), other."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}"[:300])
        self.kind = kind
        self.detail = detail


class LLMProvider(Protocol):
    def generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                 timeout: float, max_output_tokens: int) -> LLMResult:
        """Uma chamada ao modelo, com teto de tokens de saída. Devolve texto e/ou pedidos de ferramenta;
        levanta LLMError em falha. system é fixo por negócio (fica no início, para o cache implícito)."""
        ...

    def transcribe(self, audio: bytes, mime_type: str, model: str, timeout: float) -> LLMResult:
        """Transcreve um áudio (português) e devolve o texto em LLMResult.text."""
        ...

    def read_document(self, system: str, prompt: str, data: bytes, mime_type: str, schema: dict, model: str,
                      timeout: float) -> LLMResult:
        """Lê uma imagem ou PDF e devolve em LLMResult.text um JSON no formato de schema (JSON Schema)."""
        ...
