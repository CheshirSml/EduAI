"""Homework Checker service for evaluating student assignments."""

import json
import structlog
from typing import Optional
from src.core.llm_client import llm_client
from src.core.prompt_manager import prompt_manager
from src.models.schemas import ChatMessage, HomeworkCheckResult

logger = structlog.get_logger(__name__)


class HomeworkCheckerService:
    """Service for checking and evaluating homework assignments."""
    
    def __init__(self):
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
    
    async def check_homework(
        self,
        homework_text: str,
        topic: Optional[str] = None
    ) -> HomeworkCheckResult:
        """
        Check a homework assignment and return structured evaluation.
        
        Args:
            homework_text: The student's homework text
            topic: Optional topic/context of the assignment
            
        Returns:
            HomeworkCheckResult with score, feedback, strengths, weaknesses, and suggestions
        """
        try:
            prompt = self.prompt_manager.get_homework_checker_prompt(
                topic=topic or "Not specified",
                homework=homework_text
            )
            
            messages = [
                ChatMessage(
                    role="system", 
                    content="You are an expert educational assistant. Always respond with valid JSON."
                ),
                ChatMessage(role="user", content=prompt)
            ]
            
            logger.info("Checking homework", 
                       topic=topic,
                       homework_length=len(homework_text))
            
            response = await self.llm_client.chat_completion(
                messages=messages,
                temperature=0.3,  # Lower temperature for more consistent evaluation
                max_tokens=1000
            )
            
            if not response.choices or len(response.choices) == 0:
                logger.error("No choices in homework check response")
                raise ValueError("Empty response from LLM")
            
            content = response.choices[0].message.content.strip()
            
            # Try to parse JSON from the response
            result = self._parse_json_response(content)
            
            logger.info("Homework checked successfully",
                       score=result.score,
                       strengths_count=len(result.strengths),
                       weaknesses_count=len(result.weaknesses))
            
            return result
            
        except Exception as e:
            logger.error("Error during homework checking", error=str(e))
            # Return a fallback result
            return HomeworkCheckResult(
                score=5,
                feedback=f"Unable to complete detailed evaluation due to technical error: {str(e)}. Please try again.",
                strengths=["Assignment submitted"],
                weaknesses=["Technical error prevented full analysis"],
                suggestions=["Retry the submission", "Contact support if issue persists"]
            )
    
    def _parse_json_response(self, content: str) -> HomeworkCheckResult:
        """
        Parse JSON response from LLM into HomeworkCheckResult.
        
        Handles cases where the response might contain markdown code blocks
        or extra text around the JSON.
        """
        # Try to extract JSON from markdown code blocks
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            content = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            content = content[start:end].strip()
        
        # Try to find JSON object in the content
        try:
            # First attempt: parse the entire content
            data = json.loads(content)
        except json.JSONDecodeError:
            # Second attempt: find JSON object using string matching
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx]
                data = json.loads(json_str)
            else:
                logger.error("Failed to parse JSON from response", content_preview=content[:200])
                raise ValueError("Invalid JSON response from LLM")
        
        # Validate and create result object
        try:
            return HomeworkCheckResult(
                score=int(data.get("score", 5)),
                feedback=str(data.get("feedback", "No feedback provided")),
                strengths=data.get("strengths", []),
                weaknesses=data.get("weaknesses", []),
                suggestions=data.get("suggestions", [])
            )
        except (TypeError, ValueError) as e:
            logger.error("Error validating homework result structure", error=str(e))
            raise ValueError("Invalid homework result structure")


# Global homework checker service instance
homework_checker_service = HomeworkCheckerService()
