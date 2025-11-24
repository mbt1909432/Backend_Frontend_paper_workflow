from typing import AsyncIterator, Dict, Any, Callable
from app.core.schemas import StreamChunk


async def generate_sse_stream(
    openai_stream: AsyncIterator,
    conversation_id: str = None,
    on_complete: Callable[[str], None] = None
) -> AsyncIterator[str]:
    """
    将 OpenAI 流式响应转换为 SSE 格式
    
    Args:
        openai_stream: OpenAI 流式响应迭代器
        conversation_id: 会话ID
        on_complete: 流完成时的回调函数，接收完整响应文本
        
    Yields:
        SSE 格式的字符串
    """
    accumulated_text = ""
    usage_info = None
    
    try:
        async for chunk in openai_stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                
                # 提取内容
                if hasattr(delta, 'content') and delta.content:
                    content = delta.content
                    accumulated_text += content
                    # 发送数据块
                    stream_chunk = StreamChunk(
                        chunk=content,
                        done=False
                    )
                    yield f"data: {stream_chunk.model_dump_json()}\n\n"
                
                # 检查是否完成
                if chunk.choices[0].finish_reason:
                    # 流结束，尝试提取使用情况
                    if hasattr(chunk, 'usage') and chunk.usage:
                        usage_info = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
        
        # 调用完成回调
        if on_complete and accumulated_text:
            on_complete(accumulated_text)
        
        # 发送完成信号
        final_chunk = StreamChunk(
            chunk="",
            done=True,
            usage=usage_info
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        
    except Exception as e:
        # 错误处理
        error_chunk = StreamChunk(
            chunk=f"Error: {str(e)}",
            done=True
        )
        yield f"data: {error_chunk.model_dump_json()}\n\n"

