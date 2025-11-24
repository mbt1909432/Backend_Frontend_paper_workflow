from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncIterator
from app.core.agent import Agent
from app.core.schemas import ChatRequest, ChatResponse, StreamChunk
from app.core.streaming import generate_sse_stream
from app.api.deps import get_agent
from app.utils.logger import logger


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    agent: Agent = Depends(get_agent)
):
    """
    非流式对话端点
    """
    try:
        response, conversation_id, usage = await agent.chat(
            message=request.message,
            conversation_id=request.conversation_id,
            custom_messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return ChatResponse(
            response=response,
            conversation_id=conversation_id,
            usage=usage
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    agent: Agent = Depends(get_agent)
):
    """
    流式对话端点（Server-Sent Events）
    """
    try:
        stream, conversation_id = await agent.chat_stream(
            message=request.message,
            conversation_id=request.conversation_id,
            custom_messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        # 定义完成回调，用于更新会话历史
        def on_stream_complete(full_response: str):
            agent.update_conversation_history(conversation_id, full_response)
        
        # 转换为 SSE 流
        sse_stream = generate_sse_stream(stream, conversation_id, on_complete=on_stream_complete)
        
        # 返回流式响应
        return StreamingResponse(
            sse_stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )
        
    except Exception as e:
        logger.error(f"Stream endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

