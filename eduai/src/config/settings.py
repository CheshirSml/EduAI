"""
Конфигурация проекта EduAI (локальная версия).
Использует pydantic-settings для загрузки из .env файла.
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """Настройки проекта EduAI."""
    
    # Корневые пути
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
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
    
    class Config:
        env_file = ".env"
        extra = "ignore"


# Глобальный экземпляр настроек
settings = Settings()
