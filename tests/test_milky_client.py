"""验证 T05 Milky HTTP Action client 的协议和传输边界。"""

from __future__ import annotations

import asyncio
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
            response(ok({"message": []})),
            response(ok({"messages": []})),
            response(ok({"url": "https://media.example/resource"})),
            response(ok({})),
            response(ok({})),
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
        "file": "https://media.example/file",
        "name": "fixture.txt",
    }


async def _call_message_resource_uploads(client: MilkyClient) -> tuple[str, str]:
    """按各 Action 的最小参数调用消息、资源和上传方法。"""

    group_result = await client.send_group_message(
        700000001, [{"type": "text", "data": {"text": "你好"}}]
    )
    private_result = await client.send_private_message(
        800000001, [{"type": "text", "data": {"text": "你好"}}]
    )
    await client.get_message(42)
    await client.get_forwarded_messages("fixture-forward-id")
    await client.get_resource_temp_url("fixture-resource-id")
    await client.upload_group_file(700000001, "https://media.example/file", "fixture.txt")
    await client.upload_private_file(800000001, "https://media.example/file", "fixture.txt")
    return group_result.message_id, private_result.message_id


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
