from typing import Dict, Any, Optional, List, Union, Tuple
import base64
import time
from pathlib import Path
from io import BytesIO
from PIL import Image
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
- Output raw content only, nothing else

## Special Rule: References / Bibliography

- If any portion of the image corresponds to references, bibliography, citation lists, or footnotes (titles such as "References", "Bibliography", "Works Cited", "参考文献", or lines that start with bracketed numbers `[1]`, numbered lists, author-year patterns, etc.), you MUST skip those lines entirely.
- Do NOT transcribe citation entries even if only part of the page is references—leave that portion blank and continue with any non-reference content.
- If an image page contains ONLY references, output a single short note (≤20 Chinese characters or ≤15 English words) such as "参考文献页，内容跳过" / "Reference list skipped", then output nothing else.
- Never paraphrase or restate the skipped reference content itself.
"""

    # Anthropic API 限制：base64 编码后的图片不能超过 5MB (5242880 bytes)
    # base64 编码会增加约 33% 的大小（4/3 倍），所以原始图片应该控制在约 3.75MB
    MAX_BASE64_SIZE_BYTES = 5_242_880  # 5MB，API 限制
    MAX_ORIGINAL_SIZE_BYTES = 3_750_000  # 约 3.75MB，确保 base64 编码后不超过 5MB
    
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
    
    def _get_base64_size(self, image_data: bytes) -> int:
        """
        计算图片 base64 编码后的大小
        
        Args:
            image_data: 原始图片数据
            
        Returns:
            base64 编码后的大小（字节）
        """
        # base64 编码会增加约 33% 的大小（4/3 倍）
        # 实际大小 = len(base64.b64encode(image_data))
        # 但为了效率，我们使用近似值：original_size * 4 / 3
        return int(len(image_data) * 4 / 3)
    
    def _compress_image(
        self,
        image_data: bytes,
        media_type: str,
        max_base64_size_bytes: int = MAX_BASE64_SIZE_BYTES
    ) -> Tuple[bytes, str]:
        """
        压缩图片直到 base64 编码后小于指定大小
        
        Args:
            image_data: 原始图片数据
            media_type: 原始图片类型
            max_base64_size_bytes: base64 编码后的最大允许大小（字节）
            
        Returns:
            (压缩后的图片数据, 压缩后的媒体类型)
        """
        original_size = len(image_data)
        original_base64_size = self._get_base64_size(image_data)
        
        # 如果 base64 编码后已经小于限制，直接返回
        if original_base64_size <= max_base64_size_bytes:
            logger.debug(
                f"Image size {original_size} bytes (base64: ~{original_base64_size} bytes) "
                f"is within limit, no compression needed"
            )
            return image_data, media_type
        
        logger.warning(
            f"Image size {original_size} bytes (base64: ~{original_base64_size} bytes) "
            f"exceeds limit {max_base64_size_bytes} bytes, compressing..."
        )
        
        # 计算目标原始大小（考虑 base64 编码的膨胀）
        # 目标原始大小 = max_base64_size * 3 / 4
        target_original_size = int(max_base64_size_bytes * 3 / 4)
        
        try:
            # 打开图片
            img = Image.open(BytesIO(image_data))
            original_format = img.format
            original_mode = img.mode
            
            # 转换为 RGB 模式（JPEG 不支持透明度）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 计算初始质量
            quality = 85
            scale_factor = 1.0
            
            # 尝试压缩
            for attempt in range(10):  # 最多尝试 10 次
                output = BytesIO()
                
                # 如果尺寸太大，先缩小尺寸
                if scale_factor < 1.0:
                    new_width = int(img.width * scale_factor)
                    new_height = int(img.height * scale_factor)
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    resized_img = img
                
                # 保存为 JPEG
                resized_img.save(
                    output,
                    format='JPEG',
                    quality=quality,
                    optimize=True
                )
                
                compressed_data = output.getvalue()
                compressed_size = len(compressed_data)
                compressed_base64_size = self._get_base64_size(compressed_data)
                
                # 如果 base64 编码后小于限制，返回
                if compressed_base64_size <= max_base64_size_bytes:
                    logger.info(
                        f"Image compressed successfully: {original_size} -> {compressed_size} bytes "
                        f"(base64: ~{compressed_base64_size} bytes, quality={quality}, scale={scale_factor:.2f})"
                    )
                    return compressed_data, "image/jpeg"
                
                # 调整压缩参数
                if attempt < 3:
                    # 前3次尝试降低质量
                    quality = max(30, quality - 15)
                elif attempt < 6:
                    # 接下来3次尝试缩小尺寸
                    scale_factor = max(0.5, scale_factor - 0.1)
                    quality = max(30, quality - 5)
                else:
                    # 最后几次同时降低质量和尺寸
                    scale_factor = max(0.3, scale_factor - 0.1)
                    quality = max(20, quality - 5)
            
            # 如果还是太大，返回最后一次尝试的结果（即使超过限制）
            logger.warning(
                f"Image compression reached limit: {compressed_size} bytes "
                f"(base64: ~{compressed_base64_size} bytes, target base64: {max_base64_size_bytes} bytes). "
                f"Using compressed version anyway."
            )
            return compressed_data, "image/jpeg"
            
        except Exception as e:
            logger.error(f"Failed to compress image: {e}. Using original image.")
            return image_data, media_type
    
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
            start_time = time.perf_counter()
            source_desc = self._describe_image_source(image)
            # 如果已经是格式化的图片块，直接使用
            if isinstance(image, dict) and image.get("type") == "image":
                content.append(image)
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"VisionAgent image {idx + 1}/{len(images)} prepared in "
                    f"{duration_ms:.2f} ms (source={source_desc})"
                )
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
            
            # 检查并压缩图片（如果需要）
            original_size = len(image_data)
            original_base64_size = self._get_base64_size(image_data)
            
            if original_base64_size > self.MAX_BASE64_SIZE_BYTES:
                image_data, media_type = self._compress_image(image_data, media_type)
                compressed_base64_size = self._get_base64_size(image_data)
                logger.info(
                    f"Image compressed: {original_size} -> {len(image_data)} bytes "
                    f"(base64: ~{original_base64_size} -> ~{compressed_base64_size} bytes, "
                    f"media_type: {media_type})"
                )
            
            # 创建图片块
            image_block = self.anthropic_service.create_image_block(image_data, media_type)
            content.append(image_block)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"VisionAgent image {idx + 1}/{len(images)} prepared in "
                f"{duration_ms:.2f} ms (source={source_desc})"
            )
            
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

    def _describe_image_source(self, image: Union[str, Path, bytes, Dict[str, Any]]) -> str:
        """
        Describe the image source for logging purposes.
        """
        if isinstance(image, (str, Path)):
            path = str(image)
            return path if len(path) <= 64 else f"{path[:30]}...{path[-30:]}"
        if isinstance(image, bytes):
            return f"bytes({len(image)}B)"
        if isinstance(image, dict):
            return image.get("type", "dict")
        return type(image).__name__
    
    async def analyze_image(
        self,
        images: Union[str, Path, bytes, List[Union[str, Path, bytes]]],
        text_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 44444,
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
        
        usage_summary = "Token usage unavailable"
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if total is not None:
                usage_summary = (
                    f"Tokens - total: {total}, input: {input_tokens}, output: {output_tokens}"
                )
        logger.info(f"Vision analysis completed. {usage_summary}")
        
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
        max_tokens: int = 44444,
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

