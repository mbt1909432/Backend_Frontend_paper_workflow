from typing import Dict, Any, Optional, List, Union
import base64
from pathlib import Path
from app.services.anthropic_service import AnthropicService
from app.utils.logger import logger


class VisionAgent:
    """Vision Agent - 使用 Anthropic Claude 进行图片识别和多模态分析"""
    
    SYSTEM_PROMPT = """You are a specialized vision agent that extracts content from images.

## Your Task

Extract and output ONLY the actual content from images. Do NOT add any:
- Descriptions or explanations
- Analysis or interpretations
- Comments or observations
- Context or insights
- Additional information beyond what is directly visible

## Guidelines

- For text content (OCR): Output ONLY the text exactly as it appears in the image
- For images with text: Transcribe the text verbatim, preserving structure and formatting
- For academic content: Extract ONLY the content (text, formulas, tables, etc.) without analysis
- Do NOT add phrases like "This image shows...", "I can see...", "The image contains..."
- Do NOT provide summaries or interpretations
- Output raw content only, nothing else"""

    def __init__(self, anthropic_service: AnthropicService):
        self.anthropic_service = anthropic_service
    
    def _load_image_from_path(self, image_path: Union[str, Path]) -> bytes:
        """
        从文件路径加载图片
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            图片的二进制数据
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        with open(path, "rb") as f:
            return f.read()
    
    def _detect_media_type(self, image_path: Union[str, Path]) -> str:
        """
        根据文件扩展名检测媒体类型
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            媒体类型字符串
        """
        path = Path(image_path)
        ext = path.suffix.lower()
        
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        
        return media_type_map.get(ext, "image/jpeg")
    
    def _prepare_image_content(
        self,
        images: List[Union[str, Path, bytes, Dict[str, Any]]],
        text_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        准备多模态内容（图片 + 文本）
        
        Args:
            images: 图片列表，可以是：
                - 文件路径 (str/Path)
                - 二进制数据 (bytes)
                - base64 字符串 (str，需要是有效的 base64)
                - 已格式化的图片块 (Dict)
            text_prompt: 可选的文本提示
            
        Returns:
            内容块列表
        """
        content = []
        
        for idx, image in enumerate(images):
            # 如果已经是格式化的图片块，直接使用
            if isinstance(image, dict) and image.get("type") == "image":
                content.append(image)
                continue
            
            # 处理不同类型的图片输入
            if isinstance(image, (str, Path)):
                # 文件路径
                image_data = self._load_image_from_path(image)
                media_type = self._detect_media_type(image)
            elif isinstance(image, bytes):
                # 二进制数据
                image_data = image
                media_type = "image/jpeg"  # 默认，可以后续改进自动检测
            elif isinstance(image, str):
                # 可能是 base64 字符串或文件路径
                try:
                    # 尝试解码 base64
                    image_data = base64.b64decode(image)
                    media_type = "image/jpeg"  # 默认
                except Exception:
                    # 如果不是 base64，当作文件路径处理
                    image_data = self._load_image_from_path(image)
                    media_type = self._detect_media_type(image)
            else:
                raise ValueError(f"Unsupported image type: {type(image)}")
            
            # 创建图片块
            image_block = self.anthropic_service.create_image_block(image_data, media_type)
            content.append(image_block)
            
            # 如果有多张图片，添加分隔文本
            if len(images) > 1 and idx < len(images) - 1:
                content.append(self.anthropic_service.create_text_block(f"Image {idx + 1}:"))
        
        # 添加文本提示
        if text_prompt:
            if content:  # 如果已有图片，先添加提示文本
                content.insert(0, self.anthropic_service.create_text_block(text_prompt))
            else:
                content.append(self.anthropic_service.create_text_block(text_prompt))
        
        return content
    
    async def analyze_image(
        self,
        images: Union[str, Path, bytes, List[Union[str, Path, bytes]]],
        text_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析图片（非流式）
        
        Args:
            images: 单张图片或多张图片列表，可以是：
                - 文件路径 (str/Path)
                - 二进制数据 (bytes)
                - base64 字符串 (str)
            text_prompt: 可选的文本提示或问题
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            {
                "response": str,  # 分析结果文本
                "usage": dict,    # Token 使用情况
                "raw_response": str  # 原始响应（与 response 相同）
            }
        """
        # 确保 images 是列表
        if not isinstance(images, list):
            images = [images]
        
        # 准备内容
        content = self._prepare_image_content(images, text_prompt)
        
        # 如果没有文本提示，使用默认提示
        if not text_prompt:
            if len(images) == 1:
                default_prompt = "请详细分析这张图片，包括其中的内容、对象、场景、文字（如果有）等。"
            else:
                default_prompt = f"请分析这 {len(images)} 张图片，描述每张图片的内容，并比较它们之间的异同。"
            content.insert(0, self.anthropic_service.create_text_block(default_prompt))
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        # 调用 Anthropic API
        response_text, usage = await self.anthropic_service.messages_create(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            system=self.SYSTEM_PROMPT
        )
        
        logger.info(f"Vision analysis completed. Response length: {len(response_text)} characters")
        
        return {
            "response": response_text,
            "usage": usage,
            "raw_response": response_text
        }
    
    async def analyze_image_stream(
        self,
        images: Union[str, Path, bytes, List[Union[str, Path, bytes]]],
        text_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None
    ):
        """
        流式分析图片
        
        Args:
            images: 单张图片或多张图片列表
            text_prompt: 可选的文本提示或问题
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            Anthropic 流式响应迭代器
        """
        # 确保 images 是列表
        if not isinstance(images, list):
            images = [images]
        
        # 准备内容
        content = self._prepare_image_content(images, text_prompt)
        
        # 如果没有文本提示，使用默认提示
        if not text_prompt:
            if len(images) == 1:
                default_prompt = "请详细分析这张图片，包括其中的内容、对象、场景、文字（如果有）等。"
            else:
                default_prompt = f"请分析这 {len(images)} 张图片，描述每张图片的内容，并比较它们之间的异同。"
            content.insert(0, self.anthropic_service.create_text_block(default_prompt))
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        # 调用 Anthropic API 流式接口
        stream = await self.anthropic_service.messages_create_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            system=self.SYSTEM_PROMPT
        )
        
        return stream
    
    async def compare_images(
        self,
        images: List[Union[str, Path, bytes]],
        comparison_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        比较多张图片
        
        Args:
            images: 图片列表（至少2张）
            comparison_prompt: 可选的比较提示
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            分析结果字典
        """
        if len(images) < 2:
            raise ValueError("compare_images requires at least 2 images")
        
        default_prompt = comparison_prompt or "请详细比较这些图片，指出它们的相似之处和不同之处。"
        
        return await self.analyze_image(
            images=images,
            text_prompt=default_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
    
    async def extract_text_from_image(
        self,
        image: Union[str, Path, bytes],
        text_prompt: Optional[str] = None,
        temperature: float = 0.3,  # OCR 使用较低温度
        max_tokens: int = 2048,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从图片中提取文字（OCR）
        
        Args:
            image: 图片（单张）
            text_prompt: 自定义文本提示，如果不提供则使用默认 OCR 提示
            temperature: 温度参数（OCR 建议使用较低温度）
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            提取的文字结果
        """
        if text_prompt is None:
            prompt = "请直接输出图片中的所有文字内容，不要添加任何描述、说明或解释。如果图片中没有文字，只输出空内容。"
        else:
            prompt = text_prompt
        
        return await self.analyze_image(
            images=image,
            text_prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )

