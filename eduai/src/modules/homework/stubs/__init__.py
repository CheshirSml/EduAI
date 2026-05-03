"""Заглушки для внешних сервисов."""
from modules.homework.stubs.telegram_stub import send_feedback_stub, notify_error_stub

__all__ = ["send_feedback_stub", "notify_error_stub"]
