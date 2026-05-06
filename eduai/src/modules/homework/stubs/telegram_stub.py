"""
Заглушка для Telegram бота.
Логирует сообщения вместо реальной отправки.
"""
from utils.logger import get_logger

logger = get_logger(__name__)


def send_feedback_stub(student_fio: str, comment: str) -> bool:
    """
    Заглушка для отправки фидбека через Telegram.
    
    Вместо реальной отправки просто логирует сообщение.
    
    Args:
        student_fio: ФИО студента
        comment: Текст фидбека
    
    Returns:
        True (всегда успешно для заглушки)
    """
    logger.info(
        "telegram_stub",
        action="send_feedback",
        student_fio=student_fio,
        comment_length=len(comment),
        comment_preview=comment[:100] + ("..." if len(comment) > 100 else "")
    )
    return True


def notify_error_stub(student_fio: str, error_message: str) -> bool:
    """
    Заглушка для уведомления об ошибке.
    
    Args:
        student_fio: ФИО студента
        error_message: Сообщение об ошибке
    
    Returns:
        True (всегда успешно для заглушки)
    """
    logger.warning(
        "telegram_stub",
        action="notify_error",
        student_fio=student_fio,
        error_message=error_message
    )
    return True
