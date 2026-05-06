"""
Утилиты логирования для EduAI.
Использует structlog для структурированного логирования в файл и консоль.
"""
import structlog
from pathlib import Path
import logging
import sys
from typing import Optional


def setup_logging(
    log_file: Optional[Path] = None,
    log_level: str = "INFO"
) -> None:
    """
    Настройка структурированного логирования.
    
    Args:
        log_file: Путь к файлу для записи логов (JSONL формат)
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    """
    # Создаём директорию для логов, если не существует
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Конфигурация logging для базовых handlers
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file) if log_file else logging.NullHandler()
        ]
    )
    
    # Конфигурация structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if log_file else structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Получение логгера по имени.
    
    Args:
        name: Имя логгера (обычно __name__ модуля)
    
    Returns:
        BoundLogger для структурированного логирования
    """
    return structlog.get_logger(name)
