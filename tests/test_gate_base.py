"""验证 Gate 基类只依赖规范化输入。"""

from __future__ import annotations

from gates.base import GateContext, GateResult


def test_gate_context_uses_canonical_identity_and_fail_closed_mute_defaults() -> None:
    """Gate 上下文应使用 friend/group 和完整 chat key，不携带消息正文。"""

    context = GateContext(
        self_id="100",
        sender_id="200",
        scene="group",
        chat_key="group:300",
    )

    assert context.self_id == "100"
    assert context.sender_id == "200"
    assert context.scene == "group"
    assert context.chat_key == "group:300"
    assert context.member_mute == "muted"
    assert context.whole_mute == "muted"
    assert not hasattr(context, "text")
    assert not hasattr(context, "raw")


def test_gate_result_requires_a_diagnostic_reason() -> None:
    """Gate 结果应始终携带可观察的诊断原因。"""

    result = GateResult(allow=False, reason="self_message")

    assert result.allow is False
    assert result.reason == "self_message"
