"""
Локальный LLM-клиент для работы с GGUF-моделями через llama.cpp.

Поддерживает два режима:
1. subprocess к llama.cpp main (предпочтительно)
2. llama-cpp-python (если установлен)
"""
import asyncio
import subprocess
import json
import time
import structlog
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from src.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class ChatMessage:
    """Сообщение для чата."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Ответ от LLM."""
    content: str
    model: str
    tokens_prompt: int
    tokens_completion: int
    inference_time_ms: float
    error: Optional[str] = None


class LocalLLMClient:
    """
    Клиент для локальных LLM-моделей в формате GGUF.
    
    Использует llama.cpp для инференса через subprocess.
    """
    
    def __init__(self, model_path: Optional[Path] = None):
        """
        Инициализация клиента.
        
        Args:
            model_path: Путь к GGUF-модели. Если None, используется settings.DEFAULT_MODEL
        """
        self.model_path = model_path or (settings.MODELS_ROOT / settings.DEFAULT_MODEL)
        self.llama_cpp_path = settings.LLAMA_CPP_PATH
        
        # Проверяем существование модели
        if not self.model_path.exists():
            logger.warning(
                "Модель не найдена", 
                model_path=str(self.model_path),
                expected_location=str(settings.MODELS_ROOT)
            )
        
        # Проверяем существование llama.cpp
        if not self.llama_cpp_path.exists():
            logger.warning(
                "llama.cpp не найден", 
                llama_cpp_path=str(self.llama_cpp_path),
                hint="Установите llama.cpp или используйте llama-cpp-python"
            )
    
    def _build_command(self, prompt: str, config: Dict[str, Any]) -> List[str]:
        """
        Строит команду для запуска llama.cpp.
        
        Args:
            prompt: Текст промпта
            config: Конфигурация инференса
        
        Returns:
            Список аргументов для subprocess
        """
        cmd = [
            str(self.llama_cpp_path),
            "-m", str(self.model_path),
            "-p", prompt,
            "-n", str(config.get("max_tokens", 1024)),
            "-t", str(config.get("threads", settings.CPU_THREADS)),
            "-c", str(config.get("context_size", settings.MAX_CONTEXT)),
            "--temp", str(config.get("temperature", 0.3)),
            "--seed", str(config.get("seed", 42)),
        ]
        
        # GPU слои (если > 0)
        gpu_layers = config.get("gpu_layers", settings.GPU_LAYERS)
        if gpu_layers > 0:
            cmd.extend(["-ngl", str(gpu_layers)])
        
        # Дополнительные параметры
        if config.get("stop_sequences"):
            for stop_seq in config["stop_sequences"]:
                cmd.extend(["--stop", stop_seq])
        
        return cmd
    
    async def run_inference(
        self,
        prompt: str,
        config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Запускает инференс через llama.cpp subprocess.
        
        Args:
            prompt: Текст промпта
            config: Опциональная конфигурация
                - temperature: float (по умолчанию 0.3)
                - max_tokens: int (по умолчанию 1024)
                - gpu_layers: int (по умолчанию settings.GPU_LAYERS)
                - threads: int (по умолчанию settings.CPU_THREADS)
                - context_size: int (по умолчанию settings.MAX_CONTEXT)
                - seed: int (по умолчанию 42)
                - timeout: int (по умолчанию settings.INFERENCE_TIMEOUT)
        
        Returns:
            Текст ответа от модели
        
        Raises:
            FileNotFoundError: Если модель или llama.cpp не найдены
            TimeoutError: Если превышено время ожидания
            RuntimeError: Если процесс завершился с ошибкой
        """
        config = config or {}
        timeout = config.get("timeout", settings.INFERENCE_TIMEOUT)
        
        logger.info(
            "Запуск инференса",
            model=str(self.model_path.name),
            prompt_length=len(prompt),
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 1024)
        )
        
        start_time = time.time()
        
        try:
            # Проверка существования файлов перед запуском
            if not self.model_path.exists():
                raise FileNotFoundError(f"Модель не найдена: {self.model_path}")
            
            if not self.llama_cpp_path.exists():
                raise FileNotFoundError(f"llama.cpp не найден: {self.llama_cpp_path}")
            
            # Формируем команду
            cmd = self._build_command(prompt, config)
            
            # Запускаем процесс
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # Ждём завершения с таймаутом
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise TimeoutError(f"Инференс превысил таймаут {timeout} сек")
            
            # Обработка результата
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Неизвестная ошибка"
                logger.error("Ошибка llama.cpp", returncode=process.returncode, error=error_msg[:500])
                raise RuntimeError(f"llama.cpp вернул ошибку: {error_msg[:200]}")
            
            # Парсим вывод
            output = stdout.decode('utf-8', errors='ignore')
            
            # Извлекаем только сгенерированный текст (после промпта)
            # llama.cpp обычно выводит промпт + ответ, нужно отделить ответ
            if prompt in output:
                response = output.split(prompt, 1)[-1].strip()
            else:
                response = output.strip()
            
            inference_time = (time.time() - start_time) * 1000
            
            logger.info(
                "Инференс завершён",
                model=str(self.model_path.name),
                response_length=len(response),
                inference_time_ms=round(inference_time, 2)
            )
            
            return response
            
        except FileNotFoundError:
            raise
        except TimeoutError:
            raise
        except Exception as e:
            logger.error("Ошибка инференса", error=str(e), model=str(self.model_path.name))
            raise
    
    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: float = 0.3,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None
    ) -> ChatResponse:
        """
        Отправляет сообщения в чат-формате.
        
        Args:
            messages: Список сообщений
            temperature: Температура генерации
            max_tokens: Максимум токенов
            system_prompt: Системный промпт (опционально)
        
        Returns:
            ChatResponse с ответом модели
        """
        # Формируем промпт в стиле диалога
        formatted_messages = []
        
        if system_prompt:
            formatted_messages.append(f"<|system|>\n{system_prompt}")
        
        for msg in messages:
            if msg.role == "user":
                formatted_messages.append(f"<|user|>\n{msg.content}")
            elif msg.role == "assistant":
                formatted_messages.append(f"<|assistant|>\n{msg.content}")
            elif msg.role == "system":
                formatted_messages.append(f"<|system|>\n{msg.content}")
        
        # Добавляем маркер начала ответа ассистента
        formatted_messages.append("<|assistant|>")
        
        prompt = "\n".join(formatted_messages)
        
        config = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stop_sequences": ["<|user|>", "<|system|>"],
        }
        
        start_time = time.time()
        
        try:
            response_text = await self.run_inference(prompt, config)
            inference_time = (time.time() - start_time) * 1000
            
            # Оценка количества токенов (приблизительно)
            tokens_prompt = len(prompt) // 4  # Грубая оценка
            tokens_completion = len(response_text) // 4
            
            return ChatResponse(
                content=response_text,
                model=settings.DEFAULT_MODEL,
                tokens_prompt=tokens_prompt,
                tokens_completion=tokens_completion,
                inference_time_ms=inference_time
            )
            
        except FileNotFoundError as e:
            return ChatResponse(
                content="",
                model=settings.DEFAULT_MODEL,
                tokens_prompt=0,
                tokens_completion=0,
                inference_time_ms=0,
                error=f"model_not_found: {str(e)}"
            )
        except TimeoutError as e:
            return ChatResponse(
                content="",
                model=settings.DEFAULT_MODEL,
                tokens_prompt=0,
                tokens_completion=0,
                inference_time_ms=0,
                error=f"inference_timeout: {str(e)}"
            )
        except Exception as e:
            return ChatResponse(
                content="",
                model=settings.DEFAULT_MODEL,
                tokens_prompt=0,
                tokens_completion=0,
                inference_time_ms=0,
                error=f"inference_error: {str(e)}"
            )


# Глобальный экземпляр клиента
llm_client = LocalLLMClient()
