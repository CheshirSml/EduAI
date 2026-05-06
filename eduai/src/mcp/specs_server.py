"""
Specs MCP Server.
Предоставляет доступ к дисциплинарным спецификациям через протокол MCP.
"""
import re
from pathlib import Path
from functools import lru_cache
import json

from fastmcp import FastMCP

from src.config.settings import settings
from src.utils.logger import get_logger, setup_logging

# Инициализация логгера
setup_logging(log_file=settings.LOG_FILE, log_level=settings.LOG_LEVEL)
logger = get_logger(__name__)

# Создание MCP сервера
mcp = FastMCP(
    name="specs_server",
    instructions="Сервер для доступа к спецификациям дисциплин"
)


@mcp.resource("spec://{discipline:str}/assignment")
def get_assignment_spec(discipline: str) -> str:
    """
    Возвращает спецификацию заданий по дисциплине из локального файла.
    
    Args:
        discipline: Идентификатор дисциплины
    
    Returns:
        Текст спецификации в Markdown
    
    Raises:
        ValueError: если discipline содержит недопустимые символы
        FileNotFoundError: если файл не найден
    """
    # Валидация
    if not re.match(r'^[a-zA-Z0-9_-]+$', discipline):
        raise ValueError(
            f"Недопустимый идентификатор дисциплины: {discipline}. "
            f"Разрешены только буквы, цифры, дефис и подчёркивание."
        )
    
    spec_path = settings.SPECS_ROOT / discipline / "assignment_spec.md"
    
    # Проверка path traversal
    try:
        spec_path.resolve().relative_to(settings.SPECS_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Недопустимый путь к спецификации: {discipline}")
    
    if not spec_path.exists():
        raise FileNotFoundError(
            f"Спецификация не найдена: {spec_path}\n"
            f"Создайте файл {spec_path} с описанием задания."
        )
    
    with open(spec_path, 'r', encoding='utf-8') as f:
        spec_text = f.read()
    
    logger.debug("spec_loaded", discipline=discipline, path=str(spec_path))
    return spec_text


@mcp.resource("spec://{discipline:str}/rubric")
@lru_cache(maxsize=128)
def get_grading_rubric(discipline: str) -> dict:
    """
    Возвращает структурированную рубрику оценки.
    
    Args:
        discipline: Идентификатор дисциплины
    
    Returns:
        Dict с критериями оценки
    """
    # Валидация
    if not re.match(r'^[a-zA-Z0-9_-]+$', discipline):
        raise ValueError(f"Недопустимый идентификатор дисциплины: {discipline}")
    
    rubric_path = settings.SPECS_ROOT / discipline / "grading_rubric.json"
    
    # Попытка загрузить JSON-рубрику
    if rubric_path.exists():
        try:
            with open(rubric_path, 'r', encoding='utf-8') as f:
                rubric = json.load(f)
            logger.debug("rubric_loaded_json", discipline=discipline)
            return rubric
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("rubric_json_parse_failed", discipline=discipline, error=str(e))
    
    # Fallback: рубрика по умолчанию
    logger.info("rubric_default", discipline=discipline)
    return {
        "соответствие_теме": {"min": 0, "max": 3, "description": "Соответствие работы заданной теме", "weight": 1.0},
        "глубина_анализа": {"min": 0, "max": 3, "description": "Глубина анализа источников", "weight": 1.0},
        "структура": {"min": 0, "max": 2, "description": "Соблюдение структуры работы", "weight": 1.0},
        "оформление": {"min": 0, "max": 2, "description": "Качество оформления и цитирования", "weight": 1.0}
    }


if __name__ == "__main__":
    mcp.run()
