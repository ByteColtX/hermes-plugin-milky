"""验证新增 QQ ToolSpec 的 schema、协议、调用和安全边界。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from __init__ import register_tools
from config import load_config
from milky.client import ActionError, MilkyClient, TransportResponse
from milky.models import MilkyEnvelope
from milky.parser import parse_event
from outbound.sender import MilkyOutboundSender
from outbound.tools import TOOL_SPECS, bind_sender, unbind_sender

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
GROUP_TOOL_NAMES = (
    "get_group_file_download_url",
    "accept_group_request",
    "reject_group_request",
    "accept_group_invitation",
    "reject_group_invitation",
    "get_group_files",
)
ADDITIONAL_TOOL_NAMES = (
    "get_friend_info",
    "set_group_member_special_title",
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
        elif action == "get_group_file_download_url":
            data = {"download_url": "fixture-group-download-url", "future_data": "fixture"}
        elif action == "get_group_files":
            data = {
                "files": [{"file_id": "fixture-group-file", "future": True}],
                "folders": [{"folder_id": "fixture-folder", "future": True}],
                "future_data": "fixture",
            }
        elif action == "get_private_file_download_url":
            data = {"download_url": "fixture-download-url", "future_data": True}
        elif action == "get_friend_requests":
            data = {"requests": [{"initiator_uid": "fixture-uid"}], "future_data": "fixture"}
        elif action == "get_friend_info":
            data = {
                "user_id": 800000001,
                "nickname": "合成好友",
                "opaque_extension": {"kind": "fixture"},
            }
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
    """schema fixture 应覆盖当前新增工具并排除凭证、路径和可访问 URL。"""

    fixture = load_fixture("schemas.json")
    actual = {spec["name"]: spec["parameters"] for spec in TOOL_SPECS}
    expected = {entry["operation_id"]: entry for entry in fixture["tools"]}

    all_new_names = NEW_TOOL_NAMES + GROUP_TOOL_NAMES + ADDITIONAL_TOOL_NAMES
    assert set(expected) == set(all_new_names)
    assert set(actual) >= set(all_new_names)
    for name in all_new_names:
        entry = expected[name]
        schema = actual[name]
        assert schema["required"] == entry["required"]
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == set(entry["properties"])
        for field, expected_shape in entry["properties"].items():
            for key, value in expected_shape.items():
                assert schema["properties"][field][key] == value

    assert actual["accept_group_request"]["properties"]["notification_type"]["enum"] == [
        "join_request",
        "invited_join_request",
    ]
    assert actual["reject_group_request"]["properties"]["reason"]["nullable"] is True

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
    """好友资料和其他查询 fixture 应包含最小字段和非敏感未知扩展。"""

    fixture = load_fixture("responses/query_ok.json")
    assert isinstance(fixture["get_forwarded_messages"]["data"]["messages"], list)
    assert fixture["get_forwarded_messages"]["data"]["future_envelope"] == "fixture-envelope"
    assert (
        fixture["get_private_file_download_url"]["data"]["download_url"] == "fixture-download-url"
    )
    assert fixture["get_private_file_download_url"]["data"]["future_data"] == {"kind": "fixture"}
    assert isinstance(fixture["get_friend_requests"]["data"]["requests"], list)
    assert fixture["get_friend_requests"]["data"]["future_data"] == "fixture-requests-extension"
    assert fixture["get_friend_info"]["data"]["opaque_extension"] == {"kind": "fixture"}
    assert fixture["get_friend_info"]["future_envelope"] == "fixture-friend-envelope"


def test_friend_info_contract_keeps_opaque_data_and_records_unconfirmed_fields() -> None:
    """公开 v1.3 未声明好友资料字段时只测试 object data，不创建本地 DTO。"""

    fixture = load_fixture("responses/friend_info_outcomes.json")
    assert isinstance(fixture["success"]["data"], dict)
    assert fixture["success"]["data"]["opaque_extension"] == "fixture-friend-extension"
    assert fixture["transport_unknown"]["classification"] == "transport_unknown"
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
    assert requests[10]["body"] == {"user_id": 800000001}
    assert requests[11]["body"] == {
        "group_id": 700000001,
        "user_id": 800000001,
        "special_title": "合成头衔",
    }
    assert requests[12]["body"]["special_title"] == ""
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


def test_group_request_fixture_covers_omitted_nullable_and_boundaries() -> None:
    """群工具请求 fixture 应锁定序号、枚举、nullable 和父目录字段。"""

    fixture = load_fixture("requests/group_bodies.json")
    requests = fixture["requests"]
    assert requests[0]["body"] == {
        "group_id": 700000001,
        "file_id": "fixture-group-file",
    }
    assert requests[1]["body"]["notification_seq"] == 0
    assert requests[1]["body"]["notification_type"] == "join_request"
    assert requests[2]["body"]["notification_seq"] == 9007199254740991
    assert requests[2]["body"]["is_filtered"] is None
    assert requests[3]["body"]["invitation_seq"] == 123
    assert requests[5]["body"] == {"group_id": 700000001}
    assert requests[6]["body"]["parent_folder_id"] is None
    assert requests[7]["body"]["parent_folder_id"] == "fixture-folder"
    contents = json.dumps(fixture, ensure_ascii=False)
    for forbidden in ("MILKY_ACCESS_TOKEN", "Authorization", "Bearer ", "https://", "http://"):
        assert forbidden not in contents


def test_group_response_fixtures_keep_minimum_fields_and_unknown_values() -> None:
    """群文件查询 fixture 应保留最小字段和未知扩展。"""

    query = load_fixture("responses/group_query_ok.json")
    assert query["get_group_file_download_url"]["data"]["download_url"] == (
        "fixture-group-download-url"
    )
    assert query["get_group_file_download_url"]["data"]["future_data"] == {"kind": "fixture"}
    assert isinstance(query["get_group_files"]["data"]["files"], list)
    assert isinstance(query["get_group_files"]["data"]["folders"], list)
    assert query["get_group_files"]["data"]["future_data"] == "fixture-files-extension"


def test_group_management_response_fixture_covers_all_actions_and_errors() -> None:
    """群管理 fixture 应覆盖四个 Action 和所有安全错误形状。"""

    fixture = load_fixture("responses/group_management_outcomes.json")
    assert tuple(fixture["actions"]) == (
        "accept_group_request",
        "reject_group_request",
        "accept_group_invitation",
        "reject_group_invitation",
    )
    assert fixture["success"]["data"] == {}
    assert fixture["rejected"]["status"] == "failed"
    assert fixture["malformed_data"]["data"] != {}
    assert fixture["malformed_envelope"]["data"] == []
    assert fixture["http_error"]["status_code"] == 403
    assert fixture["non_json"]["status_code"] == 200
    assert fixture["transport_unknown"]["classification"] == "transport_unknown"


def test_file_placeholder_fixture_covers_hash_presence_and_missing_values() -> None:
    """文件 placeholder fixture 应区分有效、null、缺失和空 hash。"""

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/inbound_context/file_placeholders.json").read_text(
            encoding="utf-8"
        )
    )
    assert [case["name"] for case in fixture["cases"]] == [
        "available_hash",
        "null_hash",
        "missing_hash",
        "empty_hash",
    ]
    assert fixture["cases"][0]["expected"].endswith("file_hash=fixture-file-hash]")
    assert all(
        case["expected"].endswith("file_hash=NOT SUPPORTED]") for case in fixture["cases"][1:]
    )


def test_client_calls_each_new_action_once_with_prefixed_post_and_exact_body() -> None:
    """好友请求、资料查询和其他 friend Action 应各自只访问对应 path。"""

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
        query["get_friend_info"],
        success,
    ]
    transport = FakeTransport([http_response(payload) for payload in payloads])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    async def call_all() -> None:
        """按工具顺序执行新增 friend/group Action。"""

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
        await client.call_tool("get_friend_info", {"user_id": 800000001})
        await client.call_tool(
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": ""},
        )

    asyncio.run(call_all())
    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == list(
        NEW_TOOL_NAMES + ADDITIONAL_TOOL_NAMES
    )
    assert [request["method"] for request in transport.requests] == ["POST"] * 10
    assert transport.requests[0]["body"] == {"forward_id": "fixture-forward-id"}
    assert transport.requests[1]["body"]["is_self_send"] is None
    assert transport.requests[2]["body"]["reject_add_request"] is True
    assert transport.requests[5]["body"] == {}
    assert transport.requests[7]["body"]["reason"] == "synthetic-reason"
    assert transport.requests[8]["body"] == {"user_id": 800000001}
    assert transport.requests[9]["body"] == {
        "group_id": 700000001,
        "user_id": 800000001,
        "special_title": "",
    }


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("get_friend_info", {}),
        ("get_friend_info", {"user_id": True}),
        ("get_friend_info", {"user_id": 10000}),
        ("get_friend_info", {"user_id": 800000001, "extra": "fixture"}),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001},
        ),
        (
            "set_group_member_special_title",
            {"group_id": True, "user_id": 800000001, "special_title": "fixture"},
        ),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 4294967296, "special_title": "fixture"},
        ),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": 1},
        ),
        (
            "set_group_member_special_title",
            {
                "group_id": 700000001,
                "user_id": 800000001,
                "special_title": "fixture",
                "extra": True,
            },
        ),
    ],
)
def test_added_client_tool_params_are_rejected_before_network(
    action: str, params: dict[str, object]
) -> None:
    """新增工具的缺失、类型、范围和额外字段错误不得触网。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool(action, params))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


