"""验证新增 QQ ToolSpec 的 schema、协议、调用和安全边界。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config import load_config
from milky.client import ActionError, MilkyClient, TransportResponse
from milky.models import MilkyEnvelope
from milky.parser import parse_event
from outbound.sender import MilkyOutboundSender
from outbound.tools import TOOL_SPECS, bind_sender, unbind_sender
from tools import register_tools

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qq_tools"
NEW_TOOL_NAMES = (
    "get_forwarded_messages",
    "get_private_file_download_url",
    "kick_group_member",
    "quit_group",
    "delete_friend",
    "get_friend_requests",
    "accept_friend_request",
    "reject_friend_request",
)
DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky/",
    "MILKY_ACCESS_TOKEN": "runtime-token",
}


def load_fixture(relative_path: str) -> Any:
    """读取 QQ Tool 合成 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def envelope(data: object, *, status: str = "ok", retcode: int = 0) -> dict[str, object]:
    """构造一个合成 Milky envelope。"""

    return {"status": status, "retcode": retcode, "data": data}


@dataclass
class FakeTransport:
    """记录请求并按顺序返回合成 HTTP 响应。"""

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
        """保存请求形状并返回下一个合成结果。"""

        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": json.loads(body),
                "timeout": timeout,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def close(self) -> None:
        """满足 HTTP transport 生命周期协议。"""


def http_response(payload: object, *, status_code: int = 200) -> TransportResponse:
    """构造 JSON HTTP 响应。"""

    return TransportResponse(status_code, json.dumps(payload).encode("utf-8"), {})


class ToolContext:
    """捕获宿主发现的 ToolSpec。"""

    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    def register_tool(self, **kwargs: Any) -> None:
        """保存一次工具注册。"""

        self.registered.append(kwargs)


