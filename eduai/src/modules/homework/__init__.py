"""Модуль проверки домашних заданий."""
from modules.homework.mcp_server import (
    get_assignment_spec,
    get_grading_rubric,
    list_pending_assignments,
    validate_assignment_format,
    assess_assignment_content,
    mark_assignment_processed
)

__all__ = [
    "get_assignment_spec",
    "get_grading_rubric",
    "list_pending_assignments",
    "validate_assignment_format",
    "assess_assignment_content",
    "mark_assignment_processed"
]
