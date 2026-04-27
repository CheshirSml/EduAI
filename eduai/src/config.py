import logging
import sys
from typing import Any

import structlog
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Configuration (GigaChat via Sber API)
    gigachat_client_id: str = ""
    gigachat_client_secret: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_auth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_chat_url: str = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    
    # Fallback for direct API key usage (if needed in future)
    llm_api_key: str = ""
    
    # Application Settings - aliases for compatibility
    host: str = "0.0.0.0"
    port: int = 8000
    app_host: str = "0.0.0.0"  # Alias for host
    app_port: int = 8000  # Alias for port
    llm_model_name: str = "GigaChat"  # Default model name
    
    log_level: str = "INFO"
    
    # OpenWebUI Compatibility
    enable_streaming: bool = True
    
    # Homework Checking Parameters
    homework_checking_interval_minutes: int = 5
    max_homework_checks_per_day: int = 10
    
    # Database (optional for now, but good to have)
    database_url: str = "sqlite:///./test.db"
    
    # Environment
    environment: str = "development"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore extra fields in .env that are not defined here


def setup_logging(settings: Settings) -> None:
    """Configure structured logging for the application."""
    
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


settings = Settings()
setup_logging(settings)
logger = structlog.get_logger(__name__)
