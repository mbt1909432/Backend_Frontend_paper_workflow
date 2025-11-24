from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from typing import List, Optional, Tuple
from app.core.agents.vision_agent import VisionAgent
from app.core.schemas import (
    VisionAnalysisRequest, 
    VisionAnalysisResponse, 
    StreamChunk,
    PDFProcessRequest,
    PDFProcessResponse
)
from app.api.deps import get_vision_agent
from app.utils.logger import logger
from app.utils.pdf_converter import pdf_to_pngs
from app.core.streaming import generate_sse_stream
import base64
import os
import tempfile
import shutil
import asyncio
from pathlib import Path


router = APIRouter()


@router.post("/analyze", response_model=VisionAnalysisResponse)
async def analyze_image(
    request: VisionAnalysisRequest,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    分析图片（非流式）
    
    支持：
    - 单张或多张图片
    - base64 编码的图片字符串
    - 文件路径（相对或绝对路径）
    """
    try:
        result = await vision_agent.analyze_image(
            images=request.images,
            text_prompt=request.text_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return VisionAnalysisResponse(
            response=result["response"],
            usage=result["usage"],
            raw_response=result["raw_response"]
        )
        
    except Exception as e:
        logger.error(f"Vision analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/analyze/stream")
async def analyze_image_stream(
    request: VisionAnalysisRequest,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    流式分析图片（Server-Sent Events）
    """
    try:
        stream = await vision_agent.analyze_image_stream(
            images=request.images,
            text_prompt=request.text_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        # 转换 Anthropic 流式响应为 SSE 格式
        async def anthropic_to_sse_stream():
            accumulated_text = ""
            usage_info = None
            stream_ended = False
            
            async for chunk in stream:
                # 处理不同类型的 chunk
                chunk_type = getattr(chunk, 'type', None)
                
                if chunk_type == 'content_block_delta':
                    # 文本增量
                    delta = getattr(chunk, 'delta', None)
                    if delta:
                        text = getattr(delta, 'text', None)
                        if text:
                            accumulated_text += text
                            yield f"data: {StreamChunk(chunk=text, done=False).model_dump_json()}\n\n"
                
                elif chunk_type == 'message_delta':
                    # 消息增量（可能包含 usage 信息）
                    usage = getattr(chunk, 'usage', None)
                    if usage:
                        usage_info = {
                            "input_tokens": getattr(usage, 'input_tokens', 0),
                            "output_tokens": getattr(usage, 'output_tokens', 0),
                            "total_tokens": getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)
                        }
                
                elif chunk_type == 'message_stop':
                    # 流结束
                    stream_ended = True
                    # 尝试从 chunk 获取 usage 信息
                    usage = getattr(chunk, 'usage', None)
                    if usage:
                        usage_info = {
                            "input_tokens": getattr(usage, 'input_tokens', 0),
                            "output_tokens": getattr(usage, 'output_tokens', 0),
                            "total_tokens": getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)
                        }
                    break
            
            # 发送完成信号
            if not stream_ended:
                yield f"data: {StreamChunk(chunk='', done=True, usage=usage_info).model_dump_json()}\n\n"
            else:
                # 如果已经发送了 message_stop，确保发送完成信号
                yield f"data: {StreamChunk(chunk='', done=True, usage=usage_info).model_dump_json()}\n\n"
        
        return StreamingResponse(
            anthropic_to_sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
        
    except Exception as e:
        logger.error(f"Vision streaming error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/upload", response_model=VisionAnalysisResponse)
async def analyze_uploaded_image(
    files: List[UploadFile] = File(...),
    text_prompt: Optional[str] = None,
    temperature: Optional[float] = 0.7,
    max_tokens: Optional[int] = 4096,
    model: Optional[str] = None,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    上传图片并分析（非流式）
    
    支持通过 multipart/form-data 上传图片文件
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        
        # 读取上传的图片
        images = []
        for file in files:
            image_data = await file.read()
            images.append(image_data)
        
        result = await vision_agent.analyze_image(
            images=images,
            text_prompt=text_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        return VisionAnalysisResponse(
            response=result["response"],
            usage=result["usage"],
            raw_response=result["raw_response"]
        )
        
    except Exception as e:
        logger.error(f"Vision upload analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/compare", response_model=VisionAnalysisResponse)
async def compare_images(
    request: VisionAnalysisRequest,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    比较多张图片
    """
    try:
        if len(request.images) < 2:
            raise HTTPException(status_code=400, detail="At least 2 images are required for comparison")
        
        result = await vision_agent.compare_images(
            images=request.images,
            comparison_prompt=request.text_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model
        )
        
        return VisionAnalysisResponse(
            response=result["response"],
            usage=result["usage"],
            raw_response=result["raw_response"]
        )
        
    except Exception as e:
        logger.error(f"Vision comparison error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/ocr", response_model=VisionAnalysisResponse)
async def extract_text_from_image(
    request: VisionAnalysisRequest,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    从图片中提取文字（OCR）
    """
    try:
        if len(request.images) != 1:
            raise HTTPException(status_code=400, detail="OCR requires exactly 1 image")
        
        result = await vision_agent.extract_text_from_image(
            image=request.images[0],
            temperature=request.temperature or 0.3,  # OCR 使用较低温度
            max_tokens=request.max_tokens or 2048,
            model=request.model
        )
        
        return VisionAnalysisResponse(
            response=result["response"],
            usage=result["usage"],
            raw_response=result["raw_response"]
        )
        
    except Exception as e:
        logger.error(f"Vision OCR error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/pdf/process", response_model=PDFProcessResponse)
async def process_pdf(
    file: UploadFile = File(...),
    text_prompt: Optional[str] = None,
    temperature: Optional[float] = 0.3,
    max_tokens: Optional[int] = 4096,
    model: Optional[str] = None,
    dpi: Optional[int] = 300,
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    处理 PDF 文件：转换为 PNG，使用 Vision Agent 提取文字描述，拼接结果
    
    流程：
    1. 接收上传的 PDF 文件
    2. 将 PDF 转换为多个 PNG 图片（每页一张）
    3. 使用 Vision Agent 并发分析所有图片，提取文字描述
    4. 拼接所有页面的文字描述并返回（保持页面顺序）
    """
    temp_pdf_path = None
    temp_output_dir = None
    
    try:
        # 验证文件类型
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="File must be a PDF")
        
        # 创建临时文件保存上传的 PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            content = await file.read()
            temp_pdf.write(content)
            temp_pdf_path = temp_pdf.name
        
        logger.info(f"Received PDF file: {file.filename}, size: {len(content)} bytes")
        
        # 创建临时输出目录
        temp_output_dir = tempfile.mkdtemp(prefix="pdf_pngs_")
        logger.info(f"Created temporary output directory: {temp_output_dir}")
        
        # 将 PDF 转换为 PNG
        png_paths = pdf_to_pngs(
            pdf_path=temp_pdf_path,
            output_dir=temp_output_dir,
            dpi=dpi
        )
        
        if not png_paths:
            raise HTTPException(status_code=500, detail="Failed to convert PDF to PNGs")
        
        logger.info(f"Converted PDF to {len(png_paths)} PNG files")
        
        # 如果没有提供 text_prompt，使用默认的 OCR 提示
        if not text_prompt:
            text_prompt = "请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
        
        # 定义处理单张图片的异步函数
        async def process_single_page(idx: int, png_path: str) -> Tuple[int, str, dict]:
            """
            处理单张图片
            
            Returns:
                (页面索引, 描述文本, usage字典) 或 (页面索引, 错误信息, 空字典)
            """
            logger.info(f"Processing page {idx}/{len(png_paths)}: {png_path}")
            
            try:
                # 使用 Vision Agent 提取文字描述
                result = await vision_agent.extract_text_from_image(
                    image=png_path,
                    text_prompt=text_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model
                )
                
                page_description = result["response"]
                usage = result.get("usage", {})
                
                logger.info(f"Page {idx} processed. Description length: {len(page_description)} characters")
                
                return (idx, page_description, usage)
                
            except Exception as e:
                logger.error(f"Error processing page {idx}: {str(e)}")
                # 如果某页处理失败，返回错误标记
                return (idx, f"[页面 {idx} 处理失败: {str(e)}]", {})
        
        # 并发处理所有图片
        logger.info(f"Starting concurrent processing of {len(png_paths)} pages...")
        tasks = [
            process_single_page(idx, png_path)
            for idx, png_path in enumerate(png_paths, 1)
        ]
        
        # 使用 asyncio.gather 并发执行所有任务
        results = await asyncio.gather(*tasks)
        
        # 按页面索引排序（保持顺序）
        results.sort(key=lambda x: x[0])
        
        # 提取结果并累计 token 使用量
        page_descriptions = []
        total_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }
        
        for idx, page_description, usage in results:
            page_descriptions.append(page_description)
            
            # 累计 token 使用量
            if usage:
                total_usage["input_tokens"] += usage.get("input_tokens", 0)
                total_usage["output_tokens"] += usage.get("output_tokens", 0)
                total_usage["total_tokens"] += usage.get("total_tokens", 0)
        
        logger.info(f"All {len(png_paths)} pages processed concurrently. Total tokens: {total_usage['total_tokens']}")
        
        # 拼接所有页面的文字描述
        # 添加页面分隔符
        separator = "\n\n" + "=" * 80 + "\n"
        separator += "页面分隔符\n"
        separator += "=" * 80 + "\n\n"
        
        full_description = ""
        for idx, desc in enumerate(page_descriptions, 1):
            full_description += f"=== 第 {idx} 页 ===\n\n"
            full_description += desc
            if idx < len(page_descriptions):
                full_description += separator
        
        logger.info(f"PDF processing completed. Total pages: {len(png_paths)}, Total description length: {len(full_description)} characters")
        
        return PDFProcessResponse(
            response=full_description,
            page_count=len(png_paths),
            page_descriptions=page_descriptions,
            total_usage=total_usage,
            raw_response=full_description
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    finally:
        # 清理临时文件
        try:
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.unlink(temp_pdf_path)
                logger.info(f"Deleted temporary PDF file: {temp_pdf_path}")
            
            if temp_output_dir and os.path.exists(temp_output_dir):
                # 删除临时目录及其所有内容
                shutil.rmtree(temp_output_dir)
                logger.info(f"Deleted temporary output directory: {temp_output_dir}")
        except Exception as e:
            logger.warning(f"Error cleaning up temporary files: {str(e)}")

