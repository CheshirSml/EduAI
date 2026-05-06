import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Корневые пути
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_ROOT: Path = PROJECT_ROOT / "data"
    
    # Локальные папки
    SPECS_ROOT: Path = DATA_ROOT / "specs"              # ./data/specs/
    ASSIGNMENTS_ROOT: Path = DATA_ROOT / "assignments"  # ./data/assignments/
    MODELS_ROOT: Path = DATA_ROOT / "models"            # ./data/models/
    LOGS_ROOT: Path = DATA_ROOT / "logs"                # ./data/logs/
    VECTOR_STORE_ROOT: Path = DATA_ROOT / "vector_store"  # ./data/vector_store/
    
    # Модель и инференс
    DEFAULT_MODEL: str = "Qwen3.5-4B-Q4_K_M.gguf"
    LLAMA_CPP_PATH: Path = PROJECT_ROOT / "llama.cpp" / "build" / "bin" / "main"
    GPU_LAYERS: int = 35  # Для RTX 3050
    CPU_THREADS: int = 6
    MAX_CONTEXT: int = 4096
    
    # Поведение
    INFERENCE_TIMEOUT: int = 300  # секунд
    MAX_FILE_SIZE_MB: int = 10
    WORD_TOLERANCE_PCT: int = 10  # ±10% допуск по объёму
    
    # Логирование
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = LOGS_ROOT / "homework.jsonl"
    
    # Опционально: Comet
    COMET_API_KEY: Optional[str] = None
    COMET_PROJECT: str = "eduai-local"
    
    # Application Settings - aliases for compatibility
    host: str = "0.0.0.0"
    port: int = 8000
    app_host: str = "0.0.0.0"  # Alias for host
    app_port: int = 8000  # Alias for port
    llm_model_name: str = "Qwen3.5-4B-Q4_K_M"  # Default local model name
    
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
