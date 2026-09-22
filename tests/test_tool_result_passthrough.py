"""验证 Milky Tool 响应在插件边界保持不透明。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config import load_config
from milky.client import ActionError, MilkyClient, TransportResponse
from outbound.sender import MilkyOutboundSender
from outbound.tools import bind_sender, register_tools, unbind_sender

DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky/",
    "MILKY_ACCESS_TOKEN": "runtime-token",
}
RAW_OUTCOMES = Path(__file__).parent / "fixtures" / "qq_tools" / "responses" / "raw_outcomes.json"


@dataclass
class RawTransport:
    """返回合成 body 并记录 HTTP 请求。"""

    responses: list[TransportResponse | BaseException]

    def __post_init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """记录请求并返回队首结果。"""

        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": body,
                "timeout": timeout,
            }
        )
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def close(self) -> None:
        """满足 client 生命周期协议。"""


class ToolHost:
    """捕获注册的工具，不提供任何结果变换 hook。"""

    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    def register_tool(self, **kwargs: Any) -> None:
        """保存 ToolSpec。"""

        self.registered.append(kwargs)


def response(body: bytes | str, *, status_code: int = 200) -> TransportResponse:
    """创建原始 HTTP 响应。"""

    return TransportResponse(
        status_code, body.encode("utf-8") if isinstance(body, str) else body, {}
    )


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (200, b'{"status":"ok","retcode":0,"data":{"future":true}}'),
        (200, b'{"status":"failed","retcode":1001,"message":"\\u62d2\\u7edd"}'),
        (500, b"<html>synthetic failure</html>"),
        (200, b"synthetic-not-json"),
        (200, b'["array",{"token":"fixture-token"}]'),
        (200, b"42"),
        (200, b"null"),
        (
            200,
            b'{"TOKEN":"top","nested":{"Authorization":"header","Password":"secret"}}',
        ),
        (200, b""),
        (200, b"prefix\xffsuffix"),
    ],
)
def test_tool_delivers_every_acquired_body_without_parser_or_redaction(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    body: bytes,
) -> None:
    """Tool body 应逐字节解码，不调用 envelope parser 或敏感键过滤。"""

    def fail_parser(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Tool path must not invoke parser")

    monkeypatch.setattr("milky.client.parse_envelope", fail_parser)
    monkeypatch.setattr("milky.client.parse_action_response", fail_parser)
    transport = RawTransport([response(body, status_code=status_code)])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    result = asyncio.run(client.call_tool("get_friend_info", {"user_id": 800000001}))

    assert result == body.decode("utf-8", errors="replace")
    assert isinstance(result, str)
    assert len(transport.requests) == 1


def test_raw_outcome_fixture_is_delivered_without_shape_or_key_filtering() -> None:
    """合成 fixture 中的未知字段和非对象 JSON 都保持原始 body。"""

    outcomes = json.loads(RAW_OUTCOMES.read_text(encoding="utf-8"))
    for payload in outcomes.values():
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        transport = RawTransport([response(body)])
        client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

        result = asyncio.run(client.call_tool("get_friend_info", {"user_id": 800000001}))

        assert result == body.decode("utf-8", errors="replace")


def test_tool_local_and_transport_categories_are_bounded_and_single_shot() -> None:
    """本地失败和未取得 body 只产生三类结果且不重试。"""

    transport = RawTransport([OSError("opaque")])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)
    with pytest.raises(ActionError) as transport_error:
        asyncio.run(client.call_tool("kick_group_member", {"group_id": 700000001}))
    assert transport_error.value.classification == "invalid_input"
    assert transport.requests == []

    transport = RawTransport([OSError("opaque")])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)
    with pytest.raises(ActionError) as unknown_error:
        asyncio.run(
            client.call_tool(
                "kick_group_member",
                {"group_id": 700000001, "user_id": 800000001},
            )
        )
    assert unknown_error.value.classification == "transport_unknown"
    assert len(transport.requests) == 1

    with pytest.raises(ActionError) as unsupported_error:
        asyncio.run(client.call_tool("get_impl_info", {}))
    assert unsupported_error.value.classification == "unsupported"

    asyncio.run(client.close())
    with pytest.raises(ActionError) as closed_error:
        asyncio.run(
            client.call_tool(
                "kick_group_member",
                {"group_id": 700000001, "user_id": 800000001},
            )
        )
    assert closed_error.value.classification == "unsupported"
    assert len(transport.requests) == 1


def test_tool_handler_delivers_raw_body_and_logs_only_delivery_metadata(caplog) -> None:
    """Tool handler 交付原文，日志只保留分类和状态码。"""

    body = b'{"status":"failed","retcode":7,"token":"fixture-token"}'
    transport = RawTransport([response(body, status_code=500)])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)
    host = ToolHost()
    register_tools(host)
    handler = next(item["handler"] for item in host.registered if item["name"] == "get_friend_info")
    bind_sender(MilkyOutboundSender(client))
    try:
        with caplog.at_level("INFO", logger="hermes_plugins.milky.outbound.tools"):
            result = asyncio.run(handler({"user_id": 800000001}))
    finally:
        unbind_sender()

    assert result == body.decode()
    record = next(record for record in caplog.records if "event=milky.tool" in record.getMessage())
    rendered = record.getMessage()
    assert "classification=delivered" in rendered
    assert "status_code=500" in rendered
    assert "fixture-token" not in rendered
    assert "800000001" not in rendered


def test_sender_tool_failures_do_not_schedule_mute_refresh() -> None:
    """Tool 的协议/HTTP/未知结果不触发 MuteTracker 刷新。"""

    class RawClient:
        async def call_tool(self, action: str, params: dict[str, object]) -> str:
            del action, params
            return '{"status":"failed"}'

    class Tracker:
        def __init__(self) -> None:
            self.targets: list[str] = []

        async def refresh_after_send_failure(self, target: str) -> None:
            self.targets.append(target)

    tracker = Tracker()
    sender = MilkyOutboundSender(RawClient(), mute_tracker=tracker)
    assert asyncio.run(sender.nudge("group:700000001", user_id=800000001)) == (
        '{"status":"failed"}'
    )
    assert asyncio.run(sender.recall_group_message("group:700000001", 123)) == (
        '{"status":"failed"}'
    )
    assert tracker.targets == []


def test_tool_registration_has_no_result_transform_hook() -> None:
    """Tool 注册只登记固定 ToolSpec，不登记 core 结果变换。"""

    host = ToolHost()
    register_tools(host)
    assert not any(
        key in {"transform_tool_result", "truncate_tool_result", "persist_tool_result"}
        for item in host.registered
        for key in item
    )
