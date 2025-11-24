from typing import List, Optional, Dict, Any, AsyncIterator
from app.core.schemas import Message
from app.services.openai_service import OpenAIService
from app.utils.logger import logger


class Agent:
    """Agent 核心类"""
    
    def __init__(self, openai_service: OpenAIService):
        self.openai_service = openai_service
        # 会话历史存储（简单内存存储，后续可扩展为持久化）
        self.conversations: Dict[str, List[Message]] = {}
    
    def _get_or_create_conversation(self, conversation_id: Optional[str]) -> tuple[str, List[Message]]:
        """获取或创建会话"""
        if conversation_id is None:
            import uuid
            conversation_id = str(uuid.uuid4())
        
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        return conversation_id, self.conversations[conversation_id]
    
    def _prepare_messages(
        self,
        user_message: str,
        conversation_id: str,
        history: List[Message],
        custom_messages: Optional[List[Message]] = None
    ) -> List[Dict[str, str]]:
        """准备发送给 OpenAI 的消息列表"""
        messages = []
        
        # 如果提供了自定义消息列表，使用它
        if custom_messages:
            messages = [msg.model_dump() for msg in custom_messages]
        else:
            # 否则使用会话历史
            for msg in history:
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        custom_messages: Optional[List[Message]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> tuple[str, str, Dict[str, Any]]:
        """
        非流式对话
        
        Returns:
            (response, conversation_id, usage)
        """
        conv_id, history = self._get_or_create_conversation(conversation_id)
        
        messages = self._prepare_messages(message, conv_id, history, custom_messages)
        
        # 调用 OpenAI
        response, usage = await self.openai_service.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        # 更新会话历史
        history.append(Message(role="user", content=message))
        history.append(Message(role="assistant", content=response))
        
        logger.info(f"Conversation {conv_id}: User message processed")
        
        return response, conv_id, usage
    
    async def chat_stream(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        custom_messages: Optional[List[Message]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> tuple[AsyncIterator, str]:
        """
        流式对话
        
        Returns:
            (stream_iterator, conversation_id)
        """
        conv_id, history = self._get_or_create_conversation(conversation_id)
        
        messages = self._prepare_messages(message, conv_id, history, custom_messages)
        
        # 调用 OpenAI 流式接口
        stream = await self.openai_service.chat_completion_stream(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model
        )
        
        # 注意：流式响应中，历史更新需要在流完成后进行
        # 这里先添加用户消息，assistant 消息在流完成后添加
        history.append(Message(role="user", content=message))
        
        logger.info(f"Conversation {conv_id}: Streaming started")
        
        return stream, conv_id
    
    def update_conversation_history(
        self,
        conversation_id: str,
        assistant_response: str
    ):
        """更新会话历史（用于流式响应完成后）"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id].append(
                Message(role="assistant", content=assistant_response)
            )

