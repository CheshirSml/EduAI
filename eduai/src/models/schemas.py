from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class IntentType(str, Enum):
    """Supported intent types for routing."""
    HOMEWORK_CHECK = "homework_check"
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"


class ChatMessage(BaseModel):
    """Standard chat message format."""
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """OpenAI-compatible chat request format."""
    messages: list[ChatMessage]
    model: Optional[str] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    """OpenAI-compatible chat response format."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list["Choice"]
    usage: Optional["Usage"] = None


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class HomeworkCheckResult(BaseModel):
    """Structured result of homework checking."""
    score: int = Field(ge=1, le=10, description="Score from 1 to 10")
    feedback: str = Field(description="Detailed feedback for the student")
    strengths: list[str] = Field(default_factory=list, description="List of strengths")
    weaknesses: list[str] = Field(default_factory=list, description="List of areas for improvement")
    suggestions: list[str] = Field(default_factory=list, description="Specific suggestions for improvement")
