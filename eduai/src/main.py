"""Main FastAPI application for EduAI with OpenWebUI compatibility."""

import time
import uuid
import json
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import structlog

from src.config import settings
from src.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    Choice,
    Usage,
    HomeworkCheckResult,
)
from src.core.llm_client import llm_client
from src.routers.intent_router import router, IntentType
from src.services.homework_checker import homework_checker_service

logger = structlog.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="EduAI API",
    description="Educational AI Assistant with OpenWebUI compatibility",
    version="0.1.0-alpha",
)

# Enable CORS for OpenWebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    logger.info("EduAI starting up", 
                host=settings.app_host, 
                port=settings.app_port,
                model=settings.llm_model_name)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    await llm_client.close()
    logger.info("EduAI shut down")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "EduAI"}


@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """
    OpenAI-compatible chat completions endpoint.
    
    This endpoint handles routing to appropriate handlers based on intent:
    - homework_check: Routes to homework checker service
    - general_chat: Routes to general LLM conversation
    """
    try:
        # Route the request based on intent
        intent, user_message = await router.route_request(request.messages)
        
        logger.info("Processing chat request", 
                   intent=intent.value,
                   message_count=len(request.messages),
                   stream=request.stream)
        
        if intent == IntentType.HOMEWORK_CHECK:
            # Handle homework checking
            result = await _handle_homework_check(request.messages)
            
            # Convert result to chat response format
            response_content = _format_homework_result(result)
            
            return ChatResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model or settings.llm_model_name,
                choices=[
                    Choice(
                        index=0,
                        message=ChatMessage(role="assistant", content=response_content),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            )
        
        else:
            # Handle general chat
            if request.stream and settings.enable_streaming:
                # Return streaming response
                return StreamingResponse(
                    _stream_general_chat(request),
                    media_type="text/event-stream"
                )
            else:
                # Return standard response
                response = await llm_client.chat_completion(
                    messages=request.messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=False
                )
                return response
    
    except Exception as e:
        logger.error("Error in chat completions", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_homework_check(messages: list[ChatMessage]) -> HomeworkCheckResult:
    """Handle homework checking intent."""
    # Extract homework text and optional topic from messages
    homework_text = ""
    topic = None
    
    # Look for the last user message as the homework
    for msg in reversed(messages):
        if msg.role == "user":
            # Simple heuristic: use the last user message as homework
            # In a more advanced version, we could parse for topic/homework structure
            homework_text = msg.content
            
            # Check if there's a topic mentioned (simple keyword detection)
            lower_content = msg.content.lower()
            if "topic:" in lower_content or "тема:" in lower_content:
                # Try to extract topic
                lines = msg.content.split("\n")
                for line in lines:
                    if "topic:" in line.lower() or "тема:" in line.lower():
                        topic = line.split(":", 1)[1].strip()
                        break
            
            break
    
    if not homework_text:
        raise ValueError("No homework text found in request")
    
    return await homework_checker_service.check_homework(
        homework_text=homework_text,
        topic=topic
    )


def _format_homework_result(result: HomeworkCheckResult) -> str:
    """Format homework check result as a readable response."""
    output = []
    output.append(f"📊 **Оценка: {result.score}/10**\n")
    
    output.append("💬 **Общий отзыв:**")
    output.append(result.feedback)
    output.append("")
    
    if result.strengths:
        output.append("✅ **Сильные стороны:**")
        for strength in result.strengths:
            output.append(f"  • {strength}")
        output.append("")
    
    if result.weaknesses:
        output.append("⚠️ **Области для улучшения:**")
        for weakness in result.weaknesses:
            output.append(f"  • {weakness}")
        output.append("")
    
    if result.suggestions:
        output.append("💡 **Рекомендации:**")
        for suggestion in result.suggestions:
            output.append(f"  • {suggestion}")
    
    return "\n".join(output)


async def _stream_general_chat(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Stream general chat response."""
    try:
        async for chunk in llm_client.chat_completion_stream(
            messages=request.messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        ):
            # Format as SSE (Server-Sent Events)
            data = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": request.model or settings.llm_model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None
                    }
                ]
            }
            yield f"data: {json.dumps(data)}\n\n"
        
        # Send final chunk
        final_data = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": request.model or settings.llm_model_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
        yield f"data: {json.dumps(final_data)}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error("Error during streaming", error=str(e))
        # Send error chunk
        error_data = {
            "error": {"message": str(e), "type": "server_error"}
        }
        yield f"data: {json.dumps(error_data)}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.environment == "development")
    )
