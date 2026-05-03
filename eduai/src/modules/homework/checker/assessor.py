"""
Оценщик заданий: LLM-оценка через локальную модель.
"""
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from config.settings import settings
from utils.logger import get_logger
from utils.llm_runner import LLMRunner, MockLLMRunner
from modules.homework.checker.file_parser import parse_assignment_file

logger = get_logger(__name__)


class AssignmentAssessor:
    """Оценщик студенческих работ через LLM."""
    
    def __init__(self, use_mock: bool = False):
        """
        Args:
            use_mock: Если True, использовать MockLLMRunner для тестов
        """
        self.use_mock = use_mock
        self.llm_runner = MockLLMRunner() if use_mock else LLMRunner()
    
    def _build_assessment_prompt(
        self,
        spec: str,
        rubric: dict,
        text: str,
        max_context: int = 4096
    ) -> str:
        """
        Конструирует финальный промпт для локальной LLM.
        
        Структура:
        1. Системный промпт (кратко)
        2. Контекст: рубрика в компактном JSON
        3. Текст работы: обрезка до (max_context - 1024) токенов
        4. Инструкция вывода: строгий JSON без markdown
        
        Args:
            spec: Текст спецификации дисциплины
            rubric: Рубрика оценки
            text: Текст студенческой работы
            max_context: Максимальный размер контекста
        
        Returns:
            Готовый промпт для llama.cpp
        """
        # Системный промпт
        system_prompt = (
            "Ты — ассистент преподавателя психологии. "
            "Твоя задача — оценить студенческую работу по заданным критериям. "
            "Будь объективен, конкретен и конструктивен. "
            "Не выдумывай факты, источники или цитаты. "
            "Если информации недостаточно — честно сообщи об этом."
        )
        
        # Компактная рубрика
        rubric_compact = json.dumps(rubric, ensure_ascii=False, indent=2)[:2000]
        
        # Обрезка текста работы
        max_text_tokens = max_context - 1024  # Оставляем место для промпта
        max_text_chars = max_text_tokens * 4  # Грубая оценка: 1 токен ≈ 4 символа
        
        truncated_warning = ""
        if len(text) > max_text_chars:
            text = text[:max_text_chars] + "\n\n[...усечено...]"
            truncated_warning = "ВНИМАНИЕ: Текст работы усечён из-за ограничений контекста.\n"
        
        # Формирование промпта
        prompt = f"""<｜begin▁of▁sentence｜>{system_prompt}

КРИТЕРИИ ОЦЕНКИ:
{rubric_compact}

{truncated_warning}ТЕКСТ РАБОТЫ:
{text}

ИНСТРУКЦИЯ:
Ответь СТРОГО в формате JSON без markdown-обёртки, без пояснений вне JSON.
Пример структуры ответа:
{{
    "score": 8.0,
    "criteria_scores": {{
        "соответствие_теме": {{"score": 3, "max": 3, "comment": "..."}},
        "глубина_анализа": {{"score": 2.5, "max": 3, "comment": "..."}}
    }},
    "strengths": ["конкретный пункт 1", "конкретный пункт 2"],
    "weaknesses": ["конкретное замечание 1"],
    "recommendations": ["конкретный совет 1"],
    "comment_for_student": "развёрнутый фидбек на ~150 слов"
}}

Требования к ответу:
- score: число от 0 до 10, округление до 0.5
- criteria_scores: объект с оценками по каждому критерию
- strengths: 2-4 конкретных сильных стороны
- weaknesses: 2-4 конструктивных замечания (может быть пустым)
- recommendations: 2-3 actionable совета
- comment_for_student: итоговый фидбек на русском, академический стиль, ~150 слов

Ответ:"""
        
        return prompt
    
    def _parse_llm_response(
        self,
        raw_output: str,
        fallback_comment: str = "Требуется ручная проверка"
    ) -> dict:
        """
        Извлекает валидный JSON из ответа модели.
        
        Стратегии (по порядку):
        1. json.loads(raw_output) — если ответ чистый
        2. Поиск первого '{' и последнего '}' через рекурсивный подсчёт скобок
        3. Попытка исправить распространённые ошибки
        4. Fallback на безопасный ответ
        
        Args:
            raw_output: Сырой вывод модели
            fallback_comment: Комментарий для fallback-ответа
        
        Returns:
            Гарантированно валидный dict
        """
        # Попытка 1: прямой парсинг
        try:
            result = json.loads(raw_output.strip())
            logger.debug("json_parsed_directly")
            return self._validate_result(result, fallback_comment)
        except json.JSONDecodeError:
            pass
        
        # Попытка 2: поиск JSON в тексте
        try:
            # Находим первую '{' и последнюю '}'
            start_idx = raw_output.find('{')
            end_idx = raw_output.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = raw_output[start_idx:end_idx]
                result = json.loads(json_str)
                logger.debug("json_extracted_from_text")
                return self._validate_result(result, fallback_comment)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Попытка 3: исправление распространённых ошибок
        try:
            fixed = raw_output.strip()
            # Замена одинарных кавычек на двойные
            fixed = fixed.replace("'", '"')
            # Удаление лишних запятых перед закрывающими скобками
            fixed = re.sub(r',\s*}', '}', fixed)
            fixed = re.sub(r',\s*]', ']', fixed)
            
            result = json.loads(fixed)
            logger.debug("json_fixed_and_parsed")
            return self._validate_result(result, fallback_comment)
        except (json.JSONDecodeError, ValueError):
            pass
        
        # Fallback: безопасный ответ
        logger.warning("json_parse_failed", raw_output_length=len(raw_output))
        return {
            "score": 5.0,
            "criteria_scores": {
                "общая_оценка": {"score": 5.0, "max": 10.0, "comment": "Не удалось автоматически распарсить ответ модели"}
            },
            "strengths": [],
            "weaknesses": [],
            "recommendations": ["Требуется ручная проверка работы"],
            "comment_for_student": fallback_comment,
            "metadata": {
                "parse_error": True,
                "raw_output_truncated": raw_output[:500]
            }
        }
    
    def _validate_result(self, result: dict, fallback_comment: str) -> dict:
        """
        Валидация и дополнение результата обязательными полями.
        
        Args:
            result: Распарсенный результат от модели
            fallback_comment: Комментарий для заполнения пропущенных полей
        
        Returns:
            Валидированный dict с гарантированными полями
        """
        # Обязательные поля с дефолтными значениями
        if "score" not in result:
            result["score"] = 5.0
            logger.warning("missing_score_field")
        
        # Нормализация score (0-10)
        try:
            score = float(result["score"])
            result["score"] = round(max(0, min(10, score)) * 2) / 2  # Округление до 0.5
        except (ValueError, TypeError):
            result["score"] = 5.0
            logger.warning("invalid_score_value")
        
        if "comment_for_student" not in result or not result["comment_for_student"]:
            result["comment_for_student"] = fallback_comment
            logger.warning("missing_comment_field")
        
        if "criteria_scores" not in result:
            result["criteria_scores"] = {}
        
        if "strengths" not in result:
            result["strengths"] = []
        
        if "weaknesses" not in result:
            result["weaknesses"] = []
        
        if "recommendations" not in result:
            result["recommendations"] = []
        
        return result
    
    def assess(
        self,
        file_relative_path: str,
        discipline: str,
        spec_text: str,
        rubric: dict,
        inference_config: Optional[dict] = None
    ) -> dict:
        """
        Полная оценка содержания работы через LLM.
        
        Args:
            file_relative_path: Путь к файлу относительно ASSIGNMENTS_ROOT
            discipline: Идентификатор дисциплины
            spec_text: Текст спецификации
            rubric: Рубрика оценки
            inference_config: Параметры инференса
        
        Returns:
            Dict с результатами оценки
        """
        inference_config = inference_config or {}
        
        # Парсинг файла
        try:
            parse_result = parse_assignment_file(file_relative_path)
        except Exception as e:
            logger.error("file_parse_failed", path=file_relative_path, error=str(e))
            return {
                "error": "file_parse_error",
                "message": str(e),
                "file_path": file_relative_path
            }
        
        text = parse_result['text']
        file_hash = parse_result['file_hash']
        
        if not text.strip():
            logger.warning("empty_file_content", path=file_relative_path)
            return {
                "score": 0.0,
                "criteria_scores": {},
                "strengths": [],
                "weaknesses": ["Работа пустая или не содержит текста"],
                "recommendations": ["Загрузите файл с содержимым работы"],
                "comment_for_student": "Работа не содержит текста. Пожалуйста, загрузите корректный файл.",
                "metadata": {
                    "model_used": "N/A",
                    "inference_time_ms": 0,
                    "tokens_prompt": 0,
                    "tokens_completion": 0,
                    "file_hash": file_hash
                }
            }
        
        # Построение промпта
        prompt = self._build_assessment_prompt(
            spec=spec_text,
            rubric=rubric,
            text=text,
            max_context=inference_config.get('max_context', settings.MAX_CONTEXT)
        )
        
        # Запуск инференса
        try:
            llm_result = self.llm_runner.run_inference(
                prompt=prompt,
                temperature=inference_config.get('temperature', 0.3),
                max_tokens=inference_config.get('max_tokens', 1024),
                seed=inference_config.get('seed', 42),
                timeout=inference_config.get('timeout', settings.INFERENCE_TIMEOUT)
            )
        except FileNotFoundError as e:
            logger.error("model_not_found", error=str(e))
            return {
                "error": "model_not_found",
                "message": str(e),
                "model": settings.DEFAULT_MODEL
            }
        except Exception as e:
            logger.error("inference_failed", error=str(e))
            return {
                "error": "inference_error",
                "message": str(e)
            }
        
        # Парсинг ответа
        assessment = self._parse_llm_response(llm_result['text'])
        
        # Добавление метаданных
        assessment['metadata'] = {
            "model_used": llm_result['model_used'],
            "inference_time_ms": round(llm_result['inference_time_ms'], 2),
            "tokens_prompt": llm_result['tokens_prompt'],
            "tokens_completion": llm_result['tokens_completion'],
            "file_hash": file_hash
        }
        
        # Логирование
        logger.info(
            "assessment_completed",
            discipline=discipline,
            file_hash=file_hash,
            score=assessment.get('score'),
            model=llm_result['model_used']
        )
        
        return assessment


def assess_assignment_content(
    file_relative_path: str,
    discipline: str,
    inference_config: Optional[dict] = None
) -> dict:
    """
    Утилита для оценки содержания задания.
    
    Args:
        file_relative_path: Относительный путь от ASSIGNMENTS_ROOT
        discipline: Идентификатор дисциплины
        inference_config: Параметры инференса
    
    Returns:
        Dict с результатами оценки
    """
    # Загрузка спецификации и рубрики
    from modules.homework.mcp_server import get_assignment_spec, get_grading_rubric
    
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
    
    assessor = AssignmentAssessor(use_mock=False)
    return assessor.assess(
        file_relative_path=file_relative_path,
        discipline=discipline,
        spec_text=spec_text,
        rubric=rubric,
        inference_config=inference_config
    )
