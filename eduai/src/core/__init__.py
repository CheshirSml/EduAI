"""Ядро системы EduAI."""
from src.core.router import LocalRouter, SUPPORTED_DOMAINS
from src.core.orchestrator import LocalOrchestrator

__all__ = ["LocalRouter", "SUPPORTED_DOMAINS", "LocalOrchestrator"]
