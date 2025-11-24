#!/usr/bin/env python3
"""
OpenAI API 客户端脚本 - 支持自定义 endpoint
"""

import os
from openai import OpenAI, base_url


def chat_completion(
        prompt: str,
        api_key: str = None,
        base_url: str = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
):
    """
    调用 OpenAI Chat Completion API

    Args:
        prompt: 用户输入的提示词
        api_key: API 密钥（默认从环境变量 OPENAI_API_KEY 读取）
        base_url: API endpoint 地址（默认 https://api.openai.com/v1）
        model: 模型名称
        temperature: 温度参数 (0-2)
        max_tokens: 最大生成 token 数
        stream: 是否启用流式输出

    Returns:
        str: API 返回的回复内容
    """
    # 初始化客户端
    client = OpenAI(
        api_key=api_key or os.getenv("OPENAI_API_KEY", "sk-xxx"),
        base_url=base_url or os.getenv("OPENAI_BASE_URL")
    )

    # 构建消息
    messages = [{"role": "user", "content": prompt}]

    # 调用 API
    if stream:
        print("AI 回复: ", end="", flush=True)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True
        )

        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                print(content, end="", flush=True)
                full_response += content
        print()
        return full_response
    else:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content


# ============ 使用示例 ============
"""
# OpenAI 配置
OPENAI_API_KEY=sk-hirXqbo268kF1NDHRpe4mt5d5eLwEGIz5OzcOU1HqGq4yjzV
#sk-ktZmyFj5fpSnpLrfD1Ba232a89E046De97D02942Ee8158C8
OPENAI_API_BASE=https://globalai.vip/v1/chat/completions
#https://api.openai-next.com/v1
OPENAI_MODEL=claude-sonnet-4-20250514
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=50000

# Anthropic 配置（可选）
ANTHROPIC_API_KEY=sk-hirXqbo268kF1NDHRpe4mt5d5eLwEGIz5OzcOU1HqGq4yjzV
#sk-ktZmyFj5fpSnpLrfD1Ba232a89E046De97D02942Ee8158C8
ANTHROPIC_API_BASE=https://globalai.vip
#https://api.openai-next.com
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_TEMPERATURE=0.7
ANTHROPIC_MAX_TOKENS=50000
"""
if __name__ == "__main__":
    # 示例 1: 基本使用（使用默认 endpoint）
    response = chat_completion(
        prompt="你好，介绍一下自己",
        api_key="sk-hirXqbo268kF1NDHRpe4mt5d5eLwEGIz5OzcOU1HqGq4yjzV",
        base_url="https://globalai.vip/v1"
    )
    print(response)

    # 示例 2: 自定义 endpoint (Azure OpenAI)
    # response = chat_completion(
    #     prompt="解释一下量子计算",
    #     api_key="your-azure-key",
    #     base_url="https://your-resource.openai.azure.com/openai/deployments/gpt-4",
    #     model="gpt-4"
    # )
    # print(response)

    # 示例 3: 本地 LLM (Ollama)
    # response = chat_completion(
    #     prompt="写一首诗",
    #     api_key="dummy",
    #     base_url="http://localhost:11434/v1",
    #     model="llama2"
    # )
    # print(response)

    # 示例 4: 流式输出
    # response = chat_completion(
    #     prompt="写一个 Python 排序算法",
    #     api_key="sk-xxxxxxxx",
    #     stream=True
    # )

    # 示