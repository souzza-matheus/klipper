import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from .ai.usage import startup_notice
from .api import access, admin, ai as ai_api, catalog, finance, sales, team, webhook
from .api import sync as sync_api
from .config import settings
from .jobs import start_scheduler
from .security import (
    BodySizeLimitMiddleware, SecurityHeadersMiddleware, check_production, install_log_redaction, login_limiter,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O esquema do banco é criado/atualizado pelo Alembic: alembic upgrade head
    startup_notice()  # aviso no log quando a IA está no plano gratuito do provedor
    sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


def create_app(cfg=settings) -> FastAPI:
    check_production(cfg)  # DEV_MODE=false com segredos de exemplo ou CORS "*": não sobe
    install_log_redaction()
    if cfg.redis_url:
        login_limiter.use_redis(cfg.redis_url)
    docs = cfg.dev_mode  # documentação interativa só em desenvolvimento
    app = FastAPI(title="SyncServ", version="1.0.0", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)

    origins = [o.strip() for o in (cfg.cors_origins or "").split(",") if o.strip()]
    if not origins and cfg.dev_mode:
        origins = ["*"]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=cfg.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(DBAPIError)
    async def db_error(request: Request, exc: DBAPIError):
        # Valor que o banco recusou (tamanho, número fora do limite...): 422 sem detalhes do banco
        log.warning("Erro do banco em %s %s: %s", request.method, request.url.path, type(exc.orig).__name__)
        return JSONResponse({"detail": "Dados inválidos."}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("Erro inesperado em %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Erro interno. Tente de novo em instantes."}, status_code=500)

    app.include_router(admin.router, prefix="/api")
    app.include_router(finance.router, prefix="/api")
    app.include_router(access.router, prefix="/api")
    app.include_router(ai_api.router, prefix="/api")
    app.include_router(team.router, prefix="/api")
    app.include_router(catalog.router, prefix="/api")
    app.include_router(sales.router, prefix="/api")
    app.include_router(sync_api.router, prefix="/api")
    app.include_router(webhook.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