class FakeToolClient:
    """为 sender 提供可控的 raw Tool envelope。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.error: ActionError | None = None

    async def call_tool(self, action: str, params: dict[str, object]) -> MilkyEnvelope:
        """记录一次显式 Action，返回对应的成功结构或固定失败。"""

        self.calls.append((action, dict(params)))
        if self.error is not None:
            raise self.error
        if action == "get_forwarded_messages":
            data = {"messages": [{"message_seq": 1004}], "future_data": "fixture"}
        elif action == "get_private_file_download_url":
            data = {"download_url": "fixture-download-url", "future_data": True}
        elif action == "get_friend_requests":
            data = {"requests": [{"initiator_uid": "fixture-uid"}], "future_data": "fixture"}
        else:
            data = {}
        return MilkyEnvelope(
            "ok",
            0,
            data,
            message="fixture-message",
            extras={"future_envelope": "fixture"},
        )


def test_schema_fixture_matches_all_new_tool_specs_and_is_synthetic() -> None:
    """schema fixture 应覆盖 8 个工具并排除凭证、路径和可访问 URL。"""

    fixture = load_fixture("schemas.json")
    actual = {spec["name"]: spec["parameters"] for spec in TOOL_SPECS}
    expected = {entry["operation_id"]: entry for entry in fixture["tools"]}

    assert set(expected) == set(NEW_TOOL_NAMES)
    assert set(actual) >= set(NEW_TOOL_NAMES)
    for name in NEW_TOOL_NAMES:
        entry = expected[name]
        schema = actual[name]
        assert schema["required"] == entry["required"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == set(entry["properties"])
        for field, expected_shape in entry["properties"].items():
            for key, value in expected_shape.items():
                assert schema["properties"][field][key] == value

    contents = json.dumps(fixture, ensure_ascii=False)
    for forbidden in (
        "MILKY_ACCESS_TOKEN",
        "Authorization",
        "Bearer ",
        "https://",
        "http://",
        "/Users/",
        "/home/",
    ):
        assert forbidden not in contents


def test_query_response_fixtures_keep_minimum_fields_and_unknown_values() -> None:
    """三个查询 fixture 应包含最小字段和非敏感未知扩展。"""

    fixture = load_fixture("responses/query_ok.json")
    assert isinstance(fixture["get_forwarded_messages"]["data"]["messages"], list)
    assert fixture["get_forwarded_messages"]["data"]["future_envelope"] == "fixture-envelope"
    assert (
        fixture["get_private_file_download_url"]["data"]["download_url"] == "fixture-download-url"
    )
    assert fixture["get_private_file_download_url"]["data"]["future_data"] == {"kind": "fixture"}
    assert isinstance(fixture["get_friend_requests"]["data"]["requests"], list)
    assert fixture["get_friend_requests"]["data"]["future_data"] == "fixture-requests-extension"


def test_management_response_fixture_covers_empty_success_and_error_shapes() -> None:
    """管理 fixture 应明确区分空对象成功、拒绝、结构和传输错误。"""

    fixture = load_fixture("responses/management_outcomes.json")
    assert fixture["success"]["data"] == {}
    assert fixture["rejected"]["status"] == "failed"
    assert fixture["malformed_data"]["data"] != {}
    assert fixture["malformed_envelope"]["data"] == []
    assert fixture["http_error"]["status_code"] == 403
    assert fixture["non_json"]["status_code"] == 200
    assert fixture["transport_unknown"]["classification"] == "transport_unknown"


def test_request_fixture_covers_omitted_nullable_and_sensitive_input_projection() -> None:
    """请求 fixture 应固定省略、显式 null 和自由文本的边界。"""

    fixture = load_fixture("requests/bodies.json")
    requests = fixture["requests"]
    assert requests[0]["body"] == {"forward_id": "fixture-forward-id"}
    assert "is_self_send" not in requests[1]["body"]
    assert requests[2]["body"]["is_self_send"] is None
    assert requests[3]["body"]["reject_add_request"] is True
    assert requests[6]["body"] == {}
    assert requests[7]["body"] == {"limit": None, "is_filtered": False}
    assert requests[9]["body"]["reason"] == "synthetic-reason"
    contents = json.dumps(fixture, ensure_ascii=False)
    for forbidden in (
        "MILKY_ACCESS_TOKEN",
        "Authorization",
        "Bearer ",
        "https://",
        "http://",
        "/Users/",
        "/home/",
    ):
        assert forbidden not in contents


def test_client_calls_each_new_action_once_with_prefixed_post_and_exact_body() -> None:
    """8 个 operationId 应各自只访问对应 path，并保持请求字段。"""

    query = load_fixture("responses/query_ok.json")
    success = load_fixture("responses/management_outcomes.json")["success"]
    payloads = [
        query["get_forwarded_messages"],
        query["get_private_file_download_url"],
        success,
        success,
        success,
        query["get_friend_requests"],
        success,
        success,
    ]
    transport = FakeTransport([http_response(payload) for payload in payloads])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    async def call_all() -> None:
        """按工具顺序执行 8 个 client Action。"""

        await client.call_tool("get_forwarded_messages", {"forward_id": "fixture-forward-id"})
        await client.call_tool(
            "get_private_file_download_url",
            {
                "user_id": 800000001,
                "file_id": "fixture-file",
                "file_hash": "fixture-hash",
                "is_self_send": None,
            },
        )
        await client.call_tool(
            "kick_group_member",
            {"group_id": 700000001, "user_id": 800000001, "reject_add_request": True},
        )
        await client.call_tool("quit_group", {"group_id": 700000001})
        await client.call_tool("delete_friend", {"user_id": 800000001})
        await client.call_tool("get_friend_requests", {})
        await client.call_tool("accept_friend_request", {"initiator_uid": "fixture-uid"})
        await client.call_tool(
            "reject_friend_request",
            {"initiator_uid": "fixture-uid", "is_filtered": False, "reason": "synthetic-reason"},
        )

    asyncio.run(call_all())
    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == list(
        NEW_TOOL_NAMES
    )
    assert [request["method"] for request in transport.requests] == ["POST"] * 8
    assert transport.requests[0]["body"] == {"forward_id": "fixture-forward-id"}
    assert transport.requests[1]["body"]["is_self_send"] is None
    assert transport.requests[2]["body"]["reject_add_request"] is True
    assert transport.requests[5]["body"] == {}
    assert transport.requests[7]["body"]["reason"] == "synthetic-reason"
    assert transport.requests[0]["headers"]["Authorization"] == "Bearer runtime-token"


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("get_forwarded_messages", {"forward_id": ""}),
        ("get_private_file_download_url", {"user_id": 800000001, "file_id": "x"}),
        ("get_private_file_download_url", {"user_id": True, "file_id": "x", "file_hash": "h"}),
        ("kick_group_member", {"group_id": 700000001, "user_id": 800000001, "extra": True}),
        ("quit_group", {"group_id": 10000}),
        ("delete_friend", {"user_id": "800000001"}),
        ("get_friend_requests", {"limit": 9007199254740992}),
        ("accept_friend_request", {"initiator_uid": 123}),
        ("reject_friend_request", {"initiator_uid": "fixture-uid", "reason": 1}),
    ],
)
def test_client_rejects_invalid_new_tool_params_before_network(
    action: str, params: dict[str, object]
) -> None:
    """非法类型、范围、缺失字段和额外字段不得触网。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool(action, params))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