def test_sender_added_tools_preserve_exact_params_and_raw_envelopes() -> None:
    """sender 应为两个新增工具只委托同名 Action，并保留成功 envelope。"""

    client = FakeToolClient()
    sender = MilkyOutboundSender(client)

    friend_result = asyncio.run(sender.get_friend_info(800000001))
    title_result = asyncio.run(sender.set_group_member_special_title(700000001, 800000001, ""))

    assert isinstance(friend_result, MilkyEnvelope)
    assert friend_result.data["opaque_extension"]["kind"] == "fixture"
    assert isinstance(title_result, MilkyEnvelope)
    assert title_result.data == {}
    assert client.calls == [
        ("get_friend_info", {"user_id": 800000001}),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": ""},
        ),
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda sender: sender.get_friend_info(True),
        lambda sender: sender.get_friend_info(10000),
        lambda sender: sender.set_group_member_special_title(700000001, 800000001, 1),
    ],
)
def test_sender_added_tool_invalid_params_do_not_call_client(call) -> None:
    """sender 的新增工具参数错误应在 client 前返回 invalid_input。"""

    client = FakeToolClient()
    sender = MilkyOutboundSender(client)
    result = asyncio.run(call(sender))

    assert result.error_kind == "invalid_input"
    assert client.calls == []


