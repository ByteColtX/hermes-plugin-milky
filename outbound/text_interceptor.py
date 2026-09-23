"""普通文本出站的精确拦截规则。"""

from __future__ import annotations

from collections.abc import Collection

# 上游文案来源：hermes-agent/gateway/run_turn.py::_UNEXPECTED_SILENCE_REPLY；
# 上游修改文案时，须同步更新此登记值和对应测试。
HERMES_UNEXPECTED_SILENCE_REPLY = (
    "⚠️ The model returned only a silence marker for a message that needed a reply. "
    "Try again or rephrase."
)

OUTBOUND_TEXT_INTERCEPTIONS = (HERMES_UNEXPECTED_SILENCE_REPLY,)


def should_intercept_text(
    text: object,
    registered_texts: Collection[str] = OUTBOUND_TEXT_INTERCEPTIONS,
) -> bool:
    """仅当文本与某条已登记完整字符串相等时返回 True。"""

    return isinstance(text, str) and text in registered_texts
