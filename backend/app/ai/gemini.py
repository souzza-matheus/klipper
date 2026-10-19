"""Adaptador do Google Gemini (SDK oficial google-genai, function calling manual com generate_content).
A chave vem de GEMINI_API_KEY no .env e nunca vai para o log."""
import logging

import httpx

from ..config import settings

from .provider import LLMError, LLMResult, Message, ToolCall, ToolSpec

log = logging.getLogger("ai.gemini")

TRANSCRIBE_PROMPT = ("Transcreva este áudio em português do Brasil, exatamente como foi falado, sem comentários. "
                     "Se não houver fala compreensível, responda apenas: [inaudível]")


class GeminiProvider:
    def __init__(self, api_key: str):
        from google import genai  # importado aqui para os testes não dependerem do pacote
        from google.genai import types
        self._types = types
        self._client = genai.Client(api_key=api_key)

    # ---------------------------------------------------------------- conversão

    def _contents(self, messages: list[Message]):
        t = self._types
        out = []
        for m in messages:
            if m.role == "user":
                out.append(t.Content(role="user", parts=[t.Part.from_text(text=m.text)]))
            elif m.role == "model":
                if m.raw is not None:  # conteúdo original da resposta (preserva as assinaturas de raciocínio)
                    out.append(m.raw)
                else:
                    out.append(t.Content(role="model", parts=[t.Part.from_text(text=m.text)]))
            elif m.role == "tool":
                # A API do Gemini só aceita user/model: a resposta da função vai com role "user"
                out.append(t.Content(role="user", parts=[
                    t.Part.from_function_response(name=call.name, response=result) for call, result in m.tool_results
                ]))
        return out

    def _tools(self, tools: list[ToolSpec]):
        t = self._types
        if not tools:
            return None
        return [t.Tool(function_declarations=[
            t.FunctionDeclaration(name=x.name, description=x.description, parameters_json_schema=x.parameters)
            for x in tools
        ])]

    def _call(self, model: str, contents, config) -> object:
        from google.genai import errors
        try:
            return self._client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            # 5xx: modelo sobrecarregado ou fora do ar (ex.: 503 "high demand"); o reserva costuma estar livre
            kind = "quota" if e.code == 429 else "unavailable" if (e.code or 0) >= 500 else "other"
            raise LLMError(kind, f"HTTP {e.code}: {getattr(e, 'message', '') or ''}"[:200]) from e
        except (httpx.TimeoutException, TimeoutError) as e:
            raise LLMError("timeout", str(e)[:200]) from e
        except httpx.HTTPError as e:
            raise LLMError("other", f"rede: {e!r}"[:200]) from e

    @staticmethod
    def _usage(resp) -> dict:
        """Tokens da chamada: entrada, saída visível, raciocínio (cobrado como saída) e entrada vinda do cache."""
        u = getattr(resp, "usage_metadata", None)
        if not u:
            return {}
        return {"input_tokens": u.prompt_token_count or 0, "output_tokens": u.candidates_token_count or 0,
                "thinking_tokens": getattr(u, "thoughts_token_count", 0) or 0,
                "cached_tokens": getattr(u, "cached_content_token_count", 0) or 0}

    def _thinking(self):
        """AI_THINKING_BUDGET: nível (minimal/low/medium/high, modelos 3.x) ou número de tokens (modelos 2.5)."""
        v = (settings.ai_thinking_budget or "").strip().lower()
        if not v:
            return None
        if v.lstrip("-").isdigit():
            return self._types.ThinkingConfig(thinking_budget=int(v))
        return self._types.ThinkingConfig(thinking_level=v.upper())

    # ---------------------------------------------------------------- interface

    def generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                 timeout: float, max_output_tokens: int) -> LLMResult:
        try:
            return self._generate(system, messages, tools, model, timeout, max_output_tokens)
        except LLMError as e:
            # O raciocínio conta no limite de saída: às vezes ele gasta tudo e não sobra texto. Repete uma vez com
            # folga (o tamanho da resposta visível continua contido pelo prompt)
            if e.kind != "invalid" or "MAX_TOKENS" not in str(e):
                raise
            return self._generate(system, messages, tools, model, timeout, max_output_tokens * 4)

    def _generate(self, system: str, messages: list[Message], tools: list[ToolSpec], model: str,
                  timeout: float, max_output_tokens: int) -> LLMResult:
        t = self._types
        config = t.GenerateContentConfig(
            system_instruction=system,  # fixo por negócio e no início: aproveita o cache implícito
            tools=self._tools(tools),
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
            http_options=t.HttpOptions(timeout=int(timeout * 1000)),
            max_output_tokens=max_output_tokens,
            thinking_config=self._thinking(),
            temperature=0.3,
        )
        resp = self._call(model, self._contents(messages), config)
        candidate = (resp.candidates or [None])[0]
        content = getattr(candidate, "content", None)
        calls = [ToolCall(name=fc.name, args=dict(fc.args or {}), id=fc.id or "") for fc in (resp.function_calls or [])]
        text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None) and not getattr(p, "thought", False)) \
            if content else ""
        if not calls and not text.strip():
            reason = getattr(candidate, "finish_reason", None)
            raise LLMError("invalid", f"resposta vazia (finish_reason={reason})")
        return LLMResult(text=text.strip(), tool_calls=calls, raw=content, model=model, **self._usage(resp))

    def transcribe(self, audio: bytes, mime_type: str, model: str, timeout: float) -> LLMResult:
        t = self._types
        config = t.GenerateContentConfig(http_options=t.HttpOptions(timeout=int(timeout * 1000)), temperature=0,
                                         max_output_tokens=1024, thinking_config=self._thinking())
        contents = [t.Content(role="user", parts=[t.Part.from_bytes(data=audio, mime_type=mime_type),
                                                  t.Part.from_text(text=TRANSCRIBE_PROMPT)])]
        resp = self._call(model, contents, config)
        text = (resp.text or "").strip()
        if not text:
            raise LLMError("invalid", "transcrição vazia")
        return LLMResult(text=text, model=model, **self._usage(resp))

    def read_document(self, system: str, prompt: str, data: bytes, mime_type: str, schema: dict, model: str,
                      timeout: float) -> LLMResult:
        """Imagem ou PDF inline (Part.from_bytes) com saída estruturada: response_mime_type=application/json e
        response_json_schema. Temperatura 0: é extração, não criação."""
        t = self._types
        config = t.GenerateContentConfig(
            system_instruction=system, http_options=t.HttpOptions(timeout=int(timeout * 1000)), temperature=0,
            max_output_tokens=2048, thinking_config=self._thinking(),
            response_mime_type="application/json", response_json_schema=schema,
        )
        contents = [t.Content(role="user", parts=[t.Part.from_bytes(data=data, mime_type=mime_type),
                                                  t.Part.from_text(text=prompt)])]
        resp = self._call(model, contents, config)
        text = (resp.text or "").strip()
        if not text:
            reason = getattr((resp.candidates or [None])[0], "finish_reason", None)
            raise LLMError("invalid", f"leitura vazia (finish_reason={reason})")
        return LLMResult(text=text, model=model, **self._usage(resp))
