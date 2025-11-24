from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class Message(BaseModel):
    """消息模型"""
    role: str = Field(..., description="消息角色: system, user, assistant")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息")
    conversation_id: Optional[str] = Field(None, description="会话ID，用于多轮对话")
    messages: Optional[List[Message]] = Field(None, description="历史消息列表")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(2000, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    response: str = Field(..., description="AI回复")
    conversation_id: str = Field(..., description="会话ID")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class StreamChunk(BaseModel):
    """流式数据块模型"""
    chunk: str = Field(..., description="数据块内容")
    done: bool = Field(False, description="是否完成")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况（仅在done=True时）")


class PaperOverviewRequest(BaseModel):
    """论文概览生成请求模型"""
    document: str = Field(..., description="用户提供的文档内容")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(4000, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class PaperOverviewResponse(BaseModel):
    """论文概览生成响应模型"""
    file_name: str = Field(..., description="生成的文件名")
    file_content: str = Field(..., description="文件内容")
    raw_response: str = Field(..., description="原始响应（包含markdown格式）")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class LaTeXPaperRequest(BaseModel):
    """LaTeX 论文生成请求模型"""
    paper_overview: str = Field(..., description="从 Paper Overview Agent 得到的文本内容")
    user_info: Optional[str] = Field(None, description="用户提供的额外信息")
    has_outline: Optional[bool] = Field(False, description="用户是否提供了论文大纲")
    has_existing_tex: Optional[bool] = Field(False, description="是否存在现有的 .tex 文件")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(16000, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class LaTeXPaperResponse(BaseModel):
    """LaTeX 论文生成响应模型"""
    file_name: Optional[str] = Field(None, description="生成的文件名（如果跳过则为None）")
    file_content: Optional[str] = Field(None, description="文件内容（如果跳过则为None）")
    raw_response: str = Field(..., description="原始响应（包含markdown格式）")
    is_skipped: bool = Field(..., description="是否跳过生成")
    skip_reason: Optional[str] = Field(None, description="跳过原因（如果跳过）")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class RequirementChecklistRequest(BaseModel):
    """需求清单生成请求模型"""
    paper_overview: str = Field(..., description="从 Paper Overview Agent 得到的文本内容")
    latex_content: Optional[str] = Field(None, description="从 LaTeX Paper Generator Agent 得到的 LaTeX 内容（如果 Agent 2 没有跳过）")
    user_original_input: Optional[str] = Field(None, description="用户原始输入（如果 Agent 2 SKIPPED 则使用此输入）")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(4000, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class RequirementChecklistResponse(BaseModel):
    """需求清单生成响应模型"""
    file_name: str = Field(..., description="生成的文件名")
    file_content: str = Field(..., description="文件内容")
    raw_response: str = Field(..., description="原始响应（包含markdown格式）")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class PaperGenerationWorkflowRequest(BaseModel):
    """论文生成工作流请求模型"""
    document: str = Field(..., description="用户提供的文档内容")
    session_id: Optional[str] = Field(None, description="可选的 session ID，如果不提供则自动生成")
    user_info: Optional[str] = Field(None, description="用户提供的额外信息（用于 LaTeX 生成）")
    has_outline: Optional[bool] = Field(False, description="用户是否提供了论文大纲")
    has_existing_tex: Optional[bool] = Field(False, description="是否存在现有的 .tex 文件")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class PaperOverviewResult(BaseModel):
    """论文概览结果模型"""
    file_name: str = Field(..., description="生成的文件名")
    file_path: str = Field(..., description="文件保存路径")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class LaTeXPaperResult(BaseModel):
    """LaTeX 论文结果模型"""
    file_name: Optional[str] = Field(None, description="生成的文件名（如果跳过则为None）")
    file_path: Optional[str] = Field(None, description="文件保存路径（如果跳过则为None）")
    is_skipped: bool = Field(..., description="是否跳过生成")
    skip_reason: Optional[str] = Field(None, description="跳过原因（如果跳过）")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class RequirementChecklistResult(BaseModel):
    """需求清单结果模型"""
    file_name: str = Field(..., description="生成的文件名")
    file_path: str = Field(..., description="文件保存路径")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")


class PaperGenerationWorkflowResponse(BaseModel):
    """论文生成工作流响应模型"""
    session_id: str = Field(..., description="Session ID")
    session_folder: str = Field(..., description="Session 文件夹路径")
    paper_overview: PaperOverviewResult = Field(..., description="论文概览结果")
    latex_paper: LaTeXPaperResult = Field(..., description="LaTeX 论文结果")
    requirement_checklist: RequirementChecklistResult = Field(..., description="需求清单结果")
    total_usage: Dict[str, Any] = Field(..., description="总 Token 使用情况")


class WorkflowProgressChunk(BaseModel):
    """工作流进度块模型"""
    type: str = Field(..., description="类型: progress, log, result")
    step: Optional[int] = Field(None, description="当前步骤 (1-3)")
    step_name: Optional[str] = Field(None, description="步骤名称")
    message: Optional[str] = Field(None, description="进度消息")
    log: Optional[str] = Field(None, description="日志内容（用于流式日志）")
    done: bool = Field(False, description="是否完成")
    result: Optional[PaperGenerationWorkflowResponse] = Field(None, description="最终结果（仅在done=True时）")


class VisionAnalysisRequest(BaseModel):
    """图片分析请求模型"""
    images: List[str] = Field(..., description="图片列表，可以是 base64 编码的字符串或文件路径")
    text_prompt: Optional[str] = Field(None, description="可选的文本提示或问题")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(4096, ge=1, description="最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")


class VisionAnalysisResponse(BaseModel):
    """图片分析响应模型"""
    response: str = Field(..., description="分析结果文本")
    usage: Optional[Dict[str, Any]] = Field(None, description="Token使用情况")
    raw_response: str = Field(..., description="原始响应（与response相同）")


class PDFProcessRequest(BaseModel):
    """PDF 处理请求模型"""
    text_prompt: Optional[str] = Field(
        None,
        description="可选的文本提示，用于指导图片分析。如果不提供，将使用默认提示来提取文字描述"
    )
    temperature: Optional[float] = Field(0.3, ge=0, le=2, description="温度参数，OCR 建议使用较低温度")
    max_tokens: Optional[int] = Field(4096, ge=1, description="每页的最大token数")
    model: Optional[str] = Field(None, description="模型名称，覆盖默认配置")
    dpi: Optional[int] = Field(300, ge=72, le=600, description="PDF 转 PNG 的 DPI 分辨率")


class PDFProcessResponse(BaseModel):
    """PDF 处理响应模型"""
    response: str = Field(..., description="拼接后的完整文字描述")
    page_count: int = Field(..., description="PDF 总页数")
    page_descriptions: List[str] = Field(..., description="每页的文字描述列表")
    total_usage: Dict[str, Any] = Field(..., description="总 Token 使用情况（所有页面的累计）")
    raw_response: str = Field(..., description="原始响应（与response相同）")


# 工作流任务相关的 schemas
class FileInfo(BaseModel):
    """文件信息模型"""
    name: str = Field(..., description="文件名")
    size: int = Field(..., description="文件大小（字节）")
    type: str = Field(..., description="文件类型")


class WorkflowTaskCreate(BaseModel):
    """创建工作流任务请求模型"""
    name: Optional[str] = Field(None, description="任务名称")
    document: Optional[str] = Field(None, description="文档内容")
    user_info: Optional[str] = Field(None, description="用户信息")
    session_id: Optional[str] = Field(None, description="Session ID")
    has_outline: Optional[bool] = Field(False, description="是否有大纲")
    has_existing_tex: Optional[bool] = Field(False, description="是否有现有tex文件")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大token数")


class WorkflowTaskUpdate(BaseModel):
    """更新工作流任务请求模型"""
    name: Optional[str] = Field(None, description="任务名称")
    document: Optional[str] = Field(None, description="文档内容")
    user_info: Optional[str] = Field(None, description="用户信息")
    session_id: Optional[str] = Field(None, description="Session ID")
    status: Optional[str] = Field(None, description="任务状态")
    has_outline: Optional[bool] = Field(None, description="是否有大纲")
    has_existing_tex: Optional[bool] = Field(None, description="是否有现有tex文件")
    temperature: Optional[float] = Field(None, description="温度参数")
    max_tokens: Optional[int] = Field(None, description="最大token数")
    error: Optional[str] = Field(None, description="错误信息")
    current_step: Optional[str] = Field(None, description="当前步骤")
    logs: Optional[List[str]] = Field(None, description="日志列表")
    response: Optional[PaperGenerationWorkflowResponse] = Field(None, description="工作流响应结果")
    pdf_file_info: Optional[FileInfo] = Field(None, description="PDF文件信息")
    image_files_info: Optional[List[FileInfo]] = Field(None, description="图片文件信息列表")


class WorkflowTaskResponse(BaseModel):
    """工作流任务响应模型"""
    id: str = Field(..., description="任务ID")
    task_id: str = Field(..., description="任务标识符")
    name: Optional[str] = Field(None, description="任务名称")
    status: str = Field(..., description="任务状态")
    document: Optional[str] = Field(None, description="文档内容")
    user_info: Optional[str] = Field(None, description="用户信息")
    session_id: Optional[str] = Field(None, description="Session ID")
    has_outline: bool = Field(False, description="是否有大纲")
    has_existing_tex: bool = Field(False, description="是否有现有tex文件")
    temperature: Optional[str] = Field(None, description="温度参数")
    max_tokens: Optional[str] = Field(None, description="最大token数")
    error: Optional[str] = Field(None, description="错误信息")
    current_step: Optional[str] = Field(None, description="当前步骤")
    logs: Optional[List[str]] = Field(None, description="日志列表")
    response: Optional[PaperGenerationWorkflowResponse] = Field(None, description="工作流响应结果")
    pdf_file_info: Optional[FileInfo] = Field(None, description="PDF文件信息")
    image_files_info: Optional[List[FileInfo]] = Field(None, description="图片文件信息列表")
    created_at: str = Field(..., description="创建时间（ISO格式）")
    updated_at: str = Field(..., description="更新时间（ISO格式）")
    completed_at: Optional[str] = Field(None, description="完成时间（ISO格式）")
    
    class Config:
        from_attributes = True

