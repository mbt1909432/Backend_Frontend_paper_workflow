from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.core.agents.requirement_checklist_agent import RequirementChecklistAgent
from app.core.schemas import RequirementChecklistRequest, RequirementChecklistResponse, StreamChunk
from app.core.streaming import generate_sse_stream
from app.api.deps import get_requirement_checklist_agent
from app.utils.logger import logger


router = APIRouter()


@router.post("/generate", response_model=RequirementChecklistResponse)
async def generate_requirement_checklist(
    request: RequirementChecklistRequest,
    agent: RequirementChecklistAgent = Depends(get_requirement_checklist_agent)
):
    """
    生成需求清单文件（非流式）
    
    根据 Paper Overview Agent 的输出和 LaTeX Paper Generator Agent 的输出（或用户原始输入）生成需求清单。
    """
    try:
        result = await agent.generate_requirement_checklist(
            paper_overview=request.paper_overview,
            latex_content=request.latex_content,
            user_original_input=request.user_original_input,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return RequirementChecklistResponse(
            file_name=result["file_name"],
            file_content=result["file_content"],
            raw_response=result["raw_response"],
            usage=result["usage"]
        )
        
    except ValueError as e:
        logger.error(f"Requirement checklist generation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Requirement checklist generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/generate/stream")
async def generate_requirement_checklist_stream(
    request: RequirementChecklistRequest,
    agent: RequirementChecklistAgent = Depends(get_requirement_checklist_agent)
):
    """
    流式生成需求清单文件（Server-Sent Events）
    
    根据 Paper Overview Agent 的输出和 LaTeX Paper Generator Agent 的输出（或用户原始输入）流式生成需求清单。
    """
    try:
        stream = await agent.generate_requirement_checklist_stream(
            paper_overview=request.paper_overview,
            latex_content=request.latex_content,
            user_original_input=request.user_original_input,
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
        logger.error(f"Requirement checklist streaming error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

