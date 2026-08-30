"""验证 T05 Milky HTTP Action client 的协议和传输边界。"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

import pytest

from config import load_config
from milky.client import ActionError, MilkyClient, TransportResponse
from milky.models import GroupList, LoginInfo

DEFAULT_ENV = {
    "MILKY_BASE_URL": "https://localhost:5500/milky/",
    "MILKY_ACCESS_TOKEN": "client-test-secret",
}


@dataclass
class FakeTransport:
    """记录请求并按顺序返回预先准备的 fake 响应。"""

    responses: list[TransportResponse | BaseException]

    def __post_init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.close_calls = 0

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> TransportResponse:
        """记录一次请求并返回 fake 结果。"""

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
        """记录客户端释放。"""

        self.close_calls += 1


def response(data: object, *, status_code: int = 200) -> TransportResponse:
    """构造一个 JSON fake 响应。"""

    return TransportResponse(status_code, json.dumps(data).encode("utf-8"), {})


def ok(data: object) -> dict[str, object]:
    """构造成功 envelope。"""

    return {"status": "ok", "retcode": 0, "data": data}


def test_action_uses_prefixed_post_bearer_and_empty_json_body() -> None:
    """无参数 Action 应使用正确 URL、POST、Bearer 和空对象 body。"""

    transport = FakeTransport([response(ok({"uin": 900000001, "nickname": "合成机器人"}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    result = asyncio.run(client.get_login_info())

    assert result == LoginInfo(900000001, "合成机器人")
    assert transport.requests == [
        {
            "method": "POST",
            "url": "https://localhost:5500/milky/api/get_login_info",
            "headers": {
                "Authorization": "Bearer client-test-secret",
                "Content-Type": "application/json",
            },
            "body": {},
            "timeout": 10.0,
        }
    ]


def test_state_sync_methods_validate_milky_data_layers() -> None:
    """状态同步方法应读取 uin、groups 和 member 的对象层级。"""

    transport = FakeTransport(
        [
            response(ok({"groups": []})),
            response(
                ok(
                    {
                        "member": {
                            "user_id": 900000001,
                            "group_id": 700000001,
                            "nickname": "合成机器人",
                        }
                    }
                )
            ),
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    groups, member = asyncio.run(_get_group_data(client))

    assert isinstance(groups, GroupList)
    assert groups.groups == ()
    assert member.member.user_id == 900000001
    assert transport.requests[0]["body"] == {}
    assert transport.requests[1]["body"] == {
        "group_id": 700000001,
        "user_id": 900000001,
    }


def test_group_member_info_can_bypass_server_cache() -> None:
    """状态同步需要显式发送 Milky 的 no_cache 参数绕过旧成员缓存。"""

    transport = FakeTransport(
        [
            response(
                ok(
                    {
                        "member": {
                            "user_id": 900000001,
                            "group_id": 700000001,
                            "nickname": "合成机器人",
                        }
                    }
                )
            )
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(client.get_group_member_info(700000001, 900000001, no_cache=True))

    assert transport.requests[0]["body"] == {
        "group_id": 700000001,
        "user_id": 900000001,
        "no_cache": True,
    }


def test_group_member_info_rejects_invalid_no_cache_before_network() -> None:
    """no_cache 必须是布尔值，并在网络访问前拒绝非法输入。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.get_group_member_info(700000001, 900000001, no_cache="true"))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


async def _get_group_data(client: MilkyClient) -> tuple[GroupList, Any]:
    """并发测试不参与，按初始化契约顺序调用状态 Action。"""

    groups = await client.get_group_list()
    member = await client.get_group_member_info(700000001, 900000001)
    return groups, member


