import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import access, admin, ai as ai_api, finance, webhook
from .ai.usage import startup_notice
from .jobs import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # O esquema do banco é criado/atualizado pelo Alembic: alembic upgrade head
    startup_notice()  # aviso no log quando a IA está no plano gratuito do provedor
    sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="BarberBot", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(admin.router, prefix="/api")
app.include_router(finance.router, prefix="/api")
app.include_router(access.router, prefix="/api")
app.include_router(ai_api.router, prefix="/api")
app.include_router(webhook.router)


@app.get("/health")
def health():
    return {"ok": True}
