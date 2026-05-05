"""
Локальный роутер: маршрутизация запросов → локальные MCP-инструменты.
Без облачных фолбэков, без внешних зависимостей.
"""
from typing import Literal, Any, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


# Типы доменов для маршрутизации
SUPPORTED_DOMAINS = Literal[
    "homework.check",      # Проверка ДЗ
    "homework.list",       # Список необработанных работ
    "homework.validate",   # Валидация формата
    "homework.mark",       # Отметка обработанного
    "rag.query",           # Локальный RAG-поиск
    "papers.search",       # Поиск по локальной базе статей
    "specs.read.assignment",  # Чтение спецификации задания
    "specs.read.rubric"      # Чтение рубрики оценки
]


class LocalRouter:
    """Маршрутизатор запросов в локальной архитектуре."""
    
    def __init__(self, mcp_clients: Optional[Dict[str, Any]] = None):
        """
        Args:
            mcp_clients: {server_name: MCPClient} — предварительно подключённые клиенты
                         Если None, используется прямой импорт функций из модулей
        """
        self.clients = mcp_clients or {}
        
        # Маппинг доменов → серверы и инструменты
        self._routes: Dict[SUPPORTED_DOMAINS, tuple] = {
            "homework.check": ("homework_server", "assess_assignment_content"),
            "homework.list": ("homework_server", "list_pending_assignments"),
            "homework.validate": ("homework_server", "validate_assignment_format"),
            "homework.mark": ("homework_server", "mark_assignment_processed"),
            "specs.read.assignment": ("specs_server", "get_assignment_spec"),
            "specs.read.rubric": ("specs_server", "get_grading_rubric"),
            # RAG и papers будут добавлены позже
            # "rag.query": ("rag_server", "query"),
            # "papers.search": ("papers_server", "search"),
        }
        
        logger.info("router_initialized", routes_count=len(self._routes))
    
    async def route(self, domain: SUPPORTED_DOMAINS, **kwargs) -> Any:
        """
        Маршрутизация запроса к соответствующему MCP-инструменту.
        
        Args:
            domain: Домен запроса (например, "homework.check")
            **kwargs: Аргументы для инструмента
        
        Returns:
            Результат выполнения инструмента
        
        Raises:
            ValueError: если домен не поддерживается
            RuntimeError: если MCP-сервер недоступен
        """
        if domain not in self._routes:
            error_msg = f"Неподдерживаемый домен: {domain}"
            logger.error("unsupported_domain", domain=domain)
            raise ValueError(error_msg)
        
        server_name, tool_name = self._routes[domain]
        
        logger.debug(
            "routing_request",
            domain=domain,
            server=server_name,
            tool=tool_name,
            args_count=len(kwargs)
        )
        
        # Попытка вызова через MCP-клиент
        if server_name in self.clients:
            client = self.clients[server_name]
            try:
                # Вызов инструмента через MCP-клиент
                result = await client.call_tool(tool_name, **kwargs)
                logger.info(
                    "tool_called_via_mcp",
                    domain=domain,
                    server=server_name,
                    tool=tool_name
                )
                return result
            except Exception as e:
                logger.error(
                    "mcp_call_failed",
                    domain=domain,
                    server=server_name,
                    tool=tool_name,
                    error=str(e)
                )
                raise RuntimeError(f"Ошибка вызова MCP-инструмента: {e}")
        
        # Fallback: прямой импорт из модулей (для локального режима без MCP-транспорта)
        try:
            result = await self._call_local_tool(server_name, tool_name, **kwargs)
            logger.info(
                "tool_called_locally",
                domain=domain,
                server=server_name,
                tool=tool_name
            )
            return result
        except Exception as e:
            logger.error(
                "local_call_failed",
                domain=domain,
                server=server_name,
                tool=tool_name,
                error=str(e)
            )
            raise RuntimeError(f"Ошибка локального вызова инструмента: {e}")
    
    async def _call_local_tool(self, server_name: str, tool_name: str, **kwargs) -> Any:
        """
        Прямой вызов локальной функции (без MCP-транспорта).
        
        Args:
            server_name: Имя сервера (определяет модуль)
            tool_name: Имя инструмента (функции)
            **kwargs: Аргументы функции
        
        Returns:
            Результат выполнения функции
        """
        # Маппинг серверов на модули
        module_map = {
            "homework_server": "modules.homework.mcp_server",
            "specs_server": "mcp.specs_server",
            # "rag_server": "modules.rag_local.mcp_server",
            # "papers_server": "modules.papers_local.mcp_server",
        }
        
        if server_name not in module_map:
            raise RuntimeError(f"Неизвестный сервер: {server_name}")
        
        module_name = module_map[server_name]
        
        # Динамический импорт модуля
        import importlib
        module = importlib.import_module(module_name)
        
        # Получение функции
        if not hasattr(module, tool_name):
            raise RuntimeError(f"Инструмент не найден: {tool_name} в модуле {module_name}")
        
        func = getattr(module, tool_name)
        
        # Вызов функции (может быть sync или async)
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)
    
    def get_supported_domains(self) -> list:
        """Возвращает список поддерживаемых доменов."""
        return list(self._routes.keys())
    
    def get_route_info(self, domain: SUPPORTED_DOMAINS) -> Optional[dict]:
        """
        Возвращает информацию о маршруте.
        
        Args:
            domain: Домен запроса
        
        Returns:
            Dict с информацией о маршруте или None
        """
        if domain not in self._routes:
            return None
        
        server_name, tool_name = self._routes[domain]
        return {
            "domain": domain,
            "server": server_name,
            "tool": tool_name,
            "has_client": server_name in self.clients
        }