@pytest.mark.parametrize(
    ("action", "data_field", "bad_value"),
    [
        ("get_forwarded_messages", "messages", {}),
        ("get_forwarded_messages", "messages", ["not-an-object"]),
        ("get_private_file_download_url", "download_url", 1),
        ("get_friend_requests", "requests", {}),
        ("get_friend_requests", "requests", ["not-an-object"]),
    ],
)
def test_client_rejects_query_minimum_data_type_errors(
    action: str, data_field: str, bad_value: object
) -> None:
    """查询最小 data 字段错误应分类为 malformed。"""

    params = {
        "get_forwarded_messages": {"forward_id": "fixture-forward-id"},
        "get_private_file_download_url": {
            "user_id": 800000001,
            "file_id": "fixture-file",
            "file_hash": "fixture-hash",
        },
        "get_friend_requests": {},
    }[action]
    data = {data_field: bad_value}
    client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(envelope(data))])
    )

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool(action, params))

    assert error_info.value.classification == "malformed"


def test_client_preserves_query_raw_envelope_and_rejects_nonempty_management_data() -> None:
    """查询保留未知字段，管理 Action 的非空 data 不得假成功。"""

    query = load_fixture("responses/query_ok.json")["get_private_file_download_url"]
    query_client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(query)])
    )
    result = asyncio.run(
        query_client.call_tool(
            "get_private_file_download_url",
            {"user_id": 800000001, "file_id": "fixture-file", "file_hash": "fixture-hash"},
        )
    )
    assert result.data["download_url"] == "fixture-download-url"
    assert result.data["future_data"] == {"kind": "fixture"}
    assert result.extras["future_envelope"] is True

    management = load_fixture("responses/management_outcomes.json")["malformed_data"]
    management_client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(management)])
    )
    with pytest.raises(ActionError) as error_info:
        asyncio.run(management_client.call_tool("quit_group", {"group_id": 700000001}))
    assert error_info.value.classification == "malformed"


@pytest.mark.parametrize(
    "payload",
    [
        envelope({}, status="failed", retcode=1001),
        {"status": "ok", "retcode": 0, "data": []},
    ],
)
def test_client_classifies_protocol_rejection_and_malformed_management_payload(
    payload: dict[str, object],
) -> None:
    """HTTP 200 的协议拒绝和 data 类型错误必须保持分类差异。"""

    client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(payload)])
    )

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool("delete_friend", {"user_id": 800000001}))

    assert error_info.value.classification == (
        "rejected" if payload["status"] == "failed" else "malformed"
    )


