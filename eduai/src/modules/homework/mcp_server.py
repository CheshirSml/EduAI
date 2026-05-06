"""
Homework Checker MCP Server.
Предоставляет ресурсы и инструменты для проверки студенческих работ через протокол MCP.
"""
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Literal, Optional
from functools import lru_cache
import json

from fastmcp import FastMCP

from src.config.settings import settings
from src.utils.logger import get_logger, setup_logging
from src.modules.homework.checker.file_parser import FileParser
from src.modules.homework.checker.validator import AssignmentValidator
from src.modules.homework.checker.assessor import AssignmentAssessor
from src.modules.homework.monitor.cache import get_cache, mark_assignment_processed

# Инициализация логгера
setup_logging(log_file=settings.LOG_FILE, log_level=settings.LOG_LEVEL)
logger = get_logger(__name__)

# Создание MCP сервера
mcp = FastMCP(
    name="homework_server",
    instructions="Сервер для проверки студенческих работ через локальную файловую систему"
)


# =============================================================================
# РЕСУРСЫ (Resources) - read-only доступ к данным
# =============================================================================

@mcp.resource("spec://{discipline}/assignment")
def get_assignment_spec(discipline: str) -> str:
    """
    Возвращает спецификацию заданий по дисциплине из локального файла.
    
    Путь: {settings.SPECS_ROOT}/{discipline}/assignment_spec.md
    
    Требования:
    - Валидация: запрет на path traversal
    - Кэширование: LRU-кэш в памяти (ttl=300 сек)
    - Ошибки: чёткие сообщения на русском
    
    Args:
        discipline: Идентификатор дисциплины (например, "psychology_stress")
    
    Returns:
        Полный текст спецификации в Markdown
    
    Raises:
        ValueError: если discipline содержит недопустимые символы
        FileNotFoundError: если файл спецификации отсутствует
    """
    # Валидация: запрет на path traversal
    if not re.match(r'^[a-zA-Z0-9_-]+$', discipline):
        raise ValueError(
            f"Недопустимый идентификатор дисциплины: {discipline}. "
            f"Разрешены только буквы, цифры, дефис и подчёркивание."
        )
    
    spec_path = settings.SPECS_ROOT / discipline / "assignment_spec.md"
    
    # Проверка на path traversal после конкатенации
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
    
    Приоритет: 
    1. {SPECS_ROOT}/{discipline}/grading_rubric.json (если существует)
    2. Парсинг критериев из assignment_spec.md (fallback)
    
    Args:
        discipline: Идентификатор дисциплины
    
    Returns:
        Dict с критериями оценки:
        {
            "criterion_name": {
                "min": int, 
                "max": int, 
                "description": str,
                "weight": float
            }
        }
    """
    # Валидация
    if not re.match(r'^[a-zA-Z0-9_-]+$', discipline):
        raise ValueError(
            f"Недопустимый идентификатор дисциплины: {discipline}"
        )
    
    rubric_path = settings.SPECS_ROOT / discipline / "grading_rubric.json"
    
    # Попытка загрузить JSON-рубрику
    if rubric_path.exists():
        try:
            with open(rubric_path, 'r', encoding='utf-8') as f:
                rubric = json.load(f)
            logger.debug("rubric_loaded_json", discipline=discipline, path=str(rubric_path))
            return rubric
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("rubric_json_parse_failed", discipline=discipline, error=str(e))
    
    # Fallback: парсинг из спецификации
    try:
        spec_text = get_assignment_spec(discipline)
        rubric = _parse_rubric_from_spec(spec_text)
        logger.debug("rubric_parsed_from_spec", discipline=discipline)
        return rubric
    except Exception as e:
        logger.error("rubric_load_failed", discipline=discipline, error=str(e))
        # Возврат рубрики по умолчанию
        return {
            "соответствие_теме": {"min": 0, "max": 3, "description": "Соответствие работы заданной теме", "weight": 1.0},
            "глубина_анализа": {"min": 0, "max": 3, "description": "Глубина анализа источников", "weight": 1.0},
            "структура": {"min": 0, "max": 2, "description": "Соблюдение структуры работы", "weight": 1.0},
            "оформление": {"min": 0, "max": 2, "description": "Качество оформления и цитирования", "weight": 1.0}
        }


def _parse_rubric_from_spec(spec_md: str) -> dict:
    """
    Парсинг рубрики из Markdown-спецификации.
    
    Ищет разделы вида:
    ## Критерии оценки
    - Соответствие теме: 3 балла
    - Глубина анализа: 3 балла
    
    Args:
        spec_md: Текст спецификации
    
    Returns:
        Dict с критериями
    """
    rubric = {}
    
    # Поиск раздела с критериями
    criteria_match = re.search(
        r'##?\s*критерии[:\s]*\n([\s\S]*?)(?=\n##|\Z)',
        spec_md,
        re.IGNORECASE
    )
    
    if not criteria_match:
        return rubric
    
    criteria_text = criteria_match.group(1)
    
    # Парсинг пунктов списка
    for line in criteria_text.strip().split('\n'):
        # Паттерн: "- Название: N баллов" или "- Название (N баллов)"
        match = re.match(r'\s*[-•*]\s*([^:]+):\s*(\d+)\s*балл', line, re.IGNORECASE)
        if not match:
            match = re.match(r'\s*[-•*]\s*([^(]+)\s*\((\d+)\s*балл', line, re.IGNORECASE)
        
        if match:
            name = match.group(1).strip().lower().replace(' ', '_')
            max_score = int(match.group(2))
            rubric[name] = {
                "min": 0,
                "max": max_score,
                "description": match.group(1).strip(),
                "weight": 1.0
            }
    
    return rubric


# =============================================================================
# ИНСТРУМЕНТЫ (Tools) - вызов с аргументами
# =============================================================================

@mcp.tool
def list_pending_assignments(
    discipline: Optional[str] = None,
    group: Optional[str] = None
) -> list:
    """
    Возвращает список необработанных работ в локальной папке.
    
    Структура папок: {ASSIGNMENTS_ROOT}/{group_number}/{student_fio}/
    
    Args:
        discipline: Фильтр по дисциплине (сопоставление через папку/мета-файл)
        group: Фильтр по номеру группы (например, "ПСи-201")
    
    Returns:
        List[dict] со списком работ:
        [
            {
                "file_id": "hash или относительный путь",
                "file_path": str,
                "student_fio": str,
                "group": str,
                "discipline": str,
                "created_at": "ISO8601",
                "file_size_bytes": int,
                "status": "pending" | "processing" | "completed" | "error"
            }
        ]
    """
    cache = get_cache()
    pending = []
    
    if not settings.ASSIGNMENTS_ROOT.exists():
        logger.warning("assignments_root_not_found", path=str(settings.ASSIGNMENTS_ROOT))
        return []
    
    # Сканирование директорий (рекурсивно, но не глубже 3 уровней)
    for group_dir in settings.ASSIGNMENTS_ROOT.iterdir():
        if not group_dir.is_dir():
            continue
        
        group_name = group_dir.name
        
        # Фильтр по группе
        if group and group_name != group:
            continue
        
        for student_dir in group_dir.iterdir():
            if not student_dir.is_dir():
                continue
            
            student_fio = student_dir.name
            
            # Поиск файлов в папке студента (не глубже 2 уровней)
            for file_path in student_dir.rglob('*'):
                if not file_path.is_file():
                    continue
                
                # Пропуск скрытых файлов
                if file_path.name.startswith('.'):
                    continue
                
                # Поддерживаемые расширения
                if file_path.suffix.lower() not in ['.txt', '.docx', '.pdf']:
                    continue
                
                # Относительный путь
                rel_path = str(file_path.relative_to(settings.ASSIGNMENTS_ROOT))
                
                # Проверка кэша
                if cache.is_processed(rel_path):
                    status = cache.get_status(rel_path) or "completed"
                else:
                    status = "pending"
                
                # Пропуск обработанных (опционально можно вернуть все)
                # if status in ('completed', 'error'):
                #     continue
                
                # Метаданные файла
                try:
                    stat = file_path.stat()
                    created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
                    file_size = stat.st_size
                except OSError:
                    created_at = datetime.now().isoformat()
                    file_size = 0
                
                # Определение дисциплины (по мета-файлу или названию папки)
                file_discipline = discipline or _detect_discipline(student_dir)
                
                pending.append({
                    "file_id": hashlib.sha256(rel_path.encode()).hexdigest()[:16],
                    "file_path": rel_path,
                    "student_fio": student_fio,
                    "group": group_name,
                    "discipline": file_discipline,
                    "created_at": created_at,
                    "file_size_bytes": file_size,
                    "status": status
                })
    
    # Сортировка по дате создания (новые первые)
    pending.sort(key=lambda x: x['created_at'], reverse=True)
    
    logger.info("pending_listed", count=len(pending), discipline=discipline, group=group)
    return pending


def _detect_discipline(student_dir: Path) -> str:
    """
    Попытка определить дисциплину по содержимому папки.
    
    Ищет файл discipline.txt или meta.json.
    """
    # Проверка discipline.txt
    disc_file = student_dir / "discipline.txt"
    if disc_file.exists():
        try:
            with open(disc_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except IOError:
            pass
    
    # Проверка meta.json
    meta_file = student_dir / "meta.json"
    if meta_file.exists():
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)
                return meta.get('discipline', 'unknown')
        except (json.JSONDecodeError, IOError):
            pass
    
    return 'unknown'


@mcp.tool
def validate_assignment_format(
    file_relative_path: str,
    discipline: str
) -> dict:
    """
    Быстрая пред-проверка локального файла: объём, структура, оформление.
    
    Args:
        file_relative_path: Путь относительно ASSIGNMENTS_ROOT
        discipline: Идентификатор дисциплины для загрузки спецификации
    
    Returns:
        Dict с результатами валидации:
        {
            "word_count": int,
            "issues": List[str],
            "is_valid": bool,
            "checked_at": "ISO8601",
            "file_hash": str
        }
    """
    # Валидация пути
    _validate_file_path(file_relative_path)
    
    validator = AssignmentValidator()
    result = validator.validate(file_relative_path, discipline)
    
    logger.info(
        "assignment_validated",
        file_path=file_relative_path,
        discipline=discipline,
        is_valid=result['is_valid'],
        word_count=result['word_count']
    )
    
    return result


@mcp.tool
def assess_assignment_content(
    file_relative_path: str,
    discipline: str,
    inference_config: Optional[dict] = None
) -> dict:
    """
    Полная оценка содержания работы через локальную LLM.
    
    Args:
        file_relative_path: Путь к файлу относительно ASSIGNMENTS_ROOT
        discipline: Идентификатор дисциплины
        inference_config: Опциональные параметры инференса
            {"temperature": 0.3, "max_tokens": 1024, "gpu_layers": 35, "seed": 42}
    
    Returns:
        Dict с результатами оценки:
        {
            "score": float,
            "criteria_scores": {...},
            "strengths": List[str],
            "weaknesses": List[str],
            "recommendations": List[str],
            "comment_for_student": str,
            "metadata": {...}
        }
    """
    # Валидация пути
    _validate_file_path(file_relative_path)
    
    # Загрузка спецификации и рубрики
    try:
        spec_text = get_assignment_spec(discipline)
    except Exception as e:
        logger.warning("spec_load_failed", discipline=discipline, error=str(e))
        spec_text = ""
    
    try:
        rubric = get_grading_rubric(discipline)
    except Exception as e:
        logger.warning("rubric_load_failed", discipline=discipline, error=str(e))
        rubric = {}
    
    # Оценка
    assessor = AssignmentAssessor(use_mock=False)
    result = assessor.assess(
        file_relative_path=file_relative_path,
        discipline=discipline,
        spec_text=spec_text,
        rubric=rubric,
        inference_config=inference_config
    )
    
    # Если есть ошибка — логируем и возвращаем
    if 'error' in result:
        logger.error("assessment_error", **result)
        return result
    
    logger.info(
        "assignment_assessed",
        file_path=file_relative_path,
        discipline=discipline,
        score=result.get('score'),
        model=result.get('metadata', {}).get('model_used', 'unknown')
    )
    
    return result


@mcp.tool
def mark_assignment_processed(
    file_relative_path: str,
    status: Literal["completed", "error"],
    error_message: Optional[str] = None
) -> bool:
    """
    Обновляет кэш обработанных файлов.
    
    Используется для идемпотентности: чтобы не проверять один файл дважды.
    
    Args:
        file_relative_path: Путь относительно ASSIGNMENTS_ROOT
        status: Статус обработки ("completed" или "error")
        error_message: Сообщение об ошибке (если status="error")
    
    Returns:
        True если запись успешно добавлена/обновлена
    """
    # Валидация пути
    _validate_file_path(file_relative_path)
    
    result = mark_assignment_processed(
        file_relative_path=file_relative_path,
        status=status,
        error_message=error_message
    )
    
    logger.info(
        "assignment_marked_processed",
        file_path=file_relative_path,
        status=status
    )
    
    return result


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def _validate_file_path(file_relative_path: str) -> None:
    """
    Валидация относительного пути файла.
    
    Запрещает:
    - Абсолютные пути
    - Path traversal (..)
    - Специальные символы
    
    Args:
        file_relative_path: Путь для валидации
    
    Raises:
        ValueError: если путь недопустим
    """
    if not file_relative_path:
        raise ValueError("Путь к файлу не может быть пустым")
    
    # Запрет абсолютных путей
    if Path(file_relative_path).is_absolute():
        raise ValueError("Абсолютные пути не разрешены")
    
    # Запрет path traversal
    if '..' in file_relative_path:
        raise ValueError("Path traversal (..) не разрешён")
    
    # Запрет специальных символов
    forbidden_chars = set('\\/:*?"<>|')
    if any(c in file_relative_path for c in forbidden_chars):
        raise ValueError(f"Путь содержит недопустимые символы: {forbidden_chars & set(file_relative_path)}")
    
    # Проверка существования файла
    full_path = settings.ASSIGNMENTS_ROOT / file_relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"Файл не найден: {full_path}")
    
    # Проверка что путь внутри ASSIGNMENTS_ROOT
    try:
        full_path.resolve().relative_to(settings.ASSIGNMENTS_ROOT.resolve())
    except ValueError:
        raise ValueError("Путь выходит за пределы ASSIGNMENTS_ROOT")


# =============================================================================
# ЗАПУСК СЕРВЕРА
# =============================================================================

if __name__ == "__main__":
    # Запуск в stdio-режиме для интеграции с MCP-клиентами
    mcp.run()
