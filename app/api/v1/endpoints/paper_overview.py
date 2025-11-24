from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.agents.paper_overview_agent import PaperOverviewAgent
from app.core.schemas import PaperOverviewRequest, PaperOverviewResponse, StreamChunk
from app.core.streaming import generate_sse_stream
from app.api.deps import get_paper_overview_agent
from app.utils.logger import logger


router = APIRouter()


@router.post("/generate", response_model=PaperOverviewResponse)
async def generate_paper_overview(
    request: PaperOverviewRequest,
    agent: PaperOverviewAgent = Depends(get_paper_overview_agent)
):
    """
    生成论文概览文件（非流式）
    
    根据用户提供的文档生成论文概览，输出格式为 markdown，包含文件名和内容。
    """
    try:
        result = await agent.generate_overview(
            user_document=request.document,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return PaperOverviewResponse(
            file_name=result["file_name"],
            file_content=result["file_content"],
            raw_response=result["raw_response"],
            usage=result["usage"]
        )
        
    except ValueError as e:
        logger.error(f"Paper overview generation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Paper overview generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate/stream")
async def generate_paper_overview_stream(
    request: PaperOverviewRequest,
    agent: PaperOverviewAgent = Depends(get_paper_overview_agent)
):
    """
    流式生成论文概览文件（Server-Sent Events）
    
    根据用户提供的文档流式生成论文概览，输出格式为 markdown，包含文件名和内容。
    """
    try:
        stream = await agent.generate_overview_stream(
            user_document=request.document,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        # 转换为 SSE 流
        sse_stream = generate_sse_stream(stream, conversation_id=None, on_complete=None)
        
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
        logger.error(f"Paper overview streaming error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

