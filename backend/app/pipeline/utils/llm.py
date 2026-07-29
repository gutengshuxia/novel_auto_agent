"""LLM 客户端工厂 —— 多 Provider 统一入口。

支持的 Provider (通过 .env 的 LLM_PROVIDER 切换):
- openai:     OpenAI 官方
- deepseek:   DeepSeek (国内, 性价比最高)
- claude:     Anthropic Claude (原生 SDK)
- gemini:     Google Gemini (OpenAI 兼容端点)
- zhipu:      智谱 GLM (OpenAI 兼容)
- kimi:       月之暗面 Moonshot (OpenAI 兼容)
- qwen:       阿里通义 (DashScope, OpenAI 兼容)
- doubao:     字节豆包 (火山方舟, OpenAI 兼容)
- yi:         零一万物 (OpenAI 兼容)

向后兼容: 如果 .env 没设 LLM_PROVIDER, 自动从 OPENAI_* 变量推断 (老配置仍可用)。
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache
from typing import Any, Optional

# ============================================================
# DB 配置覆盖 (前端模型管理 → Pipeline 打通)
# ============================================================
# 当前端选择了某个模型时, bridge 会调用 set_llm_override() 设置覆盖配置
# get_llm() 会优先使用这个覆盖配置, 而不是读 .env 环境变量

_llm_override: dict[str, Any] | None = None
_llm_override_lock = threading.Lock()


def set_llm_override(
    *,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    provider_key: str | None = None,
    protocol: str = "openai",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> None:
    """设置全局 LLM 覆盖配置 (由 bridge 在调用 Pipeline 前设置)。

    设置后, get_llm() 会优先使用此配置, 忽略 .env 环境变量。
    用于打通前端模型管理 UI 和 Pipeline。
    """
    global _llm_override
    with _llm_override_lock:
        _llm_override = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "provider_key": provider_key,
            "protocol": protocol,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }


def clear_llm_override() -> None:
    """清除 LLM 覆盖配置。"""
    global _llm_override
    with _llm_override_lock:
        _llm_override = None


def get_llm_override() -> dict[str, Any] | None:
    """获取当前 LLM 覆盖配置 (线程安全)。"""
    with _llm_override_lock:
        return dict(_llm_override) if _llm_override is not None else None

from langchain_core.messages import AIMessage


# ============================================================
# Provider 预设配置
# ============================================================

# 每个 Provider 的默认 base_url + 默认模型 + API Key 环境变量名
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "model_env": "OPENAI_MODEL",
        "protocol": "openai",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "protocol": "openai",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "api_key_env": "ZHIPU_API_KEY",
        "base_url_env": None,
        "model_env": "ZHIPU_MODEL",
        "protocol": "openai",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-128k",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url_env": None,
        "model_env": "MOONSHOT_MODEL",
        "protocol": "openai",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url_env": None,
        "model_env": "DASHSCOPE_MODEL",
        "protocol": "openai",
    },
    "doubao": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-pro-32k",
        "api_key_env": "ARK_API_KEY",
        "base_url_env": None,
        "model_env": "ARK_MODEL",
        "protocol": "openai",
    },
    "yi": {
        "base_url": "https://api.lingyiwanwu.com/v1",
        "default_model": "yi-large",
        "api_key_env": "YI_API_KEY",
        "base_url_env": None,
        "model_env": "YI_MODEL",
        "protocol": "openai",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-pro",
        "api_key_env": "GOOGLE_API_KEY",
        "base_url_env": None,
        "model_env": "GEMINI_MODEL",
        "protocol": "openai",
    },
    "claude": {
        "base_url": None,  # Claude 走原生 SDK, 不需要 base_url
        "default_model": "claude-sonnet-4-20250514",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": None,
        "model_env": "CLAUDE_MODEL",
        "protocol": "anthropic",
    },
    "anthropic": {  # claude 的别名
        "base_url": None,
        "default_model": "claude-sonnet-4-20250514",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": None,
        "model_env": "CLAUDE_MODEL",
        "protocol": "anthropic",
    },
}


def _detect_provider() -> str:
    """自动检测当前应该用哪个 Provider。

    优先级:
    1. 显式 LLM_PROVIDER 环境变量
    2. 按以下顺序找第一个有 API Key 的:
       deepseek > openai > claude > gemini > zhipu > kimi > qwen > doubao > yi
    """
    explicit = os.getenv("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit

    # 隐式探测
    for name in ("deepseek", "openai", "claude", "gemini",
                 "zhipu", "kimi", "qwen", "doubao", "yi"):
        preset = PROVIDER_PRESETS[name]
        if os.getenv(preset["api_key_env"]):
            return name

    return "openai"  # 默认


def _build_openai_provider(
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    max_tokens: Optional[int],
) -> Any:
    """构建 OpenAI 兼容的 LangChain Chat Model。"""
    from langchain_openai import ChatOpenAI

    # 智能补 /v1 后缀
    normalized_url = base_url.rstrip("/")
    if not normalized_url.endswith("/v1"):
        normalized_url = normalized_url + "/v1"

    # 默认 16384 tokens, 避免 Step 3/Step 4 等输出大量 JSON 时被截断
    effective_max_tokens = (
        max_tokens if max_tokens is not None
        else int(os.getenv("LLM_MAX_TOKENS", "16384"))
    )

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=effective_max_tokens,
        api_key=api_key,
        base_url=normalized_url,
        timeout=int(os.getenv("LLM_TIMEOUT", "180")),
    )


def _build_anthropic_provider(
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: Optional[int],
) -> Any:
    """构建 Anthropic Claude 原生 Chat Model。"""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as e:
        raise RuntimeError(
            "使用 Claude 需要安装 langchain-anthropic:\n"
            "  pip install langchain-anthropic"
        ) from e

    # Claude 必须设置 max_tokens, 默认 16384
    if max_tokens is None:
        max_tokens = 16384

    return ChatAnthropic(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        timeout=int(os.getenv("LLM_TIMEOUT", "120")),
    )


@lru_cache(maxsize=8)
def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    provider: Optional[str] = None,
):
    """获取 LLM 客户端实例 (带缓存)。

    Args:
        model: 模型名, 覆盖默认值
        temperature: 采样温度 (默认 0.7)
        max_tokens: 最大输出 token (Claude 必须设, OpenAI 可选)
        provider: Provider 名, 覆盖 LLM_PROVIDER 环境变量

    Returns:
        LangChain Chat Model, 调用 .invoke(messages) 返回 AIMessage
    """
    # 0. 检查 DB 覆盖配置 (前端模型管理打通)
    override = get_llm_override()
    if override and not provider:
        # 使用前端选择的模型配置
        ovr_provider = override.get("provider_key")
        ovr_protocol = override.get("protocol", "openai")

        if ovr_protocol == "openai":
            ovr_base_url = override.get("base_url") or "https://api.openai.com/v1"
            ovr_model = model or override.get("model") or "gpt-4o"
            ovr_temp = temperature if temperature is not None else (override.get("temperature") or 0.7)
            ovr_max_tokens = max_tokens if max_tokens is not None else override.get("max_tokens")
            return _build_openai_provider(
                api_key=override["api_key"],
                base_url=ovr_base_url,
                model=ovr_model,
                temperature=ovr_temp,
                max_tokens=ovr_max_tokens,
            )
        elif ovr_protocol == "anthropic":
            ovr_model = model or override.get("model") or "claude-sonnet-4-20250514"
            ovr_temp = temperature if temperature is not None else (override.get("temperature") or 0.7)
            ovr_max_tokens = max_tokens if max_tokens is not None else override.get("max_tokens")
            return _build_anthropic_provider(
                api_key=override["api_key"],
                model=ovr_model,
                temperature=ovr_temp,
                max_tokens=ovr_max_tokens,
            )

    # 1. 确定 Provider
    name = (provider or _detect_provider()).lower()
    if name not in PROVIDER_PRESETS:
        raise RuntimeError(
            f"未知的 LLM Provider: {name}\n"
            f"支持的 Provider: {list(PROVIDER_PRESETS.keys())}"
        )
    preset = PROVIDER_PRESETS[name]

    # 2. 读取 API Key
    api_key = os.getenv(preset["api_key_env"])
    # 回退: deepseek 也可以读 OPENAI_API_KEY (兼容旧配置)
    if not api_key and name == "deepseek":
        api_key = os.getenv("OPENAI_API_KEY")
    # 回退: openai 也可以读 DEEPSEEK_API_KEY (反之亦然)
    if not api_key and name == "openai":
        api_key = os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise RuntimeError(
            f"Provider {name} 需要 {preset['api_key_env']} 环境变量\n"
            f"在 .env 中设置: {preset['api_key_env']}=你的密钥"
        )

    # 3. 读取模型名
    model_name = (
        model
        or os.getenv(preset["model_env"])
        or preset["default_model"]
    )

    # 4. 读取温度
    temp = temperature
    if temp is None:
        temp = float(os.getenv("LLM_TEMPERATURE", "0.7"))

    # 5. 按协议类型构建
    if preset["protocol"] == "openai":
        base_url = (
            os.getenv(preset["base_url_env"])
            if preset["base_url_env"]
            else None
        ) or preset["base_url"]

        return _build_openai_provider(
            api_key=api_key,
            base_url=base_url,
            model=model_name,
            temperature=temp,
            max_tokens=max_tokens,
        )
    elif preset["protocol"] == "anthropic":
        return _build_anthropic_provider(
            api_key=api_key,
            model=model_name,
            temperature=temp,
            max_tokens=max_tokens,
        )
    else:
        raise RuntimeError(f"未知协议: {preset['protocol']}")


# 向后兼容: 暴露 ChatOpenAI 让老代码可以 import
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None


__all__ = [
    "get_llm",
    "ChatOpenAI",
    "PROVIDER_PRESETS",
    "set_llm_override",
    "clear_llm_override",
    "get_llm_override",
]