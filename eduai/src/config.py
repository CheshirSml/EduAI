import logging
import sys
from typing import Any

import structlog
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Configuration
    llm_api_key: str = ""
    llm_base_url: str = "https://llm.api.cloud.ru/v1"
    llm_model_name: str = "gigachat"
    
    # Application Settings
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    
    # OpenWebUI Compatibility
    enable_streaming: bool = True
    
    class Config:
        env_file = ".env"


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
