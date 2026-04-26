"""Router module for intent classification and request dispatching."""

import structlog
from typing import Optional
from src.core.llm_client import llm_client
from src.core.prompt_manager import prompt_manager
from src.models.schemas import ChatMessage, IntentType

logger = structlog.get_logger(__name__)


class Router:
    """Routes user requests to appropriate handlers based on intent."""
    
    def __init__(self):
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager
    
    async def classify_intent(self, user_message: str) -> IntentType:
        """
        Classify the user's intent using LLM.
        
        Args:
            user_message: The user's input message
            
        Returns:
            Detected IntentType
        """
        try:
            prompt = self.prompt_manager.get_intent_classifier_prompt(user_message)
            
            messages = [
                ChatMessage(role="system", content="You are an intent classifier. Respond with only the intent name."),
                ChatMessage(role="user", content=prompt)
            ]
            
            response = await self.llm_client.chat_completion(
                messages=messages,
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=50
            )
            
            if response.choices and len(response.choices) > 0:
                intent_str = response.choices[0].message.content.strip().lower()
                
                logger.info("Intent classified", 
                           original_intent=intent_str,
                           user_message_length=len(user_message))
                
                # Map to IntentType enum
                if "homework" in intent_str or "check" in intent_str:
                    return IntentType.HOMEWORK_CHECK
                elif "general" in intent_str or "chat" in intent_str:
                    return IntentType.GENERAL_CHAT
                else:
                    # Default to general chat for unknown intents
                    logger.warning("Unknown intent detected, defaulting to general_chat",
                                  detected_intent=intent_str)
                    return IntentType.GENERAL_CHAT
            else:
                logger.warning("No choices in classification response")
                return IntentType.GENERAL_CHAT
                
        except Exception as e:
            logger.error("Error during intent classification", error=str(e))
            # Default to general chat on error
            return IntentType.GENERAL_CHAT
    
    async def route_request(
        self,
        messages: list[ChatMessage],
        force_intent: Optional[IntentType] = None
    ) -> tuple[IntentType, any]:
        """
        Route a request to the appropriate handler.
        
        Args:
            messages: List of chat messages
            force_intent: Optionally force a specific intent (bypass classification)
            
        Returns:
            Tuple of (IntentType, handler_result)
        """
        # Get the last user message for classification
        user_message = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            logger.warning("No user message found in request")
            return IntentType.GENERAL_CHAT, None
        
        # Determine intent
        if force_intent:
            intent = force_intent
            logger.info("Using forced intent", intent=force_intent.value)
        else:
            intent = await self.classify_intent(user_message)
        
        logger.info("Request routed", intent=intent.value)
        
        return intent, user_message


# Global router instance
router = Router()
