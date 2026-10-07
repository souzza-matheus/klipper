"""Provedor falso para os testes: devolve respostas roteirizadas, sem rede.

Cada item do roteiro é usado em uma chamada ao modelo, na ordem:
- str: resposta em texto;
- ToolCall ou lista de ToolCall: pedidos de ferramenta;
- LLMError: falha (ex.: LLMError("quota") para simular o 429);
- função (system, messages, tools, model) -> qualquer um dos itens acima, para decidir com base no que chegou.
"""
from .provider import LLMError, LLMResult, Message, ToolCall, ToolSpec


class FakeProvider:
    def __init__(self, script=None, transcript: str = "quero cortar amanhã"):
        self.script = list(script or [])
        self.calls: list[dict] = []  # o que foi enviado em cada chamada (para os testes conferirem)
        self.transcript = transcript

    def generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                 timeout: float) -> LLMResult:
        self.calls.append({"system": system, "messages": list(messages), "tools": [t.name for t in tools],
                           "model": model})
        if not self.script:
            raise LLMError("invalid", "roteiro do FakeProvider acabou")
        item = self.script.pop(0)
        if callable(item) and not isinstance(item, ToolCall):
            item = item(system, messages, tools, model)
        if isinstance(item, LLMError):
            raise item
        if isinstance(item, str):
            return LLMResult(text=item, model=model, input_tokens=100, output_tokens=20)
        calls = item if isinstance(item, list) else [item]
        return LLMResult(tool_calls=calls, model=model, input_tokens=100, output_tokens=10)

    def transcribe(self, audio: bytes, mime_type: str, model: str, timeout: float) -> LLMResult:
        self.calls.append({"transcribe": len(audio), "mime": mime_type, "model": model})
        return LLMResult(text=self.transcript, model=model, input_tokens=50, output_tokens=10)


def last_tool_result(messages: list[Message], name: str) -> dict | None:
    """Resultado mais recente de uma ferramenta no histórico enviado ao modelo (ajuda nos roteiros)."""
    for m in reversed(messages):
        for call, result in reversed(m.tool_results):
            if call.name == name:
                return result
    return None