@pytest.mark.parametrize(
    ("payload_name", "expected"),
    [
        ("success", None),
        ("rejected", "rejected"),
        ("malformed_data", "malformed"),
        ("malformed_non_object", "malformed"),
    ],
)
def test_friend_info_response_keeps_opaque_fields_and_classifies_errors(
    payload_name: str, expected: str | None
) -> None:
    """好友资料只要求 object data，协议拒绝和损坏结构不报告成功。"""

    outcomes = load_fixture("responses/friend_info_outcomes.json")
    payload = outcomes[payload_name]
    client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(payload)])
    )

    if expected is not None:
        with pytest.raises(ActionError) as error_info:
            asyncio.run(client.call_tool("get_friend_info", {"user_id": 800000001}))
        assert error_info.value.classification == expected
        return

    result = asyncio.run(client.call_tool("get_friend_info", {"user_id": 800000001}))
    assert result.data["opaque_extension"] == "fixture-friend-extension"
    assert result.extras["future_envelope"] is True


@pytest.mark.parametrize(
    ("action", "params", "payload"),
    [
        ("get_friend_info", {"user_id": 800000001}, {"status": "ok", "retcode": 0, "data": {}}),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": "fixture"},
            {"status": "ok", "retcode": 0, "data": {"unexpected": True}},
        ),
    ],
)
def test_added_client_tool_success_shapes_reject_wrong_data(
    action: str, params: dict[str, object], payload: dict[str, object]
) -> None:
    """好友资料拒绝空对象，专属头衔拒绝非空成功 data。"""

    transport = FakeTransport([http_response(payload)])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool(action, params))

    assert error_info.value.classification == "malformed"
    assert len(transport.requests) == 1


