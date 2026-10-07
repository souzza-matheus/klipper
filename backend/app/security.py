"""Proteções transversais da API: limite de tentativas de login, validação da configuração de produção,
cabeçalhos de segurança, limite de tamanho do corpo e remoção de segredos dos logs."""
import hmac
import logging
import re
import threading
import time
from collections import deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("security")


def same_secret(given: str | None, expected: str) -> bool:
    """Compara segredos em tempo constante (não revela quantos caracteres batem)."""
    return bool(expected) and hmac.compare_digest((given or "").encode(), expected.encode())


# ---------------------------------------------------------------- força bruta no login

class LoginLimiter:
    """Bloqueio temporário depois de muitas senhas erradas, por e-mail e por IP (em memória: a API roda com um
    worker só; com vários workers, trocar por Redis). O login certo zera as falhas do e-mail."""

    def __init__(self, max_per_email: int = 5, max_per_ip: int = 20, window: int = 900, lock: int = 900):
        self.max_per_email, self.max_per_ip, self.window, self.lock = max_per_email, max_per_ip, window, lock
        self._fails: dict[str, deque] = {}
        self._locked: dict[str, float] = {}
        self._mx = threading.Lock()

    def _keys(self, email: str, ip: str) -> list[tuple[str, int]]:
        return [(f"email:{email.lower().strip()}", self.max_per_email), (f"ip:{ip}", self.max_per_ip)]

    def retry_after(self, email: str, ip: str) -> int:
        """Segundos até poder tentar de novo (0 = liberado)."""
        now = time.monotonic()
        with self._mx:
            waits = [int(self._locked[k] - now) + 1 for k, _ in self._keys(email, ip)
                     if self._locked.get(k, 0) > now]
        return max(waits, default=0)

    def failed(self, email: str, ip: str) -> None:
        now = time.monotonic()
        with self._mx:
            for key, limit in self._keys(email, ip):
                q = self._fails.setdefault(key, deque())
                q.append(now)
                while q and q[0] < now - self.window:
                    q.popleft()
                if len(q) >= limit:
                    self._locked[key] = now + self.lock
                    q.clear()
                    log.warning("Login bloqueado temporariamente para %s", key.split(":")[0])

    def succeeded(self, email: str, ip: str) -> None:
        with self._mx:
            self._fails.pop(f"email:{email.lower().strip()}", None)

    def reset(self) -> None:
        with self._mx:
            self._fails.clear()
            self._locked.clear()


login_limiter = LoginLimiter()


# ---------------------------------------------------------------- configuração de produção

DEFAULT_SECRETS = {"troque-este-segredo", "troque-este-segredo-do-webhook", "troque-este-token-de-setup", ""}


def _weak(value: str, min_len: int = 16) -> bool:
    v = (value or "").strip()
    return v in DEFAULT_SECRETS or v.lower().startswith("troque") or len(v) < min_len


def production_problems(cfg) -> list[str]:
    """Problemas que impedem subir com DEV_MODE=false."""
    problems = []
    # JWT_SECRET assina os tokens (HS256): pelo menos 32 caracteres, como recomenda a RFC 7518
    for name, min_len in (("jwt_secret", 32), ("webhook_secret", 16), ("setup_token", 16)):
        if _weak(getattr(cfg, name), min_len):
            problems.append(f"{name.upper()} está com o valor de exemplo ou tem menos de {min_len} caracteres")
    origins = [o.strip() for o in (cfg.cors_origins or "").split(",") if o.strip()]
    if "*" in origins:
        problems.append("CORS_ORIGINS não pode ter * em produção")
    return problems


def check_production(cfg) -> None:
    if cfg.dev_mode:
        return
    problems = production_problems(cfg)
    if problems:
        raise RuntimeError("Configuração insegura para produção (DEV_MODE=false):\n- " + "\n- ".join(problems))


# ---------------------------------------------------------------- middlewares

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Recusa corpos maiores que max_bytes pelo Content-Length (413), antes de ler a requisição."""

    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        size = request.headers.get("content-length")
        if size and (not size.isdigit() or int(size) > self.max_bytes):
            return JSONResponse({"detail": "Requisição grande demais."}, status_code=413)
        return await call_next(request)


# ---------------------------------------------------------------- logs

_SECRET_QS = re.compile(r"((?:secret|token|apikey|api_key|key|password)=)[^&\s\"']+", re.I)


def redact(text: str) -> str:
    return _SECRET_QS.sub(r"\1***", text)


class RedactSecretsFilter(logging.Filter):
    """Tira segredos de query string dos logs (ex.: o ?secret= do webhook no log de acesso do uvicorn)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            # Também objetos (ex.: a URL do httpx): viram texto só se tiverem algo a esconder
            record.args = tuple(a if isinstance(a, (int, float)) or a is None
                                else (redact(str(a)) if _SECRET_QS.search(str(a)) else a) for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def install_log_redaction() -> None:
    f = RedactSecretsFilter()
    for name in ("uvicorn.access", "uvicorn.error", "httpx", ""):
        logger = logging.getLogger(name)
        if not any(isinstance(x, RedactSecretsFilter) for x in logger.filters):
            logger.addFilter(f)
