"""
Кэш обработанных файлов для идемпотентности.
Хранит информацию о проверенных работах в JSON-файле.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import hashlib

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ProcessedCache:
    """Кэш обработанных файлов."""
    
    def __init__(self, cache_file: Optional[Path] = None):
        """
        Args:
            cache_file: Путь к файлу кэша (по умолчанию ./data/cache/processed.json)
        """
        self.cache_file = cache_file or settings.DATA_ROOT / "cache" / "processed.json"
        self._ensure_cache_dir()
        self._cache: Dict[str, Any] = self._load_cache()
    
    def _ensure_cache_dir(self) -> None:
        """Создание директории для кэша если не существует."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_cache(self) -> dict:
        """Загрузка кэша из файла."""
        if not self.cache_file.exists():
            return {}
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug("cache_loaded", file=str(self.cache_file), entries=len(data))
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("cache_load_failed", error=str(e))
            return {}
    
    def _save_cache(self) -> bool:
        """Сохранение кэша в файл."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            logger.debug("cache_saved", file=str(self.cache_file), entries=len(self._cache))
            return True
        except IOError as e:
            logger.error("cache_save_failed", error=str(e))
            return False
    
    def _compute_key(self, file_relative_path: str) -> str:
        """
        Вычисление ключа для кэша.
        
        Args:
            file_relative_path: Относительный путь файла
        
        Returns:
            Нормализованный ключ (нижний регистр, прямые слеши)
        """
        # Нормализация пути
        normalized = file_relative_path.replace('\\', '/').lower().strip()
        return normalized
    
    def is_processed(self, file_relative_path: str) -> bool:
        """
        Проверка, был ли файл уже обработан.
        
        Args:
            file_relative_path: Относительный путь файла
        
        Returns:
            True если файл есть в кэше со статусом completed/error
        """
        key = self._compute_key(file_relative_path)
        return key in self._cache
    
    def get_status(self, file_relative_path: str) -> Optional[str]:
        """
        Получение статуса обработки файла.
        
        Args:
            file_relative_path: Относительный путь файла
        
        Returns:
            Статус ("completed" | "error") или None если не найден
        """
        key = self._compute_key(file_relative_path)
        if key in self._cache:
            return self._cache[key].get('status')
        return None
    
    def mark_processed(
        self,
        file_relative_path: str,
        status: str,
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> bool:
        """
        Отметка файла как обработанного.
        
        Args:
            file_relative_path: Относительный путь файла
            status: Статус ("completed" | "error")
            error_message: Сообщение об ошибке (если status="error")
            metadata: Дополнительные метаданные
        
        Returns:
            True если успешно сохранено
        """
        if status not in ('completed', 'error'):
            logger.warning("invalid_status", status=status)
            return False
        
        key = self._compute_key(file_relative_path)
        
        self._cache[key] = {
            "status": status,
            "processed_at": datetime.now().isoformat(),
            "file_path": file_relative_path,
            "error_message": error_message,
            "metadata": metadata or {}
        }
        
        return self._save_cache()
    
    def get_all_pending(self) -> list:
        """
        Получение всех файлов, которые ещё не обработаны.
        
        NOTE: Этот метод только возвращает ключи из кэша,
        для полного списка pending файлов используйте list_pending_assignments.
        
        Returns:
            Список путей к обработанным файлам
        """
        return list(self._cache.keys())
    
    def clear(self) -> bool:
        """Очистка всего кэша."""
        self._cache = {}
        return self._save_cache()
    
    def remove(self, file_relative_path: str) -> bool:
        """
        Удаление записи из кэша.
        
        Args:
            file_relative_path: Относительный путь файла
        
        Returns:
            True если запись была удалена
        """
        key = self._compute_key(file_relative_path)
        if key in self._cache:
            del self._cache[key]
            return self._save_cache()
        return False


# Глобальный экземпляр кэша
_cache_instance: Optional[ProcessedCache] = None


def get_cache() -> ProcessedCache:
    """Получение глобального экземпляра кэша."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ProcessedCache()
    return _cache_instance


def mark_assignment_processed(
    file_relative_path: str,
    status: str,
    error_message: Optional[str] = None
) -> bool:
    """
    Утилита для отметки файла как обработанного.
    
    Args:
        file_relative_path: Относительный путь от ASSIGNMENTS_ROOT
        status: "completed" или "error"
        error_message: Сообщение об ошибке (опционально)
    
    Returns:
        True если запись успешно добавлена/обновлена
    """
    cache = get_cache()
    return cache.mark_processed(
        file_relative_path=file_relative_path,
        status=status,
        error_message=error_message
    )
