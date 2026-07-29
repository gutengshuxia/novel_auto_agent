"""LLM 连接测试服务 — 验证供应商/模型是否能正常工作。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 测试用的简单 prompt
TEST_PROMPT = "请用一句话回复：你好"
TEST_TIMEOUT = 30  # 秒


async def test_provider_connection_service(provider: Any) -> dict[str, Any]:
    """测试供应商连接。

    使用供应商的 API Key 和 Base URL 构建一个简单的 LLM 客户端，
    发送一个测试消息验证连接是否正常。

    Returns:
        {"success": bool, "message": str, "response": str | None, "latency_ms": float}
    """
    import time

    provider_name = (provider.name or "").lower()
    api_key = provider.api_key
    base_url = provider.base_url

    if not api_key:
        return {
            "success": False,
            "message": "供应商未配置 API Key",
            "response": None,
            "latency_ms": 0,
        }

    if not base_url:
        return {
            "success": False,
            "message": "供应商未配置 Base URL",
            "response": None,
            "latency_ms": 0,
        }

    # 判断协议
    is_anthropic = "claude" in provider_name or "anthropic" in provider_name

    start = time.monotonic()
    try:
        if is_anthropic:
            response_text = await _test_anthropic(api_key, provider_name)
        else:
            response_text = await _test_openai_compatible(api_key, base_url)

        latency = (time.monotonic() - start) * 1000
        return {
            "success": True,
            "message": f"连接成功！延迟 {latency:.0f}ms",
            "response": response_text,
            "latency_ms": round(latency, 1),
        }

    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        error_msg = str(e)
        logger.warning("Provider test failed: %s (%.0fms)", error_msg, latency)
        return {
            "success": False,
            "message": f"连接失败: {error_msg}",
            "response": None,
            "latency_ms": round(latency, 1),
        }


async def test_model_connection_service(model: Any, provider: Any) -> dict[str, Any]:
    """测试指定模型的生成能力。

    使用供应商的凭证和模型的名称发送测试请求。

    Returns:
        {"success": bool, "message": str, "response": str | None, "latency_ms": float, "model": str}
    """
    import time

    provider_name = (provider.name or "").lower()
    api_key = provider.api_key
    base_url = provider.base_url
    model_name = model.name

    if not api_key:
        return {
            "success": False,
            "message": "供应商未配置 API Key",
            "response": None,
            "latency_ms": 0,
            "model": model_name,
        }

    is_anthropic = "claude" in provider_name or "anthropic" in provider_name

    start = time.monotonic()
    try:
        if is_anthropic:
            response_text = await _test_anthropic(api_key, model_name)
        else:
            response_text = await _test_openai_compatible(api_key, base_url, model_name)

        latency = (time.monotonic() - start) * 1000
        return {
            "success": True,
            "message": f"模型 {model_name} 测试成功！延迟 {latency:.0f}ms",
            "response": response_text,
            "latency_ms": round(latency, 1),
            "model": model_name,
        }

    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        error_msg = str(e)
        logger.warning("Model test failed: %s (%.0fms)", error_msg, latency)
        return {
            "success": False,
            "message": f"测试失败: {error_msg}",
            "response": None,
            "latency_ms": round(latency, 1),
            "model": model_name,
        }


async def _test_openai_compatible(
    api_key: str,
    base_url: str,
    model: str = "gpt-3.5-turbo",
) -> str:
    """测试 OpenAI 兼容的 API。"""
    import httpx

    # 标准化 base_url
    normalized_url = base_url.rstrip("/")
    if not normalized_url.endswith("/v1"):
        normalized_url = normalized_url + "/v1"

    url = f"{normalized_url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
        "max_tokens": 50,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # 提取回复内容
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return "(无回复内容)"


async def _test_anthropic(
    api_key: str,
    model: str = "claude-sonnet-4-20250514",
) -> str:
    """测试 Anthropic Claude API。"""
    import httpx

    url = "https://api.anthropic.com/v1/messages"

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model": model,
        "max_tokens": 50,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
    }

    async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # 提取回复内容
    content = data.get("content", [])
    if content:
        return content[0].get("text", "")
    return "(无回复内容)"
