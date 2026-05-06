"""
Основной агент (оркестратор) для локальной архитектуры EduAI.
Принимает запрос от OpenWebUI, использует Router и MCP-клиенты,
возвращает структурированный ответ. Без телеметрии в облако, без внешних вызовов.
"""
import time
from typing import Dict, Any, Optional
import structlog

from core.router import LocalRouter

logger = structlog.get_logger(__name__)


class LocalOrchestrator:
    """Оркестратор для локальной архитектуры EduAI."""
    
    def __init__(self, router: LocalRouter):
        """
        Args:
            router: Экземпляр LocalRouter для маршрутизации запросов
        """
        self.router = router
        self.session_context: Dict[str, Any] = {}  # Простой контекст сессии
        
        logger.info("orchestrator_initialized")
    
    async def handle_homework_check_request(
        self,
        file_path: str,
        discipline: str,
        student_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Обработка запроса на проверку ДЗ от OpenWebUI.
        
        Поток:
        1. Валидация входных данных
        2. Вызов validate_assignment_format (быстрая проверка)
        3. Если валидно → вызов assess_assignment_content (LLM-оценка)
        4. Форматирование ответа для фронтенда
        5. Логирование результата
        
        Args:
            file_path: Относительный путь к файлу работы
            discipline: Идентификатор дисциплины
            student_meta: Метаданные студента (опционально)
        
        Returns:
            Dict, пригодный для отображения в OpenWebUI:
            {
                "status": "success" | "error",
                "data": { ... оценка ... } | {"error": "..."},
                "meta": {"processing_time_ms": ..., "model": ...}
            }
        """
        start_time = time.time()
        
        logger.info(
            "homework_check_started",
            file_path=file_path,
            discipline=discipline,
            student_meta=student_meta
        )
        
        # Шаг 1: Валидация входных данных
        if not file_path or not isinstance(file_path, str):
            return self._error_response(
                "Некорректный путь к файлу",
                "file_path_invalid",
                start_time
            )
        
        if not discipline or not isinstance(discipline, str):
            return self._error_response(
                "Некорректный идентификатор дисциплины",
                "discipline_invalid",
                start_time
            )
        
        # Шаг 2: Быстрая валидация формата
        try:
            validation_result = await self.router.route(
                "homework.validate",
                file_relative_path=file_path,
                discipline=discipline
            )
        except Exception as e:
            logger.error("validation_failed", error=str(e))
            return self._error_response(
                f"Ошибка валидации: {str(e)}",
                "validation_error",
                start_time
            )
        
        # Проверка результатов валидации
        if not validation_result.get('is_valid', False):
            issues = validation_result.get('issues', [])
            logger.warning("validation_issues", issues=issues)
            
            # Возвращаем предупреждения но не блокируем проверку
            # Преподаватель может решить проверить работу несмотря на проблемы
            
        # Шаг 3: LLM-оценка содержания
        try:
            assessment_result = await self.router.route(
                "homework.check",
                file_relative_path=file_path,
                discipline=discipline
            )
        except Exception as e:
            logger.error("assessment_failed", error=str(e))
            return self._error_response(
                f"Ошибка оценки: {str(e)}",
                "assessment_error",
                start_time
            )
        
        # Проверка на ошибку в результате оценки
        if 'error' in assessment_result:
            logger.error("assessment_returned_error", **assessment_result)
            return self._error_response(
                assessment_result.get('message', 'Неизвестная ошибка оценки'),
                assessment_result.get('error', 'unknown_error'),
                start_time,
                data=assessment_result
            )
        
        # Шаг 4: Форматирование ответа
        processing_time_ms = (time.time() - start_time) * 1000
        
        response = {
            "status": "success",
            "data": {
                "validation": validation_result,
                "assessment": assessment_result,
                "student_meta": student_meta
            },
            "meta": {
                "processing_time_ms": round(processing_time_ms, 2),
                "model": assessment_result.get('metadata', {}).get('model_used', 'unknown'),
                "file_hash": assessment_result.get('metadata', {}).get('file_hash', ''),
                "tokens_prompt": assessment_result.get('metadata', {}).get('tokens_prompt', 0),
                "tokens_completion": assessment_result.get('metadata', {}).get('tokens_completion', 0)
            }
        }
        
        # Шаг 5: Логирование результата
        logger.info(
            "homework_check_completed",
            file_path=file_path,
            discipline=discipline,
            score=assessment_result.get('score'),
            processing_time_ms=round(processing_time_ms, 2)
        )
        
        # Шаг 6: Отметка файла как обработанного (опционально)
        try:
            await self.router.route(
                "homework.mark",
                file_relative_path=file_path,
                status="completed"
            )
        except Exception as e:
            logger.warning("mark_processed_failed", error=str(e))
            # Не блокируем ответ из-за ошибки кэширования
        
        return response
    
    async def handle_list_pending_request(
        self,
        discipline: Optional[str] = None,
        group: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Обработка запроса на список необработанных работ.
        
        Args:
            discipline: Фильтр по дисциплине
            group: Фильтр по группе
        
        Returns:
            Dict со списком работ
        """
        start_time = time.time()
        
        logger.info(
            "list_pending_started",
            discipline=discipline,
            group=group
        )
        
        try:
            pending_list = await self.router.route(
                "homework.list",
                discipline=discipline,
                group=group
            )
        except Exception as e:
            logger.error("list_pending_failed", error=str(e))
            return {
                "status": "error",
                "data": {"error": str(e)},
                "meta": {"processing_time_ms": (time.time() - start_time) * 1000}
            }
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "list_pending_completed",
            count=len(pending_list),
            processing_time_ms=round(processing_time_ms, 2)
        )
        
        return {
            "status": "success",
            "data": {"pending": pending_list},
            "meta": {
                "processing_time_ms": round(processing_time_ms, 2),
                "count": len(pending_list)
            }
        }
    
    async def handle_spec_read_request(
        self,
        discipline: str,
        spec_type: str = "assignment"
    ) -> Dict[str, Any]:
        """
        Обработка запроса на чтение спецификации.
        
        Args:
            discipline: Идентификатор дисциплины
            spec_type: Тип спецификации ("assignment" или "rubric")
        
        Returns:
            Dict со спецификацией
        """
        start_time = time.time()
        
        domain = f"specs.read.{spec_type}"
        
        logger.info(
            "spec_read_started",
            discipline=discipline,
            spec_type=spec_type
        )
        
        try:
            spec_content = await self.router.route(domain, discipline=discipline)
        except Exception as e:
            logger.error("spec_read_failed", error=str(e))
            return {
                "status": "error",
                "data": {"error": str(e)},
                "meta": {"processing_time_ms": (time.time() - start_time) * 1000}
            }
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            "spec_read_completed",
            discipline=discipline,
            spec_type=spec_type,
            content_length=len(str(spec_content)) if spec_content else 0
        )
        
        return {
            "status": "success",
            "data": {"content": spec_content},
            "meta": {"processing_time_ms": round(processing_time_ms, 2)}
        }
    
    def _error_response(
        self,
        message: str,
        error_code: str,
        start_time: float,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Формирование ответа об ошибке.
        
        Args:
            message: Сообщение об ошибке
            error_code: Код ошибки
            start_time: Время начала обработки
            data: Дополнительные данные
        
        Returns:
            Dict с ошибкой
        """
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.error("error_response", error_code=error_code, message=message)
        
        return {
            "status": "error",
            "data": {
                "error": error_code,
                "message": message,
                **(data or {})
            },
            "meta": {
                "processing_time_ms": round(processing_time_ms, 2)
            }
        }
    
    def set_session_context(self, key: str, value: Any) -> None:
        """
        Установка значения в контекст сессии.
        
        Args:
            key: Ключ
            value: Значение
        """
        self.session_context[key] = value
        logger.debug("session_context_set", key=key)
    
    def get_session_context(self, key: str, default: Any = None) -> Any:
        """
        Получение значения из контекста сессии.
        
        Args:
            key: Ключ
            default: Значение по умолчанию
        
        Returns:
            Значение из контекста или default
        """
        return self.session_context.get(key, default)
    
    def clear_session_context(self) -> None:
        """Очистка контекста сессии."""
        self.session_context.clear()
        logger.debug("session_context_cleared")
