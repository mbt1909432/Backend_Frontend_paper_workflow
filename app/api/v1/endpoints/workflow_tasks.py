"""工作流任务管理 API 端点"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.db.models import Task, User
from app.api.deps_auth import get_current_backend_user
from app.core.schemas import (
    WorkflowTaskCreate,
    WorkflowTaskUpdate,
    WorkflowTaskResponse
)
from app.utils.logger import logger
import uuid
from datetime import datetime

router = APIRouter()


def generate_task_id() -> str:
    """生成任务ID"""
    return f"task_{int(datetime.now().timestamp() * 1000)}_{uuid.uuid4().hex[:9]}"


@router.get("/", response_model=List[WorkflowTaskResponse])
async def list_tasks(
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取当前用户的所有工作流任务
    
    普通用户只能看到自己的任务，管理员可以看到所有任务
    """
    try:
        if current_user.is_admin:
            # 管理员可以看到所有任务
            tasks = db.query(Task).order_by(Task.created_at.desc()).all()
        else:
            # 普通用户只能看到自己的任务
            tasks = db.query(Task).filter(
                Task.user_id == current_user.id
            ).order_by(Task.created_at.desc()).all()
        
        result = []
        for task in tasks:
            # 获取 session_id 字符串（如果存在关联的 Session）
            session_id_str = None
            if task.session_id:
                from app.db.models import Session
                session = db.query(Session).filter(Session.id == task.session_id).first()
                if session:
                    session_id_str = session.session_id
            
            # 转换数据库模型为响应模型
            task_dict = {
                "id": task.id,
                "task_id": task.task_id,
                "name": task.name,
                "status": task.status,
                "document": task.document,
                "user_info": task.user_info,
                "session_id": session_id_str,  # 使用 Session 的 session_id 字符串
                "has_outline": task.has_outline,
                "has_existing_tex": task.has_existing_tex,
                "temperature": task.temperature,
                "max_tokens": task.max_tokens,
                "error": task.error,
                "current_step": task.current_step,
                "logs": task.logs if task.logs else [],
                "response": task.result_data if task.result_data else None,
                "pdf_file_info": task.pdf_file_info,
                "image_files_info": task.image_files_info if task.image_files_info else [],
                "created_at": task.created_at.isoformat() if task.created_at else "",
                "updated_at": task.updated_at.isoformat() if task.updated_at else "",
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            result.append(WorkflowTaskResponse(**task_dict))
        
        return result
    except Exception as e:
        logger.error(f"Error listing tasks: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}"
        )


@router.get("/{task_id}", response_model=WorkflowTaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    获取指定任务详情
    
    普通用户只能获取自己的任务，管理员可以获取任何任务
    """
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )
        
        # 权限检查
        if not current_user.is_admin and task.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此任务"
            )
        
        # 获取 session_id 字符串（如果存在关联的 Session）
        session_id_str = None
        if task.session_id:
            from app.db.models import Session
            session = db.query(Session).filter(Session.id == task.session_id).first()
            if session:
                session_id_str = session.session_id
        
        task_dict = {
            "id": task.id,
            "task_id": task.task_id,
            "name": task.name,
            "status": task.status,
            "document": task.document,
            "user_info": task.user_info,
            "session_id": session_id_str,  # 使用 Session 的 session_id 字符串
            "has_outline": task.has_outline,
            "has_existing_tex": task.has_existing_tex,
            "temperature": task.temperature,
            "max_tokens": task.max_tokens,
            "error": task.error,
            "current_step": task.current_step,
            "logs": task.logs if task.logs else [],
            "response": task.result_data if task.result_data else None,
            "pdf_file_info": task.pdf_file_info,
            "image_files_info": task.image_files_info if task.image_files_info else [],
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        
        return WorkflowTaskResponse(**task_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务失败: {str(e)}"
        )


@router.post("/", response_model=WorkflowTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: WorkflowTaskCreate,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    创建新的工作流任务
    """
    try:
        # 检查并发数限制
        running_tasks_count = db.query(Task).filter(
            Task.user_id == current_user.id,
            Task.status == "running"
        ).count()
        
        max_concurrent = current_user.max_concurrent_workflows or 10
        if running_tasks_count >= max_concurrent:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"已达到最大并发数限制（{running_tasks_count}/{max_concurrent}），请等待任务完成后再启动新任务"
            )
        
        task_id = generate_task_id()
        
        # 生成默认任务名称
        if not task_data.name:
            # 计算任务序号
            existing_count = db.query(Task).filter(
                Task.user_id == current_user.id
            ).count()
            task_data.name = f"任务 {existing_count + 1}"
        
        # 如果提供了 session_id，尝试查找对应的 Session 对象
        session_db_id = None
        if task_data.session_id:
            from app.db.models import Session
            session = db.query(Session).filter(Session.session_id == task_data.session_id).first()
            if session:
                session_db_id = session.id
        
        task = Task(
            task_id=task_id,
            user_id=current_user.id,
            name=task_data.name,
            document=task_data.document or "",
            user_info=task_data.user_info or "",
            session_id=session_db_id,  # 使用 Session 的数据库 ID，而不是字符串
            has_outline=task_data.has_outline or False,
            has_existing_tex=task_data.has_existing_tex or False,
            status="pending",
            temperature=str(task_data.temperature) if task_data.temperature is not None else None,
            max_tokens=str(task_data.max_tokens) if task_data.max_tokens is not None else None,
            logs=[],
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        logger.info(f"Created task {task.id} for user {current_user.username}")
        
        # 获取 session_id 字符串（如果存在关联的 Session）
        session_id_str = None
        if task.session_id:
            from app.db.models import Session
            session = db.query(Session).filter(Session.id == task.session_id).first()
            if session:
                session_id_str = session.session_id
        
        task_dict = {
            "id": task.id,
            "task_id": task.task_id,
            "name": task.name,
            "status": task.status,
            "document": task.document,
            "user_info": task.user_info,
            "session_id": session_id_str,  # 使用 Session 的 session_id 字符串
            "has_outline": task.has_outline,
            "has_existing_tex": task.has_existing_tex,
            "temperature": task.temperature,
            "max_tokens": task.max_tokens,
            "error": task.error,
            "current_step": task.current_step,
            "logs": task.logs if task.logs else [],
            "response": task.result_data if task.result_data else None,
            "pdf_file_info": task.pdf_file_info,
            "image_files_info": task.image_files_info if task.image_files_info else [],
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        
        return WorkflowTaskResponse(**task_dict)
    except Exception as e:
        logger.error(f"Error creating task: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建任务失败: {str(e)}"
        )


@router.put("/{task_id}", response_model=WorkflowTaskResponse)
async def update_task(
    task_id: str,
    task_data: WorkflowTaskUpdate,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    更新工作流任务
    
    普通用户只能更新自己的任务，管理员可以更新任何任务
    """
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )
        
        # 权限检查
        if not current_user.is_admin and task.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权更新此任务"
            )
        
        # 更新字段
        if task_data.name is not None:
            task.name = task_data.name
        if task_data.document is not None:
            task.document = task_data.document
        if task_data.user_info is not None:
            task.user_info = task_data.user_info
        if task_data.session_id is not None:
            # 如果提供了 session_id 字符串，查找对应的 Session 对象
            if task_data.session_id:
                from app.db.models import Session
                session = db.query(Session).filter(Session.session_id == task_data.session_id).first()
                if session:
                    task.session_id = session.id
                else:
                    # Session 不存在，设置为 None
                    task.session_id = None
            else:
                # 空字符串，设置为 None
                task.session_id = None
        if task_data.status is not None:
            task.status = task_data.status
        if task_data.has_outline is not None:
            task.has_outline = task_data.has_outline
        if task_data.has_existing_tex is not None:
            task.has_existing_tex = task_data.has_existing_tex
        if task_data.temperature is not None:
            task.temperature = str(task_data.temperature)
        if task_data.max_tokens is not None:
            task.max_tokens = str(task_data.max_tokens)
        if task_data.error is not None:
            task.error = task_data.error
        if task_data.current_step is not None:
            task.current_step = task_data.current_step
        if task_data.logs is not None:
            task.logs = task_data.logs
        if task_data.response is not None:
            task.result_data = task_data.response.model_dump() if hasattr(task_data.response, 'model_dump') else task_data.response
        if task_data.pdf_file_info is not None:
            task.pdf_file_info = task_data.pdf_file_info.model_dump() if hasattr(task_data.pdf_file_info, 'model_dump') else task_data.pdf_file_info
        if task_data.image_files_info is not None:
            task.image_files_info = [info.model_dump() if hasattr(info, 'model_dump') else info for info in task_data.image_files_info]
        
        # 如果状态变为完成，设置完成时间
        if task_data.status == "completed" and not task.completed_at:
            task.completed_at = datetime.now()
        
        db.commit()
        db.refresh(task)
        
        logger.info(f"Updated task {task.id}")
        
        # 获取 session_id 字符串（如果存在关联的 Session）
        session_id_str = None
        if task.session_id:
            from app.db.models import Session
            session = db.query(Session).filter(Session.id == task.session_id).first()
            if session:
                session_id_str = session.session_id
        
        task_dict = {
            "id": task.id,
            "task_id": task.task_id,
            "name": task.name,
            "status": task.status,
            "document": task.document,
            "user_info": task.user_info,
            "session_id": session_id_str,  # 使用 Session 的 session_id 字符串
            "has_outline": task.has_outline,
            "has_existing_tex": task.has_existing_tex,
            "temperature": task.temperature,
            "max_tokens": task.max_tokens,
            "error": task.error,
            "current_step": task.current_step,
            "logs": task.logs if task.logs else [],
            "response": task.result_data if task.result_data else None,
            "pdf_file_info": task.pdf_file_info,
            "image_files_info": task.image_files_info if task.image_files_info else [],
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        
        return WorkflowTaskResponse(**task_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating task: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新任务失败: {str(e)}"
        )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_backend_user),
    db: Session = Depends(get_db)
):
    """
    删除工作流任务
    
    普通用户只能删除自己的任务，管理员可以删除任何任务
    """
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )
        
        # 权限检查
        if not current_user.is_admin and task.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除此任务"
            )
        
        db.delete(task)
        db.commit()
        
        logger.info(f"Deleted task {task_id}")
        
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除任务失败: {str(e)}"
        )

