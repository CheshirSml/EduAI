"""Core module for EduAI - LLM client and prompt management."""

from src.core.llm_client import LLMClient, llm_client
from src.core.prompt_manager import PromptManager, prompt_manager

__all__ = [
    "LLMClient",
    "llm_client",
    "PromptManager",
    "prompt_manager",
]