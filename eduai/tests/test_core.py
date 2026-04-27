"""Unit tests for EduAI Core components."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from src.models.schemas import (
    IntentType,
    ChatMessage,
    HomeworkCheckResult,
    ChatRequest,
)
from src.core.prompt_manager import PromptManager
from src.services.homework_checker import HomeworkCheckerService


class TestPromptManager:
    """Tests for PromptManager class."""
    
    def test_intent_classifier_prompt_formatting(self):
        """Test that intent classifier prompt is properly formatted."""
        pm = PromptManager()
        user_message = "Check my homework on psychology"
        prompt = pm.get_intent_classifier_prompt(user_message)
        
        assert "Check my homework on psychology" in prompt
        assert "homework_check" in prompt
        assert "general_chat" in prompt
    
    def test_homework_checker_prompt_formatting(self):
        """Test that homework checker prompt is properly formatted."""
        pm = PromptManager()
        topic = "Cognitive Psychology"
        homework = "This is my essay about memory."
        
        prompt = pm.get_homework_checker_prompt(topic=topic, homework=homework)
        
        assert "Cognitive Psychology" in prompt
        assert "This is my essay about memory." in prompt
        assert "JSON format" in prompt
    
    def test_homework_checker_prompt_default_topic(self):
        """Test homework checker prompt with default topic."""
        pm = PromptManager()
        homework = "My homework text"
        
        prompt = pm.get_homework_checker_prompt(topic=None, homework=homework)
        
        assert "Not specified" in prompt or "topic" in prompt.lower()
    
    def test_general_chat_prompt(self):
        """Test general chat prompt retrieval."""
        pm = PromptManager()
        prompt = pm.get_general_chat_prompt()
        
        assert "EduAI" in prompt
        assert "educational" in prompt.lower()


class TestHomeworkCheckResult:
    """Tests for HomeworkCheckResult schema."""
    
    def test_valid_result_creation(self):
        """Test creating a valid HomeworkCheckResult."""
        result = HomeworkCheckResult(
            score=8,
            feedback="Good work overall",
            strengths=["Well structured", "Good analysis"],
            weaknesses=["Minor grammar issues"],
            suggestions=["Proofread before submission"]
        )
        
        assert result.score == 8
        assert len(result.strengths) == 2
        assert len(result.weaknesses) == 1
        assert len(result.suggestions) == 1
    
    def test_score_validation(self):
        """Test score validation (1-10 range)."""
        # Valid scores
        result = HomeworkCheckResult(score=1, feedback="Test")
        assert result.score == 1
        
        result = HomeworkCheckResult(score=10, feedback="Test")
        assert result.score == 10
        
        # Invalid scores should raise validation error
        with pytest.raises(Exception):  # Pydantic ValidationError
            HomeworkCheckResult(score=0, feedback="Test")
        
        with pytest.raises(Exception):
            HomeworkCheckResult(score=11, feedback="Test")
    
    def test_default_empty_lists(self):
        """Test that optional fields default to empty lists."""
        result = HomeworkCheckResult(score=5, feedback="Basic feedback")
        
        assert result.strengths == []
        assert result.weaknesses == []
        assert result.suggestions == []


class TestIntentType:
    """Tests for IntentType enum."""
    
    def test_intent_values(self):
        """Test intent type values."""
        assert IntentType.HOMEWORK_CHECK.value == "homework_check"
        assert IntentType.GENERAL_CHAT.value == "general_chat"
    
    def test_intent_comparison(self):
        """Test intent type comparison."""
        intent = IntentType.HOMEWORK_CHECK
        assert intent == IntentType.HOMEWORK_CHECK
        assert intent != IntentType.GENERAL_CHAT


class TestChatMessage:
    """Tests for ChatMessage schema."""
    
    def test_valid_roles(self):
        """Test valid message roles."""
        for role in ["user", "assistant", "system"]:
            msg = ChatMessage(role=role, content="Test message")
            assert msg.role == role
    
    def test_invalid_role(self):
        """Test invalid role raises error."""
        with pytest.raises(Exception):
            ChatMessage(role="invalid", content="Test")


@pytest.mark.asyncio
class TestHomeworkCheckerServiceAsync:
    """Async tests for HomeworkCheckerService."""
    
    @patch('src.services.homework_checker.llm_client')
    async def test_check_homework_success(self, mock_llm_client):
        """Test successful homework checking."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='''
            {
                "score": 8,
                "feedback": "Good work",
                "strengths": ["Well structured"],
                "weaknesses": ["Minor issues"],
                "suggestions": ["Proofread"]
            }
            '''))
        ]
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)
        
        service = HomeworkCheckerService()
        result = await service.check_homework(
            homework_text="Test homework",
            topic="Test topic"
        )
        
        assert result.score == 8
        assert "Good work" in result.feedback
        mock_llm_client.chat_completion.assert_called_once()
    
    @patch('src.services.homework_checker.llm_client')
    async def test_check_homework_with_markdown_json(self, mock_llm_client):
        """Test parsing JSON from markdown code blocks."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='''
            ```json
            {
                "score": 7,
                "feedback": "Decent work",
                "strengths": [],
                "weaknesses": [],
                "suggestions": []
            }
            ```
            '''))
        ]
        mock_llm_client.chat_completion = AsyncMock(return_value=mock_response)
        
        service = HomeworkCheckerService()
        result = await service.check_homework(homework_text="Test")
        
        assert result.score == 7
    
    @patch('src.services.homework_checker.llm_client')
    async def test_check_homework_error_fallback(self, mock_llm_client):
        """Test fallback behavior on LLM error."""
        mock_llm_client.chat_completion = AsyncMock(side_effect=Exception("API Error"))
        
        service = HomeworkCheckerService()
        result = await service.check_homework(homework_text="Test")
        
        # Should return fallback result
        assert result.score == 5
        assert "technical error" in result.feedback.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
