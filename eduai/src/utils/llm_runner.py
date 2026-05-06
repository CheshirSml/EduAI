"""
LLM Runner - единый интерфейс для локального инференса через llama.cpp.
Поддерживает два бэкенда:
1. subprocess к llama.cpp (предпочтительно)
2. llama-cpp-python (если установлен)
"""
import subprocess
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
import hashlib

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class LLMRunner:
    """Единый интерфейс для запуска локальной LLM."""
    
    def __init__(
        self,
        model_path: Optional[Path] = None,
        gpu_layers: Optional[int] = None,
        cpu_threads: Optional[int] = None,
        max_context: Optional[int] = None
    ):
        """
        Args:
            model_path: Путь к GGUF модели
            gpu_layers: Количество слоёв для GPU (0 = CPU only)
            cpu_threads: Количество потоков CPU
            max_context: Максимальный размер контекста
        """
        self.model_path = model_path or settings.MODELS_ROOT / settings.DEFAULT_MODEL
        self.gpu_layers = gpu_layers if gpu_layers is not None else settings.GPU_LAYERS
        self.cpu_threads = cpu_threads if cpu_threads is not None else settings.CPU_THREADS
        self.max_context = max_context if max_context is not None else settings.MAX_CONTEXT
        self.llama_cpp_path = settings.LLAMA_CPP_PATH
    
    def _compute_file_hash(self, text: str) -> str:
        """Вычисляет SHA256 хэш первых 4KB текста для идемпотентности."""
        return hashlib.sha256(text[:4096].encode('utf-8')).hexdigest()
    
    def run_inference(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        seed: Optional[int] = 42,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Запуск инференса через llama.cpp subprocess.
        
        Args:
            prompt: Текст промпта
            temperature: Температура генерации (0.0-1.0)
            max_tokens: Максимальное количество токенов ответа
            seed: Seed для воспроизводимости
            timeout: Таймаут в секундах
        
        Returns:
            Dict с результатами:
            {
                "text": str,              # Сырой ответ модели
                "tokens_prompt": int,     # Примерное количество токенов промпта
                "tokens_completion": int, # Примерное количество токенов ответа
                "inference_time_ms": float,
                "model_used": str,
                "file_hash": str          # Хэш промпта для логирования
            }
        
        Raises:
            FileNotFoundError: Если модель или llama.cpp не найдены
            subprocess.TimeoutExpired: Если превышен таймаут
            RuntimeError: Если subprocess вернул ошибку
        """
        timeout = timeout or settings.INFERENCE_TIMEOUT
        
        # Проверка наличия модели
        if not self.model_path.exists():
            logger.error("model_not_found", model_path=str(self.model_path))
            raise FileNotFoundError(f"Модель не найдена: {self.model_path}")
        
        # Проверка наличия llama.cpp
        if not self.llama_cpp_path.exists():
            logger.error("llama_cpp_not_found", path=str(self.llama_cpp_path))
            raise FileNotFoundError(
                f"llama.cpp не найден: {self.llama_cpp_path}\n"
                f"Убедитесь, что llama.cpp собран: cd llama.cpp && cmake -B build && cmake --build build --config Release"
            )
        
        # Формирование команды
        cmd = [
            str(self.llama_cpp_path),
            "-m", str(self.model_path),
            "-t", str(self.cpu_threads),
            "-c", str(self.max_context),
            "--temp", str(temperature),
            "-n", str(max_tokens),
        ]
        
        if self.gpu_layers > 0:
            cmd.extend(["-ngl", str(self.gpu_layers)])
        
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        
        # Добавляем промпт через stdin
        try:
            start_time = time.time()
            
            result = subprocess.run(
                cmd,
                input=prompt.encode('utf-8'),
                capture_output=True,
                timeout=timeout,
                check=False  # Не выбрасываем исключение при ненулевом exit code
            )
            
            inference_time_ms = (time.time() - start_time) * 1000
            
            # Обработка ошибок llama.cpp
            if result.returncode != 0:
                error_msg = result.stderr.decode('utf-8', errors='replace')
                logger.error("llama_cpp_error", returncode=result.returncode, error=error_msg)
                raise RuntimeError(f"Ошибка llama.cpp (код {result.returncode}): {error_msg}")
            
            # Парсинг вывода
            raw_output = result.stdout.decode('utf-8', errors='replace')
            
            # Оценка количества токенов (примерная, по символам)
            tokens_prompt = len(prompt) // 4  # Грубая оценка
            tokens_completion = len(raw_output) // 4
            
            response = {
                "text": raw_output,
                "tokens_prompt": tokens_prompt,
                "tokens_completion": tokens_completion,
                "inference_time_ms": inference_time_ms,
                "model_used": self.model_path.name,
                "file_hash": self._compute_file_hash(prompt)
            }
            
            logger.info(
                "inference_completed",
                model=self.model_path.name,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                inference_time_ms=round(inference_time_ms, 2)
            )
            
            return response
            
        except subprocess.TimeoutExpired:
            logger.error("inference_timeout", timeout_sec=timeout)
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        except Exception as e:
            logger.error("inference_failed", error=str(e))
            raise


class MockLLMRunner:
    """
    Мок LLM Runner для тестов.
    Возвращает предопределённый JSON-ответ без реального инференса.
    """
    
    def __init__(self, mock_response: Optional[Dict[str, Any]] = None):
        """
        Args:
            mock_response: Предопределённый ответ для возврата
        """
        self.mock_response = mock_response or {
            "score": 8.0,
            "criteria_scores": {
                "соответствие_теме": {"score": 3.0, "max": 3.0, "comment": "Работа полностью соответствует теме"},
                "глубина_анализа": {"score": 2.5, "max": 3.0, "comment": "Анализ достаточно глубокий"},
                "структура": {"score": 2.5, "max": 3.0, "comment": "Структура соблюдена"},
                "оформление": {"score": 2.0, "max": 2.0, "comment": "Оформление корректное"}
            },
            "strengths": ["Чёткая структура работы", "Глубокий анализ источников"],
            "weaknesses": ["Недостаточно примеров из практики"],
            "recommendations": ["Добавить больше практических примеров", "Расширить раздел выводов"],
            "comment_for_student": (
                "Работа выполнена на высоком уровне. Тема раскрыта полно, структура соблюдена. "
                "Рекомендуется добавить больше практических примеров для иллюстрации теоретических положений."
            ),
            "metadata": {
                "model_used": "MockLLM",
                "inference_time_ms": 100.0,
                "tokens_prompt": 500,
                "tokens_completion": 200,
                "file_hash": "mock_hash"
            }
        }
    
    def run_inference(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        seed: Optional[int] = 42,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Возвращает мок-ответ для тестов."""
        logger.debug("mock_inference_called", prompt_length=len(prompt))
        return {
            "text": json.dumps(self.mock_response, ensure_ascii=False),
            "tokens_prompt": 500,
            "tokens_completion": 200,
            "inference_time_ms": 100.0,
            "model_used": "MockLLM",
            "file_hash": hashlib.sha256(prompt[:4096].encode('utf-8')).hexdigest()
        }
