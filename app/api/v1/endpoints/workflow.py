"""论文生成工作流 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Request, status
from fastapi.responses import StreamingResponse, FileResponse
from typing import Optional, List
from sqlalchemy.orm import Session
from app.core.workflows.paper_generation_workflow import PaperGenerationWorkflow
from app.core.schemas import (
    PaperGenerationWorkflowResponse,
    PaperOverviewResult,
    LaTeXPaperResult,
    RequirementChecklistResult,
    WorkflowProgressChunk
)
from app.api.deps import get_paper_generation_workflow, get_vision_agent
from app.api.deps_auth import get_current_backend_user
from app.db.database import get_db
from app.db.models import User, Task
from app.core.agents.vision_agent import VisionAgent
from app.utils.pdf_converter import pdf_to_pngs
from app.utils.file_manager import save_uploaded_file, create_session_folder, delete_session_folder, list_all_sessions, get_session_details, get_session_folder_path
from app.utils.logger import logger
from app.utils.token_tracker import record_usage_from_dict, settle_token_usage
import tempfile
import asyncio
from typing import Tuple


router = APIRouter()


@router.post("/execute", response_model=PaperGenerationWorkflowResponse)
async def execute_workflow(
    document: Optional[str] = Form(None, description="用户提供的文字描述"),
    pdf_file: Optional[UploadFile] = File(None, description="用户上传的PDF文件"),
    image_files: Optional[List[UploadFile]] = File(None, description="用户上传的图片文件（支持多张）"),
    session_id: Optional[str] = Form(None, description="可选的 session ID"),
    user_info: Optional[str] = Form(None, description="用户提供的额外信息"),
    has_outline: Optional[bool] = Form(False, description="用户是否提供了论文大纲"),
    has_existing_tex: Optional[bool] = Form(False, description="是否存在现有的 .tex 文件"),
    temperature: Optional[float] = Form(None, description="温度参数"),
    max_tokens: Optional[int] = Form(None, description="最大token数"),
    model: Optional[str] = Form(None, description="模型名称"),
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db),
    workflow: PaperGenerationWorkflow = Depends(get_paper_generation_workflow),
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    执行完整的论文生成工作流
    
    支持多种输入方式：
    1. 文字描述（document 参数）
    2. PDF文件上传（pdf_file 参数）
    3. 图片文件上传（image_files 参数，支持多张）
    4. 以上可以任意组合提供
    
    按顺序执行：
    1. Paper Overview Agent - 生成论文概览文件
    2. LaTeX Paper Generator Agent - 生成 LaTeX 论文文件
    3. Requirement Checklist Agent - 生成需求清单文件
    
    所有文件将保存在同一个 session 文件夹中：
    - session/uploaded: 上传的文件（PDF、图片等）
    - session/generated: 生成的文件（概览、LaTeX、清单等）
    """
    try:
        # 检查用户当前运行中的workflow数量
        running_workflows_count = db.query(Task).filter(
            Task.user_id == current_user.id,
            Task.status == "running"
        ).count()
        
        max_concurrent = current_user.max_concurrent_workflows or 10
        if running_workflows_count >= max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"已达到最大并发数限制（{running_workflows_count}/{max_concurrent}），请等待任务完成后再启动新任务"
            )
        
        # 创建session文件夹（如果还没有创建），使用当前用户名
        session_folder = create_session_folder(session_id, username=current_user.username)
        
        # 处理用户输入
        user_document = document or ""
        pdf_text_content = ""
        image_text_content = ""
        has_pdf = False
        pdf_session_folder = None
        
        # 处理PDF文件上传
        if pdf_file:
            has_pdf = True
            # 验证文件类型
            if not pdf_file.filename.endswith('.pdf'):
                raise HTTPException(status_code=400, detail="上传的文件必须是PDF格式")
            
            # 读取PDF内容
            pdf_content = await pdf_file.read()
            
            # 创建临时文件处理PDF
            temp_pdf_path = None
            temp_output_dir = None
            
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                    temp_pdf.write(pdf_content)
                    temp_pdf_path = temp_pdf.name
                
                logger.info(f"Received PDF file: {pdf_file.filename}, size: {len(pdf_content)} bytes")
                
                # 创建临时输出目录用于PDF转PNG
                temp_output_dir = tempfile.mkdtemp(prefix="pdf_pngs_")
                
                # 将PDF转换为PNG
                png_paths = pdf_to_pngs(
                    pdf_path=temp_pdf_path,
                    output_dir=temp_output_dir,
                    dpi=300
                )
                
                if not png_paths:
                    raise HTTPException(status_code=500, detail="PDF转PNG失败")
                
                logger.info(f"Converted PDF to {len(png_paths)} PNG files")
                
                # 提取文字内容
                text_prompt = "请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
                
                async def process_single_page(idx: int, png_path: str) -> Tuple[int, str, dict]:
                    try:
                        # 检查客户端是否断开
                        if await request.is_disconnected():
                            logger.warning(f"客户端已断开，取消页面 {idx} 的处理")
                            raise asyncio.CancelledError("客户端已断开连接")
                        
                        result = await vision_agent.extract_text_from_image(
                            image=png_path,
                            text_prompt=text_prompt,
                            temperature=0.3,
                            max_tokens=4096,
                            model=None
                        )
                        return (idx, result["response"], result.get("usage", {}))
                    except asyncio.CancelledError:
                        logger.info(f"页面 {idx} 处理被取消（客户端断开）")
                        raise
                    except Exception as e:
                        logger.error(f"Error processing page {idx}: {str(e)}")
                        return (idx, f"[页面 {idx} 处理失败: {str(e)}]", {})
                
                # 并发处理所有页面，使用 asyncio.Task 以便可以取消
                page_tasks = [
                    asyncio.create_task(process_single_page(idx, png_path)) 
                    for idx, png_path in enumerate(png_paths, 1)
                ]
                
                try:
                    # 等待所有任务完成，但如果客户端断开则取消
                    results = await asyncio.gather(*page_tasks, return_exceptions=True)
                    
                    # 检查是否有客户端断开的情况
                    if await request.is_disconnected():
                        logger.warning("客户端已断开，取消剩余的PDF页面处理任务")
                        # 取消所有未完成的任务
                        for task in page_tasks:
                            if not task.done():
                                task.cancel()
                        raise asyncio.CancelledError("客户端已断开连接")
                    
                    # 处理结果，过滤掉异常
                    valid_results = []
                    for result in results:
                        if isinstance(result, Exception):
                            if isinstance(result, asyncio.CancelledError):
                                logger.info("部分PDF页面处理被取消")
                                continue
                            logger.error(f"PDF页面处理异常: {result}")
                            continue
                        valid_results.append(result)
                    
                    results = valid_results
                    results.sort(key=lambda x: x[0])
                    
                except asyncio.CancelledError:
                    logger.info("PDF页面处理被取消（客户端断开）")
                    # 取消所有任务
                    for task in page_tasks:
                        if not task.done():
                            task.cancel()
                    # 等待任务取消完成
                    await asyncio.gather(*page_tasks, return_exceptions=True)
                    raise
                
                # 拼接所有页面的文字内容并汇总 token 使用量
                page_descriptions = [result[1] for result in results]
                pdf_text_content = "\n\n".join(page_descriptions)
                
                # 汇总所有页面的 token 使用量
                total_pdf_usage = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                }
                for result in results:
                    usage = result[2] if len(result) > 2 else {}
                    if usage:
                        total_pdf_usage["input_tokens"] += usage.get("input_tokens", 0)
                        total_pdf_usage["output_tokens"] += usage.get("output_tokens", 0)
                        total_pdf_usage["total_tokens"] += usage.get("total_tokens", 0)
                
                # 记录 PDF 处理的 token 使用
                if total_pdf_usage["total_tokens"] > 0:
                    try:
                        # 获取模型名称（从 vision_agent 或使用默认值）
                        model_name = None  # vision agent 会使用默认模型
                        record_usage_from_dict(
                            db=db,
                            user_id=current_user.id,
                            usage_dict={
                                "prompt_tokens": total_pdf_usage["input_tokens"],
                                "completion_tokens": total_pdf_usage["output_tokens"],
                                "total_tokens": total_pdf_usage["total_tokens"]
                            },
                            model=model_name,
                            stage="pdf_processing",
                            session_id=session_id
                        )
                        logger.info(f"Recorded PDF processing token usage: {total_pdf_usage['total_tokens']} tokens")
                    except Exception as e:
                        logger.error(f"Failed to record PDF processing token usage: {str(e)}")
                
                logger.info(f"Extracted text from PDF: {len(pdf_text_content)} characters")
                
            finally:
                # 清理临时文件
                import os
                if temp_pdf_path and os.path.exists(temp_pdf_path):
                    try:
                        os.unlink(temp_pdf_path)
                    except:
                        pass
                if temp_output_dir and os.path.exists(temp_output_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_output_dir)
                    except:
                        pass
        
        # 处理图片文件上传
        if image_files:
            logger.info(f"Received {len(image_files)} image files")
            
            # 支持的图片格式
            allowed_image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            
            # 提取文字内容
            text_prompt = "请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
            
            async def process_single_image(idx: int, image_file: UploadFile) -> Tuple[int, str, str, dict]:
                """处理单张图片"""
                try:
                    # 验证文件类型
                    file_ext = None
                    for ext in allowed_image_extensions:
                        if image_file.filename and image_file.filename.lower().endswith(ext):
                            file_ext = ext
                            break
                    
                    if not file_ext:
                        logger.warning(f"Image {idx} ({image_file.filename}) has unsupported format, skipping")
                        return (idx, "", "", {})
                    
                    # 读取图片内容
                    image_content = await image_file.read()
                    
                    # 保存图片到session文件夹
                    image_filename = image_file.filename or f"image_{idx}{file_ext}"
                    image_path = save_uploaded_file(
                        session_folder=session_folder,
                        file_name=image_filename,
                        content=image_content
                    )
                    
                    logger.info(f"Processing image {idx}/{len(image_files)}: {image_filename}")
                    
                    # 使用 Vision Agent 提取文字
                    result = await vision_agent.extract_text_from_image(
                        image=image_path,
                        text_prompt=text_prompt,
                        temperature=0.3,
                        max_tokens=4096,
                        model=None
                    )
                    
                    extracted_text = result["response"]
                    usage = result.get("usage", {})
                    logger.info(f"Image {idx} processed. Text length: {len(extracted_text)} characters")
                    
                    return (idx, extracted_text, image_filename, usage)
                    
                except Exception as e:
                    logger.error(f"Error processing image {idx}: {str(e)}")
                    return (idx, f"[图片 {idx} 处理失败: {str(e)}]", "", {})
            
            # 并发处理所有图片
            tasks = [process_single_image(idx, img_file) for idx, img_file in enumerate(image_files, 1)]
            image_results = await asyncio.gather(*tasks)
            image_results.sort(key=lambda x: x[0])
            
            # 拼接所有图片的文字内容并汇总 token 使用量
            image_texts = []
            total_image_usage = {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0
            }
            for result in image_results:
                idx = result[0]
                text = result[1] if len(result) > 1 else ""
                filename = result[2] if len(result) > 2 else ""
                usage = result[3] if len(result) > 3 else {}
                
                if text:
                    image_texts.append(f"--- 图片 {idx}: {filename} ---\n\n{text}")
                
                # 累计 token 使用量
                if usage:
                    total_image_usage["input_tokens"] += usage.get("input_tokens", 0)
                    total_image_usage["output_tokens"] += usage.get("output_tokens", 0)
                    total_image_usage["total_tokens"] += usage.get("total_tokens", 0)
            
            # 记录图片处理的 token 使用
            if total_image_usage["total_tokens"] > 0:
                try:
                    model_name = None  # vision agent 会使用默认模型
                    record_usage_from_dict(
                        db=db,
                        user_id=current_user.id,
                        usage_dict={
                            "prompt_tokens": total_image_usage["input_tokens"],
                            "completion_tokens": total_image_usage["output_tokens"],
                            "total_tokens": total_image_usage["total_tokens"]
                        },
                        model=model_name,
                        stage="image_processing",
                        session_id=session_id
                    )
                    logger.info(f"Recorded image processing token usage: {total_image_usage['total_tokens']} tokens")
                except Exception as e:
                    logger.error(f"Failed to record image processing token usage: {str(e)}")
            
            if image_texts:
                image_text_content = "\n\n".join(image_texts)
                logger.info(f"Extracted text from images: {len(image_text_content)} characters")
        
        # 合并所有输入内容
        content_parts = []
        if user_document:
            content_parts.append(user_document)
        if pdf_text_content:
            content_parts.append(f"--- PDF内容 ---\n\n{pdf_text_content}")
        if image_text_content:
            content_parts.append(f"--- 图片内容 ---\n\n{image_text_content}")
        
        if content_parts:
            combined_document = "\n\n".join(content_parts)
        else:
            combined_document = ""
        
        if not combined_document.strip():
            raise HTTPException(status_code=400, detail="必须提供文字描述、上传PDF文件或上传图片文件")
        
        # 执行工作流（直接传递PDF内容和文件名，避免文件关闭问题）
        result = await workflow.execute(
            user_document=combined_document,
            session_id=session_id,
            user_info=user_info,
            has_outline=has_outline,  # 只使用用户明确勾选的选项
            has_existing_tex=has_existing_tex,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            pdf_content=pdf_content if pdf_file else None,  # 直接传递PDF字节内容
            pdf_filename=pdf_file.filename if pdf_file else None,  # 传递PDF文件名
            username=current_user.username,
            user_id=current_user.id,
            db_session=db
        )
        
        # 结算token使用（在流程结束时扣除用户余额）
        total_tokens = result.get("total_usage", {}).get("total_tokens", 0)
        if total_tokens > 0:
            try:
                settlement = settle_token_usage(
                    db=db,
                    user_id=current_user.id,
                    total_tokens=total_tokens,
                    session_id=session_id
                )
                logger.info(
                    f"Token settlement completed: previous_balance={settlement['previous_balance']}, "
                    f"tokens_used={settlement['tokens_used']}, new_balance={settlement['new_balance']}, "
                    f"is_overdraft={settlement['is_overdraft']}"
                )
            except Exception as e:
                logger.error(f"Failed to settle token usage: {str(e)}")
                # 不抛出异常，允许流程完成
        
        # 转换为响应模型
        return PaperGenerationWorkflowResponse(
            session_id=result["session_id"],
            session_folder=result["session_folder"],
            paper_overview=PaperOverviewResult(
                file_name=result["paper_overview"]["file_name"],
                file_path=result["paper_overview"]["file_path"],
                usage=result["paper_overview"].get("usage")
            ),
            latex_paper=LaTeXPaperResult(
                file_name=result["latex_paper"].get("file_name"),
                file_path=result["latex_paper"].get("file_path"),
                is_skipped=result["latex_paper"]["is_skipped"],
                skip_reason=result["latex_paper"].get("skip_reason"),
                usage=result["latex_paper"].get("usage")
            ),
            requirement_checklist=RequirementChecklistResult(
                file_name=result["requirement_checklist"]["file_name"],
                file_path=result["requirement_checklist"]["file_path"],
                usage=result["requirement_checklist"].get("usage")
            ),
            total_usage=result["total_usage"]
        )
        
    except ValueError as e:
        logger.error(f"Workflow execution error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Workflow execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/execute/stream")