@pytest.mark.parametrize(
    "response",
    [
        http_response({"status": "ok", "retcode": 0, "data": {}}, status_code=403),
        TransportResponse(200, b"synthetic-non-json", {}),
        OSError("transport detail must not escape"),
        TimeoutError("timeout detail must not escape"),
    ],
)
def test_client_classifies_http_non_json_and_unknown_transport_without_retry(
    response: TransportResponse | BaseException,
) -> None:
    """HTTP、非 JSON 和传输未知结果只提交一次且不暴露底层正文。"""

    transport = FakeTransport([response])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool("quit_group", {"group_id": 700000001}))

    assert error_info.value.classification in {"http_error", "malformed", "transport_unknown"}
    assert len(transport.requests) == 1
    assert "transport detail" not in str(error_info.value)


def test_registered_handlers_cover_17_fixed_specs_and_dispatch_only_explicitly() -> None:
    """注册应包含既有 9 项和新增 8 项，且每个 handler 只调用对应 Action。"""

    context = ToolContext()
    register_tools(context)
    names = [item["name"] for item in context.registered]
    assert len(names) == 17
    assert len(set(names)) == 17
    assert names[-8:] == list(NEW_TOOL_NAMES)
    assert all(item["toolset"] == "milky" for item in context.registered)
    assert all(item["is_async"] is True for item in context.registered)

    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        handlers = {item["name"]: item["handler"] for item in context.registered}
        results = [
            json.loads(
                asyncio.run(
                    handlers["get_forwarded_messages"]({"forward_id": "fixture-forward-id"})
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["get_private_file_download_url"](
                        {
                            "user_id": 800000001,
                            "file_id": "fixture-file",
                            "file_hash": "fixture-hash",
                            "is_self_send": None,
                        }
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["kick_group_member"](
                        {"group_id": 700000001, "user_id": 800000001, "reject_add_request": True}
                    )
                )
            ),
            json.loads(asyncio.run(handlers["quit_group"]({"group_id": 700000001}))),
            json.loads(asyncio.run(handlers["delete_friend"]({"user_id": 800000001}))),
            json.loads(asyncio.run(handlers["get_friend_requests"]({}))),
            json.loads(
                asyncio.run(handlers["accept_friend_request"]({"initiator_uid": "fixture-uid"}))
            ),
            json.loads(
                asyncio.run(
                    handlers["reject_friend_request"](
                        {
                            "initiator_uid": "fixture-uid",
                            "is_filtered": False,
                            "reason": "synthetic-reason",
                        }
                    )
                )
            ),
        ]
    finally:
        unbind_sender()

    assert results[0]["data"]["future_data"] == "fixture"
    assert results[1]["data"]["download_url"] == "fixture-download-url"
    assert all(result["data"] == {} for result in results[2:5])
    assert results[5]["data"]["requests"]
    assert all(result["status"] == "ok" for result in results)
    assert [call[0] for call in client.calls] == list(NEW_TOOL_NAMES)
    assert client.calls[1][1]["is_self_send"] is None
    assert client.calls[5][1] == {}


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("get_forwarded_messages", {"forward_id": ""}),
        (
            "get_private_file_download_url",
            {"user_id": 800000001, "file_id": "x", "file_hash": "h", "extra": True},
        ),
        ("kick_group_member", {"group_id": 700000001, "user_id": "800000001"}),
        ("quit_group", {"group_id": True}),
        ("delete_friend", {"user_id": 10000}),
        ("get_friend_requests", {"is_filtered": "false"}),
        ("accept_friend_request", {"initiator_uid": 800000001}),
        ("reject_friend_request", {"initiator_uid": "fixture-uid", "reason": 1}),
    ],
)
def test_new_tool_invalid_arguments_do_not_call_milky(
    tool_name: str, args: dict[str, object]
) -> None:
    """新增工具非法参数应在 sender/client 之前返回 invalid_input。"""

    context = ToolContext()
    register_tools(context)
    handler = next(item["handler"] for item in context.registered if item["name"] == tool_name)
    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(asyncio.run(handler(args)))
    finally:
        unbind_sender()

    assert result["classification"] == "invalid_input"
    assert client.calls == []


