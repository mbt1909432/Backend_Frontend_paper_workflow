from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.agents.latex_paper_generator_agent import LaTeXPaperGeneratorAgent
from app.core.schemas import LaTeXPaperRequest, LaTeXPaperResponse, StreamChunk
from app.core.streaming import generate_sse_stream
from app.api.deps import get_latex_paper_generator_agent
from app.utils.logger import logger


router = APIRouter()


@router.post("/generate", response_model=LaTeXPaperResponse)
async def generate_latex_paper(
    request: LaTeXPaperRequest,
    agent: LaTeXPaperGeneratorAgent = Depends(get_latex_paper_generator_agent)
):
    """
    生成 LaTeX 论文文件（非流式）
    
    根据 Paper Overview Agent 的输出和用户提供的信息生成完整的 LaTeX 论文。
    如果用户提供了大纲或存在现有的 .tex 文件，则跳过生成。
    """
    try:
        result = await agent.generate_latex_paper(
            paper_overview=request.paper_overview,
            user_info=request.user_info,
            has_outline=request.has_outline,
            has_existing_tex=request.has_existing_tex,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return LaTeXPaperResponse(
            file_name=result["file_name"],
            file_content=result["file_content"],
            raw_response=result["raw_response"],
            is_skipped=result["is_skipped"],
            skip_reason=result["skip_reason"],
            usage=result["usage"]
        )
        
    except ValueError as e:
        logger.error(f"LaTeX paper generation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"LaTeX paper generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate/stream")
async def generate_latex_paper_stream(
    request: LaTeXPaperRequest,
    agent: LaTeXPaperGeneratorAgent = Depends(get_latex_paper_generator_agent)
):
    """
    流式生成 LaTeX 论文文件（Server-Sent Events）
    
    根据 Paper Overview Agent 的输出和用户提供的信息流式生成完整的 LaTeX 论文。
    如果用户提供了大纲或存在现有的 .tex 文件，则跳过生成。
    """
    try:
        stream = await agent.generate_latex_paper_stream(
            paper_overview=request.paper_overview,
            user_info=request.user_info,
            has_outline=request.has_outline,
            has_existing_tex=request.has_existing_tex,
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
        logger.error(f"LaTeX paper streaming error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

