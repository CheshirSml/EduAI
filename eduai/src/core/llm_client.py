"""LLM Client for GigaChat integration via Sber API."""

import httpx
import structlog
from typing import AsyncGenerator, Optional
from src.config import settings
from src.models.schemas import ChatMessage, ChatRequest, ChatResponse, Choice, Usage
import time
import uuid
import json

logger = structlog.get_logger(__name__)


class GigaChatAuth:
    """Authentication handler for GigaChat via Sber OAuth 2.0."""
    
    def __init__(self):
        self.auth_url = settings.gigachat_auth_url
        self.client_id = settings.gigachat_client_id
        self.client_secret = settings.gigachat_client_secret
        self.scope = settings.gigachat_scope
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    async def get_access_token(self) -> str:
        """
        Get or refresh access token from Sber OAuth.
        
        Returns:
            Valid access token string
            
        Raises:
            ValueError: If credentials are not configured
            httpx.RequestError: If authentication request fails
        """
        # Check if we have a valid token cached
        if self._access_token and time.time() < self._token_expires_at:
            logger.debug("Using cached access token")
            return self._access_token
        
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "GigaChat credentials not configured. "
                "Please set GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET environment variables."
            )
        
        logger.info("Requesting new access token from Sber OAuth")
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.post(
                    self.auth_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "scope": self.scope,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "RqUID": str(uuid.uuid4()),
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                
                data = response.json()
                self._access_token = data.get("access_token")
                
                if not self._access_token:
                    raise ValueError("No access_token in response from Sber OAuth")
                
                # Token expires in 30 minutes by default, we'll refresh at 80% of lifetime
                expires_in = data.get("expires_in", 1800)  # Default 30 minutes
                self._token_expires_at = time.time() + (expires_in * 0.8)
                
                logger.info(
                    "Successfully obtained access token",
                    expires_in=expires_in,
                    expires_at=self._token_expires_at
                )
                
                return self._access_token
                
            except httpx.HTTPStatusError as e:
                logger.error(
                    "Authentication failed",
                    status_code=e.response.status_code,
                    response_text=e.response.text
                )
                raise ValueError(f"Authentication failed: {e.response.status_code}")
            except httpx.RequestError as e:
                logger.error("Request error during authentication", error=str(e))
                raise


class LLMClient:
    """Async client for interacting with LLM APIs (GigaChat via Sber)."""
    
    def __init__(self):
        self.base_url = settings.gigachat_chat_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self.auth = GigaChatAuth()
        self._access_token: Optional[str] = None
    
    async def _get_access_token(self) -> str:
        """Get valid access token for GigaChat, refreshing if expired."""
        # Always check with auth class which handles expiration
        self._access_token = await self.auth.get_access_token()
        return self._access_token
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with current access token."""
        # Get fresh token (may be cached if still valid)
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
                verify=False,  # For self-signed certificates
            )
        else:
            # Update token in existing client
            self._client.headers["Authorization"] = f"Bearer {access_token}"
        
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def chat_completion(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        model: Optional[str] = None,
    ) -> ChatResponse:
        """
        Send a chat completion request to the LLM.
        
        Args:
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            model: Model name to use (optional, defaults to GigaChat)
            
        Returns:
            ChatResponse object with the model's response
        """
        client = await self._get_client()
        model_to_use = model or "GigaChat"  # Use provided model or default
        
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
            response = await client.post("", json=payload)
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
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat completion response.
        
        Args:
            messages: List of chat messages
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            model: Model name to use (optional, defaults to GigaChat)
        
        Yields:
            Chunks of text as they are generated
        """
        client = await self._get_client()
        model_to_use = model or "GigaChat"
        
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
            async with client.stream("POST", "", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data.strip() == "[DONE]":
                            break
                        
                        try:
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
