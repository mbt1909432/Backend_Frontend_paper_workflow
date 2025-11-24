#!/usr/bin/env python3
"""
Anthropic Claude API 客户端脚本 - 支持自定义 endpoint
"""

import os
from anthropic import Anthropic


def chat_completion(
        prompt: str,
        api_key: str = None,
        base_url: str = None,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 1.0,
        max_tokens: int = 1024,
        stream: bool = False,
        system: str = None
):
    """
    调用 Anthropic Claude API

    Args:
        prompt: 用户输入的提示词
        api_key: API 密钥（默认从环境变量 ANTHROPIC_API_KEY 读取）
        base_url: API endpoint 地址（默认 https://api.anthropic.com）
        model: 模型名称
        temperature: 温度参数 (0-1)
        max_tokens: 最大生成 token 数
        stream: 是否启用流式输出
        system: 系统提示词

    Returns:
        str: API 返回的回复内容
    """
    # 初始化客户端
    client = Anthropic(
        api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
        base_url=base_url or os.getenv("ANTHROPIC_BASE_URL")
    )

    # 构建消息
    messages = [{"role": "user", "content": prompt}]

    # 构建请求参数
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    # 添加系统提示词（如果有）
    if system:
        kwargs["system"] = system

    # 调用 API
    if stream:
        print("Claude 回复: ", end="", flush=True)
        full_response = ""

        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
                full_response += text

        print()
        return full_response
    else:
        response = client.messages.create(**kwargs)
        return response.content[0].text


# ============ 使用示例 ============

if __name__ == "__main__":
    # 示例 1: 基本使用
    response = chat_completion(
        prompt="你好，介绍一下自己",
        api_key="sk-hirXqbo268kF1NDHRpe4mt5d5eLwEGIz5OzcOU1HqGq4yjzV",
        base_url="https://globalai.vip"
    )
    print(response)

    # 示例 2: 使用 Claude Sonnet 4
    # response = chat_completion(
    #     prompt="解释一下量子计算",
    #     api_key="sk-ant-xxxxx",
    #     model="claude-sonnet-4-20250514"
    # )
    # print(response)

    # 示例 3: 使用 Claude Opus
    # response = chat_completion(
    #     prompt="写一首诗",
    #     api_key="sk-ant-xxxxx",
    #     model="claude-opus-4-20250514"
    # )
    # print(response)

    # 示例 4: 流式输出
    # response = chat_completion(
    #     prompt="写一个 Python 排序算法",
    #     api_key="sk-ant-xxxxx",
    #     stream=True
    # )

    # 示例 5: 使用系统提示词
    # response = chat_completion(
    #     prompt="今天天气怎么样？",
    #     api_key="sk-ant-xxxxx",
    #     system="你是一个专业的气象学家，用科学的方式解释天气现象。"
    # )
    # print(response)

    # 示例 6: 自定义 endpoint (如代理服务器)
    # response = chat_completion(
    #     prompt="你好",
    #     api_key="sk-ant-xxxxx",
    #     base_url="https://your-proxy.com"
    # )
    # print(response)

    # 示例 7: 从环境变量读取配置
    # export ANTHROPIC_API_KEY="sk-ant-xxxxx"
    # export ANTHROPIC_BASE_URL="https://api.anthropic.com"
    # response = chat_completion(prompt="你好")
    # print(response)

    # 示例 8: 调整温度和长度
    # response = chat_completion(
    #     prompt="创作一个科幻故事",
    #     api_key="sk-ant-xxxxx",
    #     temperature=0.9,
    #     max_tokens=2048
    # )
    # print(response)