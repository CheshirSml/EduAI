"""Ядро системы EduAI."""
from core.router import LocalRouter, SUPPORTED_DOMAINS
from core.orchestrator import LocalOrchestrator

__all__ = ["LocalRouter", "SUPPORTED_DOMAINS", "LocalOrchestrator"]