async def execute_workflow_stream(
    request: Request,
    document: Optional[str] = Form(None, description="用户提供的文字描述"),
    pdf_file: Optional[UploadFile] = File(None, description="用户上传的PDF文件"),
    image_files: Optional[List[UploadFile]] = File(None, description="用户上传的图片文件（支持多张）"),
    session_id: Optional[str] = Form(None, description="可选的 session ID"),
    user_info: Optional[str] = Form(None, description="用户提供的额外信息"),
    has_outline: Optional[bool] = Form(False, description="用户是否提供了论文大纲"),
    has_existing_tex: Optional[bool] = Form(False, description="是否存在现有的 .tex 文件"),
    temperature: Optional[float] = Form(None, description="温度参数"),
    max_tokens: Optional[int] = Form(None, description="最大token数"),
    model: Optional[str] = Form(None, description="模型名称"),
    task_id: Optional[str] = Form(None, description="任务ID（如果提供，将在开始执行前更新任务状态）"),
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db),
    workflow: PaperGenerationWorkflow = Depends(get_paper_generation_workflow),
    vision_agent: VisionAgent = Depends(get_vision_agent)
):
    """
    流式执行完整的论文生成工作流（Server-Sent Events）
    
    支持多种输入方式：
    1. 文字描述（document 参数）
    2. PDF文件上传（pdf_file 参数）
    3. 图片文件上传（image_files 参数，支持多张）
    4. 以上可以任意组合提供
    
    按顺序执行：
    1. Paper Overview Agent - 生成论文概览文件
    2. LaTeX Paper Generator Agent - 生成 LaTeX 论文文件（流式）
    3. Requirement Checklist Agent - 生成需求清单文件
    
    所有文件将保存在同一个 session 文件夹中：
    - session/uploaded: 上传的文件（PDF、图片等）
    - session/generated: 生成的文件（概览、LaTeX、清单等）
    流式响应会发送进度更新和日志信息。
    """
    # 在生成器函数外部读取文件内容，避免文件对象被提前关闭
    pdf_content = None
    pdf_filename = None
    image_contents = []  # 存储所有图片的内容和文件名
    
    if pdf_file:
        logger.info("=" * 80)
        logger.info("在生成器外部读取PDF文件...")
        logger.info(f"PDF文件: {pdf_file.filename}")
        logger.info(f"PDF文件对象类型: {type(pdf_file)}")
        logger.info(f"PDF文件对象状态: closed={getattr(pdf_file.file, 'closed', 'unknown')}")
        
        # 验证文件类型
        if not pdf_file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="上传的文件必须是PDF格式")
        
        try:
            # 立即读取文件内容，在文件对象关闭之前
            pdf_filename = pdf_file.filename
            pdf_content = await pdf_file.read()
            logger.info(f"✓ PDF内容读取成功，大小: {len(pdf_content)} 字节")
            logger.info(f"PDF文件名: {pdf_filename}")
            logger.info("=" * 80)
        except Exception as e:
            logger.error(f"读取PDF文件失败: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"读取PDF文件失败: {str(e)}")
    
    # 读取图片文件内容
    if image_files:
        logger.info(f"读取 {len(image_files)} 张图片文件...")
        allowed_image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        
        for idx, image_file in enumerate(image_files):
            try:
                # 验证文件类型
                file_ext = None
                if image_file.filename:
                    for ext in allowed_image_extensions:
                        if image_file.filename.lower().endswith(ext):
                            file_ext = ext
                            break
                
                if not file_ext:
                    logger.warning(f"图片 {idx+1} ({image_file.filename}) 格式不支持，将跳过")
                    continue
                
                image_content = await image_file.read()
                image_contents.append({
                    'filename': image_file.filename or f"image_{idx+1}{file_ext}",
                    'content': image_content,
                    'index': idx + 1
                })
                logger.info(f"✓ 图片 {idx+1} 读取成功: {image_file.filename}, 大小: {len(image_content)} 字节")
            except Exception as e:
                logger.error(f"读取图片 {idx+1} 失败: {str(e)}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    async def generate_sse_stream():
        try:
            # 如果提供了 task_id，先尝试更新任务状态为 running（在检查并发数之前）
            # 这样可以确保状态更新和并发数检查在同一事务中，避免竞态条件
            task_db_obj = None
            if task_id:
                task_db_obj = db.query(Task).filter(
                    Task.id == task_id,
                    Task.user_id == current_user.id
                ).first()
                
                if not task_db_obj:
                    error_chunk = WorkflowProgressChunk(
                        type="error",
                        message=f"任务不存在或无权访问",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    return
                
                # 检查任务状态，只有 pending 状态的任务才能开始执行
                if task_db_obj.status != "pending":
                    error_chunk = WorkflowProgressChunk(
                        type="error",
                        message=f"任务状态为 {task_db_obj.status}，无法开始执行",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    return
            
            # 检查用户当前运行中的workflow数量
            running_workflows_count = db.query(Task).filter(
                Task.user_id == current_user.id,
                Task.status == "running"
            ).count()
            
            max_concurrent = current_user.max_concurrent_workflows or 10
            
            # 如果提供了 task_id，使用原子操作更新任务状态为 running
            # 这样可以确保只有pending状态的任务才能被更新，避免竞态条件
            if task_db_obj:
                # 使用原子操作：只有pending状态的任务才能被更新为running
                # 同时检查并发数限制
                if running_workflows_count >= max_concurrent:
                    error_chunk = WorkflowProgressChunk(
                        type="error",
                        message=f"已达到最大并发数限制（{running_workflows_count}/{max_concurrent}），请等待任务完成后再启动新任务",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    return
                
                # 原子更新：只有pending状态的任务才能被更新为running
                updated_rows = db.query(Task).filter(
                    Task.id == task_id,
                    Task.user_id == current_user.id,
                    Task.status == "pending"
                ).update({
                    "status": "running",
                    "current_step": "正在初始化工作流..."
                }, synchronize_session=False)
                
                if updated_rows == 0:
                    # 任务状态已经不是pending，可能已经被其他请求更新
                    error_chunk = WorkflowProgressChunk(
                        type="error",
                        message=f"任务状态已变更，无法开始执行",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    return
                
                db.commit()
                # 刷新对象以获取最新状态
                db.refresh(task_db_obj)
                logger.info(f"Updated task {task_id} status to running (atomic update)")
            else:
                # 如果没有提供task_id，只检查并发数
                if running_workflows_count >= max_concurrent:
                    error_chunk = WorkflowProgressChunk(
                        type="error",
                        message=f"已达到最大并发数限制（{running_workflows_count}/{max_concurrent}），请等待任务完成后再启动新任务",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    return
            
            logger.info("=" * 80)
            logger.info("开始流式工作流处理")
            logger.info(f"PDF文件: {pdf_filename if pdf_filename else 'None'}")
            logger.info(f"文档内容长度: {len(document) if document else 0}")
            
            # 检查客户端是否断开
            if await request.is_disconnected():
                logger.warning("客户端在开始处理前已断开")
                return
            
            # 创建session文件夹（确保使用同一个session），使用当前用户名
            from app.utils.file_manager import create_session_folder
            session_folder = create_session_folder(session_id, username=current_user.username)
            # 获取实际的 session_id（如果之前是 None，现在会有新生成的 ID）
            actual_session_id = session_folder.name
            logger.info(f"使用 session_folder: {session_folder}, session_id: {actual_session_id}")
            
            # 处理用户输入
            user_document = document or ""
            pdf_text_content = ""
            image_text_content = ""
            has_pdf = False
            
            # 处理PDF文件上传（使用外部读取的内容）
            if pdf_content and pdf_filename:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.warning("客户端已断开，取消PDF处理")
                    return
                
                logger.info(f"使用已读取的PDF文件: {pdf_filename}")
                logger.info(f"PDF内容大小: {len(pdf_content)} 字节")
                has_pdf = True
                
                # 创建临时文件处理PDF
                temp_pdf_path = None
                temp_output_dir = None
                
                try:
                    yield f"data: {WorkflowProgressChunk(type='log', message=f'正在处理PDF文件: {pdf_filename}', done=False).model_dump_json()}\n\n"
                    
                    # 再次检查客户端是否断开
                    if await request.is_disconnected():
                        logger.warning("客户端已断开，取消PDF处理")
                        return
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
                        temp_pdf.write(pdf_content)
                        temp_pdf_path = temp_pdf.name
                    
                    # 创建临时输出目录用于PDF转PNG
                    temp_output_dir = tempfile.mkdtemp(prefix="pdf_pngs_")
                    
                    yield f"data: {WorkflowProgressChunk(type='log', message='正在将PDF转换为图片...', done=False).model_dump_json()}\n\n"
                    
                    # 将PDF转换为PNG
                    png_paths = pdf_to_pngs(
                        pdf_path=temp_pdf_path,
                        output_dir=temp_output_dir,
                        dpi=300
                    )
                    
                    if not png_paths:
                        error_chunk = WorkflowProgressChunk(
                            type="log",
                            message="错误: PDF转PNG失败",
                            done=True
                        )
                        yield f"data: {error_chunk.model_dump_json()}\n\n"
                        return
                    
                    yield f"data: {WorkflowProgressChunk(type='log', message=f'PDF已转换为 {len(png_paths)} 张图片，正在提取文字...', done=False).model_dump_json()}\n\n"
                    
                    # 提取文字内容
                    text_prompt = "请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
                    
                    async def process_single_page(idx: int, png_path: str) -> Tuple[int, str, dict]:
                        try:
                            result = await vision_agent.extract_text_from_image(
                                image=png_path,
                                text_prompt=text_prompt,
                                temperature=0.3,
                                max_tokens=4096,
                                model=None
                            )
                            return (idx, result["response"], result.get("usage", {}))
                        except Exception as e:
                            logger.error(f"Error processing page {idx}: {str(e)}")
                            return (idx, f"[页面 {idx} 处理失败: {str(e)}]", {})
                    
                    # 并发处理所有页面
                    tasks = [process_single_page(idx, png_path) for idx, png_path in enumerate(png_paths, 1)]
                    results = await asyncio.gather(*tasks)
                    results.sort(key=lambda x: x[0])
                    
                    # 拼接所有页面的文字内容并汇总 token 使用量
                    page_descriptions = [result[1] for result in results]
                    pdf_text_content = "\n\n".join(page_descriptions)
                    
                    # 汇总所有页面的 token 使用量
                    total_pdf_usage = {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": 0
                    }
                    for result in results:
                        usage = result[2] if len(result) > 2 else {}
                        if usage:
                            total_pdf_usage["input_tokens"] += usage.get("input_tokens", 0)
                            total_pdf_usage["output_tokens"] += usage.get("output_tokens", 0)
                            total_pdf_usage["total_tokens"] += usage.get("total_tokens", 0)
                    
                    # 记录 PDF 处理的 token 使用
                    if total_pdf_usage["total_tokens"] > 0:
                        try:
                            model_name = None  # vision agent 会使用默认模型
                            record_usage_from_dict(
                                db=db,
                                user_id=current_user.id,
                                usage_dict={
                                    "prompt_tokens": total_pdf_usage["input_tokens"],
                                    "completion_tokens": total_pdf_usage["output_tokens"],
                                    "total_tokens": total_pdf_usage["total_tokens"]
                                },
                                model=model_name,
                                stage="pdf_processing",
                                session_id=actual_session_id
                            )
                            logger.info(f"Recorded PDF processing token usage (stream): {total_pdf_usage['total_tokens']} tokens")
                        except Exception as e:
                            logger.error(f"Failed to record PDF processing token usage (stream): {str(e)}")
                    
                    yield f"data: {WorkflowProgressChunk(type='log', message=f'✓ PDF文字提取完成，共 {len(pdf_text_content)} 字符', done=False).model_dump_json()}\n\n"
                    
                finally:
                    # 清理临时文件
                    import os
                    if temp_pdf_path and os.path.exists(temp_pdf_path):
                        try:
                            os.unlink(temp_pdf_path)
                        except:
                            pass
                    if temp_output_dir and os.path.exists(temp_output_dir):
                        try:
                            import shutil
                            shutil.rmtree(temp_output_dir)
                        except:
                            pass
            
            # 处理图片文件上传（使用外部读取的内容）
            if image_contents:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    logger.warning("客户端已断开，取消图片处理")
                    return
                
                yield f"data: {WorkflowProgressChunk(type='log', message=f'正在处理 {len(image_contents)} 张图片...', done=False).model_dump_json()}\n\n"
                
                text_prompt = "请直接输出图片中的所有文字内容、图表、表格、公式等，不要添加任何描述、说明或解释。保持原有的结构和格式信息。"
                
                async def process_single_image_stream(img_data: dict) -> Tuple[int, str, str, dict]:
                    """处理单张图片（流式版本）"""
                    try:
                        idx = img_data['index']
                        filename = img_data['filename']
                        image_content = img_data['content']
                        
                        # 检查客户端是否断开
                        if await request.is_disconnected():
                            logger.warning(f"客户端已断开，取消图片 {idx} 的处理")
                            raise asyncio.CancelledError("客户端已断开连接")
                        
                        # 保存图片到session文件夹
                        image_path = save_uploaded_file(
                            session_folder=session_folder,
                            file_name=filename,
                            content=image_content
                        )
                        
                        logger.info(f"Processing image {idx}/{len(image_contents)}: {filename}")
                        
                        # 再次检查客户端是否断开
                        if await request.is_disconnected():
                            logger.warning(f"客户端已断开，取消图片 {idx} 的 OCR 处理")
                            raise asyncio.CancelledError("客户端已断开连接")
                        
                        # 使用 Vision Agent 提取文字
                        result = await vision_agent.extract_text_from_image(
                            image=image_path,
                            text_prompt=text_prompt,
                            temperature=0.3,
                            max_tokens=4096,
                            model=None
                        )
                        
                        extracted_text = result["response"]
                        usage = result.get("usage", {})
                        logger.info(f"Image {idx} processed. Text length: {len(extracted_text)} characters")
                        
                        return (idx, extracted_text, filename, usage)
                        
                    except asyncio.CancelledError:
                        logger.info(f"图片 {idx} 处理被取消（客户端断开）")
                        raise
                    except Exception as e:
                        logger.error(f"Error processing image {idx}: {str(e)}")
                        return (idx, f"[图片 {idx} 处理失败: {str(e)}]", filename, {})
                
                # 并发处理所有图片，使用 asyncio.Task 以便可以取消
                image_tasks = [
                    asyncio.create_task(process_single_image_stream(img_data)) 
                    for img_data in image_contents
                ]
                
                try:
                    # 等待所有任务完成，但如果客户端断开则取消
                    image_results = await asyncio.gather(*image_tasks, return_exceptions=True)
                    
                    # 检查是否有客户端断开的情况
                    if await request.is_disconnected():
                        logger.warning("客户端已断开，取消剩余的图片处理任务")
                        # 取消所有未完成的任务
                        for task in image_tasks:
                            if not task.done():
                                task.cancel()
                        raise asyncio.CancelledError("客户端已断开连接")
                    
                    # 处理结果，过滤掉异常
                    valid_results = []
                    for result in image_results:
                        if isinstance(result, Exception):
                            if isinstance(result, asyncio.CancelledError):
                                logger.info("部分图片处理被取消")
                                continue
                            logger.error(f"图片处理异常: {result}")
                            continue
                        valid_results.append(result)
                    
                    image_results = valid_results
                    image_results.sort(key=lambda x: x[0])
                    
                except asyncio.CancelledError:
                    logger.info("图片处理被取消（客户端断开）")
                    # 取消所有任务
                    for task in image_tasks:
                        if not task.done():
                            task.cancel()
                    # 等待任务取消完成
                    await asyncio.gather(*image_tasks, return_exceptions=True)
                    raise
                
                # 拼接所有图片的文字内容并汇总 token 使用量
                image_texts = []
                total_image_usage = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                }
                for result in image_results:
                    idx = result[0]
                    text = result[1] if len(result) > 1 else ""
                    filename = result[2] if len(result) > 2 else ""
                    usage = result[3] if len(result) > 3 else {}
                    
                    if text:
                        image_texts.append(f"--- 图片 {idx}: {filename} ---\n\n{text}")
                    
                    # 累计 token 使用量
                    if usage:
                        total_image_usage["input_tokens"] += usage.get("input_tokens", 0)
                        total_image_usage["output_tokens"] += usage.get("output_tokens", 0)
                        total_image_usage["total_tokens"] += usage.get("total_tokens", 0)
                
                # 记录图片处理的 token 使用
                if total_image_usage["total_tokens"] > 0:
                    try:
                        model_name = None  # vision agent 会使用默认模型
                        record_usage_from_dict(
                            db=db,
                            user_id=current_user.id,
                            usage_dict={
                                "prompt_tokens": total_image_usage["input_tokens"],
                                "completion_tokens": total_image_usage["output_tokens"],
                                "total_tokens": total_image_usage["total_tokens"]
                            },
                            model=model_name,
                            stage="image_processing",
                            session_id=actual_session_id
                        )
                        logger.info(f"Recorded image processing token usage (stream): {total_image_usage['total_tokens']} tokens")
                    except Exception as e:
                        logger.error(f"Failed to record image processing token usage (stream): {str(e)}")
                
                if image_texts:
                    image_text_content = "\n\n".join(image_texts)
                    yield f"data: {WorkflowProgressChunk(type='log', message=f'✓ 图片文字提取完成，共 {len(image_text_content)} 字符', done=False).model_dump_json()}\n\n"
            
            # 合并所有输入内容
            content_parts = []
            if user_document:
                content_parts.append(user_document)
            if pdf_text_content:
                content_parts.append(f"--- PDF内容 ---\n\n{pdf_text_content}")
            if image_text_content:
                content_parts.append(f"--- 图片内容 ---\n\n{image_text_content}")
            
            if content_parts:
                combined_document = "\n\n".join(content_parts)
            else:
                combined_document = ""
            
            if not combined_document.strip():
                error_chunk = WorkflowProgressChunk(
                    type="log",
                    message="错误: 必须提供文字描述、上传PDF文件或上传图片文件",
                    done=True
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
                return
            
            # 执行工作流（直接传递PDF内容和文件名，避免文件关闭问题）
            logger.info("准备调用工作流execute_stream方法...")
            logger.info(f"PDF内容是否可用: {pdf_content is not None}")
            logger.info(f"PDF文件名: {pdf_filename}")
            logger.info(f"合并后文档长度: {len(combined_document)}")
            
            try:
                # 使用实际的 session_id，确保使用同一个 session_folder
                final_result = None
                async for progress_chunk in workflow.execute_stream(
                    user_document=combined_document,
                    session_id=actual_session_id,  # 使用实际创建的 session_id
                    user_info=user_info,
                    has_outline=has_outline,  # 只使用用户明确勾选的选项
                    has_existing_tex=has_existing_tex,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model,
                    pdf_content=pdf_content,  # 直接传递PDF字节内容
                    pdf_filename=pdf_filename,  # 传递PDF文件名
                    username=current_user.username,
                    user_id=current_user.id,
                    db_session=db
                ):
                    # 保存最终结果用于token结算
                    if progress_chunk.done and progress_chunk.result:
                        final_result = progress_chunk.result
                    
                    # 转换为 JSON 并发送 SSE 格式
                    yield f"data: {progress_chunk.model_dump_json()}\n\n"
                
                # 在流式执行完成后结算token
                if final_result and final_result.total_usage:
                    total_tokens = final_result.total_usage.get("total_tokens", 0)
                    if total_tokens > 0:
                        try:
                            settlement = settle_token_usage(
                                db=db,
                                user_id=current_user.id,
                                total_tokens=total_tokens,
                                session_id=actual_session_id
                            )
                            logger.info(
                                f"Token settlement completed (stream): previous_balance={settlement['previous_balance']}, "
                                f"tokens_used={settlement['tokens_used']}, new_balance={settlement['new_balance']}, "
                                f"is_overdraft={settlement['is_overdraft']}"
                            )
                        except Exception as e:
                            logger.error(f"Failed to settle token usage (stream): {str(e)}")
                            # 不抛出异常，允许流程完成
                
                # 如果提供了 task_id，更新任务状态为 completed
                if task_db_obj and final_result:
                    try:
                        from datetime import datetime
                        task_db_obj.status = "completed"
                        task_db_obj.completed_at = datetime.now()
                        task_db_obj.result_data = final_result.model_dump() if hasattr(final_result, 'model_dump') else final_result
                        task_db_obj.current_step = "工作流执行完成"
                        db.commit()
                        logger.info(f"Updated task {task_id} status to completed")
                    except Exception as e:
                        logger.error(f"Failed to update task status to completed: {str(e)}")
                        db.rollback()
            except asyncio.CancelledError:
                logger.info("工作流执行被取消（客户端断开）")
                # 如果提供了 task_id，更新任务状态为 failed
                if task_db_obj:
                    try:
                        task_db_obj.status = "failed"
                        task_db_obj.error = "工作流执行被取消（客户端断开）"
                        task_db_obj.current_step = "已取消"
                        db.commit()
                        logger.info(f"Updated task {task_id} status to failed (cancelled)")
                    except Exception as e:
                        logger.error(f"Failed to update task status to failed: {str(e)}")
                        db.rollback()
                # 不发送错误消息，直接返回
                return
            except Exception as e:
                logger.error(f"工作流执行过程中出错: {str(e)}")
                logger.error(f"错误类型: {type(e).__name__}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                # 如果提供了 task_id，更新任务状态为 failed
                if task_db_obj:
                    try:
                        task_db_obj.status = "failed"
                        task_db_obj.error = str(e)
                        task_db_obj.current_step = f"执行错误: {str(e)}"
                        db.commit()
                        logger.info(f"Updated task {task_id} status to failed")
                    except Exception as update_error:
                        logger.error(f"Failed to update task status to failed: {str(update_error)}")
                        db.rollback()
                # 检查客户端是否仍然连接
                try:
                    if not await request.is_disconnected():
                        error_chunk = WorkflowProgressChunk(
                            type="log",
                            message=f"工作流执行错误: {str(e)}",
                            done=True
                        )
                        yield f"data: {error_chunk.model_dump_json()}\n\n"
                except:
                    pass
                return
        except asyncio.CancelledError:
            logger.info("工作流流式处理被取消（客户端断开）")
            # 如果提供了 task_id，更新任务状态为 failed
            if task_db_obj:
                try:
                    task_db_obj.status = "failed"
                    task_db_obj.error = "工作流执行被取消（客户端断开）"
                    task_db_obj.current_step = "已取消"
                    db.commit()
                    logger.info(f"Updated task {task_id} status to failed (cancelled)")
                except Exception as e:
                    logger.error(f"Failed to update task status to failed: {str(e)}")
                    db.rollback()
            # 不发送错误消息，直接返回
            return
        except Exception as e:
            logger.error("=" * 80)
            logger.error(f"Workflow streaming error: {str(e)}")
            logger.error(f"错误类型: {type(e).__name__}")
            import traceback
            logger.error(f"完整错误堆栈:\n{traceback.format_exc()}")
            logger.error("=" * 80)
            # 如果提供了 task_id，更新任务状态为 failed
            if task_db_obj:
                try:
                    task_db_obj.status = "failed"
                    task_db_obj.error = str(e)
                    task_db_obj.current_step = f"执行错误: {str(e)}"
                    db.commit()
                    logger.info(f"Updated task {task_id} status to failed")
                except Exception as update_error:
                    logger.error(f"Failed to update task status to failed: {str(update_error)}")
                    db.rollback()
            # 检查客户端是否仍然连接，如果已断开则不发送错误消息
            try:
                if not await request.is_disconnected():
                    error_chunk = WorkflowProgressChunk(
                        type="log",
                        message=f"错误: {str(e)}",
                        done=True
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
            except:
                # 如果检查连接状态时出错，说明客户端已断开，直接返回
                pass
    
    return StreamingResponse(
        generate_sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
        }
    )


@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    列出 session 文件夹及其信息
    
    普通用户只能看到自己的 session，管理员可以看到所有 session
    
    Returns:
        session 列表，每个元素包含：
        - session_id: session ID（文件夹名称，可能包含用户名路径）
        - created_at: 创建时间
        - size: 文件夹大小（字节）
        - file_count: 文件数量
    """
    try:
        # 在线程池中执行列表操作，避免阻塞
        loop = asyncio.get_event_loop()
        # 如果是管理员，可以查看所有 session；否则只查看自己的
        username = None if current_user.is_admin else current_user.username
        sessions = await loop.run_in_executor(None, list_all_sessions, username)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(e)}")


@router.delete("/session")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    删除指定的 session 文件夹及其所有内容
    
    普通用户只能删除自己的 session，管理员可以删除任何 session
    
    Args:
        session_id: session ID（文件夹名称，可能包含用户名路径，如 "username/session_xxx"）
        
    Returns:
        删除结果
    """
    import asyncio
    try:
        # 权限检查：如果不是管理员，确保只能删除自己的 session
        if not current_user.is_admin:
            # 解析 session_id，检查是否属于当前用户
            if '/' in session_id:
                parts = session_id.split('/', 1)
                session_username = parts[0]
                if session_username != current_user.username:
                    raise HTTPException(
                        status_code=403,
                        detail="无权删除其他用户的 session"
                    )
            # 如果 session_id 不包含用户名路径，使用当前用户名
            username = current_user.username
        else:
            # 管理员可以删除任何 session
            username = None
        
        # 在线程池中执行删除操作，避免阻塞
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, delete_session_folder, session_id, username)
        
        if success:
            return {"success": True, "message": f"Session {session_id} deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to delete session {session_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")


@router.get("/session")
async def get_session_details_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取指定session的详细信息，包括artifact、uploaded文件列表、generated文件内容
    
    普通用户只能查看自己的session，管理员可以查看任何session
    
    Args:
        session_id: session ID（可能包含用户名路径，如 "username/session_xxx"）
        
    Returns:
        session详细信息，包含：
        - artifacts: artifact文件列表及其内容
        - uploaded_files: 上传的文件列表（文件名和大小）
        - generated_files: generated文件列表及其内容
    """
    try:
        # 权限检查：如果不是管理员，确保只能查看自己的session
        if not current_user.is_admin:
            # 解析 session_id，检查是否属于当前用户
            if '/' in session_id:
                parts = session_id.split('/', 1)
                session_username = parts[0]
                if session_username != current_user.username:
                    raise HTTPException(
                        status_code=403,
                        detail="无权访问其他用户的 session"
                    )
            # 如果 session_id 不包含用户名路径，使用当前用户名
            username = current_user.username
        else:
            # 管理员可以查看任何 session
            username = None
        
        # 在线程池中执行获取操作，避免阻塞
        loop = asyncio.get_event_loop()
        details = await loop.run_in_executor(None, get_session_details, session_id, username)
        
        if details is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        return details
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session details for {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting session details: {str(e)}")


@router.get("/session/download")
async def download_file(
    session_id: str,
    file_name: str,
    file_type: str = "uploaded",  # uploaded, generated, or artifact
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    下载session中的文件（支持uploaded、generated、artifact三种类型）
    
    普通用户只能下载自己session中的文件，管理员可以下载任何文件
    
    Args:
        session_id: session ID（可能包含用户名路径，如 "username/session_xxx"）
        file_name: 要下载的文件名
        file_type: 文件类型，可选值：uploaded, generated, artifact（默认为uploaded）
        
    Returns:
        文件内容
    """
    try:
        # 权限检查：如果不是管理员，确保只能下载自己session中的文件
        if not current_user.is_admin:
            # 解析 session_id，检查是否属于当前用户
            if '/' in session_id:
                parts = session_id.split('/', 1)
                session_username = parts[0]
                if session_username != current_user.username:
                    raise HTTPException(
                        status_code=403,
                        detail="无权下载其他用户的文件"
                    )
            # 如果 session_id 不包含用户名路径，使用当前用户名
            username = current_user.username
        else:
            # 管理员可以下载任何文件
            username = None
        
        # 获取session文件夹路径
        session_folder = get_session_folder_path(session_id, username)
        if not session_folder:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        # 根据文件类型确定文件夹和文件名
        if file_type == "artifact":
            # artifact文件是JSON格式，需要添加.json后缀
            if not file_name.endswith('.json'):
                file_name = f"{file_name}.json"
            folder_name = "artifact"
        elif file_type == "generated":
            folder_name = "generated"
        elif file_type == "uploaded":
            folder_name = "uploaded"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file_type: {file_type}. Must be one of: uploaded, generated, artifact"
            )
        
        # 构建文件路径
        file_path = session_folder / folder_name / file_name
        
        # 安全检查：确保文件在指定文件夹内（防止路径遍历攻击）
        try:
            file_path.resolve().relative_to((session_folder / folder_name).resolve())
        except ValueError:
            raise HTTPException(
                status_code=403,
                detail="Invalid file path"
            )
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"File {file_name} not found in {file_type} folder of session {session_id}"
            )
        
        # 确定媒体类型
        if file_type == "artifact" or file_name.endswith('.json'):
            media_type = 'application/json'
        elif file_name.endswith('.tex'):
            media_type = 'application/x-tex'
        elif file_name.endswith('.md'):
            media_type = 'text/markdown'
        elif file_name.endswith('.txt'):
            media_type = 'text/plain'
        else:
            media_type = 'application/octet-stream'
        
        # 返回文件
        return FileResponse(
            path=str(file_path),
            filename=file_name,
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {file_name} ({file_type}) from session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {str(e)}")