def test_message_resource_and_upload_methods_use_explicit_actions() -> None:
    """消息、资源和上传方法应复用同一 POST Action 边界。"""

    transport = FakeTransport(
        [
            response(ok({"message_seq": 42})),
            response(ok({"message_seq": 43})),
            response(
                ok(
                    {
                        "message": {
                            "message_scene": "friend",
                            "peer_id": 800000001,
                            "message_seq": 1005,
                            "sender_id": 800000001,
                            "time": 1700000007,
                            "segments": [{"type": "text", "data": {"text": "中性回复"}}],
                            "friend": {
                                "user_id": 800000001,
                                "nickname": "合成好友",
                                "sex": "unknown",
                                "qid": "fixture-qid",
                                "remark": "fixture",
                                "category": {
                                    "category_id": 1,
                                    "category_name": "合成分组",
                                },
                            },
                        }
                    }
                )
            ),
            response(ok({"messages": []})),
            response(ok({"url": "https://media.example/resource"})),
            response(ok({"file_id": "fixture-group-upload"})),
            response(ok({"file_id": "fixture-private-upload"})),
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    results = asyncio.run(_call_message_resource_uploads(client))

    assert results[:2] == ("42", "43")
    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == [
        "send_group_message",
        "send_private_message",
        "get_message",
        "get_forwarded_messages",
        "get_resource_temp_url",
        "upload_group_file",
        "upload_private_file",
    ]
    assert transport.requests[0]["body"] == {
        "group_id": 700000001,
        "message": [{"type": "text", "data": {"text": "你好"}}],
    }
    assert transport.requests[-2]["body"] == {
        "group_id": 700000001,
        "file_uri": "https://media.example/file",
        "file_name": "fixture.txt",
    }
    assert transport.requests[-1]["body"] == {
        "user_id": 800000001,
        "file_uri": "https://media.example/file",
        "file_name": "fixture.txt",
    }


async def _call_message_resource_uploads(client: MilkyClient) -> tuple[str, str]:
    """按各 Action 的最小参数调用消息、资源和上传方法。"""

    group_result = await client.send_group_message(
        700000001, [{"type": "text", "data": {"text": "你好"}}]
    )
    private_result = await client.send_private_message(
        800000001, [{"type": "text", "data": {"text": "你好"}}]
    )
    await client.get_message("friend", 800000001, 1005)
    await client.get_forwarded_messages("fixture-forward-id")
    await client.get_resource_temp_url("fixture-resource-id")
    await client.upload_group_file(700000001, "https://media.example/file", "fixture.txt")
    await client.upload_private_file(800000001, "https://media.example/file", "fixture.txt")
    return group_result.message_id, private_result.message_id


def test_explicit_outbound_action_methods_use_openapi_fields() -> None:
    """显式出站 Action 方法应只发送 OpenAPI 已确认的字段。"""

    transport = FakeTransport(
        [
            response(ok({})),
            response(ok({})),
            response(ok({})),
            response(ok({})),
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    async def call_actions() -> None:
        """按协议顺序执行四个显式 Action。"""

        await client.send_profile_like(800000001, 2)
        await client.send_friend_nudge(800000001, True)
        await client.send_group_nudge(700000001, 900000001)
        await client.recall_group_message(700000001, 123)

    asyncio.run(call_actions())

    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == [
        "send_profile_like",
        "send_friend_nudge",
        "send_group_nudge",
        "recall_group_message",
    ]
    assert [request["body"] for request in transport.requests] == [
        {"user_id": 800000001, "count": 2},
        {"user_id": 800000001, "is_self": True},
        {"group_id": 700000001, "user_id": 900000001},
        {"group_id": 700000001, "message_seq": 123},
    ]


def test_profile_like_accepts_explicit_nullable_count() -> None:
    """名片点赞显式传入 null 时应保留该 OpenAPI 可空字段。"""

    transport = FakeTransport([response(ok({}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(client.send_profile_like(800000001, None))

    assert transport.requests[0]["body"] == {"user_id": 800000001, "count": None}


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("send_profile_like", (1,)),
        ("send_profile_like", (800000001, True)),
        ("send_friend_nudge", (800000001, "yes")),
        ("send_group_nudge", (700000001, 1)),
        ("recall_group_message", (700000001, -1)),
    ],
)
def test_explicit_outbound_action_parameters_fail_before_network(
    method_name: str, args: tuple[object, ...]
) -> None:
    """显式工具使用的 Action 参数错误时不得进入 HTTP。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(getattr(client, method_name)(*args))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


def test_file_download_methods_use_scene_specific_actions_and_fields() -> None:
    """入站 group/private file 必须使用各自确认的下载 Action。"""

    transport = FakeTransport(
        [
            response(ok({"download_url": ""})),
            response(ok({"download_url": ""})),
        ]
    )
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(_call_file_download_methods(client))

    assert [request["url"].rsplit("/", 1)[-1] for request in transport.requests] == [
        "get_group_file_download_url",
        "get_private_file_download_url",
    ]
    assert transport.requests[0]["body"] == {
        "group_id": 700000001,
        "file_id": "fixture-group-file",
    }
    assert transport.requests[1]["body"] == {
        "user_id": 800000001,
        "file_id": "fixture-private-file",
        "file_hash": "fixture-hash",
    }


def test_private_file_download_accepts_optional_is_self_send() -> None:
    """私聊文件 Action 应按协议支持可选的自己发送标志。"""

    transport = FakeTransport([response(ok({"download_url": ""}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(
        client.get_private_file_download_url(
            800000001,
            "fixture-private-file",
            "fixture-hash",
            is_self_send=True,
        )
    )

    assert transport.requests[0]["body"] == {
        "user_id": 800000001,
        "file_id": "fixture-private-file",
        "file_hash": "fixture-hash",
        "is_self_send": True,
    }


async def _call_file_download_methods(client: MilkyClient) -> None:
    """调用两类文件下载 Action。"""

    await client.get_group_file_download_url(700000001, "fixture-group-file")
    await client.get_private_file_download_url(800000001, "fixture-private-file", "fixture-hash")


@pytest.mark.parametrize(
    "method_args",
    [
        ("get_group_file_download_url", (10000, "fixture-file")),
        ("get_group_file_download_url", (4294967296, "fixture-file")),
        ("get_group_file_download_url", ("700000001:2", "fixture-file")),
        ("get_private_file_download_url", (10000, "fixture-file", "fixture-hash")),
        ("get_private_file_download_url", (4294967296, "fixture-file", "fixture-hash")),
        ("get_private_file_download_url", (800000001, "fixture-file", "")),
    ],
)
def test_file_download_parameters_are_validated_before_network(
    method_args: tuple[str, tuple[object, ...]],
) -> None:
    """文件 Action 的目标、ID 和 hash 非法时不得访问网络。"""

    method_name, args = method_args
    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(getattr(client, method_name)(*args))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


def test_group_file_upload_accepts_optional_parent_folder_id() -> None:
    """群文件上传应按协议发送可选的目标文件夹字段。"""

    transport = FakeTransport([response(ok({"file_id": "fixture-upload"}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(
        client.upload_group_file(
            700000001,
            "base64://fixture",
            "fixture.txt",
            parent_folder_id="fixture-folder",
        )
    )

    assert transport.requests[0]["body"] == {
        "group_id": 700000001,
        "parent_folder_id": "fixture-folder",
        "file_uri": "base64://fixture",
        "file_name": "fixture.txt",
    }


def test_upload_response_requires_file_id() -> None:
    """上传成功 envelope 缺少协议要求的 file_id 时必须判为 malformed。"""

    transport = FakeTransport([response(ok({}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(
            client.upload_private_file(
                800000001,
                "base64://fixture",
                "fixture.txt",
            )
        )

    assert error_info.value.classification == "malformed"
    assert len(transport.requests) == 1


def test_group_file_upload_rejects_invalid_parent_folder_id_before_network() -> None:
    """群文件上传的可选文件夹字段类型错误时不得访问网络。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(
            client.upload_group_file(
                700000001,
                "base64://fixture",
                "fixture.txt",
                parent_folder_id=1,
            )
        )

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


def test_group_file_upload_from_path_uses_base64_uri(tmp_path) -> None:
    """本地文件上传入口应把文件内容编码为协议支持的 base64 URI。"""

    file_path = tmp_path / "fixture.bin"
    file_path.write_bytes(b"fixture-bytes\x00")
    transport = FakeTransport([response(ok({"file_id": "fixture-upload"}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(
        client.upload_group_file_from_path(
            700000001,
            file_path,
            "fixture.bin",
            parent_folder_id="fixture-folder",
        )
    )

    assert transport.requests[0]["body"] == {
        "group_id": 700000001,
        "parent_folder_id": "fixture-folder",
        "file_uri": "base64://" + base64.b64encode(b"fixture-bytes\x00").decode("ascii"),
        "file_name": "fixture.bin",
    }


def test_private_file_upload_from_path_uses_base64_uri(tmp_path) -> None:
    """私聊本地文件上传入口也应复用相同的 base64 URI 约定。"""

    file_path = tmp_path / "fixture.txt"
    file_path.write_text("fixture", encoding="utf-8")
    transport = FakeTransport([response(ok({"file_id": "fixture-upload"}))])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(client.upload_private_file_from_path(800000001, file_path, "fixture.txt"))

    assert transport.requests[0]["body"] == {
        "user_id": 800000001,
        "file_uri": "base64://" + base64.b64encode(b"fixture").decode("ascii"),
        "file_name": "fixture.txt",
    }


@pytest.mark.parametrize("path_kind", ["missing", "directory", "invalid"])
def test_file_upload_from_path_rejects_unreadable_path_before_network(
    tmp_path, path_kind: str
) -> None:
    """本地文件不可读时应在 HTTP 边界前失败且不泄露路径。"""

    if path_kind == "missing":
        file_path = tmp_path / "missing.bin"
    elif path_kind == "directory":
        file_path = tmp_path / "directory"
        file_path.mkdir()
    else:
        file_path = object()

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.upload_group_file_from_path(700000001, file_path, "fixture.bin"))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []
    if path_kind != "invalid":
        assert str(file_path) not in str(error_info.value)


def test_private_file_download_rejects_invalid_is_self_send_before_network() -> None:
    """私聊文件的可选标志类型错误时不得访问网络。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(
            client.get_private_file_download_url(
                800000001,
                "fixture-file",
                "fixture-hash",
                is_self_send="yes",
            )
        )

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


@pytest.mark.parametrize(
    "method_args",
    [
        ("get_message", ("unsupported", 800000001, 1005)),
        ("get_message", ("friend", 10000, 1005)),
        ("get_message", ("friend", 4294967296, 1005)),
        ("get_message", ("friend", 800000001, -1)),
        ("get_message", ("friend", 800000001, 9007199254740992)),
    ],
)
def test_get_message_parameters_are_validated_before_network(
    method_args: tuple[str, tuple[object, ...]],
) -> None:
    """get_message 的 scene、peer 和序号边界应在网络前校验。"""

    method_name, args = method_args
    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(getattr(client, method_name)(*args))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


@pytest.mark.parametrize("classification", ["rejected", "malformed"])
def test_protocol_and_message_shape_errors_are_classified(classification: str) -> None:
    """协议拒绝和发送数据缺失必须分别分类，不能假成功。"""

    payload = (
        {"status": "failed", "retcode": 1001, "data": {}}
        if classification == "rejected"
        else ok({})
    )
    transport = FakeTransport([response(payload)])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.send_group_message(700000001, []))

    assert error_info.value.classification == classification
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("transport_error", "classification"),
    [(TimeoutError(), "transport_unknown"), (OSError("socket failed"), "transport_unknown")],
)
def test_transport_failures_are_unknown_and_never_retried(
    transport_error: BaseException, classification: str
) -> None:
    """超时或连接失败不得盲目重试可能产生副作用的 Action。"""

    transport = FakeTransport([transport_error])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.send_group_message(700000001, []))

    assert error_info.value.classification == classification
    assert len(transport.requests) == 1
    assert "socket failed" not in str(error_info.value)
    assert "client-test-secret" not in str(error_info.value)


def test_non_json_and_http_status_errors_are_distinct_and_redacted() -> None:
    """非 JSON 和 HTTP 状态错误应分类，诊断不得带出认证信息。"""

    malformed_transport = FakeTransport(
        [TransportResponse(200, b"not-json client-test-secret", {})]
    )
    malformed_client = MilkyClient(load_config(DEFAULT_ENV), transport=malformed_transport)
    with pytest.raises(ActionError) as malformed_error:
        asyncio.run(malformed_client.get_login_info())

    http_transport = FakeTransport([TransportResponse(503, b"secret body", {})])
    http_client = MilkyClient(load_config(DEFAULT_ENV), transport=http_transport)
    with pytest.raises(ActionError) as http_error:
        asyncio.run(http_client.get_login_info())

    assert malformed_error.value.classification == "malformed"
    assert http_error.value.classification == "http_error"
    assert "client-test-secret" not in str(malformed_error.value)
    assert "client-test-secret" not in str(http_error.value)
    assert "secret body" not in str(http_error.value)


def test_successful_action_requires_object_data() -> None:
    """成功 envelope 缺少对象型 data 时不得交付给调用方。"""

    transport = FakeTransport([response({"status": "ok", "retcode": 0})])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call("get_resource_temp_url", {"resource_id": "fixture"}))

    assert error_info.value.classification == "malformed"


@pytest.mark.parametrize("group_id", ["", "-1", "700000001:2", True])
def test_invalid_target_is_rejected_before_network(group_id: object) -> None:
    """非法群目标应在访问网络前失败。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.get_group_member_info(group_id, 900000001))

    assert error_info.value.classification == "invalid_input"
    assert transport.requests == []


def test_client_close_releases_transport() -> None:
    """关闭客户端应释放底层 transport。"""

    transport = FakeTransport([])
    client = MilkyClient(load_config(DEFAULT_ENV), transport=transport)

    asyncio.run(client.close())

    assert transport.close_calls == 1


def test_invalid_action_does_not_echo_untrusted_value() -> None:
    """非法 Action 名称不得把可能的凭证值带入错误。"""

    client = MilkyClient(load_config(DEFAULT_ENV), transport=FakeTransport([]))

    with pytest.raises(ActionError) as error_info:
        asyncio.run(client.call("client-test-secret"))

    assert error_info.value.classification == "invalid_input"
    assert "client-test-secret" not in str(error_info.value)
