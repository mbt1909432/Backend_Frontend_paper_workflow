from typing import List, Dict, Any, Optional, AsyncIterator, Union
from anthropic import AsyncAnthropic
from app.config.settings import settings
from app.utils.logger import logger
import base64


class AnthropicService:
    """Anthropic 服务封装 - 支持多模态输入（文本+图片）"""
    
    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables")
        
        # 如果配置了自定义 endpoint，则使用它（用于模型转发商）
        client_kwargs = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_api_base:
            client_kwargs["base_url"] = settings.anthropic_api_base
            logger.info(f"Using custom Anthropic API endpoint: {settings.anthropic_api_base}")
        
        self.client = AsyncAnthropic(**client_kwargs)
        self.default_model = settings.anthropic_model
        self.default_temperature = settings.anthropic_temperature
        self.default_max_tokens = settings.anthropic_max_tokens
    
    def _format_messages_for_log(self, messages: List[Dict[str, Any]]) -> str:
        """格式化消息列表用于日志输出"""
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # 处理多模态内容
            if isinstance(content, list):
                content_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text = part.get("text", "")
                            if len(text) > 500:
                                text = text[:500] + f"\n... (truncated, total length: {len(text)} chars)"
                            content_parts.append(f"[text: {text}]")
                        elif part.get("type") == "image":
                            source = part.get("source", {})
                            media_type = source.get("media_type", "unknown")
                            data_preview = source.get("data", "")[:50] + "..." if source.get("data") else "N/A"
                            content_parts.append(f"[image: {media_type}, data: {data_preview}]")
                    else:
                        content_parts.append(str(part)[:200])
                content_str = " ".join(content_parts)
            else:
                content_str = str(content)
                if len(content_str) > 2000:
                    content_str = content_str[:2000] + f"\n... (truncated, total length: {len(content_str)} chars)"
            
            formatted.append(f"  {role}: {content_str}")
        return "\n".join(formatted)
    
    @staticmethod
    def encode_image_to_base64(image_data: bytes, media_type: str = "image/jpeg") -> str:
        """
        将图片数据编码为 base64 字符串
        
        Args:
            image_data: 图片的二进制数据
            media_type: 图片类型 (image/jpeg, image/png, image/gif, image/webp)
            
        Returns:
            base64 编码的字符串
        """
        return base64.b64encode(image_data).decode("utf-8")
    
    @staticmethod
    def create_image_block(image_data: bytes, media_type: str = "image/jpeg") -> Dict[str, Any]:
        """
        创建图片内容块
        
        Args:
            image_data: 图片的二进制数据
            media_type: 图片类型 (image/jpeg, image/png, image/gif, image/webp)
            
        Returns:
            图片内容块字典
        """
        base64_data = AnthropicService.encode_image_to_base64(image_data, media_type)
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64_data
            }
        }
    
    @staticmethod
    def create_text_block(text: str) -> Dict[str, Any]:
        """
        创建文本内容块
        
        Args:
            text: 文本内容
            
        Returns:
            文本内容块字典
        """
        return {
            "type": "text",
            "text": text
        }
    
    async def messages_create(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        system: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """
        非流式消息创建（支持多模态）
        
        Args:
            messages: 消息列表，每个消息的 content 可以是字符串或列表（多模态）
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            (response_text, usage_info)
        """
        try:
            # 打印 prompt
            logger.info("=" * 80)
            logger.info("Anthropic API Request (Prompt):")
            logger.info(f"Model: {model or self.default_model}")
            logger.info(f"Temperature: {temperature if temperature is not None else self.default_temperature}")
            logger.info(f"Max Tokens: {max_tokens or self.default_max_tokens}")
            logger.info("Messages:")
            logger.info(self._format_messages_for_log(messages))
            logger.info("=" * 80)
            
            create_kwargs = {
                "model": model or self.default_model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens
            }
            if system:
                create_kwargs["system"] = system
            
            response = await self.client.messages.create(**create_kwargs)
            
            # 提取响应文本
            response_text = ""
            if response.content:
                for block in response.content:
                    if block.type == "text":
                        response_text += block.text
            
            usage_info = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
            
            # 打印 output
            logger.info("=" * 80)
            logger.info("Anthropic API Response (Output):")
            if len(response_text) > 2000:
                output_preview = response_text[:2000] + f"\n... (truncated, total length: {len(response_text)} chars)"
                logger.info(output_preview)
                logger.info(f"\nFull output length: {len(response_text)} characters")
            else:
                logger.info(response_text)
            logger.info(f"Usage: {usage_info['total_tokens']} tokens (input: {usage_info['input_tokens']}, output: {usage_info['output_tokens']})")
            logger.info("=" * 80)
            
            return response_text, usage_info
            
        except Exception as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise
    
    async def messages_create_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        system: Optional[str] = None
    ) -> AsyncIterator:
        """
        流式消息创建（支持多模态）
        
        Args:
            messages: 消息列表，每个消息的 content 可以是字符串或列表（多模态）
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            Anthropic 流式响应迭代器
        """
        try:
            # 打印 prompt
            logger.info("=" * 80)
            logger.info("Anthropic API Request (Prompt) - Streaming:")
            logger.info(f"Model: {model or self.default_model}")
            logger.info(f"Temperature: {temperature if temperature is not None else self.default_temperature}")
            logger.info(f"Max Tokens: {max_tokens or self.default_max_tokens}")
            logger.info("Messages:")
            logger.info(self._format_messages_for_log(messages))
            logger.info("=" * 80)
            
            create_kwargs = {
                "model": model or self.default_model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self.default_temperature,
                "max_tokens": max_tokens or self.default_max_tokens,
                "stream": True
            }
            if system:
                create_kwargs["system"] = system
            
            stream = await self.client.messages.create(**create_kwargs)
            
            # 包装流式响应，收集完整输出
            accumulated_text = ""
            usage_info = None
            
            async def wrapped_stream():
                nonlocal accumulated_text, usage_info
                try:
                    async for chunk in stream:
                        # 处理不同类型的 chunk
                        chunk_type = getattr(chunk, 'type', None)
                        
                        # 收集内容
                        if chunk_type == 'content_block_delta':
                            delta = getattr(chunk, 'delta', None)
                            if delta:
                                text = getattr(delta, 'text', None)
                                if text:
                                    accumulated_text += text
                        
                        # 检查是否有 usage 信息
                        if chunk_type == 'message_delta' or chunk_type == 'message_stop':
                            usage = getattr(chunk, 'usage', None)
                            if usage:
                                usage_info = {
                                    "input_tokens": getattr(usage, 'input_tokens', 0),
                                    "output_tokens": getattr(usage, 'output_tokens', 0),
                                    "total_tokens": getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)
                                }
                        
                        yield chunk
                    
                    # 流结束后打印完整输出
                    logger.info("=" * 80)
                    logger.info("Anthropic API Response (Output) - Streaming Complete:")
                    if len(accumulated_text) > 2000:
                        output_preview = accumulated_text[:2000] + f"\n... (truncated, total length: {len(accumulated_text)} chars)"
                        logger.info(output_preview)
                        logger.info(f"\nFull output length: {len(accumulated_text)} characters")
                    else:
                        logger.info(accumulated_text)
                    if usage_info:
                        logger.info(f"Usage: {usage_info['total_tokens']} tokens (input: {usage_info['input_tokens']}, output: {usage_info['output_tokens']})")
                    else:
                        logger.info("Usage: N/A (not provided in stream)")
                    logger.info("=" * 80)
                    
                except Exception as e:
                    logger.error(f"Error in streaming: {str(e)}")
                    raise
            
            logger.info("Anthropic streaming started")
            # 返回异步生成器对象（可以直接用于 async for）
            return wrapped_stream()
            
        except Exception as e:
            logger.error(f"Anthropic streaming error: {str(e)}")
            raise

