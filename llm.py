"""统一 LLM 调用层，通过 Provider 路由支持多服务商"""

import os
from typing import Optional

from config import AppConfig, ProviderConfig, resolve_provider


def _get_api_key(provider: ProviderConfig) -> str:
    """从环境变量获取 API key"""
    if provider.api_key_env:
        key = os.environ.get(provider.api_key_env, "")
        if key:
            return key
    return ""


def _call_anthropic(
    model: str,
    system_prompt: str,
    messages: list,
    api_key: str,
    max_tokens: int,
    temperature: float,
) -> str:
    """使用 Anthropic 原生 SDK 调用"""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
        temperature=temperature,
    )
    return response.content[0].text


def _call_openai_compatible(
    model: str,
    system_prompt: str,
    messages: list,
    api_key: str,
    base_url: str,
    max_tokens: Optional[int],
    temperature: float,
) -> str:
    """使用 OpenAI 兼容接口调用（适用于 OpenAI、DeepSeek、Moonshot、MiniMax 等）"""
    from openai import OpenAI

    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    client = OpenAI(**kwargs)

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    create_kwargs = {
        "model": model,
        "messages": full_messages,
        "temperature": temperature,
    }
    if max_tokens:
        create_kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**create_kwargs)
    return response.choices[0].message.content


def call_llm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    config: AppConfig,
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
) -> str:
    """
    统一调用 LLM。自动根据 provider 路由到对应的 SDK。

    Args:
        model: "provider/model_name" 格式，如 "deepseek/deepseek-chat"
        system_prompt: 系统 prompt
        user_prompt: 用户 prompt
        config: 应用配置
        max_tokens: 最大输出 token 数
        temperature: 温度参数
    Returns:
        模型输出的文本
    """
    messages = [{"role": "user", "content": user_prompt}]
    return _route_call(model, system_prompt, messages, config, max_tokens, temperature)


def call_llm_with_history(
    model: str,
    system_prompt: str,
    messages: list,
    config: AppConfig,
    max_tokens: Optional[int] = None,
    temperature: float = 0.3,
) -> str:
    """
    带历史消息的 LLM 调用（用于研讨模式多轮对话）。

    Args:
        model: "provider/model_name" 格式
        system_prompt: 系统 prompt
        messages: 消息历史 [{"role": "user"/"assistant", "content": "..."}]
        config: 应用配置
        max_tokens: 最大输出 token 数
        temperature: 温度参数
    Returns:
        模型输出的文本
    """
    return _route_call(model, system_prompt, messages, config, max_tokens, temperature)


def _route_call(
    model: str,
    system_prompt: str,
    messages: list,
    config: AppConfig,
    max_tokens: Optional[int],
    temperature: float,
) -> str:
    """根据 provider 路由到对应的调用方式"""
    provider, model_only = resolve_provider(model, config)
    api_key = _get_api_key(provider)

    if not provider.compatible_mode:
        # Anthropic 原生 SDK
        return _call_anthropic(
            model=model_only,
            system_prompt=system_prompt,
            messages=messages,
            api_key=api_key,
            max_tokens=max_tokens or 4096,
            temperature=temperature,
        )
    else:
        # OpenAI 兼容接口（OpenAI、DeepSeek、Moonshot、MiniMax 等）
        return _call_openai_compatible(
            model=model_only,
            system_prompt=system_prompt,
            messages=messages,
            api_key=api_key,
            base_url=provider.base_url,
            max_tokens=max_tokens,
            temperature=temperature,
        )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    粗略估算 API 调用费用（美元）。
    中国模型按人民币定价，已折算为美元（汇率约 7.2）。
    """
    # 每百万 token 的价格 (input_usd, output_usd)
    pricing = {
        # Anthropic
        "anthropic/claude-opus-4-20250115": (15.0, 75.0),
        "anthropic/claude-sonnet-4-20250514": (3.0, 15.0),
        "anthropic/claude-haiku-4-5-20251001": (0.8, 4.0),
        # OpenAI
        "openai/gpt-4o": (2.5, 10.0),
        "openai/gpt-4o-mini": (0.15, 0.6),
        "openai/o3": (10.0, 40.0),
        # DeepSeek (¥ -> $ at ~7.2)
        "deepseek/deepseek-chat": (0.14, 0.28),       # ¥1/¥2 per M tokens
        "deepseek/deepseek-reasoner": (0.55, 2.19),   # ¥4/¥16 per M tokens
        # Moonshot (¥ -> $)
        "moonshot/moonshot-v1-8k": (1.67, 1.67),      # ¥12 per M tokens
        "moonshot/moonshot-v1-32k": (3.33, 3.33),     # ¥24 per M tokens
        "moonshot/moonshot-v1-128k": (8.33, 8.33),    # ¥60 per M tokens
        # MiniMax (¥ -> $)
        "minimax/MiniMax-Text-01": (0.14, 0.14),      # ¥1 per M tokens
    }

    rate = pricing.get(model, (1.0, 2.0))  # 默认便宜价格
    cost = (input_tokens / 1_000_000) * rate[0] + (output_tokens / 1_000_000) * rate[1]
    return cost