def test_friend_info_http_unsupported_boundary_is_http_error_without_redaction_leak() -> None:
    """公开未确认的好友资料 Action 遇 HTTP 404 时保持明确错误边界。"""

    outcome = load_fixture("responses/friend_info_outcomes.json")["http_error"]
    transport = FakeTransport(
        [
            http_response(
                {"status": "ok", "retcode": 0, "data": {}}, status_code=outcome["status_code"]
            )
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool("get_friend_info", {"user_id": 800000001}))

    assert error_info.value.classification == "http_error"
    assert len(transport.requests) == 1
    assert "synthetic-http-error" not in str(error_info.value)


def test_special_title_unknown_result_is_not_retried() -> None:
    """专属头衔 Action 的超时只提交一次并返回 transport_unknown。"""

    transport = FakeTransport([TimeoutError("synthetic-timeout"), http_response({})])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(
            client.call_tool(
                "set_group_member_special_title",
                {"group_id": 700000001, "user_id": 800000001, "special_title": "fixture"},
            )
        )

    assert error_info.value.classification == "transport_unknown"
    assert len(transport.requests) == 1
    assert transport.requests[0]["headers"]["Authorization"] == "Bearer runtime-token"


def test_client_calls_each_group_action_once_with_prefixed_post_and_exact_body() -> None:
    """6 个群工具应各自只访问对应 path，并保留可选字段。"""

    query = load_fixture("responses/group_query_ok.json")
    success = load_fixture("responses/group_management_outcomes.json")["success"]
    payloads = [
        query["get_group_file_download_url"],
        success,
        success,
        success,
        success,
        query["get_group_files"],
        query["get_group_files"],
    ]
    transport = FakeTransport([http_response(payload) for payload in payloads])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    async def call_all() -> None:
        """按协议顺序执行 6 个群工具 Action。"""

        await client.call_tool(
            "get_group_file_download_url",
            {"group_id": 700000001, "file_id": "fixture-group-file"},
        )
        await client.call_tool(
            "accept_group_request",
            {
                "notification_seq": 0,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        )
        await client.call_tool(
            "reject_group_request",
            {
                "notification_seq": 1,
                "notification_type": "invited_join_request",
                "group_id": 700000001,
                "is_filtered": None,
                "reason": "synthetic-reason",
            },
        )
        await client.call_tool(
            "accept_group_invitation",
            {"group_id": 700000001, "invitation_seq": 2},
        )
        await client.call_tool(
            "reject_group_invitation",
            {"group_id": 700000001, "invitation_seq": 3},
        )
        await client.call_tool("get_group_files", {"group_id": 700000001})
        await client.call_tool(
            "get_group_files",
            {"group_id": 700000001, "parent_folder_id": None},
        )

    asyncio.run(call_all())
    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == [
        "get_group_file_download_url",
        "accept_group_request",
        "reject_group_request",
        "accept_group_invitation",
        "reject_group_invitation",
        "get_group_files",
        "get_group_files",
    ]
    assert transport.requests[1]["body"]["notification_seq"] == 0
    assert transport.requests[2]["body"]["reason"] == "synthetic-reason"
    assert transport.requests[5]["body"] == {"group_id": 700000001}
    assert transport.requests[6]["body"]["parent_folder_id"] is None


def test_sender_delegates_group_tools_without_changing_action_or_body() -> None:
    """sender 应把 6 个群工具委托给对应 client Action。"""

    query = load_fixture("responses/group_query_ok.json")
    success = load_fixture("responses/group_management_outcomes.json")["success"]
    transport = FakeTransport(
        [
            http_response(query["get_group_file_download_url"]),
            http_response(success),
            http_response(success),
            http_response(success),
            http_response(success),
            http_response(query["get_group_files"]),
        ]
    )
    sender = MilkyOutboundSender(MilkyClient(load_config(DEFAULT_ENV), transport=transport))

    async def call_all() -> None:
        """按顺序调用 sender 的群工具方法。"""

        await sender.get_group_file_download_url(700000001, "fixture-group-file")
        await sender.accept_group_request(1, "join_request", 700000001)
        await sender.reject_group_request(
            2,
            "invited_join_request",
            700000001,
            is_filtered=None,
            reason="synthetic-reason",
        )
        await sender.accept_group_invitation(700000001, 3)
        await sender.reject_group_invitation(700000001, 4)
        await sender.get_group_files(700000001, parent_folder_id=None)

    asyncio.run(call_all())
    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == list(
        GROUP_TOOL_NAMES
    )
    assert transport.requests[1]["body"] == {
        "notification_seq": 1,
        "notification_type": "join_request",
        "group_id": 700000001,
    }
    assert transport.requests[2]["body"]["reason"] == "synthetic-reason"
    assert transport.requests[-1]["body"]["parent_folder_id"] is None


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("get_group_file_download_url", {"group_id": 700000001, "file_id": ""}),
        (
            "accept_group_request",
            {
                "notification_seq": 0,
                "notification_type": "unknown",
                "group_id": 700000001,
            },
        ),
        (
            "reject_group_request",
            {
                "notification_seq": True,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        ),
        (
            "accept_group_invitation",
            {"group_id": 700000001, "invitation_seq": 9007199254740992},
        ),
        ("reject_group_invitation", {"group_id": "700000001", "invitation_seq": 1}),
        ("get_group_files", {"group_id": 700000001, "parent_folder_id": ""}),
        ("get_group_files", {"group_id": 700000001, "extra": True}),
    ],
)
def test_client_rejects_invalid_group_tool_params_before_network(
    action: str, params: dict[str, object]
) -> None:
    """群工具的非法类型、范围、枚举和额外字段不得触网。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call_tool(action, params))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


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
        ("get_group_file_download_url", "download_url", 1),
        ("get_friend_requests", "requests", {}),
        ("get_friend_requests", "requests", ["not-an-object"]),
        ("get_group_files", "files", {}),
        ("get_group_files", "folders", ["not-an-object"]),
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
        "get_group_file_download_url": {
            "group_id": 700000001,
            "file_id": "fixture-group-file",
        },
        "get_group_files": {"group_id": 700000001},
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


def test_client_preserves_group_query_raw_envelopes_and_unknown_fields() -> None:
    """群文件查询成功时保留 envelope、文件数组和未知字段。"""

    query = load_fixture("responses/group_query_ok.json")
    transport = FakeTransport(
        [
            http_response(query["get_group_file_download_url"]),
            http_response(query["get_group_files"]),
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    async def call_all() -> tuple[MilkyEnvelope, MilkyEnvelope]:
        """调用两个群文件查询 Action。"""

        download = await client.call_tool(
            "get_group_file_download_url",
            {"group_id": 700000001, "file_id": "fixture-group-file"},
        )
        files = await client.call_tool("get_group_files", {"group_id": 700000001})
        return download, files

    download, files = asyncio.run(call_all())
    assert download.data["download_url"] == "fixture-group-download-url"
    assert download.data["future_data"] == {"kind": "fixture"}
    assert download.extras["future_envelope"] == "fixture-group-envelope"
    assert files.data["files"][0]["future"] is True
    assert files.data["folders"][0]["future"] == "value"
    assert files.data["future_data"] == "fixture-files-extension"


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
    ("action", "params"),
    [
        (
            "accept_group_request",
            {
                "notification_seq": 1,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        ),
        (
            "reject_group_request",
            {
                "notification_seq": 1,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        ),
        ("accept_group_invitation", {"group_id": 700000001, "invitation_seq": 1}),
        ("reject_group_invitation", {"group_id": 700000001, "invitation_seq": 1}),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": "fixture"},
        ),
    ],
)
def test_group_management_results_keep_rejection_and_malformed_boundaries(
    action: str, params: dict[str, object]
) -> None:
    """四个群管理 Action 应区分协议拒绝和非空 data。"""

    outcomes = load_fixture("responses/group_management_outcomes.json")
    rejected_client = MilkyClient(
        load_config(DEFAULT_ENV), transport=FakeTransport([http_response(outcomes["rejected"])])
    )
    with pytest.raises(ActionError) as rejected_error:
        asyncio.run(rejected_client.call_tool(action, params))
    assert rejected_error.value.classification == "rejected"

    malformed_client = MilkyClient(
        load_config(DEFAULT_ENV),
        transport=FakeTransport([http_response(outcomes["malformed_data"])]),
    )
    with pytest.raises(ActionError) as malformed_error:
        asyncio.run(malformed_client.call_tool(action, params))
    assert malformed_error.value.classification == "malformed"


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


def test_registered_handlers_cover_25_fixed_specs_and_dispatch_only_explicitly() -> None:
    """注册应包含 25 个固定工具，且每个 handler 只调用对应 Action。"""

    context = ToolContext()
    register_tools(context)
    names = [item["name"] for item in context.registered]
    assert len(names) == 25
    assert len(set(names)) == 25
    assert names[9:17] == list(NEW_TOOL_NAMES)
    assert names[17:23] == list(GROUP_TOOL_NAMES)
    assert names[23:] == list(ADDITIONAL_TOOL_NAMES)
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
            json.loads(
                asyncio.run(
                    handlers["get_group_file_download_url"](
                        {"group_id": 700000001, "file_id": "fixture-group-file"}
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["accept_group_request"](
                        {
                            "notification_seq": 1,
                            "notification_type": "join_request",
                            "group_id": 700000001,
                        }
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["reject_group_request"](
                        {
                            "notification_seq": 2,
                            "notification_type": "invited_join_request",
                            "group_id": 700000001,
                            "reason": "synthetic-reason",
                        }
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["accept_group_invitation"](
                        {"group_id": 700000001, "invitation_seq": 3}
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["reject_group_invitation"](
                        {"group_id": 700000001, "invitation_seq": 4}
                    )
                )
            ),
            json.loads(
                asyncio.run(
                    handlers["get_group_files"]({"group_id": 700000001, "parent_folder_id": None})
                )
            ),
            json.loads(asyncio.run(handlers["get_friend_info"]({"user_id": 800000001}))),
            json.loads(
                asyncio.run(
                    handlers["set_group_member_special_title"](
                        {
                            "group_id": 700000001,
                            "user_id": 800000001,
                            "special_title": "",
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
    assert results[14]["data"]["opaque_extension"]["kind"] == "fixture"
    assert results[15]["data"] == {}
    assert all(result["status"] == "ok" for result in results)
    assert [call[0] for call in client.calls] == list(
        NEW_TOOL_NAMES + GROUP_TOOL_NAMES + ADDITIONAL_TOOL_NAMES
    )
    assert client.calls[1][1]["is_self_send"] is None
    assert client.calls[5][1] == {}
    assert client.calls[13][1]["parent_folder_id"] is None
    assert client.calls[14][1] == {"user_id": 800000001}
    assert client.calls[15][1]["special_title"] == ""


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
        ("get_friend_info", {}),
        ("get_friend_info", {"user_id": True}),
        ("get_friend_info", {"user_id": 4294967296}),
        ("get_friend_info", {"user_id": 800000001, "extra": True}),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001},
        ),
        (
            "set_group_member_special_title",
            {"group_id": 700000001, "user_id": 800000001, "special_title": 1},
        ),
        (
            "set_group_member_special_title",
            {
                "group_id": 700000001,
                "user_id": 800000001,
                "special_title": "fixture",
                "extra": True,
            },
        ),
        (
            "accept_group_request",
            {
                "notification_seq": 1,
                "notification_type": "invalid",
                "group_id": 700000001,
            },
        ),
        (
            "reject_group_request",
            {
                "notification_seq": 1,
                "notification_type": "join_request",
                "group_id": 700000001,
                "reason": "",
            },
        ),
        (
            "accept_group_invitation",
            {"group_id": 700000001, "invitation_seq": True},
        ),
        ("reject_group_invitation", {"group_id": 10000, "invitation_seq": 1}),
        ("get_group_files", {"group_id": 700000001, "parent_folder_id": 1}),
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


@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        (
            "accept_group_request",
            {
                "notification_seq": 1,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        ),
        (
            "reject_group_request",
            {
                "notification_seq": 1,
                "notification_type": "join_request",
                "group_id": 700000001,
            },
        ),
        ("accept_group_invitation", {"group_id": 700000001, "invitation_seq": 1}),
        ("reject_group_invitation", {"group_id": 700000001, "invitation_seq": 1}),
    ],
)
def test_group_management_unknown_result_is_not_retried(
    tool_name: str, args: dict[str, object]
) -> None:
    """四个群管理 Action 未知时只提交一次且不伪造成功。"""

    context = ToolContext()
    register_tools(context)
    handler = next(item["handler"] for item in context.registered if item["name"] == tool_name)
    client = FakeToolClient()
    client.error = ActionError("transport_unknown", tool_name, "opaque transport detail")
    bind_sender(MilkyOutboundSender(client))
    try:
        result = json.loads(asyncio.run(handler(args)))
    finally:
        unbind_sender()

    assert result["classification"] == "transport_unknown"
    assert client.calls == [(tool_name, args)]


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


def test_added_tool_audit_logs_exclude_friend_data_and_special_title(caplog) -> None:
    """新增工具日志只保留结构和安全 ID，不记录资料值或完整头衔。"""

    context = ToolContext()
    register_tools(context)
    handlers = {item["name"]: item["handler"] for item in context.registered}
    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        with caplog.at_level("INFO", logger="outbound.tools"):
            friend_result = json.loads(
                asyncio.run(handlers["get_friend_info"]({"user_id": 800000001}))
            )
            title_result = json.loads(
                asyncio.run(
                    handlers["set_group_member_special_title"](
                        {
                            "group_id": 700000001,
                            "user_id": 800000001,
                            "special_title": "synthetic-sensitive-title",
                        }
                    )
                )
            )
    finally:
        unbind_sender()

    records = [record for record in caplog.records if record.event_name == "milky_tool_call"]
    assert friend_result["data"]["nickname"] == "合成好友"
    assert title_result["data"] == {}
    assert len(records) == 2
    assert records[0].tool_args == {"user_id": 800000001}
    assert records[1].tool_args == {"group_id": 700000001, "user_id": 800000001}
    rendered_records = repr(records)
    assert "合成好友" not in rendered_records
    assert "synthetic-sensitive-title" not in rendered_records


def test_group_tool_audit_log_keeps_safe_ids_but_excludes_url_and_reason(caplog) -> None:
    """群工具日志保留安全关联字段，不记录 URL 或完整拒绝理由。"""

    context = ToolContext()
    register_tools(context)
    handler = next(
        item["handler"] for item in context.registered if item["name"] == "reject_group_request"
    )
    client = FakeToolClient()
    bind_sender(MilkyOutboundSender(client))
    try:
        with caplog.at_level("INFO", logger="outbound.tools"):
            result = json.loads(
                asyncio.run(
                    handler(
                        {
                            "notification_seq": 7,
                            "notification_type": "join_request",
                            "group_id": 700000001,
                            "is_filtered": False,
                            "reason": "synthetic-sensitive-reason",
                        }
                    )
                )
            )
    finally:
        unbind_sender()

    record = next(record for record in caplog.records if record.event_name == "milky_tool_call")
    assert result["status"] == "ok"
    assert record.tool_args == {
        "notification_seq": 7,
        "notification_type": "join_request",
        "group_id": 700000001,
        "is_filtered": False,
    }
    assert "reason" not in record.tool_args
    assert "synthetic-sensitive-reason" not in repr(record)


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


@pytest.mark.parametrize(
    "fixture_name",
    ["system.group_join_request.json", "system.group_invitation.json"],
)
def test_group_request_and_invitation_events_are_observe_only(fixture_name: str) -> None:
    """群请求和群邀请事件不得自动提交接受/拒绝 Action。"""

    payload = load_fixture(f"../protocol/events/{fixture_name}")
    event = parse_event(payload)
    assert event.classification == "observe_only"
    client = FakeToolClient()
    assert client.calls == []


def test_group_request_and_invitation_pipeline_events_have_no_implicit_action() -> None:
    """fake pipeline 收到群请求/邀请时只观察，不调用任何管理 Action。"""

    from tests.test_hermes_pipeline import FakeHermes, FakeResolver, make_pipeline

    async def scenario() -> tuple[list[object], list[tuple[str, dict[str, object]]]]:
        hermes = FakeHermes()
        pipeline = make_pipeline(hermes, FakeResolver())
        client = FakeToolClient()
        for fixture_name in ("system.group_join_request.json", "system.group_invitation.json"):
            result = await pipeline.handle_event(load_fixture(f"../protocol/events/{fixture_name}"))
            assert result.classification == "observe_only"
        await pipeline.wait_idle()
        return hermes.events, client.calls

    events, calls = asyncio.run(scenario())
    assert events == []
    assert calls == []


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
