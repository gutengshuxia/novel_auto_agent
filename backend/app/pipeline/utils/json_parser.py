"""鲁棒 JSON 解析 —— LLM 输出经常夹杂 ```json 围栏或前后杂质。

轻量截断挽救: 仅在围栏内 JSON 缺闭合括号时, 尝试补全。
不做激进挽救 (避免错误解析半截 JSON 后通过 Pydantic 校验失败)。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .logger import get_logger

logger = get_logger(__name__)

# 围栏正则: ```json ... ``` 或 ``` ... ```
# 容忍尾随 ``` 缺失 (LLM 输出被截断时常见)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)(?:\s*```|$)", re.DOTALL)


def _sanitize_control_chars(text: str) -> str:
    """清理 JSON 字符串值内的非法控制字符 (literal 换行/制表符)。

    JSON 规范要求字符串内的换行必须是 \\n 转义, 不能是真实换行符。
    LLM 输出经常在字符串值内包含真实换行, 导致 json.loads 失败。
    """
    # 将字符串值内的真实换行符替换为 \\n 转义
    # 策略: 在双引号内的 \n \r \t 替换为转义序列
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _try_complete_truncated_json(text: str) -> str:
    """截断挽救: 当 LLM 输出被 max_tokens 截断时, 尝试补全闭合括号。

    处理顺序:
    1. 清理字符串内非法控制字符
    2. 检测并闭合未关闭的字符串 (quote tracking)
    3. 补全缺失的 } ] 括号
    """
    if not text:
        return text

    # 先清理控制字符
    text = _sanitize_control_chars(text)

    # 用状态机跟踪是否在字符串内, 判断最后一个字符串是否未关闭
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    # 如果截断在字符串内部, 先关闭字符串
    if in_string:
        text += '"'

    # 补全括号 (忽略字符串内的括号 —— 简化处理, 直接计数)
    open_braces = text.count("{")
    close_braces = text.count("}")
    if open_braces > close_braces:
        text = text + ("}" * (open_braces - close_braces))

    open_brackets = text.count("[")
    close_brackets = text.count("]")
    if open_brackets > close_brackets:
        text = text + ("]" * (open_brackets - close_brackets))

    return text


def safe_parse_json(raw: str) -> Any:
    """尝试从 LLM 原始输出中提取并解析 JSON。

    策略 (按顺序尝试):
    1. 整段 json.loads (先清理控制字符)
    2. 抽取 ```json ... ``` 围栏内容 (再 json.loads)
    3. 围栏内 + 截断挽救 (闭合字符串 + 补括号)
    4. 截取首个 { ... } 或 [ ... ] + 截断挽救
    """
    if not raw or not raw.strip():
        raise ValueError("LLM 输出为空,无法解析为 JSON。")

    text = raw.strip()

    # 1. 整段直接解析 (先尝试原文, 再尝试清理控制字符)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_sanitize_control_chars(text))
    except json.JSONDecodeError:
        pass

    # 2. 抽取围栏内 + 直接解析
    fence_match = _JSON_FENCE.search(text)
    if fence_match:
        inner = fence_match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass
        # 2b. 清理控制字符后重试
        try:
            return json.loads(_sanitize_control_chars(inner))
        except json.JSONDecodeError:
            pass
        # 3. 围栏内 + 截断挽救 (闭合字符串 + 补括号)
        try:
            return json.loads(_try_complete_truncated_json(inner))
        except json.JSONDecodeError:
            pass

    # 4. 截取首个 { ... } 或 [ ... ]
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
            # 截断挽救
            try:
                return json.loads(_try_complete_truncated_json(candidate))
            except json.JSONDecodeError:
                continue
        # 只有开头没有结尾 (完全截断) —— 从开头截取到末尾并挽救
        if start != -1 and (end == -1 or end <= start):
            candidate = text[start:]
            try:
                return json.loads(_try_complete_truncated_json(candidate))
            except json.JSONDecodeError:
                continue

    logger.error("无法解析 LLM 输出为 JSON。原始内容前 500 字符:\\n%s", text[:500])
    raise ValueError("LLM 输出中未找到合法 JSON。")


__all__ = ["safe_parse_json"]