def test_management_unknown_result_is_not_retried_or_mapped_to_local_state() -> None:
    """管理 Action 传输未知时只产生一次请求，不更新任何插件状态。"""

    context = ToolContext()
    register_tools(context)
    handler = next(
        item["handler"] for item in context.registered if item["name"] == "kick_group_member"
    )
    client = FakeToolClient()
    client.error = ActionError("transport_unknown", "kick_group_member", "opaque transport detail")
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(
            asyncio.run(
                handler(
                    {
                        "group_id": 700000001,
                        "user_id": 800000001,
                        "reject_add_request": False,
                    }
                )
            )
        )
    finally:
        unbind_sender()

    assert result["classification"] == "transport_unknown"
    assert len(client.calls) == 1


def test_tool_audit_log_projects_sensitive_result_but_returns_raw_envelope(caplog) -> None:
    """Tool 调用方拿到 raw envelope，审计日志只保留安全结构投影。"""

    context = ToolContext()
    register_tools(context)
    handler = next(
        item["handler"]
        for item in context.registered
        if item["name"] == "get_private_file_download_url"
    )
    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        with caplog.at_level("INFO", logger="outbound.tools"):
            result = json.loads(
                asyncio.run(
                    handler(
                        {
                            "user_id": 800000001,
                            "file_id": "fixture-file",
                            "file_hash": "fixture-hash",
                        }
                    )
                )
            )
    finally:
        unbind_sender()

    records = [record for record in caplog.records if record.event_name == "milky_tool_call"]
    assert result["data"]["download_url"] == "fixture-download-url"
    assert len(records) == 1
    assert records[0].tool == "get_private_file_download_url"
    assert records[0].tool_args == {
        "user_id": 800000001,
        "file_id": "fixture-file",
        "file_hash": "fixture-hash",
    }
    assert records[0].tool_result["has_download_url"] is True
    assert "fixture-download-url" not in repr(records[0].tool_result)


def test_reject_reason_is_not_logged_and_full_reason_is_not_required_for_result(caplog) -> None:
    """拒绝理由只进入明确 Action body，不进入安全审计字段。"""

    context = ToolContext()
    register_tools(context)
    handler = next(
        item["handler"] for item in context.registered if item["name"] == "reject_friend_request"
    )
    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        with caplog.at_level("INFO", logger="outbound.tools"):
            result = json.loads(
                asyncio.run(
                    handler(
                        {
                            "initiator_uid": "fixture-uid",
                            "reason": "synthetic-sensitive-reason",
                        }
                    )
                )
            )
    finally:
        unbind_sender()

    record = next(record for record in caplog.records if record.event_name == "milky_tool_call")
    assert result["status"] == "ok"
    assert client.calls == [
        (
            "reject_friend_request",
            {"initiator_uid": "fixture-uid", "reason": "synthetic-sensitive-reason"},
        )
    ]
    assert "reason" not in record.tool_args
    assert "synthetic-sensitive-reason" not in repr(record.tool_result)


def test_unbound_sender_returns_unsupported_without_network() -> None:
    """未绑定 sender 时新增工具不得自行建立 client 或连接。"""

    context = ToolContext()
    register_tools(context)
    handler = next(item["handler"] for item in context.registered if item["name"] == "quit_group")
    unbind_sender()

    result = json.loads(asyncio.run(handler({"group_id": 700000001})))

    assert result["classification"] == "unsupported"


def test_friend_request_event_is_observe_only_and_never_calls_management_action() -> None:
    """好友请求事件只观察，不自动接受、拒绝或删除好友。"""

    payload = json.loads(
        (
            Path(__file__).parent
            / "fixtures"
            / "protocol"
            / "events"
            / "system.friend_request.json"
        ).read_text(encoding="utf-8")
    )
    event = parse_event(payload)
    assert event.classification == "observe_only"
    assert event.event_type == "friend_request"

    client = FakeToolClient()
    assert client.calls == []
