"""验证未知出站结果、传输阶段诊断和宿主兼容边界。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from config import load_config
from milky.client import ActionError, HttpxTransportError, MilkyClient
from milky.observability import log_event, sanitize_fields
from outbound.sender import MilkyOutboundSender, OutboundSendResult

_CONFIG_ENV = {
    "MILKY_BASE_URL": "https://fixture.invalid/milky",
    "MILKY_ACCESS_TOKEN": "synthetic-token",
}


@dataclass
class DelayedResponseLossTransport:
    """模拟服务端完成 Action 但客户端响应路径中断。"""

    completion_delay: float = 0.01

    def __post_init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.server_completed = asyncio.Event()
        self.server_task: asyncio.Task[None] | None = None
        self.close_calls = 0

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> Any:
        """记录请求后让服务端延迟完成，再模拟响应读取异常。"""

        del headers, body, timeout
        self.requests.append((method, url))
        self.server_task = asyncio.create_task(self._complete_server_side())
        raise HttpxTransportError("synthetic response loss", phase="read")

    async def _complete_server_side(self) -> None:
        """在客户端已返回未知结果后标记服务端处理完成。"""

        await asyncio.sleep(self.completion_delay)
        self.server_completed.set()

    async def wait_server_completion(self) -> None:
        """等待模拟服务端完成并收敛后台任务。"""

        await self.server_completed.wait()
        assert self.server_task is not None
        await self.server_task

    async def close(self) -> None:
        """记录 transport 关闭。"""

        self.close_calls += 1


@dataclass
class RecordingOutboundClient:
    """记录一次出站 Action，并返回合成的安全失败。"""

    error: ActionError | None = None
    calls: list[tuple[str, int, list[dict[str, Any]]]] = field(default_factory=list)

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> object:
        """记录群消息 Action。"""

        self.calls.append(("send_group_message", group_id, message))
        if self.error is not None:
            raise self.error
        return type("Result", (), {"message_id": "fixture-message"})()

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> object:
        """记录私聊消息 Action。"""

        self.calls.append(("send_private_message", user_id, message))
        if self.error is not None:
            raise self.error
        return type("Result", (), {"message_id": "fixture-message"})()


@dataclass
class FakeHermesGateway:
    """表达宿主必须提供的未知结果终态 contract。"""

    fallback_calls: list[str] = field(default_factory=list)

    async def send_with_fallback(
        self,
        sender: MilkyOutboundSender,
        chat_id: str,
        content: object,
    ) -> OutboundSendResult:
        """只对显式安全的宿主失败执行 fallback；未知结果直接返回。"""

        result = await sender.send(chat_id, content)
        if result.success or not self._fallback_is_safe(result):
            return result
        self.fallback_calls.append(chat_id)
        return await sender.send(chat_id, f"plain text: {content}")

    @staticmethod
    def _fallback_is_safe(result: object) -> bool:
        """要求宿主获得独立的、发送前安全标记后才允许 fallback。"""

        return (
            getattr(result, "error_kind", None) == "safe_preflight"
            and getattr(result, "fallback_allowed", False) is True
        )


@dataclass
class BlockingMuteTracker:
    """阻塞刷新以验证发送结果不依赖只读维护完成。"""

    calls: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def refresh_after_send_failure(self, target: str) -> bool:
        """等待测试释放刷新任务。"""

        self.calls.append(target)
        self.started.set()
        await self.release.wait()
        return True


@dataclass
class OutcomeMuteTracker:
    """提供成功、失败和超时三种合成刷新结果。"""

    outcome: str

    def __post_init__(self) -> None:
        self.started = asyncio.Event()
        self.completed = asyncio.Event()

    async def refresh_after_send_failure(self, target: str) -> bool:
        """按 fixture 选择刷新终态。"""

        del target
        self.started.set()
        if self.outcome == "failure":
            self.completed.set()
            raise RuntimeError("synthetic refresh detail")
        if self.outcome == "timeout":
            await asyncio.sleep(60)
        self.completed.set()
        return True


@dataclass
class AcceptedUnknownOutboundClient:
    """模拟服务端已接受首个请求、客户端只收到未知结果。"""

    calls: list[tuple[str, int, list[dict[str, Any]]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.server_completed = asyncio.Event()

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> object:
        """记录一次已接受的群消息并丢失响应。"""

        self.calls.append(("send_group_message", group_id, message))
        self.server_completed.set()
        raise ActionError("transport_unknown", "send_group_message", "synthetic response loss")

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> object:
        """记录一次已接受的私聊消息并丢失响应。"""

        self.calls.append(("send_private_message", user_id, message))
        self.server_completed.set()
        raise ActionError("transport_unknown", "send_private_message", "synthetic response loss")


@dataclass
class BlockingActionTransport:
    """阻塞一次 Action 请求以验证显式取消边界。"""

    def __post_init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.close_calls = 0

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> Any:
        """等待取消，不生成 Action 响应。"""

        del method, url, headers, body, timeout
        self.calls += 1
        self.started.set()
        await self.release.wait()
        raise AssertionError("fixture request should be cancelled")

    async def close(self) -> None:
        """记录 transport 关闭。"""

        self.close_calls += 1


def test_server_completion_after_client_response_loss_is_unknown() -> None:
    """服务端完成但响应丢失时不得伪造成功或再次提交。"""

    transport = DelayedResponseLossTransport()
    client = MilkyClient(load_config(_CONFIG_ENV), transport=transport)

    async def scenario() -> None:
        with pytest.raises(ActionError) as error_info:
            await client.send_group_message(
                700000001,
                [{"type": "text", "data": {"text": "fixture"}}],
            )
        await transport.wait_server_completion()
        await client.close()

        error = error_info.value
        assert error.classification == "transport_unknown"
        assert error.phase == "read"

    asyncio.run(scenario())

    assert transport.requests == [("POST", "https://fixture.invalid/milky/api/send_group_message")]
    assert transport.close_calls == 1


@pytest.mark.parametrize("chat_id", ["group:700000001", "dm:800000001"])
def test_outbound_preserves_unknown_terminal_result_without_resubmitting(chat_id: str) -> None:
    """群聊和私聊未知结果均只调用一次，且保持原消息和不可重试语义。"""

    client = RecordingOutboundClient(
        error=ActionError("transport_unknown", "send_message", "synthetic detail")
    )
    sender = MilkyOutboundSender(client)
    content = "原始消息 fixture"

    result = asyncio.run(sender.send(chat_id, content))

    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert result.classification == "transport_unknown"
    assert result.retryable is False
    assert len(client.calls) == 1
    assert client.calls[0][2] == [{"type": "text", "data": {"text": content}}]


@pytest.mark.parametrize(
    ("error_kind", "content"),
    [
        ("invalid_input", "   "),
        ("rejected", "明确拒绝 fixture"),
        ("transport_unknown", "未知结果 fixture"),
    ],
)
def test_fake_gateway_contract_never_fallbacks_plugin_terminal_failures(
    error_kind: str, content: str
) -> None:
    """宿主 contract 不得把 plugin 的终态失败改写为第二次可见消息。"""

    client = RecordingOutboundClient(
        error=None
        if error_kind == "invalid_input"
        else ActionError(error_kind, "send_message", "synthetic detail")
    )
    sender = MilkyOutboundSender(client)
    gateway = FakeHermesGateway()

    result = asyncio.run(gateway.send_with_fallback(sender, "group:700000001", content))

    assert result.success is False
    assert result.error_kind == error_kind
    assert gateway.fallback_calls == []
    expected_calls = 0 if error_kind == "invalid_input" else 1
    assert len(client.calls) == expected_calls


def test_fake_gateway_contract_allows_fallback_only_for_explicit_safe_failure() -> None:
    """fallback 分支必须由宿主显式证明发送尚未进入网络边界。"""

    safe_failure = type(
        "SafePreflightFailure",
        (),
        {
            "success": False,
            "error_kind": "safe_preflight",
            "retryable": False,
            "fallback_allowed": True,
        },
    )()
    unknown_failure = type(
        "UnknownFailure",
        (),
        {"success": False, "error_kind": "transport_unknown", "retryable": False},
    )()

    assert FakeHermesGateway._fallback_is_safe(safe_failure) is True
    assert FakeHermesGateway._fallback_is_safe(unknown_failure) is False


def test_fake_gateway_contract_returns_success_without_fallback() -> None:
    """成功结果直接结束，宿主不得额外发送消息。"""

    client = RecordingOutboundClient()
    sender = MilkyOutboundSender(client)
    gateway = FakeHermesGateway()

    result = asyncio.run(gateway.send_with_fallback(sender, "dm:800000001", "成功 fixture"))

    assert result.success is True
    assert gateway.fallback_calls == []
    assert len(client.calls) == 1


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout"])
def test_refresh_outcome_never_changes_unknown_send_result(outcome: str) -> None:
    """刷新完成、失败或超时均不得改写原始未知结果。"""

    tracker = OutcomeMuteTracker(outcome)
    client = RecordingOutboundClient(
        error=ActionError("transport_unknown", "send_group_message", "synthetic detail")
    )
    sender = MilkyOutboundSender(client, mute_tracker=tracker)

    async def scenario() -> None:
        result = await asyncio.wait_for(sender.send("group:700000001", "一次"), timeout=0.1)
        assert result.error_kind == "transport_unknown"
        assert result.retryable is False
        await tracker.started.wait()
        if outcome != "timeout":
            await tracker.completed.wait()
        await sender.close()
        assert result.error_kind == "transport_unknown"
        assert result.retryable is False

    asyncio.run(scenario())


def test_accepted_unknown_send_refreshes_once_without_second_message() -> None:
    """服务端接受首条消息后，状态刷新也不得触发第二条消息。"""

    tracker = OutcomeMuteTracker("success")
    client = AcceptedUnknownOutboundClient()
    sender = MilkyOutboundSender(client, mute_tracker=tracker)

    async def scenario() -> None:
        result = await sender.send("group:700000001", "服务端已接受")
        await client.server_completed.wait()
        await tracker.completed.wait()
        assert result.error_kind == "transport_unknown"
        await sender.close()

    asyncio.run(scenario())

    assert len(client.calls) == 1
    assert client.calls[0][2] == [{"type": "text", "data": {"text": "服务端已接受"}}]


def test_client_cancellation_is_not_converted_to_success_or_fallback() -> None:
    """客户端取消必须保留取消边界，不能伪装成失败可重发。"""

    transport = BlockingActionTransport()
    client = MilkyClient(load_config(_CONFIG_ENV), transport=transport)

    async def scenario() -> None:
        task = asyncio.create_task(
            client.send_group_message(
                700000001,
                [{"type": "text", "data": {"text": "cancel fixture"}}],
            )
        )
        await transport.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await client.close()

    asyncio.run(scenario())

    assert transport.calls == 1
    assert transport.close_calls == 1


def test_second_independent_message_can_send_after_unknown_result() -> None:
    """禁止的是未知结果重发，不是后续独立消息。"""

    client = RecordingOutboundClient(
        error=ActionError("transport_unknown", "send_group_message", "synthetic detail")
    )
    sender = MilkyOutboundSender(client)

    async def scenario() -> tuple[OutboundSendResult, OutboundSendResult]:
        first = await sender.send("group:700000001", "第一次")
        client.error = None
        second = await sender.send("group:700000001", "第二次独立消息")
        return first, second

    first, second = asyncio.run(scenario())

    assert first.error_kind == "transport_unknown"
    assert second.success is True
    assert len(client.calls) == 2
    assert client.calls[0][2] != client.calls[1][2]


def test_e2e_server_completion_unknown_result_has_one_visible_send() -> None:
    """串联 fake Milky、Action client、刷新、sender 和宿主 contract。"""

    transport = DelayedResponseLossTransport()
    client = MilkyClient(load_config(_CONFIG_ENV), transport=transport)
    tracker = OutcomeMuteTracker("success")
    sender = MilkyOutboundSender(client, mute_tracker=tracker)
    gateway = FakeHermesGateway()

    async def scenario() -> OutboundSendResult:
        result = await gateway.send_with_fallback(sender, "group:700000001", "一次可见消息")
        await transport.wait_server_completion()
        await tracker.completed.wait()
        await sender.close()
        await client.close()
        return result

    result = asyncio.run(scenario())

    assert result.error_kind == "transport_unknown"
    assert result.retryable is False
    assert gateway.fallback_calls == []
    assert transport.requests == [("POST", "https://fixture.invalid/milky/api/send_group_message")]


def test_user_evidence_fixture_is_sanitized_and_preserves_open_diagnostic() -> None:
    """用户证据只保留时序结论，不能伪造底层异常类型。"""

    fixture_path = Path(__file__).parent / "fixtures" / "unknown_send_outcome_timeline.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    assert payload["conclusions"] == {
        "duplicate_send_confirmed": True,
        "transport_exception_type_confirmed": False,
        "live_message_id_included": False,
        "live_identity_included": False,
    }
    assert "Authorization" not in repr(payload)
    assert "message_seq" not in repr(payload)
    assert all("path" not in event for event in payload["events"])


def test_group_refresh_is_background_and_sender_close_cleans_it_up() -> None:
    """群状态刷新不得阻塞未知结果，sender 停止时必须取消刷新任务。"""

    tracker = BlockingMuteTracker()
    client = RecordingOutboundClient(
        error=ActionError("transport_unknown", "send_group_message", "synthetic detail")
    )
    sender = MilkyOutboundSender(client, mute_tracker=tracker)

    async def scenario() -> None:
        result = await asyncio.wait_for(sender.send("group:700000001", "一次"), timeout=0.1)
        assert result.error_kind == "transport_unknown"
        await tracker.started.wait()
        assert tracker.calls == ["group:700000001"]
        assert not tracker.release.is_set()
        await sender.close()
        assert not sender._refresh_tasks

    asyncio.run(scenario())


@pytest.mark.parametrize("phase", ["connect", "write", "read", "pool", "unknown"])
def test_transport_phase_is_a_safe_allowlisted_field(phase: str) -> None:
    """传输阶段只能使用固定枚举，不能携带异常或凭证文本。"""

    fields = sanitize_fields(
        {
            "stage": "action",
            "action": "send_group_message",
            "classification": "transport_unknown",
            "reason": "request_unknown",
            "transport_phase": phase,
            "duration_ms": 7.7,
        }
    )

    assert fields["transport_phase"] == phase

    with pytest.raises(ValueError):
        sanitize_fields({"transport_phase": "read: synthetic-token"})


def test_transport_phase_log_preserves_only_safe_diagnostics(caplog) -> None:
    """阶段日志应可关联但不得输出底层错误详情。"""

    logger = logging.getLogger("milky.unknown_send_outcomes")
    with caplog.at_level(logging.WARNING, logger=logger.name):
        log_event(
            logger,
            "milky_action_failed",
            logging.WARNING,
            stage="action",
            action="send_group_message",
            classification="transport_unknown",
            reason="request_unknown",
            transport_phase="read",
            duration_ms=7.7,
        )

    record = caplog.records[-1]
    assert record.transport_phase == "read"
    assert "synthetic-token" not in record.getMessage()
    assert "request body" not in record.getMessage()


@pytest.mark.parametrize(
    ("exception_name", "phase"),
    [
        ("ConnectError", "connect"),
        ("ConnectTimeout", "connect"),
        ("WriteError", "write"),
        ("WriteTimeout", "write"),
        ("ReadError", "read"),
        ("ReadTimeout", "read"),
        ("PoolTimeout", "pool"),
    ],
)
def test_httpx_transport_maps_error_types_to_safe_phases(exception_name: str, phase: str) -> None:
    """HTTPX 传输异常应映射为阶段字段且保持未知结果。"""

    httpx = pytest.importorskip("httpx")
    exception_type = getattr(httpx, exception_name)
    calls = 0

    def handler(request: object) -> object:
        nonlocal calls
        calls += 1
        raise exception_type("synthetic transport detail", request=request)

    from milky.client import HttpxTransport

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = MilkyClient(
        load_config(_CONFIG_ENV),
        transport=HttpxTransport(client=http_client),
    )

    async def scenario() -> None:
        with pytest.raises(ActionError) as error_info:
            await client.send_group_message(
                700000001,
                [{"type": "text", "data": {"text": "fixture"}}],
            )
        await client.close()
        assert error_info.value.classification == "transport_unknown"
        assert error_info.value.phase == phase

    asyncio.run(scenario())
    assert calls == 1
