import asyncio
from typing import Dict, Literal

from app.config.settings import settings
from app.services.openai_service import OpenAIService
from app.services.anthropic_service import AnthropicService
from app.utils.logger import logger


HealthStatus = Literal["ok", "failed", "skipped"]


async def _check_openai() -> Dict[str, str]:
    """检查 OpenAI 可用性"""
    if not settings.openai_api_key:
        detail = "OpenAI API key missing; skipping connectivity check"
        logger.warning(detail)
        return {"provider": "openai", "status": "skipped", "detail": detail}

    try:
        service = OpenAIService()
        response_text, _ = await service.chat_completion(
            messages=[
                {"role": "system", "content": "You are a health-check assistant. Reply with 'ok' when prompted."},
                {"role": "user", "content": "Health check ping. Reply with ok."}
            ],
            temperature=0.0,
            max_tokens=5,
        )
        if response_text and "ok" in response_text.strip().lower():
            detail = "Received expected response 'ok' from chat completion"
            logger.info(f"OpenAI connectivity check passed: {detail}")
            return {"provider": "openai", "status": "ok", "detail": detail}

        detail = f"Unexpected OpenAI response: {response_text!r}"
        logger.error(detail)
        return {"provider": "openai", "status": "failed", "detail": detail}
    except Exception as exc:
        detail = f"OpenAI connectivity failed: {exc}"
        logger.error(detail)
        return {"provider": "openai", "status": "failed", "detail": detail}


async def _check_anthropic() -> Dict[str, str]:
    """检查 Anthropic 可用性"""
    if not settings.anthropic_api_key:
        detail = "Anthropic API key missing; skipping connectivity check"
        logger.warning(detail)
        return {"provider": "anthropic", "status": "skipped", "detail": detail}

    try:
        service = AnthropicService()
        response_text, _ = await service.messages_create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        service.create_text_block("Health check ping. Reply with ok.")
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=5,
            system="You are a health-check assistant. Reply with 'ok' when prompted.",
        )
        if response_text and "ok" in response_text.strip().lower():
            detail = "Received expected response 'ok' from conversation"
            logger.info(f"Anthropic connectivity check passed: {detail}")
            return {"provider": "anthropic", "status": "ok", "detail": detail}

        detail = f"Unexpected Anthropic response: {response_text!r}"
        logger.error(detail)
        return {"provider": "anthropic", "status": "failed", "detail": detail}
    except Exception as exc:
        detail = f"Anthropic connectivity failed: {exc}"
        logger.error(detail)
        return {"provider": "anthropic", "status": "failed", "detail": detail}


async def check_llm_connectivity() -> Dict[str, Dict[str, str]]:
    """
    同时检查 OpenAI 和 Anthropic 的可用性
    
    Returns:
        provider -> status/detail 映射
    """
    results = await asyncio.gather(_check_openai(), _check_anthropic())
    return {result["provider"]: result for result in results}

