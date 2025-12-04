from typing import List, Dict, Any, Optional, AsyncIterator
from openai import AsyncOpenAI
from app.config.settings import settings
from app.utils.logger import logger
import tiktoken


class OpenAIService:
    """OpenAI 服务封装"""
    
    def __init__(self):
        # 如果配置了自定义 endpoint，则使用它（用于模型转发商）
        client_kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_api_base:
            client_kwargs["base_url"] = settings.openai_api_base
            logger.info(f"Using custom OpenAI API endpoint: {settings.openai_api_base}")
        
        self.client = AsyncOpenAI(**client_kwargs)
        self.default_model = settings.openai_model
        self.default_temperature = settings.openai_temperature
        self.default_max_tokens = settings.openai_max_tokens
    
    def _count_tokens(self, text: str, model: Optional[str] = None) -> int:
        """使用 tiktoken 统计 token 数（优先按模型编码，失败则回退到通用编码）"""
        try:
            encoding = tiktoken.encoding_for_model(model or self.default_model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    
    def _format_messages_for_log(self, messages: List[Dict[str, str]]) -> str:
        """格式化消息列表用于日志输出"""
        formatted = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # 如果内容太长，截断显示（并用 tiktoken 统计 token 数）
            if len(content) > 200:
                total_tokens = self._count_tokens(content)
                content_preview = content[:200] + f"\n... (truncated, total tokens: {total_tokens})"
            else:
                content_preview = content
            formatted.append(f"  {role}: {content_preview}")
        return "\n".join(formatted)
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        """
        非流式聊天完成
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            (response_text, usage_info)
        """
        try:
            # 打印 prompt
            logger.info("=" * 80)
            logger.info("LLM Request (Prompt):")
            logger.info(f"Model: {model or self.default_model}")
            logger.info(f"Temperature: {temperature if temperature is not None else self.default_temperature}")
            logger.info(f"Max Tokens: {max_tokens or self.default_max_tokens}")
            logger.info("Messages:")
            logger.info(self._format_messages_for_log(messages))
            logger.info("😀" * 80)
            
            response = await self.client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens or self.default_max_tokens
            )
            
            response_text = response.choices[0].message.content
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            # 打印 output
            logger.info("=" * 80)
            logger.info("LLM Response (Output):")
            # 如果输出太长，截断显示（并用 tiktoken 统计 token 数）
            if len(response_text) > 2000:
                total_tokens = self._count_tokens(response_text, model)
                output_preview = response_text[:2000] + f"\n... (truncated, total tokens: {total_tokens})"
                logger.info(output_preview)
            else:
                logger.info(response_text)
            logger.info(f"Usage: {usage_info['total_tokens']} tokens (prompt: {usage_info['prompt_tokens']}, completion: {usage_info['completion_tokens']})")
            logger.info("=" * 80)
            
            return response_text, usage_info
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise
    
    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> AsyncIterator:
        """
        流式聊天完成
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            model: 模型名称
            
        Returns:
            OpenAI 流式响应迭代器（包装后，会收集完整输出并打印日志）
        """
        try:
            # 打印 prompt
            logger.info("=" * 80)
            logger.info("LLM Request (Prompt) - Streaming:")
            logger.info(f"Model: {model or self.default_model}")
            logger.info(f"Temperature: {temperature if temperature is not None else self.default_temperature}")
            logger.info(f"Max Tokens: {max_tokens or self.default_max_tokens}")
            logger.info("Messages:")
            logger.info(self._format_messages_for_log(messages))
            logger.info("=" * 80)
            
            stream = await self.client.chat.completions.create(
                model=model or self.default_model,
                messages=messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens or self.default_max_tokens,
                stream=True
            )
            
            # 包装流式响应，收集完整输出
            accumulated_text = ""
            usage_info = None
            
            async def wrapped_stream():
                nonlocal accumulated_text, usage_info
                try:
                    async for chunk in stream:
                        # 检查是否有 usage 信息（通常在最后一个 chunk 中）
                        if hasattr(chunk, 'usage') and chunk.usage:
                            usage_info = {
                                "prompt_tokens": chunk.usage.prompt_tokens,
                                "completion_tokens": chunk.usage.completion_tokens,
                                "total_tokens": chunk.usage.total_tokens
                            }
                        
                        # 收集内容
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if hasattr(delta, 'content') and delta.content:
                                accumulated_text += delta.content
                        
                        yield chunk
                    
                    # 流结束后打印完整输出
                    logger.info("=" * 80)
                    logger.info("LLM Response (Output) - Streaming Complete:")
                    if len(accumulated_text) > 2000:
                        total_tokens = self._count_tokens(accumulated_text, model)
                        output_preview = accumulated_text[:2000] + f"\n... (truncated, total tokens: {total_tokens})"
                        logger.info(output_preview)
                    else:
                        logger.info(accumulated_text)
                    if usage_info:
                        logger.info(f"Usage: {usage_info['total_tokens']} tokens (prompt: {usage_info['prompt_tokens']}, completion: {usage_info['completion_tokens']})")
                    else:
                        logger.info("Usage: N/A (not provided in stream)")
                    logger.info("=" * 80)
                    
                except Exception as e:
                    logger.error(f"Error in streaming: {str(e)}")
                    raise
            
            logger.info("OpenAI streaming started")
            # 返回异步生成器对象（可以直接用于 async for）
            return wrapped_stream()
            
        except Exception as e:
            logger.error(f"OpenAI streaming error: {str(e)}")
            raise

