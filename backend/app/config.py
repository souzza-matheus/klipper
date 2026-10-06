from zoneinfo import ZoneInfo
from datetime import datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./barberbot.db"
    jwt_secret: str = "troque-este-segredo"
    jwt_expire_hours: int = 24 * 30

    # Evolution API. Se evolution_url ficar vazio, as mensagens só são registradas no log (modo simulação).
    evolution_url: str = ""
    evolution_api_key: str = ""
    # URL pública do backend, usada para registrar o webhook na Evolution API
    public_url: str = "http://backend:8000"
    webhook_secret: str = "troque-este-segredo-do-webhook"

    # Token exigido para cadastrar uma nova barbearia pela API
    setup_token: str = "troque-este-token-de-setup"

    timezone: str = "America/Sao_Paulo"
    dev_mode: bool = True
    run_scheduler: bool = True


settings = Settings()
TZ = ZoneInfo(settings.timezone)


def now_local() -> datetime:
    """Horário local sem fuso (todas as datas do banco são guardadas no horário local da barbearia)."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)
