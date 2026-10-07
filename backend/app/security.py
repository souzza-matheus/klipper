"""Proteções transversais da API: limite de tentativas de login, validação da configuração de produção,
cabeçalhos de segurança, limite de tamanho do corpo e remoção de segredos dos logs."""
import hmac
import logging
import re
import threading
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("security")


def same_secret(given: str | None, expected: str) -> bool:
    """Compara segredos em tempo constante (não revela quantos caracteres batem)."""
    return bool(expected) and hmac.compare_digest((given or "").encode(), expected.encode())


# ---------------------------------------------------------------- força bruta no login

class _MemoryStore:
    """Contadores com validade, em memória (um processo)."""

    def __init__(self):
        self._data: dict[str, tuple[int, float]] = {}
        self._mx = threading.Lock()

    def _live(self, key: str):
        v = self._data.get(key)
        if v and v[1] <= time.monotonic():
            self._data.pop(key, None)
            return None
        return v

    def incr(self, key: str, ttl: int) -> int:
        with self._mx:
            v = self._live(key)
            n = (v[0] if v else 0) + 1
            self._data[key] = (n, v[1] if v else time.monotonic() + ttl)
            return n

    def set(self, key: str, ttl: int) -> None:
        with self._mx:
            self._data[key] = (1, time.monotonic() + ttl)

    def ttl(self, key: str) -> int:
        with self._mx:
            v = self._live(key)
            return int(v[1] - time.monotonic()) + 1 if v else 0

    def delete(self, *keys: str) -> None:
        with self._mx:
            for k in keys:
                self._data.pop(k, None)

    def clear(self) -> None:
        with self._mx:
            self._data.clear()


class _RedisStore:
    """Mesmos contadores no Redis: valem para todos os workers e sobrevivem a reinícios."""

    def __init__(self, client, prefix: str = "syncserv:login:"):
        self.r, self.p = client, prefix

    def incr(self, key: str, ttl: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(self.p + key)
        pipe.expire(self.p + key, ttl, nx=True)
        return int(pipe.execute()[0])

    def set(self, key: str, ttl: int) -> None:
        self.r.set(self.p + key, 1, ex=ttl)

    def ttl(self, key: str) -> int:
        return max(0, int(self.r.ttl(self.p + key)))

    def delete(self, *keys: str) -> None:
        self.r.delete(*[self.p + k for k in keys])

    def clear(self) -> None:
        for k in self.r.scan_iter(self.p + "*"):
            self.r.delete(k)


class LoginLimiter:
    """Bloqueio temporário depois de muitas senhas erradas, por e-mail e por IP. Com REDIS_URL, os contadores ficam
    no Redis (vários workers); sem ele, ou se o Redis falhar, em memória. O login certo zera as falhas do e-mail."""

    def __init__(self, max_per_email: int = 5, max_per_ip: int = 20, window: int = 900, lock: int = 900,
                 store=None):
        self.max_per_email, self.max_per_ip, self.window, self.lock = max_per_email, max_per_ip, window, lock
        self.store = store or _MemoryStore()
        self._fallback = _MemoryStore()

    def use_redis(self, url: str) -> None:
        import redis
        self.store = _RedisStore(redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2))

    def _do(self, fn, *args):
        try:
            return fn(self.store, *args)
        except Exception:  # Redis fora do ar: continua protegendo em memória
            log.warning("Limitador de login: Redis indisponível, usando memória")
            return fn(self._fallback, *args)

    def _keys(self, email: str, ip: str) -> list[tuple[str, int]]:
        return [(f"email:{email.lower().strip()}", self.max_per_email), (f"ip:{ip}", self.max_per_ip)]

    def retry_after(self, email: str, ip: str) -> int:
        """Segundos até poder tentar de novo (0 = liberado)."""
        return max((self._do(lambda st, k: st.ttl(k), f"lock:{k}") for k, _ in self._keys(email, ip)), default=0)

    def failed(self, email: str, ip: str) -> None:
        for key, limit in self._keys(email, ip):
            n = self._do(lambda st, k: st.incr(k, self.window), f"fail:{key}")
            if n >= limit:
                self._do(lambda st, k: st.set(k, self.lock), f"lock:{key}")
                self._do(lambda st, k: st.delete(k), f"fail:{key}")
                log.warning("Login bloqueado temporariamente para %s", key.split(":")[0])

    def succeeded(self, email: str, ip: str) -> None:
        self._do(lambda st, k: st.delete(k), f"fail:email:{email.lower().strip()}")

    def reset(self) -> None:
        self._do(lambda st: st.clear())
        self._fallback.clear()


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
