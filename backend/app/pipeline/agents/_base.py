"""Agent 基类 —— 共享 LLM 调用 + JSON 解析 + Schema 校验 + 审计。"""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from ..graph.state import GraphState
from ..utils import get_llm, get_logger, safe_parse_json

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_JSON_PARSE_RETRIES = 2


class BaseAgent:
    """所有 Step Agent 的基类。

    关键能力:
    - invoke_llm_json(): LLM 调用 -> JSON 提取 -> Pydantic 校验 -> 失败重试
    - audit(): 写入 state["messages"] 用于 LangGraph 追踪
    - get_state_field / update_state: 标准化 state 访问
    """

    name: str = "base"

    # 子类可覆盖: 该节点期望的输出 Schema
    output_schema: type[BaseModel] | None = None

    # 子类可覆盖: 该节点的核心 system prompt
    system_prompt: str = "You are a helpful assistant."

    # 子类可覆盖: 单次 LLM 调用参数
    temperature: float = 0.7
    max_tokens: int | None = None

    # ---------- 子类入口约定 ----------
    def __call__(self, state: GraphState) -> dict[str, Any]:
        """LangGraph 节点入口约定, 子类通常不应覆盖。

        流程: invoke_llm_json -> parse -> validate -> audit -> return dict
        """
        raise NotImplementedError

    # ---------- 通用工具 ----------
    def _build_messages(
        self,
        user_prompt: str,
        schema_hint: str | None = None,
    ) -> list:
        """组装 SystemMessage + HumanMessage, 注入 JSON Schema 契约。"""
        system_content = self.system_prompt
        if schema_hint:
            system_content += f"\n\n## 输出 JSON Schema 契约\n{schema_hint}"
        system_content += (
            "\n\n## 输出要求\n"
            "- 严格输出合法 JSON, 不要包含 ```json 之外的解释\n"
            "- 字段名严格匹配 Schema, 枚举值使用小写 snake_case\n"
            "- 列表字段即使为空也要保留为 []"
        )
        return [
            SystemMessage(content=system_content),
            HumanMessage(content=user_prompt),
        ]

    def invoke_llm_json(
        self,
        user_prompt: str,
        schema: type[T],
        schema_json: dict[str, Any] | None = None,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """调用 LLM -> 解析 JSON -> 用 Pydantic 校验。

        失败重试策略:
        - 解析失败: 把原始输出回灌给 LLM, 让它修正
        - 校验失败: 把 ValidationError 信息回灌, 让它修正
        - 最多 MAX_JSON_PARSE_RETRIES 次
        """
        llm = get_llm(temperature=temperature or self.temperature,
                       max_tokens=max_tokens or self.max_tokens)
        schema_hint = json.dumps(schema_json or schema.model_json_schema(),
                                 ensure_ascii=False, indent=2)

        last_error: Exception | None = None
        last_raw: str = ""
        prompt = user_prompt

        for attempt in range(MAX_JSON_PARSE_RETRIES + 1):
            messages = self._build_messages(prompt, schema_hint=schema_hint)
            response: AIMessage = llm.invoke(messages)
            last_raw = response.content if isinstance(response.content, str) else str(response.content)

            # 1) JSON 提取
            try:
                data = safe_parse_json(last_raw)
            except ValueError as e:
                last_error = e
                logger.warning("[%s] 第 %d 次 JSON 提取失败: %s", self.name, attempt + 1, e)
                prompt = (
                    f"{user_prompt}\n\n"
                    f"⚠️ 你上一次的输出无法被解析为 JSON。原始输出:\n```\n{last_raw[:800]}\n```\n"
                    "请只输出合法 JSON。"
                )
                continue

            # 2) Pydantic 校验
            try:
                instance = schema.model_validate(data)
                logger.info("[%s] 第 %d 次尝试: JSON 解析+Schema 校验通过 ✅", self.name, attempt + 1)
                return instance
            except ValidationError as e:
                last_error = e
                logger.warning("[%s] 第 %d 次 Pydantic 校验失败:\n%s",
                               self.name, attempt + 1, e)
                prompt = (
                    f"{user_prompt}\n\n"
                    f"⚠️ 你的输出不符合 JSON Schema, 错误如下:\n{e}\n\n"
                    f"原始输出片段:\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)[:800]}\n```\n"
                    "请修正后重新输出。"
                )
                continue

        # 全部失败
        logger.error("[%s] 全部 %d 次尝试失败。最后错误: %s\n原始输出: %s",
                     self.name, MAX_JSON_PARSE_RETRIES + 1, last_error, last_raw[:1500])
        raise RuntimeError(
            f"[{self.name}] LLM 输出在 {MAX_JSON_PARSE_RETRIES + 1} 次尝试后仍无法通过校验: {last_error}"
        )

    def audit(self, state: GraphState, role: str, content: str) -> None:
        """写入审计日志(直接修改传入的 dict 引用, LangGraph 会自动合并)。"""
        msgs = state.get("messages", [])
        if msgs is None:
            msgs = []
        msgs.append({"role": role, "content": content, "agent": self.name})
        state["messages"] = msgs


__all__ = ["BaseAgent"]
