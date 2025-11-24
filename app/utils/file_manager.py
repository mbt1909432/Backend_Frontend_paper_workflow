"""文件管理工具"""
import os
import json
import errno
import stat
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import uuid
from app.config.settings import settings
from app.utils.logger import logger


def ensure_output_dir() -> Path:
    """确保输出目录存在"""
    output_path = Path(settings.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def ensure_user_output_dir(username: str) -> Path:
    """确保用户输出目录存在"""
    output_dir = ensure_output_dir()
    user_dir = output_dir / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def create_session_folder(session_id: Optional[str] = None, username: Optional[str] = None) -> Path:
    """
    为此次 session 创建新文件夹，包括 uploaded 和 generated 子文件夹
    
    Args:
        session_id: 可选的 session ID，如果不提供则自动生成
        username: 用户名，用于创建用户专属文件夹
        
    Returns:
        session 文件夹路径
    """
    if username:
        # 创建用户专属目录
        user_dir = ensure_user_output_dir(username)
    else:
        # 兼容旧代码：如果没有用户名，使用根目录
        user_dir = ensure_output_dir()
    
    if session_id:
        session_folder = user_dir / session_id
    else:
        # 生成基于时间戳和 UUID 的唯一文件夹名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        session_folder = user_dir / f"session_{timestamp}_{unique_id}"
    
    session_folder.mkdir(parents=True, exist_ok=True)
    
    # 创建 uploaded、generated 和 artifact 子文件夹
    uploaded_folder = session_folder / "uploaded"
    generated_folder = session_folder / "generated"
    artifact_folder = session_folder / "artifact"
    uploaded_folder.mkdir(parents=True, exist_ok=True)
    generated_folder.mkdir(parents=True, exist_ok=True)
    artifact_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created session folder: {session_folder}")
    logger.info(f"Created uploaded folder: {uploaded_folder}")
    logger.info(f"Created generated folder: {generated_folder}")
    logger.info(f"Created artifact folder: {artifact_folder}")
    return session_folder


def save_file(file_path: Path, content: str) -> bool:
    """
    保存文件到指定路径
    
    Args:
        file_path: 文件路径（可以是相对路径或绝对路径）
        content: 文件内容
        
    Returns:
        是否保存成功
    """
    try:
        # 确保父目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"File saved: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save file {file_path}: {str(e)}")
        return False


def get_file_path(session_folder: Path, file_name: str, subfolder: Optional[str] = None) -> Path:
    """
    获取文件在 session 文件夹中的完整路径
    
    Args:
        session_folder: session 文件夹路径
        file_name: 文件名
        subfolder: 子文件夹名称（'uploaded' 或 'generated'），如果为 None 则保存在 session 根目录
        
    Returns:
        完整的文件路径
    """
    if subfolder:
        return session_folder / subfolder / file_name
    return session_folder / file_name


def save_uploaded_file(session_folder: Path, file_name: str, content: bytes) -> Path:
    """
    保存上传的文件到 session/uploaded 文件夹
    
    Args:
        session_folder: session 文件夹路径
        file_name: 文件名
        content: 文件内容（二进制）
        
    Returns:
        保存的文件路径
    """
    logger.info(f"save_uploaded_file 被调用")
    logger.info(f"参数: session_folder={session_folder}, file_name={file_name}")
    logger.info(f"content 类型: {type(content)}, 大小: {len(content) if content else 0} 字节")
    
    uploaded_folder = session_folder / "uploaded"
    uploaded_folder.mkdir(parents=True, exist_ok=True)
    
    file_path = uploaded_folder / file_name
    
    try:
        logger.info(f"准备写入文件: {file_path}")
        with open(file_path, 'wb') as f:
            logger.info(f"文件已打开，准备写入 {len(content)} 字节")
            f.write(content)
            logger.info(f"文件写入完成")
        logger.info(f"✓ Uploaded file saved: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"✗ Failed to save uploaded file {file_path}: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        raise


def save_artifact(session_folder: Path, stage_name: str, artifact_data: Dict[str, Any]) -> Path:
    """
    保存工作流阶段的 artifact（输入输出）到 session/artifact 文件夹
    
    Args:
        session_folder: session 文件夹路径
        stage_name: 阶段名称（如 'paper_overview', 'latex_paper', 'requirement_checklist'）
        artifact_data: 要保存的 artifact 数据（字典格式）
        
    Returns:
        保存的文件路径
    """
    artifact_folder = session_folder / "artifact"
    artifact_folder.mkdir(parents=True, exist_ok=True)
    
    artifact_file = artifact_folder / f"{stage_name}.json"
    
    try:
        # 验证 artifact_data 不为空
        if not artifact_data:
            logger.warning(f"Artifact data is empty for stage {stage_name}, skipping save")
            return artifact_file
        
        # 先写入临时文件，然后重命名，确保原子性
        temp_file = artifact_file.with_suffix('.tmp')
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(artifact_data, f, ensure_ascii=False, indent=2)
            f.flush()  # 确保数据写入磁盘
            os.fsync(f.fileno())  # 强制同步到磁盘
        
        # 验证临时文件不为空
        if temp_file.stat().st_size == 0:
            logger.error(f"Temporary artifact file is empty: {temp_file}")
            temp_file.unlink(missing_ok=True)
            raise ValueError(f"Artifact file would be empty for stage {stage_name}")
        
        # 重命名为最终文件
        temp_file.replace(artifact_file)
        
        # 验证最终文件
        if artifact_file.stat().st_size == 0:
            logger.error(f"Final artifact file is empty: {artifact_file}")
            raise ValueError(f"Artifact file is empty after save for stage {stage_name}")
        
        logger.info(f"✓ Artifact saved: {artifact_file} (size: {artifact_file.stat().st_size} bytes)")
        return artifact_file
    except Exception as e:
        logger.error(f"✗ Failed to save artifact {artifact_file}: {str(e)}")
        logger.error(f"Artifact data type: {type(artifact_data)}, keys: {list(artifact_data.keys()) if isinstance(artifact_data, dict) else 'N/A'}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


def list_all_sessions(username: Optional[str] = None) -> list[Dict[str, Any]]:
    """
    列出 session 文件夹及其信息
    
    Args:
        username: 用户名，如果提供则只列出该用户的 session，否则列出所有（仅管理员）
    
    Returns:
        session 信息列表，每个元素包含：
        - session_id: session ID（文件夹名称，包含用户名路径）
        - created_at: 创建时间（从文件夹名称或修改时间推断）
        - size: 文件夹大小（字节）
        - file_count: 文件数量
    """
    import os
    from datetime import datetime
    
    sessions = []
    
    if username:
        # 只列出指定用户的 session
        user_dir = ensure_user_output_dir(username)
        if not user_dir.exists():
            return sessions
        
        search_dir = user_dir
        prefix = ""  # 用户目录下的 session 不需要前缀
    else:
        # 列出所有用户的 session（管理员功能）
        output_dir = ensure_output_dir()
        if not output_dir.exists():
            return sessions
        
        search_dir = output_dir
        prefix = ""  # 兼容旧格式
    
    # 递归搜索所有 session 文件夹
    for item in search_dir.iterdir():
        if item.is_dir():
            # 检查是否是 session 文件夹（以 session_ 开头或在用户目录下）
            if item.name.startswith('session_') or (username and item.is_dir()):
                try:
                    # 获取文件夹修改时间作为创建时间
                    created_time = datetime.fromtimestamp(item.stat().st_mtime)
                    
                    # 计算文件夹大小和文件数量
                    total_size = 0
                    file_count = 0
                    for root, dirs, files in os.walk(item):
                        for file in files:
                            file_path = Path(root) / file
                            try:
                                total_size += file_path.stat().st_size
                                file_count += 1
                            except (OSError, PermissionError):
                                pass
                    
                    # 构建 session_id：如果是用户目录，包含用户名路径
                    if username:
                        session_id = f"{username}/{item.name}"
                    else:
                        session_id = item.name
                    
                    sessions.append({
                        'session_id': session_id,
                        'created_at': created_time.isoformat(),
                        'size': total_size,
                        'file_count': file_count,
                    })
                except Exception as e:
                    logger.warning(f"Failed to get info for session {item.name}: {str(e)}")
                    continue
    
    # 按创建时间倒序排列（最新的在前）
    sessions.sort(key=lambda x: x['created_at'], reverse=True)
    return sessions


def delete_session_folder(session_id: str, username: Optional[str] = None, max_retries: int = 5, initial_delay: float = 1.0) -> bool:
    """
    删除指定的 session 文件夹及其所有内容
    
    Args:
        session_id: session ID（文件夹名称，可能包含用户名路径，如 "username/session_xxx"）
        username: 用户名，如果 session_id 不包含路径则使用此参数
        max_retries: 最大重试次数（默认5次）
        initial_delay: 初始重试延迟（秒，默认1秒，使用指数退避）
        
    Returns:
        是否删除成功
    """
    import shutil
    import time
    import os
    
    try:
        # 解析 session_id：可能包含用户名路径
        if '/' in session_id:
            # 格式：username/session_xxx
            parts = session_id.split('/', 1)
            username_from_id = parts[0]
            actual_session_id = parts[1]
            user_dir = ensure_user_output_dir(username_from_id)
            session_folder = user_dir / actual_session_id
        elif username:
            # 使用提供的用户名
            user_dir = ensure_user_output_dir(username)
            session_folder = user_dir / session_id
        else:
            # 兼容旧格式：直接在根目录下
            output_dir = ensure_output_dir()
            session_folder = output_dir / session_id
        
        if not session_folder.exists():
            logger.warning(f"Session folder does not exist: {session_folder}")
            return True  # 不存在也算成功
        
        # Windows 上处理文件被占用的情况
        def handle_remove_readonly(func, path, exc):
            """处理只读文件的删除"""
            if exc[1].errno == errno.EACCES:
                # 修改文件权限后重试
                os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                func(path)
            else:
                raise
        
        # 递归删除整个文件夹，使用 onerror 处理 Windows 上的权限问题
        retry_delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                shutil.rmtree(session_folder, onerror=handle_remove_readonly)
                logger.info(f"✓ Session folder deleted: {session_folder} (attempt {attempt + 1})")
                return True
            except (OSError, PermissionError) as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed to delete {session_folder}, "
                        f"retrying in {retry_delay:.1f}s: {str(e)}"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    logger.error(
                        f"✗ Failed to delete session folder after {max_retries} attempts: {str(e)}"
                    )
                    raise
        
        return False
    except Exception as e:
        logger.error(f"✗ Failed to delete session folder {session_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


def get_session_folder_path(session_id: str, username: Optional[str] = None) -> Optional[Path]:
    """
    获取session文件夹路径
    
    Args:
        session_id: session ID（可能包含用户名路径，如 "username/session_xxx"）
        username: 用户名，如果 session_id 不包含路径则使用此参数
        
    Returns:
        session文件夹路径，如果不存在则返回None
    """
    try:
        # 解析 session_id：可能包含用户名路径
        if '/' in session_id:
            # 格式：username/session_xxx
            parts = session_id.split('/', 1)
            username_from_id = parts[0]
            actual_session_id = parts[1]
            user_dir = ensure_user_output_dir(username_from_id)
            session_folder = user_dir / actual_session_id
        elif username:
            # 使用提供的用户名
            user_dir = ensure_user_output_dir(username)
            session_folder = user_dir / session_id
        else:
            # 兼容旧格式：直接在根目录下
            output_dir = ensure_output_dir()
            session_folder = output_dir / session_id
        
        if not session_folder.exists():
            return None
        
        return session_folder
    except Exception as e:
        logger.error(f"Failed to get session folder path for {session_id}: {str(e)}")
        return None


def get_session_details(session_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    获取session的详细信息，包括artifact、uploaded文件列表、generated文件内容
    
    Args:
        session_id: session ID（可能包含用户名路径，如 "username/session_xxx"）
        username: 用户名，如果 session_id 不包含路径则使用此参数
        
    Returns:
        session详细信息字典，包含：
        - artifacts: artifact文件列表及其内容
        - uploaded_files: 上传的文件列表（文件名和大小）
        - generated_files: generated文件列表及其内容
        如果session不存在则返回None
    """
    try:
        session_folder = get_session_folder_path(session_id, username)
        if not session_folder:
            return None
        
        result = {
            "artifacts": {},
            "uploaded_files": [],
            "generated_files": {}
        }
        
        # 读取artifact文件夹中的JSON文件
        artifact_folder = session_folder / "artifact"
        if artifact_folder.exists():
            for artifact_file in artifact_folder.glob("*.json"):
                try:
                    with open(artifact_file, 'r', encoding='utf-8') as f:
                        artifact_data = json.load(f)
                    result["artifacts"][artifact_file.stem] = artifact_data
                except Exception as e:
                    logger.warning(f"Failed to read artifact file {artifact_file}: {str(e)}")
        
        # 读取uploaded文件夹中的文件列表
        uploaded_folder = session_folder / "uploaded"
        if uploaded_folder.exists():
            for uploaded_file in uploaded_folder.iterdir():
                if uploaded_file.is_file():
                    try:
                        file_size = uploaded_file.stat().st_size
                        result["uploaded_files"].append({
                            "name": uploaded_file.name,
                            "size": file_size
                        })
                    except Exception as e:
                        logger.warning(f"Failed to get info for uploaded file {uploaded_file}: {str(e)}")
        
        # 读取generated文件夹中的文件内容
        generated_folder = session_folder / "generated"
        if generated_folder.exists():
            # 常见的generated文件类型
            common_extensions = ['.tex', '.txt', '.md']
            for generated_file in generated_folder.iterdir():
                if generated_file.is_file():
                    try:
                        # 只读取文本文件
                        if generated_file.suffix in common_extensions or generated_file.suffix == '':
                            with open(generated_file, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            result["generated_files"][generated_file.name] = {
                                "content": content,
                                "size": len(content.encode('utf-8'))
                            }
                        else:
                            # 对于其他文件类型，只记录文件名和大小
                            file_size = generated_file.stat().st_size
                            result["generated_files"][generated_file.name] = {
                                "content": None,  # 非文本文件不读取内容
                                "size": file_size,
                                "is_binary": True
                            }
                    except Exception as e:
                        logger.warning(f"Failed to read generated file {generated_file}: {str(e)}")
        
        return result
    except Exception as e:
        logger.error(f"Failed to get session details for {session_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return None

