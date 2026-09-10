"""LLM Provider 抽象（talk-002）。

OpenAI 兼容协议（不绑死供应商：DeepSeek/通义/Kimi/glm 等均可）。
MockLLMProvider 离线生成（测试/无 key 时用）。
get_llm_provider 按 ai_config 动态构造（DB 优先，.env 兜底）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from openai import OpenAI

from app.core.config import settings
from app.services.talk_engine.ai_config_service import EffectiveAIConfig

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """LLM 抽象接口。"""

    name: str = "base"

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """生成话术，返回非空字符串。失败抛异常（由调用方降级）。"""
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """离线 mock 生成（确定性，TC-TALK-05 用）。"""

    name = "mock"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # 从 user_prompt 提取关键信息生成一段合规话术（不调用网络）
        return (
            "【mock 生成】您好，经核查您的平台使用费订单尚未结清。"
            "为避免影响后续投标资格与平台使用，请尽快登录平台完成缴费。"
            "如有疑问请联系平台客服。"
        )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容协议实现。

    用官方 openai SDK（base_url 原样传入，不手动拼路径）。
    兼容 DeepSeek/通义/Kimi/glm 等任何 OpenAI 兼容服务。
    """

    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, model: str):
        if not api_key:
            raise ValueError("OpenAICompatibleProvider 缺 api_key")
        if not base_url:
            raise ValueError("OpenAICompatibleProvider 缺 base_url")
        if not model:
            raise ValueError("OpenAICompatibleProvider 缺 model")
        self.api_key = api_key
        self.base_url = base_url  # 原样传入 SDK，不 rstrip/不拼路径
        self.model = model
        # SDK 自行处理鉴权与 URL 拼接
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=settings.LLM_TIMEOUT,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        content = resp.choices[0].message.content
        if not content or not content.strip():
            raise ValueError("LLM 返回空内容")
        return content.strip()


def get_llm_provider(eff: EffectiveAIConfig) -> LLMProvider:
    """按生效配置构造 provider。"""
    if eff.provider == "openai_compatible":
        return OpenAICompatibleProvider(
            api_key=eff.api_key or "",
            base_url=eff.base_url or "",
            model=eff.model or "",
        )
    return MockLLMProvider()


__all__ = [
    "LLMProvider",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "get_llm_provider",
]
