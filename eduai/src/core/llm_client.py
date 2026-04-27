"""LLM Client for Cloud.ru / GigaChat integration with OAuth 2.0."""

import httpx
import structlog
from typing import AsyncGenerator, Optional
from src.config import settings
from src.models.schemas import ChatMessage, ChatRequest, ChatResponse, Choice, Usage
import time
import uuid
import base64

logger = structlog.get_logger(__name__)


class GigaChatAuth:
    """Handle GigaChat OAuth 2.0 authentication."""
    
    def __init__(self):
        self.client_id = settings.gigachat_client_id
        self.client_secret = settings.gigachat_client_secret
        self.scope = "GIGACHAT_API_PERS"
        self.auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0
    
    def _get_basic_auth(self) -> str:
        """Create Basic Auth header from client credentials."""
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    async def get_access_token(self) -> str:
        """Get or refresh access token."""
        # Return cached token if still valid (with 5 min buffer)
        if self._access_token and time.time() < self._token_expiry - 300:
            return self._access_token
        
        logger.info("Requesting new GigaChat access token")
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": self._get_basic_auth(),
        }
        
        payload = {
            "scope": self.scope
        }
        
        async with httpx.AsyncClient(verify=False) as client:  # verify=False для самоподписанных сертификатов Сбера
            try:
                response = await client.post(self.auth_url, headers=headers, data=payload)
                response.raise_for_status()
                data = response.json()
                
                self._access_token = data.get("access_token")
                expires_in = data.get("expires_in", 1800)  # По умолчанию 30 минут
                self._token_expiry = time.time() + expires_in
                
                logger.info("Successfully obtained GigaChat access token", expires_in=expires_in)
                return self._access_token
                
            except httpx.HTTPStatusError as e:
                logger.error("Failed to get GigaChat access token", 
                           status_code=e.response.status_code,
                           response_text=e.response.text)
                raise
            except Exception as e:
                logger.error("Error getting GigaChat access token", error=str(e))
                raise


class LLMClient:
    """Async client for interacting with LLM APIs (OpenAI-compatible)."""
    
    def __init__(self):
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model_name = settings.llm_model_name
        self._client: Optional[httpx.AsyncClient] = None
        self.auth = GigaChatAuth()
        self._access_token: Optional[str] = None
    
    async def _get_access_token(self) -> str:
        """Get valid access token for GigaChat."""
        if not self._access_token:
            self._access_token = await self.auth.get_access_token()
        return self._access_token
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with current access token."""
        # Получаем свежий токен
        access_token = await self._get_access_token()
        
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
                verify=False,  # Для работы с самоподписанными сертификатами
            )
        else:
            # Обновляем токен в существующем клиенте
            self._client.headers["Authorization"] = f"Bearer {access_token}"
        
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def chat_completion(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> ChatResponse:
        """
        Send a chat completion request to the LLM.
        
        Args:
            messages: List of chat messages
            model: Model name to use (defaults to configured model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            
        Returns:
            ChatResponse object with the model's response
        """
        client = await self._get_client()
        model_to_use = model or self.model_name
        
        payload = {
            "messages": [msg.model_dump() for msg in messages],
            "model": model_to_use,
            "temperature": temperature,
            "stream": stream,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        logger.info("Sending chat completion request", 
                   model=model_to_use, 
                   stream=stream,
                   message_count=len(messages))
        
        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            
            if stream:
                # For streaming, we still return a complete response
                # Streaming is handled separately in the API layer
                raise ValueError("Streaming should be handled via chat_completion_stream method")
            
            data = response.json()
            
            # Parse response into our schema
            choices = []
            for choice_data in data.get("choices", []):
                message_data = choice_data.get("message", {})
                choices.append(Choice(
                    index=choice_data.get("index", 0),
                    message=ChatMessage(
                        role=message_data.get("role", "assistant"),
                        content=message_data.get("content", ""),
                    ),
                    finish_reason=choice_data.get("finish_reason"),
                ))
            
            usage_data = data.get("usage", {})
            usage = None
            if usage_data:
                usage = Usage(
                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                    completion_tokens=usage_data.get("completion_tokens", 0),
                    total_tokens=usage_data.get("total_tokens", 0),
                )
            
            chat_response = ChatResponse(
                id=data.get("id", str(uuid.uuid4())),
                object="chat.completion",
                created=data.get("created", int(time.time())),
                model=data.get("model", model_to_use),
                choices=choices,
                usage=usage,
            )
            
            logger.info("Received chat completion response",
                       model=model_to_use,
                       finish_reason=choices[0].finish_reason if choices else None)
            
            return chat_response
            
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error from LLM API", 
                        status_code=e.response.status_code,
                        response_text=e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("Request error to LLM API", error=str(e))
            raise
        except Exception as e:
            logger.error("Unexpected error during chat completion", error=str(e))
            raise
    
    async def chat_completion_stream(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.
        
        Yields:
            Chunks of text as they are generated
        """
        client = await self._get_client()
        model_to_use = model or self.model_name
        
        payload = {
            "messages": [msg.model_dump() for msg in messages],
            "model": model_to_use,
            "temperature": temperature,
            "stream": True,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        logger.info("Starting streaming chat completion", model=model_to_use)
        
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data.strip() == "[DONE]":
                            break
                        
                        try:
                            import json
                            chunk = json.loads(data)
                            choices = chunk.get("choices", [])
                            if choices and len(choices) > 0:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error during streaming", 
                        status_code=e.response.status_code)
            raise
        except Exception as e:
            logger.error("Error during streaming", error=str(e))
            raise


# Global LLM client instance
llm_client = LLMClient()
