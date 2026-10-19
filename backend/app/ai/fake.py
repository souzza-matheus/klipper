"""Provedor falso para os testes: devolve respostas roteirizadas, sem rede.

Cada item do roteiro é usado em uma chamada ao modelo, na ordem:
- str: resposta em texto;
- ToolCall ou lista de ToolCall: pedidos de ferramenta;
- LLMError: falha (ex.: LLMError("quota") para simular o 429);
- tupla (texto, ToolCall ou lista): texto e pedidos de ferramenta na mesma resposta;
- função (system, messages, tools, model) -> qualquer um dos itens acima, para decidir com base no que chegou.
"""
from .provider import LLMError, LLMResult, Message, ToolCall, ToolSpec


class FakeProvider:
    def __init__(self, script=None, transcript: str = "quero cortar amanhã", documents=None):
        self.script = list(script or [])
        # Leituras de comprovante, na ordem: dict (vira o JSON da resposta), str (texto cru), LLMError ou
        # função (data, mime_type) -> um desses
        self.documents = list(documents or [])
        self.calls: list[dict] = []  # o que foi enviado em cada chamada (para os testes conferirem)
        self.transcript = transcript

    def generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                 timeout: float, max_output_tokens: int) -> LLMResult:
        self.calls.append({"system": system, "messages": list(messages), "tools": [t.name for t in tools],
                           "model": model, "max_output_tokens": max_output_tokens})
        if not self.script:
            raise LLMError("invalid", "roteiro do FakeProvider acabou")
        item = self.script.pop(0)
        if callable(item) and not isinstance(item, ToolCall):
            item = item(system, messages, tools, model)
        if isinstance(item, LLMError):
            raise item
        if isinstance(item, str):
            return LLMResult(text=item, model=model, input_tokens=100, output_tokens=20, thinking_tokens=5)
        if isinstance(item, tuple):
            text, calls = item
            calls = calls if isinstance(calls, list) else [calls]
            return LLMResult(text=text, tool_calls=calls, model=model, input_tokens=100, output_tokens=15)
        calls = item if isinstance(item, list) else [item]
        return LLMResult(tool_calls=calls, model=model, input_tokens=100, output_tokens=10)

    def transcribe(self, audio: bytes, mime_type: str, model: str, timeout: float) -> LLMResult:
        self.calls.append({"transcribe": len(audio), "mime": mime_type, "model": model})
        return LLMResult(text=self.transcript, model=model, input_tokens=50, output_tokens=10)


    def read_document(self, system: str, prompt: str, data: bytes, mime_type: str, schema: dict, model: str,
                      timeout: float) -> LLMResult:
        import json
        self.calls.append({"document": len(data), "mime": mime_type, "model": model, "system": system})
        if not self.documents:
            raise LLMError("invalid", "roteiro de documentos do FakeProvider acabou")
        item = self.documents.pop(0)
        if callable(item):
            item = item(data, mime_type)
        if isinstance(item, LLMError):
            raise item
        text = item if isinstance(item, str) else json.dumps(item)
        return LLMResult(text=text, model=model, input_tokens=1300, output_tokens=120, thinking_tokens=40)


def last_tool_result(messages: list[Message], name: str) -> dict | None:
    """Resultado mais recente de uma ferramenta no histórico enviado ao modelo (ajuda nos roteiros)."""
    for m in reversed(messages):
        for call, result in reversed(m.tool_results):
            if call.name == name:
                return result
    return None
