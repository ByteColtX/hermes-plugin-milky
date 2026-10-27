"""验证固定 Tool 在没有 live adapter 的进程中按调用时配置执行。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from config import ConfigError, load_config
from milky.client import MilkyClient, TransportResponse
from outbound import tools as tools_module
from outbound.sender import MilkyOutboundSender
from outbound.tools import bind_sender, register_tools, unbind_sender

DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky/",
    "MILKY_ACCESS_TOKEN": "runtime-token",
}


def envelope(data: object) -> dict[str, object]:
    """构造一个合成 Milky envelope。"""

    return {"status": "ok", "retcode": 0, "data": data}


def http_response(payload: object) -> TransportResponse:
    """构造 JSON HTTP 响应。"""

    return TransportResponse(200, json.dumps(payload).encode("utf-8"), {})


@dataclass
class RecordingTransport:
    """记录请求、按顺序返回结果，并记录关闭。"""

    responses: list[object]
    requests: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """保存请求并返回下一个合成结果。"""

        self.requests.append({"method": method, "url": url, "body": json.loads(body)})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]

    async def close(self) -> None:
        """记录 transport 关闭。"""

        self.closed = True


class RecordingClient:
    """包装真实 client，并记录 close 调用。"""

    def __init__(self, client: MilkyClient) -> None:
        self._client = client
        self.closed = False

    async def call_tool(self, action: str, params: dict[str, object]) -> object:
        """把 Action 交给真实 client。"""

        return await self._client.call_tool(action, params)

    async def close(self) -> None:
        """记录 client 关闭。"""

        self.closed = True
        await self._client.close()


class ToolContext:
    """捕获宿主发现的 ToolSpec。"""

    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    def register_tool(self, **kwargs: Any) -> None:
        """保存一次工具注册。"""

        self.registered.append(kwargs)


class LiveToolClient:
    """记录 live sender 收到的 Action。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool(self, action: str, params: dict[str, object]) -> str:
        """记录 Action 并返回合成 body。"""

        self.calls.append((action, dict(params)))
        return json.dumps(envelope({"group_id": 700000001}))


def handlers() -> dict[str, Any]:
    """注册工具并返回按名字索引的 handler。"""

    context = ToolContext()
    register_tools(context)
    return {item["name"]: item["handler"] for item in context.registered}


def standalone_client(transport: RecordingTransport) -> RecordingClient:
    """构造走合成 transport 的 client。"""

    return RecordingClient(MilkyClient(load_config(DEFAULT_ENV), transport=transport))


def test_fixed_tool_runs_once_with_standalone_client_when_sender_unbound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有 live sender 时按调用时配置创建一次性 client，执行后关闭。"""

    unbind_sender()
    transport = RecordingTransport([http_response(envelope({"group_id": 700000001}))])
    client = standalone_client(transport)
    monkeypatch.setattr(tools_module, "load_config", lambda: load_config(DEFAULT_ENV))
    monkeypatch.setattr(tools_module, "MilkyClient", lambda config: client)
    try:
        result = json.loads(asyncio.run(handlers()["get_group_info"]({"group_id": 700000001})))
    finally:
        unbind_sender()

    assert result["data"] == {"group_id": 700000001}
    assert len(transport.requests) == 1
    assert transport.requests[0]["url"].endswith("/get_group_info")
    assert transport.requests[0]["body"] == {"group_id": 700000001}
    assert client.closed is True
    assert transport.closed is True


def test_fixed_tool_without_sender_reports_transport_unknown_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次性 client 的传输失败收敛为 transport_unknown，且最多一次请求。"""

    unbind_sender()
    transport = RecordingTransport([TimeoutError("timeout")])
    client = standalone_client(transport)
    monkeypatch.setattr(tools_module, "load_config", lambda: load_config(DEFAULT_ENV))
    monkeypatch.setattr(tools_module, "MilkyClient", lambda config: client)
    try:
        result = json.loads(asyncio.run(handlers()["get_group_info"]({"group_id": 700000001})))
    finally:
        unbind_sender()

    assert result == {
        "ok": False,
        "classification": "transport_unknown",
        "reason": "outcome_unknown",
        "error": "tool result is unknown",
        "retryable": False,
    }
    assert len(transport.requests) == 1
    assert client.closed is True


def test_fixed_tool_without_sender_classifies_unreadable_config_as_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 live adapter 且配置不可读时在网络前返回 unsupported。"""

    unbind_sender()

    def unavailable_config() -> object:
        raise ConfigError("configuration is unavailable")

    monkeypatch.setattr(tools_module, "load_config", unavailable_config)
    monkeypatch.setattr(
        tools_module,
        "MilkyClient",
        lambda config: pytest.fail("配置失败时不得创建 client"),
    )
    try:
        result = json.loads(asyncio.run(handlers()["get_group_info"]({"group_id": 700000001})))
    finally:
        unbind_sender()

    assert result == {
        "ok": False,
        "classification": "unsupported",
        "reason": "configuration_unavailable",
        "error": "tool is unavailable",
        "retryable": False,
    }


def test_fixed_tool_prefers_live_sender_over_standalone_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """live sender 已绑定时不创建一次性 client。"""

    live_client = LiveToolClient()
    bind_sender(MilkyOutboundSender(live_client))
    monkeypatch.setattr(
        tools_module,
        "MilkyClient",
        lambda config: pytest.fail("live sender 存在时不得创建一次性 client"),
    )
    try:
        result = json.loads(asyncio.run(handlers()["get_group_info"]({"group_id": 700000001})))
    finally:
        unbind_sender()

    assert result["data"] == {"group_id": 700000001}
    assert live_client.calls == [("get_group_info", {"group_id": 700000001})]


def test_fixed_tool_reports_closed_client_as_retryable() -> None:
    """live client 已关闭时返回可重试的本地原因码，不进入网络。"""

    transport = RecordingTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)
    bind_sender(MilkyOutboundSender(client))
    try:
        asyncio.run(client.close())
        result = json.loads(asyncio.run(handlers()["get_group_info"]({"group_id": 700000001})))
    finally:
        unbind_sender()

    assert result == {
        "ok": False,
        "classification": "unsupported",
        "reason": "client_closed",
        "error": "tool is unavailable",
        "retryable": True,
    }
    assert transport.requests == []


@pytest.mark.parametrize("count", [0, 51, -1])
def test_profile_like_count_outside_schema_range_fails_before_network(
    count: int,
) -> None:
    """count 超出 schema 声明的 1..50 时在网络前返回 invalid_input。"""

    client = LiveToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(
            asyncio.run(handlers()["send_profile_like"]({"user_id": 700000001, "count": count}))
        )
    finally:
        unbind_sender()

    assert result == {
        "ok": False,
        "classification": "invalid_input",
        "reason": "input_invalid",
        "error": "tool input is invalid",
        "retryable": False,
    }
    assert client.calls == []


def test_profile_like_accepts_schema_bounds() -> None:
    """count 的边界值 1 和 50 仍按一次 Action 发出。"""

    client = LiveToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        for count in (1, 50):
            asyncio.run(handlers()["send_profile_like"]({"user_id": 700000001, "count": count}))
    finally:
        unbind_sender()

    assert [params["count"] for _action, params in client.calls] == [1, 50]
