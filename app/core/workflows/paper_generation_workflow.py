"""论文生成工作流 - 整合三个 Agent"""
from typing import Dict, Any, Optional, AsyncIterator
from pathlib import Path
from fastapi import UploadFile
from app.core.agents.paper_overview_agent import PaperOverviewAgent
from app.core.agents.latex_paper_generator_agent import LaTeXPaperGeneratorAgent
from app.core.agents.requirement_checklist_agent import RequirementChecklistAgent
from app.core.schemas import WorkflowProgressChunk, PaperGenerationWorkflowResponse, PaperOverviewResult, LaTeXPaperResult, RequirementChecklistResult
from app.utils.file_manager import create_session_folder, save_file, get_file_path, save_uploaded_file, save_artifact
from app.utils.token_tracker import record_usage_from_dict
from app.utils.logger import logger


class PaperGenerationWorkflow:
    """论文生成工作流 - 按顺序执行三个 Agent"""
    
    def __init__(
        self,
        paper_overview_agent: PaperOverviewAgent,
        latex_paper_agent: LaTeXPaperGeneratorAgent,
        requirement_checklist_agent: RequirementChecklistAgent
    ):
        self.paper_overview_agent = paper_overview_agent
        self.latex_paper_agent = latex_paper_agent
        self.requirement_checklist_agent = requirement_checklist_agent
    
    async def execute(
        self,
        user_document: str,
        session_id: Optional[str] = None,
        user_info: Optional[str] = None,
        has_outline: bool = False,
        has_existing_tex: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        pdf_file: Optional[UploadFile] = None,
        pdf_content: Optional[bytes] = None,
        pdf_filename: Optional[str] = None,
        username: Optional[str] = None,
        user_id: Optional[str] = None,
        db_session = None
    ) -> Dict[str, Any]:
        """
        执行完整的工作流
        
        Args:
            user_document: 用户提供的文档内容
            session_id: 可选的 session ID，如果不提供则自动生成
            user_info: 用户提供的额外信息（用于 LaTeX 生成）
            has_outline: 用户是否提供了论文大纲
            has_existing_tex: 是否存在现有的 .tex 文件
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            {
                "session_id": str,
                "session_folder": str,
                "paper_overview": {
                    "file_name": str,
                    "file_path": str,
                    "usage": dict
                },
                "latex_paper": {
                    "file_name": str or None,
                    "file_path": str or None,
                    "is_skipped": bool,
                    "skip_reason": str or None,
                    "usage": dict
                },
                "requirement_checklist": {
                    "file_name": str,
                    "file_path": str,
                    "usage": dict
                },
                "total_usage": dict
            }
        """
        # 1. 创建 session 文件夹
        session_folder = create_session_folder(session_id, username=username)
        session_id = session_folder.name
        
        logger.info("=" * 80)
        logger.info(f"Starting Paper Generation Workflow - Session: {session_id}")
        logger.info("=" * 80)
        
        # 1.1 保存上传的PDF文件（如果有）
        if pdf_content and pdf_filename:
            # 优先使用直接传递的PDF内容（避免文件关闭问题）
            try:
                pdf_file_path = save_uploaded_file(
                    session_folder=session_folder,
                    file_name=pdf_filename,
                    content=pdf_content
                )
                logger.info(f"✓ PDF file saved: {pdf_file_path}")
                
                # 注意：has_outline 由用户在前端明确选择，不再自动设置
                # 如果用户勾选了"PDF为大纲/初稿"，has_outline 为 True，将跳过 LaTeX 生成
                if has_outline:
                    logger.info("用户已选择PDF为大纲/初稿（将跳过 LaTeX 生成）")
            except Exception as e:
                logger.error(f"Failed to save PDF file: {str(e)}")
        elif pdf_file:
            # 兼容旧的接口：从UploadFile读取
            try:
                file_content = await pdf_file.read()
                pdf_file_path = save_uploaded_file(
                    session_folder=session_folder,
                    file_name=pdf_file.filename or "uploaded.pdf",
                    content=file_content
                )
                logger.info(f"✓ PDF file saved: {pdf_file_path}")
                
                # 注意：has_outline 由用户在前端明确选择，不再自动设置
                # 如果用户勾选了"PDF为大纲/初稿"，has_outline 为 True，将跳过 LaTeX 生成
                if has_outline:
                    logger.info("用户已选择PDF为大纲/初稿（将跳过 LaTeX 生成）")
            except Exception as e:
                logger.error(f"Failed to save PDF file: {str(e)}")
        
        # 1.2 检查是否存在 .tex 文件
        if not has_existing_tex:
            # 检查 session 文件夹中是否有 .tex 文件
            tex_files = list(session_folder.glob("*.tex"))
            if not tex_files:
                # 检查 uploaded 和 generated 子文件夹
                uploaded_folder = session_folder / "uploaded"
                generated_folder = session_folder / "generated"
                if uploaded_folder.exists():
                    tex_files.extend(uploaded_folder.glob("*.tex"))
                if generated_folder.exists():
                    tex_files.extend(generated_folder.glob("*.tex"))
            
            if tex_files:
                has_existing_tex = True
                logger.info(f"已存在 .tex 文件（将跳过 LaTeX 生成）: {tex_files[0].name}")
        
        results = {
            "session_id": session_id,
            "session_folder": str(session_folder),
            "paper_overview": {},
            "latex_paper": {},
            "requirement_checklist": {},
            "total_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        # 2. Agent 1: 生成论文概览
        logger.info("Step 1: Generating paper overview...")
        try:
            overview_result = await self.paper_overview_agent.generate_overview(
                user_document=user_document,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            # 检查结果是否有效
            if overview_result is None:
                error_msg = "Paper overview generation returned None. Check agent logs for details."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            if not isinstance(overview_result, dict) or "file_name" not in overview_result or "file_content" not in overview_result:
                error_msg = f"Invalid overview_result format: {type(overview_result)}. Expected dict with 'file_name' and 'file_content'."
                logger.error(error_msg)
                logger.error(f"overview_result content: {overview_result}")
                raise ValueError(error_msg)
            
            # 保存文件到 generated 文件夹
            file_path = get_file_path(session_folder, overview_result["file_name"], subfolder="generated")
            save_file(file_path, overview_result["file_content"])
            
            results["paper_overview"] = {
                "file_name": overview_result["file_name"],
                "file_path": str(file_path),
                "usage": overview_result.get("usage", {})
            }
            
            # 保存 artifact
            save_artifact(
                session_folder=session_folder,
                stage_name="paper_overview",
                artifact_data={
                    "stage": "paper_overview",
                    "input": {
                        "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "model": model
                    },
                    "output": {
                        "file_name": overview_result["file_name"],
                        "file_path": str(file_path),
                        "usage": overview_result.get("usage", {})
                    }
                }
            )
            
            # 累计使用情况
            if overview_result.get("usage"):
                results["total_usage"]["prompt_tokens"] += overview_result["usage"].get("prompt_tokens", 0)
                results["total_usage"]["completion_tokens"] += overview_result["usage"].get("completion_tokens", 0)
                results["total_usage"]["total_tokens"] += overview_result["usage"].get("total_tokens", 0)
            
            logger.info(f"✓ Paper overview generated: {overview_result['file_name']}")
            
        except Exception as e:
            logger.error(f"✗ Paper overview generation failed: {str(e)}")
            raise
        
        # 3. Agent 2: 生成 LaTeX 论文
        logger.info("Step 2: Generating LaTeX paper...")
        try:
            latex_result = await self.latex_paper_agent.generate_latex_paper(
                paper_overview=overview_result["file_content"],
                user_document=user_document,
                user_info=user_info,
                has_outline=has_outline,
                has_existing_tex=has_existing_tex,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            if not latex_result["is_skipped"]:
                # 保存文件到 generated 文件夹
                file_path = get_file_path(session_folder, latex_result["file_name"], subfolder="generated")
                save_file(file_path, latex_result["file_content"])
                
                results["latex_paper"] = {
                    "file_name": latex_result["file_name"],
                    "file_path": str(file_path),
                    "is_skipped": False,
                    "skip_reason": None,
                    "usage": latex_result.get("usage", {})
                }
                
                # 保存 artifact
                save_artifact(
                    session_folder=session_folder,
                    stage_name="latex_paper",
                    artifact_data={
                        "stage": "latex_paper",
                        "input": {
                            "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                            "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                            "user_info": user_info[:500] + "..." if user_info and len(user_info) > 500 else user_info,
                            "has_outline": has_outline,
                            "has_existing_tex": has_existing_tex,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "model": model
                        },
                        "output": {
                            "file_name": latex_result["file_name"],
                            "file_path": str(file_path),
                            "usage": latex_result.get("usage", {})
                        }
                    }
                )
                
                # 累计使用情况
                if latex_result.get("usage"):
                    results["total_usage"]["prompt_tokens"] += latex_result["usage"].get("prompt_tokens", 0)
                    results["total_usage"]["completion_tokens"] += latex_result["usage"].get("completion_tokens", 0)
                    results["total_usage"]["total_tokens"] += latex_result["usage"].get("total_tokens", 0)
                    
                    # 记录 token 使用到数据库
                    if user_id and db_session:
                        try:
                            record_usage_from_dict(
                                db=db_session,
                                user_id=user_id,
                                usage_dict=latex_result["usage"],
                                model=model,
                                stage="latex_paper",
                                session_id=session_id
                            )
                        except Exception as e:
                            logger.error(f"Failed to record token usage for latex_paper: {str(e)}")
                
                logger.info(f"✓ LaTeX paper generated: {latex_result['file_name']}")
            else:
                results["latex_paper"] = {
                    "file_name": None,
                    "file_path": None,
                    "is_skipped": True,
                    "skip_reason": latex_result.get("skip_reason", "Unknown"),
                    "usage": latex_result.get("usage", {})
                }
                
                # 保存 artifact（即使跳过也保存）
                save_artifact(
                    session_folder=session_folder,
                    stage_name="latex_paper",
                    artifact_data={
                        "stage": "latex_paper",
                        "input": {
                            "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                            "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                            "user_info": user_info[:500] + "..." if user_info and len(user_info) > 500 else user_info,
                            "has_outline": has_outline,
                            "has_existing_tex": has_existing_tex,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "model": model
                        },
                        "output": {
                            "is_skipped": True,
                            "skip_reason": latex_result.get("skip_reason", "Unknown"),
                            "usage": latex_result.get("usage", {})
                        }
                    }
                )
                
                # 累计使用情况（即使跳过也可能有少量 token 使用）
                if latex_result.get("usage"):
                    results["total_usage"]["prompt_tokens"] += latex_result["usage"].get("prompt_tokens", 0)
                    results["total_usage"]["completion_tokens"] += latex_result["usage"].get("completion_tokens", 0)
                    results["total_usage"]["total_tokens"] += latex_result["usage"].get("total_tokens", 0)
                    
                    # 记录 token 使用到数据库
                    if user_id and db_session:
                        try:
                            record_usage_from_dict(
                                db=db_session,
                                user_id=user_id,
                                usage_dict=latex_result["usage"],
                                model=model,
                                stage="latex_paper",
                                session_id=session_id
                            )
                        except Exception as e:
                            logger.error(f"Failed to record token usage for latex_paper (skipped): {str(e)}")
                
                logger.info(f"⊘ LaTeX paper generation skipped: {latex_result.get('skip_reason', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"✗ LaTeX paper generation failed: {str(e)}")
            raise
        
        # 4. Agent 3: 生成需求清单
        logger.info("Step 3: Generating requirement checklist...")
        try:
            # 如果 LaTeX 生成被跳过，使用用户原始输入
            latex_content = None
            user_original_input = None
            
            if not latex_result["is_skipped"]:
                latex_content = latex_result["file_content"]
            else:
                user_original_input = user_document
            
            checklist_result = await self.requirement_checklist_agent.generate_requirement_checklist(
                paper_overview=overview_result["file_content"],
                latex_content=latex_content,
                user_original_input=user_original_input,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            # 保存文件到 generated 文件夹
            file_path = get_file_path(session_folder, checklist_result["file_name"], subfolder="generated")
            save_file(file_path, checklist_result["file_content"])
            
            results["requirement_checklist"] = {
                "file_name": checklist_result["file_name"],
                "file_path": str(file_path),
                "usage": checklist_result.get("usage", {})
            }
            
            # 保存 artifact
            save_artifact(
                session_folder=session_folder,
                stage_name="requirement_checklist",
                artifact_data={
                    "stage": "requirement_checklist",
                    "input": {
                        "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                        "latex_content": latex_content[:1000] + "..." if latex_content and len(latex_content) > 1000 else latex_content,
                        "user_original_input": user_original_input[:1000] + "..." if user_original_input and len(user_original_input) > 1000 else user_original_input,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "model": model
                    },
                    "output": {
                        "file_name": checklist_result["file_name"],
                        "file_path": str(file_path),
                        "usage": checklist_result.get("usage", {})
                    }
                }
            )
            
            # 累计使用情况
            if checklist_result.get("usage"):
                results["total_usage"]["prompt_tokens"] += checklist_result["usage"].get("prompt_tokens", 0)
                results["total_usage"]["completion_tokens"] += checklist_result["usage"].get("completion_tokens", 0)
                results["total_usage"]["total_tokens"] += checklist_result["usage"].get("total_tokens", 0)
                
                # 记录 token 使用到数据库
                if user_id and db_session:
                    try:
                        record_usage_from_dict(
                            db=db_session,
                            user_id=user_id,
                            usage_dict=checklist_result["usage"],
                            model=model,
                            stage="requirement_checklist",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to record token usage for requirement_checklist: {str(e)}")
            
            logger.info(f"✓ Requirement checklist generated: {checklist_result['file_name']}")
            
        except Exception as e:
            logger.error(f"✗ Requirement checklist generation failed: {str(e)}")
            raise
        
        logger.info("=" * 80)
        logger.info(f"Workflow completed successfully - Session: {session_id}")
        logger.info(f"Total tokens used: {results['total_usage']['total_tokens']}")
        logger.info(f"Session folder: {session_folder}")
        logger.info("=" * 80)
        
        return results
    
    async def execute_stream(
        self,
        user_document: str,
        session_id: Optional[str] = None,
        user_info: Optional[str] = None,
        has_outline: bool = False,
        has_existing_tex: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        pdf_file: Optional[UploadFile] = None,
        pdf_content: Optional[bytes] = None,
        pdf_filename: Optional[str] = None,
        username: Optional[str] = None,
        user_id: Optional[str] = None,
        db_session = None
    ) -> AsyncIterator[WorkflowProgressChunk]:
        """
        流式执行完整的工作流，发送进度更新和日志
        
        Yields:
            WorkflowProgressChunk: 进度更新块
        """
        # 1. 创建 session 文件夹
        session_folder = create_session_folder(session_id, username=username)
        session_id = session_folder.name
        
        yield WorkflowProgressChunk(
            type="progress",
            step=0,
            step_name="初始化",
            message=f"正在初始化工作流，Session ID: {session_id}",
            done=False
        )
        
        # 1.1 保存上传的PDF文件（如果有）
        logger.info("检查PDF文件参数...")
        logger.info(f"pdf_content is None: {pdf_content is None}")
        logger.info(f"pdf_filename: {pdf_filename}")
        logger.info(f"pdf_file is None: {pdf_file is None}")
        
        if pdf_content and pdf_filename:
            # 优先使用直接传递的PDF内容（避免文件关闭问题）
            logger.info(f"使用直接传递的PDF内容保存文件: {pdf_filename}, 大小: {len(pdf_content)} 字节")
            try:
                pdf_file_path = save_uploaded_file(
                    session_folder=session_folder,
                    file_name=pdf_filename,
                    content=pdf_content
                )
                logger.info(f"✓ PDF文件保存成功: {pdf_file_path}")
                yield WorkflowProgressChunk(
                    type="log",
                    message=f"✓ PDF文件已保存: {pdf_filename}",
                    done=False
                )
                
                # 注意：has_outline 由用户在前端明确选择，不再自动设置
                # 如果用户勾选了"PDF为大纲/初稿"，has_outline 为 True，将跳过 LaTeX 生成
                if has_outline:
                    yield WorkflowProgressChunk(
                        type="log",
                        message="用户已选择PDF为大纲/初稿（将跳过 LaTeX 生成）",
                        done=False
                    )
            except Exception as e:
                logger.error(f"保存PDF文件失败: {str(e)}")
                logger.error(f"错误类型: {type(e).__name__}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                yield WorkflowProgressChunk(
                    type="log",
                    message=f"保存PDF文件失败: {str(e)}",
                    done=False
                )
        elif pdf_file:
            # 兼容旧的接口：从UploadFile读取
            logger.info(f"从UploadFile读取PDF内容: {pdf_file.filename}")
            logger.info(f"UploadFile对象类型: {type(pdf_file)}")
            logger.info(f"UploadFile文件对象状态: closed={getattr(pdf_file.file, 'closed', 'unknown')}")
            try:
                file_content = await pdf_file.read()
                logger.info(f"✓ 从UploadFile读取成功，大小: {len(file_content)} 字节")
                pdf_file_path = save_uploaded_file(
                    session_folder=session_folder,
                    file_name=pdf_file.filename or "uploaded.pdf",
                    content=file_content
                )
                logger.info(f"✓ PDF文件保存成功: {pdf_file_path}")
                yield WorkflowProgressChunk(
                    type="log",
                    message=f"✓ PDF文件已保存: {pdf_file.filename}",
                    done=False
                )
                
                # 注意：has_outline 由用户在前端明确选择，不再自动设置
                # 如果用户勾选了"PDF为大纲/初稿"，has_outline 为 True，将跳过 LaTeX 生成
                if has_outline:
                    yield WorkflowProgressChunk(
                        type="log",
                        message="用户已选择PDF为大纲/初稿（将跳过 LaTeX 生成）",
                        done=False
                    )
            except Exception as e:
                logger.error(f"从UploadFile读取或保存PDF文件失败: {str(e)}")
                logger.error(f"错误类型: {type(e).__name__}")
                import traceback
                logger.error(f"错误堆栈: {traceback.format_exc()}")
                yield WorkflowProgressChunk(
                    type="log",
                    message=f"保存PDF文件失败: {str(e)}",
                    done=False
                )
        else:
            logger.info("没有PDF文件需要保存")
        
        # 1.2 检查是否存在 .tex 文件
        if not has_existing_tex:
            # 检查 session 文件夹中是否有 .tex 文件
            tex_files = list(session_folder.glob("*.tex"))
            if not tex_files:
                # 检查 uploaded 和 generated 子文件夹
                uploaded_folder = session_folder / "uploaded"
                generated_folder = session_folder / "generated"
                if uploaded_folder.exists():
                    tex_files.extend(uploaded_folder.glob("*.tex"))
                if generated_folder.exists():
                    tex_files.extend(generated_folder.glob("*.tex"))
            
            if tex_files:
                has_existing_tex = True
                yield WorkflowProgressChunk(
                    type="log",
                    message=f"已存在 .tex 文件（将跳过 LaTeX 生成）: {tex_files[0].name}",
                    done=False
                )
        
        results = {
            "session_id": session_id,
            "session_folder": str(session_folder),
            "paper_overview": {},
            "latex_paper": {},
            "requirement_checklist": {},
            "total_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        # 2. Agent 1: 生成论文概览
        yield WorkflowProgressChunk(
            type="progress",
            step=1,
            step_name="生成论文概览",
            message="步骤 1/3: 正在生成论文概览...",
            done=False
        )
        
        try:
            overview_result = await self.paper_overview_agent.generate_overview(
                user_document=user_document,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            # 检查结果是否有效
            if overview_result is None:
                error_msg = "Paper overview generation returned None. Check agent logs for details."
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            if not isinstance(overview_result, dict) or "file_name" not in overview_result or "file_content" not in overview_result:
                error_msg = f"Invalid overview_result format: {type(overview_result)}. Expected dict with 'file_name' and 'file_content'."
                logger.error(error_msg)
                logger.error(f"overview_result content: {overview_result}")
                raise ValueError(error_msg)
            
            # 保存文件到 generated 文件夹
            file_path = get_file_path(session_folder, overview_result["file_name"], subfolder="generated")
            save_file(file_path, overview_result["file_content"])
            
            results["paper_overview"] = {
                "file_name": overview_result["file_name"],
                "file_path": str(file_path),
                "usage": overview_result.get("usage", {})
            }
            
            # 保存 artifact
            save_artifact(
                session_folder=session_folder,
                stage_name="paper_overview",
                artifact_data={
                    "stage": "paper_overview",
                    "input": {
                        "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "model": model
                    },
                    "output": {
                        "file_name": overview_result["file_name"],
                        "file_path": str(file_path),
                        "usage": overview_result.get("usage", {})
                    }
                }
            )
            
            # 累计使用情况
            if overview_result.get("usage"):
                results["total_usage"]["prompt_tokens"] += overview_result["usage"].get("prompt_tokens", 0)
                results["total_usage"]["completion_tokens"] += overview_result["usage"].get("completion_tokens", 0)
                results["total_usage"]["total_tokens"] += overview_result["usage"].get("total_tokens", 0)
                
                # 记录 token 使用到数据库（流式版本）
                if user_id and db_session:
                    try:
                        record_usage_from_dict(
                            db=db_session,
                            user_id=user_id,
                            usage_dict=overview_result["usage"],
                            model=model,
                            stage="paper_overview",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to record token usage for paper_overview (stream): {str(e)}")
            
            yield WorkflowProgressChunk(
                type="progress",
                step=1,
                step_name="生成论文概览",
                message=f"✓ 论文概览生成完成: {overview_result['file_name']}",
                done=False
            )
            
        except Exception as e:
            logger.error(f"✗ Paper overview generation failed: {str(e)}")
            yield WorkflowProgressChunk(
                type="log",
                message=f"错误: 论文概览生成失败: {str(e)}",
                done=True
            )
            raise
        
        # 3. Agent 2: 生成 LaTeX 论文
        yield WorkflowProgressChunk(
            type="progress",
            step=2,
            step_name="生成 LaTeX 论文",
            message="步骤 2/3: 正在生成 LaTeX 论文...",
            done=False
        )
        
        try:
            # 检查是否需要跳过
            if has_outline or has_existing_tex:
                skip_reason = "用户已提供论文大纲" if has_outline else "已存在 .tex 文件"
                results["latex_paper"] = {
                    "file_name": None,
                    "file_path": None,
                    "is_skipped": True,
                    "skip_reason": skip_reason,
                    "usage": {}
                }
                
                # 保存 artifact（即使跳过也保存）
                save_artifact(
                    session_folder=session_folder,
                    stage_name="latex_paper",
                    artifact_data={
                        "stage": "latex_paper",
                        "input": {
                            "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                            "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                            "user_info": user_info[:500] + "..." if user_info and len(user_info) > 500 else user_info,
                            "has_outline": has_outline,
                            "has_existing_tex": has_existing_tex,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "model": model
                        },
                        "output": {
                            "is_skipped": True,
                            "skip_reason": skip_reason,
                            "usage": {}
                        }
                    }
                )
                
                yield WorkflowProgressChunk(
                    type="progress",
                    step=2,
                    step_name="生成 LaTeX 论文",
                    message=f"⊘ LaTeX 论文生成已跳过: {skip_reason}",
                    done=False
                )
            else:
                # 使用流式生成 LaTeX 论文
                yield WorkflowProgressChunk(
                    type="log",
                    log="开始流式生成 LaTeX 论文内容...",
                    done=False
                )
                
                accumulated_latex = ""
                latex_usage = None
                
                async for chunk in self.latex_paper_agent.generate_latex_paper_stream(
                    paper_overview=overview_result["file_content"],
                    user_document=user_document,
                    user_info=user_info,
                    has_outline=False,  # 已经检查过了
                    has_existing_tex=False,  # 已经检查过了
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model
                ):
                    if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                        delta = chunk.choices[0].delta
                        
                        # 提取内容并转发日志
                        if delta and hasattr(delta, 'content') and delta.content:
                            content = delta.content
                            accumulated_latex += content
                            # 发送日志块（显示生成进度）
                            yield WorkflowProgressChunk(
                                type="log",
                                log=content,
                                done=False
                            )
                        
                        # 检查是否完成并提取使用情况
                        if chunk.choices[0].finish_reason:
                            if hasattr(chunk, 'usage') and chunk.usage:
                                latex_usage = {
                                    "prompt_tokens": chunk.usage.prompt_tokens,
                                    "completion_tokens": chunk.usage.completion_tokens,
                                    "total_tokens": chunk.usage.total_tokens
                                }
                                logger.info(f"LaTeX paper token usage: {latex_usage}")
                        # 也检查是否有独立的 usage 字段（某些情况下可能在非最后一个chunk中）
                        if hasattr(chunk, 'usage') and chunk.usage and not latex_usage:
                            latex_usage = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens
                            }
                            logger.info(f"LaTeX paper token usage (from chunk): {latex_usage}")
                
                # 解析 LaTeX 内容
                latex_result = {
                    "file_content": accumulated_latex,
                    "raw_response": accumulated_latex,
                    "usage": latex_usage or {}
                }
                
                # 记录 token 使用到数据库
                if latex_usage and user_id and db_session:
                    try:
                        record_usage_from_dict(
                            db=db_session,
                            user_id=user_id,
                            usage_dict=latex_usage,
                            model=model,
                            stage="latex_paper",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to record token usage for latex_paper (stream): {str(e)}")
                
                # 尝试提取文件名和内容
                import re
                path_pattern = r'```path\s*\n?(.*?)\n?```'
                latex_pattern = r'```latex\s*\n?(.*?)\n?```'
                
                path_match = re.search(path_pattern, accumulated_latex, re.DOTALL)
                latex_match = re.search(latex_pattern, accumulated_latex, re.DOTALL)
                
                if path_match and latex_match:
                    latex_result["file_name"] = path_match.group(1).strip()
                    latex_result["file_content"] = latex_match.group(1).strip()
                else:
                    # 如果没有找到，使用默认文件名
                    latex_result["file_name"] = "paper_framework.tex"
                    # 尝试提取任何代码块
                    code_block_pattern = r'```\w*\s*\n?(.*?)```'
                    code_match = re.search(code_block_pattern, accumulated_latex, re.DOTALL)
                    if code_match:
                        latex_result["file_content"] = code_match.group(1).strip()
                
                # 保存文件到 generated 文件夹
                file_path = get_file_path(session_folder, latex_result["file_name"], subfolder="generated")
                save_file(file_path, latex_result["file_content"])
                
                results["latex_paper"] = {
                    "file_name": latex_result["file_name"],
                    "file_path": str(file_path),
                    "is_skipped": False,
                    "skip_reason": None,
                    "usage": latex_result.get("usage", {})
                }
                
                # 保存 artifact
                save_artifact(
                    session_folder=session_folder,
                    stage_name="latex_paper",
                    artifact_data={
                        "stage": "latex_paper",
                        "input": {
                            "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                            "user_document": user_document[:1000] + "..." if len(user_document) > 1000 else user_document,
                            "user_info": user_info[:500] + "..." if user_info and len(user_info) > 500 else user_info,
                            "has_outline": has_outline,
                            "has_existing_tex": has_existing_tex,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "model": model
                        },
                        "output": {
                            "file_name": latex_result["file_name"],
                            "file_path": str(file_path),
                            "usage": latex_result.get("usage", {})
                        }
                    }
                )
                
                # 累计使用情况
                if latex_result.get("usage"):
                    results["total_usage"]["prompt_tokens"] += latex_result["usage"].get("prompt_tokens", 0)
                    results["total_usage"]["completion_tokens"] += latex_result["usage"].get("completion_tokens", 0)
                    results["total_usage"]["total_tokens"] += latex_result["usage"].get("total_tokens", 0)
                
                yield WorkflowProgressChunk(
                    type="progress",
                    step=2,
                    step_name="生成 LaTeX 论文",
                    message=f"✓ LaTeX 论文生成完成: {latex_result['file_name']}",
                    done=False
                )
            
        except Exception as e:
            logger.error(f"✗ LaTeX paper generation failed: {str(e)}")
            yield WorkflowProgressChunk(
                type="log",
                message=f"错误: LaTeX 论文生成失败: {str(e)}",
                done=False
            )
            raise
        
        # 4. Agent 3: 生成需求清单
        yield WorkflowProgressChunk(
            type="progress",
            step=3,
            step_name="生成需求清单",
            message="步骤 3/3: 正在生成需求清单...",
            done=False
        )
        
        try:
            # 如果 LaTeX 生成被跳过，使用用户原始输入
            latex_content = None
            user_original_input = None
            
            if not results["latex_paper"].get("is_skipped", True):
                # 从保存的文件读取内容
                latex_file_path = results["latex_paper"]["file_path"]
                if latex_file_path:
                    with open(latex_file_path, 'r', encoding='utf-8') as f:
                        latex_content = f.read()
            else:
                user_original_input = user_document
            
            checklist_result = await self.requirement_checklist_agent.generate_requirement_checklist(
                paper_overview=overview_result["file_content"],
                latex_content=latex_content,
                user_original_input=user_original_input,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            # 保存文件到 generated 文件夹
            file_path = get_file_path(session_folder, checklist_result["file_name"], subfolder="generated")
            save_file(file_path, checklist_result["file_content"])
            
            results["requirement_checklist"] = {
                "file_name": checklist_result["file_name"],
                "file_path": str(file_path),
                "usage": checklist_result.get("usage", {})
            }
            
            # 保存 artifact
            save_artifact(
                session_folder=session_folder,
                stage_name="requirement_checklist",
                artifact_data={
                    "stage": "requirement_checklist",
                    "input": {
                        "paper_overview": overview_result["file_content"][:1000] + "..." if len(overview_result["file_content"]) > 1000 else overview_result["file_content"],
                        "latex_content": latex_content[:1000] + "..." if latex_content and len(latex_content) > 1000 else latex_content,
                        "user_original_input": user_original_input[:1000] + "..." if user_original_input and len(user_original_input) > 1000 else user_original_input,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "model": model
                    },
                    "output": {
                        "file_name": checklist_result["file_name"],
                        "file_path": str(file_path),
                        "usage": checklist_result.get("usage", {})
                    }
                }
            )
            
            # 累计使用情况
            if checklist_result.get("usage"):
                results["total_usage"]["prompt_tokens"] += checklist_result["usage"].get("prompt_tokens", 0)
                results["total_usage"]["completion_tokens"] += checklist_result["usage"].get("completion_tokens", 0)
                results["total_usage"]["total_tokens"] += checklist_result["usage"].get("total_tokens", 0)
                
                # 记录 token 使用到数据库
                if user_id and db_session:
                    try:
                        record_usage_from_dict(
                            db=db_session,
                            user_id=user_id,
                            usage_dict=checklist_result["usage"],
                            model=model,
                            stage="requirement_checklist",
                            session_id=session_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to record token usage for requirement_checklist (stream): {str(e)}")
            
            yield WorkflowProgressChunk(
                type="progress",
                step=3,
                step_name="生成需求清单",
                message=f"✓ 需求清单生成完成: {checklist_result['file_name']}",
                done=False
            )
            
        except Exception as e:
            logger.error(f"✗ Requirement checklist generation failed: {str(e)}")
            yield WorkflowProgressChunk(
                type="log",
                message=f"错误: 需求清单生成失败: {str(e)}",
                done=False
            )
            raise
        
        # 5. 发送最终结果
        final_response = PaperGenerationWorkflowResponse(
            session_id=results["session_id"],
            session_folder=results["session_folder"],
            paper_overview=PaperOverviewResult(
                file_name=results["paper_overview"]["file_name"],
                file_path=results["paper_overview"]["file_path"],
                usage=results["paper_overview"].get("usage")
            ),
            latex_paper=LaTeXPaperResult(
                file_name=results["latex_paper"].get("file_name"),
                file_path=results["latex_paper"].get("file_path"),
                is_skipped=results["latex_paper"]["is_skipped"],
                skip_reason=results["latex_paper"].get("skip_reason"),
                usage=results["latex_paper"].get("usage")
            ),
            requirement_checklist=RequirementChecklistResult(
                file_name=results["requirement_checklist"]["file_name"],
                file_path=results["requirement_checklist"]["file_path"],
                usage=results["requirement_checklist"].get("usage")
            ),
            total_usage=results["total_usage"]
        )
        
        yield WorkflowProgressChunk(
            type="result",
            step=3,
            step_name="完成",
            message="工作流执行完成！",
            done=True,
            result=final_response
        )

