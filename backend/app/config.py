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

    # Agente de IA na conversa do cliente (backend/app/ai). Sem chave, a IA fica desligada e vale só o menu.
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    ai_model: str = "gemini-3.8-flash"            # Flash estável atual
    ai_fallback_model: str = "gemini-3.5-flash-lite"  # usado quando o principal estoura a cota (429)
    # free: só barbearias com ai_allow_free_tier (no plano gratuito o Google pode usar o conteúdo);
    # paid: qualquer barbearia com ai_enabled
    ai_tier: str = "free"
    ai_timeout_seconds: int = 15
    ai_max_tool_calls: int = 6
    ai_history_messages: int = 12
    ai_hourly_limit_per_customer: int = 20
    ai_audio_max_seconds: int = 120
    # Economia de tokens e conversas fora do tema
    ai_max_output_tokens: int = 300
    # Raciocínio (thinking), cobrado como saída: nível "minimal" | "low" | "medium" | "high" (modelos 3.x; o
    # gemini-3.8-flash aceita a partir de "low") ou um número de tokens (modelos 2.5). Vazio = padrão do modelo.
    ai_thinking_budget: str = "low"
    ai_offtopic_cooldown_minutes: int = 60
    ai_max_input_chars: int = 500      # acima disso o texto é cortado antes de ir para o modelo
    ai_reject_input_chars: int = 1500  # acima disso nem chama o modelo: pede uma mensagem mais curta
    ai_flood_messages: int = 5         # mais que isso em ai_flood_seconds = flood
    ai_flood_seconds: int = 30
    ai_repeat_limit: int = 3           # a mesma mensagem 3 vezes seguidas


settings = Settings()
TZ = ZoneInfo(settings.timezone)


def now_local() -> datetime:
    """Horário local sem fuso (todas as datas do banco são guardadas no horário local da barbearia)."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)
