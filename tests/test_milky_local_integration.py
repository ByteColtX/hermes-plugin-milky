"""通过本地 HTTP/SSE 服务验证 Milky 传输、生命周期和出站边界。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Self
from urllib.parse import urlsplit

import pytest

from adapter import MilkyAdapter
from config import load_config
from milky.client import ActionError, MilkyClient
from milky.event_stream import HttpxSseTransport, SseEventStream
from outbound.sender import OutboundSendResult

_TOKEN = "integration-test-token"
_SELF_ID = 900000001
_GROUP_IDS = (700000001, 700000002)
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("httpx") is None,
    reason="HTTPX 由 Hermes 宿主提供，当前独立 uv 环境未安装",
)


class _MilkyFixtureState:
    """保存本地协议服务状态，不向测试输出原始响应。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []
        self.event_connections = 0
        self.event_payload: dict[str, Any] | None = None
        self.event_chunked = False
        self.fail_group_message = False
        self.fail_private_message = False

    def append_request(self, path: str, authorization: str | None, body: dict[str, Any]) -> None:
        """记录请求的安全测试副本。"""

        with self.lock:
            self.requests.append({"path": path, "authorization": authorization, "body": body})

    def request_snapshot(self) -> list[dict[str, Any]]:
        """返回请求记录副本。"""

        with self.lock:
            return list(self.requests)

    def next_event_connection(self) -> int:
        """分配 SSE 连接序号。"""

        with self.lock:
            self.event_connections += 1
            return self.event_connections


class _MilkyFixtureHandler(BaseHTTPRequestHandler):
    """提供脱敏的 v1.3 Action 和 SSE 响应。"""

    server_version = "MilkyFixture/1"

    @property
    def state(self) -> _MilkyFixtureState:
        """返回测试服务状态。"""

        return self.server.fixture_state  # type: ignore[attr-defined,no-any-return]

    def log_message(self, format: str, *args: object) -> None:
        """禁止 HTTP server 将请求内容写入测试日志。"""

        del format, args

    def do_POST(self) -> None:
        """按 Action 路径返回最小成功或失败 envelope。"""

        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"status": "failed", "retcode": 400, "data": {}})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"status": "failed", "retcode": 400, "data": {}})
            return
        self.state.append_request(path, self.headers.get("Authorization"), body)

        if path == "/milky/api/get_login_info":
            self._send_json(
                200,
                {"status": "ok", "retcode": 0, "data": {"uin": _SELF_ID, "nickname": "fixture"}},
            )
            return
        if path == "/milky/api/get_group_list":
            groups = [{"group_id": group_id, "group_name": "fixture"} for group_id in _GROUP_IDS]
            self._send_json(200, {"status": "ok", "retcode": 0, "data": {"groups": groups}})
            return
        if path == "/milky/api/get_group_member_info":
            group_id = body.get("group_id")
            self._send_json(
                200,
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": {
                        "member": {
                            "group_id": group_id,
                            "user_id": _SELF_ID,
                            "nickname": "fixture",
                        }
                    },
                },
            )
            return
        if path == "/milky/api/send_group_message" and self.state.fail_group_message:
            self._send_json(200, {"status": "failed", "retcode": 403, "data": {}})
            return
        if path == "/milky/api/send_private_message" and self.state.fail_private_message:
            self._send_json(200, {"status": "failed", "retcode": 403, "data": {}})
            return
        if path in {"/milky/api/send_group_message", "/milky/api/send_private_message"}:
            sequence = 1000 + len(
                [item for item in self.state.request_snapshot() if "send_" in item["path"]]
            )
            self._send_json(200, {"status": "ok", "retcode": 0, "data": {"message_seq": sequence}})
            return
        if path in {"/milky/api/upload_group_file", "/milky/api/upload_private_file"}:
            file_uri = body.get("file_uri")
            if not isinstance(file_uri, str) or not file_uri.startswith("base64://"):
                self._send_json(200, {"status": "failed", "retcode": 422, "data": {}})
                return
            self._send_json(
                200, {"status": "ok", "retcode": 0, "data": {"file_id": "fixture-file"}}
            )
            return
        self._send_json(404, {"status": "failed", "retcode": 404, "data": {}})

    def do_GET(self) -> None:
        """返回一条事件后关闭连接，第二次连接返回另一条事件。"""

        if urlsplit(self.path).path != "/milky/event":
            self._send_json(404, {"status": "failed", "retcode": 404, "data": {}})
            return
        connection = self.state.next_event_connection()
        payload = self.state.event_payload or {
            "event_type": "bot_offline",
            "time": 1700000000 + connection,
            "self_id": _SELF_ID,
            "data": {"reason": "fixture"},
        }
        serialized = json.dumps(payload, ensure_ascii=False)
        midpoint = serialized.index('"self_id"')
        body = (
            ": heartbeat\n\n"
            "event: milky_event\n"
            f"data: {serialized[:midpoint]}\n"
            f"data: {serialized[midpoint:]}\n\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        if self.state.event_chunked:
            self.send_header("Transfer-Encoding", "chunked")
        else:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.state.event_chunked:
            chunk = f"{len(body):X}\r\n".encode() + body + b"\r\n0\r\n\r\n"
            self.wfile.write(chunk)
        else:
            self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        """发送 JSON envelope。"""

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


class _MilkyFixtureServer:
    """管理本地线程 HTTP server 的生命周期。"""

    def __init__(self) -> None:
        self.state = _MilkyFixtureState()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _MilkyFixtureHandler)
        self.server.fixture_state = self.state  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        """启动测试服务。"""

        self.thread.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """停止并回收测试服务。"""

        del exc_type, exc_value, traceback
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        """返回带 prefix 的本地测试基址。"""

        return f"http://127.0.0.1:{self.server.server_port}/milky"


def _config(server: _MilkyFixtureServer):
    """创建只用于本地集成服务的配置。"""

    return load_config(
        {
            "MILKY_BASE_URL": server.base_url,
            "MILKY_ACCESS_TOKEN": _TOKEN,
            "MILKY_ALLOWED_CHATS": "group:700000001,dm:800000001",
        }
    )


class _RecordingPipeline:
    """记录 adapter 事件流交给 pipeline 的事件类型。"""

    def __init__(self) -> None:
        self.events: list[object] = []

    def start(self) -> None:
        """提供 adapter 生命周期所需的启动接口。"""

    async def handle_event(self, event: object) -> None:
        """记录一个已通过 SSE 解码的事件。"""

        self.events.append(event)

    async def close(self) -> None:
        """提供 adapter 生命周期所需的关闭接口。"""


def test_local_sse_delivers_message_receive_to_adapter_pipeline() -> None:
    """有效 message_receive 应从真实 HTTPX SSE 进入 adapter pipeline。"""

    event_payload = json.loads(
        (_FIXTURE_ROOT / "events/message_receive.friend.json").read_text(encoding="utf-8")
    )
    with _MilkyFixtureServer() as server:
        server.state.event_payload = event_payload
        pipeline = _RecordingPipeline()
        client = MilkyClient(_config(server), timeout=2)
        adapter = MilkyAdapter(
            SimpleNamespace(),
            milky_config=_config(server),
            client=client,
            pipeline=pipeline,
        )

        async def scenario() -> None:
            assert await adapter.connect() is True
            for _ in range(200):
                if pipeline.events:
                    break
                await asyncio.sleep(0.01)
            assert len(pipeline.events) == 1
            assert pipeline.events[0].event_type == "message_receive"
            await adapter.disconnect()

        asyncio.run(scenario())


def test_local_chunked_sse_delivers_message_receive_to_adapter_pipeline() -> None:
    """chunked 长连接 SSE 也应把 message_receive 交给 adapter pipeline。"""

    event_payload = json.loads(
        (_FIXTURE_ROOT / "events/message_receive.friend.json").read_text(encoding="utf-8")
    )
    with _MilkyFixtureServer() as server:
        server.state.event_payload = event_payload
        server.state.event_chunked = True
        pipeline = _RecordingPipeline()
        config = _config(server)
        client = MilkyClient(config, timeout=2)
        adapter = MilkyAdapter(
            SimpleNamespace(),
            milky_config=config,
            client=client,
            pipeline=pipeline,
        )

        async def scenario() -> None:
            assert await adapter.connect() is True
            for _ in range(200):
                if pipeline.events:
                    break
                await asyncio.sleep(0.01)
            assert len(pipeline.events) == 1
            assert pipeline.events[0].event_type == "message_receive"
            await adapter.disconnect()

        asyncio.run(scenario())


def test_local_http_lifecycle_outbound_refresh_and_upload(tmp_path: Path) -> None:
    """真实 HTTPX transport 应串起初始化、SSE、group/dm 和独立上传。"""

    with _MilkyFixtureServer() as server:
        config = _config(server)
        client = MilkyClient(config, timeout=2)
        adapter = MilkyAdapter(SimpleNamespace(), milky_config=config, client=client)
        file_path = tmp_path / "fixture.txt"
        file_path.write_text("fixture", encoding="utf-8")

        async def scenario() -> None:
            assert await adapter.connect() is True
            for _ in range(100):
                if server.state.event_connections:
                    break
                await asyncio.sleep(0.01)
            assert server.state.event_connections >= 1
            assert adapter.ready is True

            group_result = await adapter.send("group:700000001", "群 smoke")
            dm_result = await adapter.send("dm:800000001", "私聊 smoke")
            upload_result = await adapter.outbound_sender.send_document(
                "group:700000001", file_path
            )
            assert group_result.success is True
            assert group_result.message_id == "1001"
            assert dm_result.success is True
            assert dm_result.message_id == "1002"
            assert upload_result.success is True
            assert upload_result.message_id == "fixture-file"

            server.state.fail_group_message = True
            member_calls_before = len(
                [
                    item
                    for item in server.state.request_snapshot()
                    if "get_group_member_info" in item["path"]
                ]
            )
            failed_group = await adapter.send("group:700000001", "失败 smoke")
            assert failed_group.error_kind == "rejected"
            member_calls_after = len(
                [
                    item
                    for item in server.state.request_snapshot()
                    if "get_group_member_info" in item["path"]
                ]
            )
            assert member_calls_after == member_calls_before + 1

            server.state.fail_private_message = True
            member_calls_before = member_calls_after
            failed_dm = await adapter.send("dm:800000001", "失败 smoke")
            assert failed_dm.error_kind == "rejected"
            assert (
                len(
                    [
                        item
                        for item in server.state.request_snapshot()
                        if "get_group_member_info" in item["path"]
                    ]
                )
                == member_calls_before
            )
            await adapter.disconnect()

        asyncio.run(scenario())

        requests = server.state.request_snapshot()
        assert all(item["authorization"] == f"Bearer {_TOKEN}" for item in requests)
        assert all(item["path"].startswith("/milky/api/") for item in requests)
        assert requests[0]["body"] == {}
        assert requests[1]["body"] == {}
        member_requests = [
            item for item in requests if item["path"].endswith("get_group_member_info")
        ]
        assert member_requests
        assert all(
            item["body"]
            == {
                "group_id": item["body"]["group_id"],
                "user_id": _SELF_ID,
                "no_cache": True,
            }
            for item in member_requests
        )
        upload = next(item for item in requests if item["path"].endswith("upload_group_file"))
        assert upload["body"]["file_uri"].startswith("base64://")
        assert "file" not in upload["body"]
        assert all("?" not in item["path"] for item in requests)


def test_local_sse_reconnects_and_preserves_safe_contract() -> None:
    """真实 HTTPX SSE transport 应处理多行 data、断线和第二次连接。"""

    with _MilkyFixtureServer() as server:
        config = _config(server)
        stream = SseEventStream(
            config,
            transport=HttpxSseTransport(),
            initial_backoff=0,
            max_backoff=0,
        )
        received: list[object] = []

        async def scenario() -> None:
            task = asyncio.create_task(stream.run(received.append))
            for _ in range(200):
                if len(received) >= 2:
                    break
                await asyncio.sleep(0.01)
            assert len(received) >= 2, repr(stream.diagnostics)
            await stream.close()
            await task

        asyncio.run(scenario())

        assert server.state.event_connections >= 2
        assert len(received) >= 2
        assert not any(item.classification == "malformed" for item in stream.diagnostics)


def test_local_protocol_rejection_is_classified_without_retry() -> None:
    """真实 HTTP 200 失败 envelope 应分类 rejected 且只调用一次。"""

    with _MilkyFixtureServer() as server:
        server.state.fail_private_message = True
        client = MilkyClient(_config(server), timeout=2)

        async def scenario() -> None:
            try:
                await client.send_private_message(
                    800000001, [{"type": "text", "data": {"text": "x"}}]
                )
            except ActionError as error:
                assert error.classification == "rejected"
                assert _TOKEN not in str(error)
            else:
                raise AssertionError("expected rejected Action")
            await client.close()

        asyncio.run(scenario())

        calls = [
            item
            for item in server.state.request_snapshot()
            if "send_private_message" in item["path"]
        ]
        assert len(calls) == 1


def test_smoke_summary_never_exposes_file_uri_or_message_id() -> None:
    """smoke 输出所依赖的摘要只能保留固定分类。"""

    result = OutboundSendResult(
        success=False,
        error="rejected: secret-message-id-or-file-uri",
        error_kind="rejected",
    )
    from scripts.milky_smoke import _send_summary

    summary = _send_summary(result)
    assert summary == {"status": "rejected"}
    assert "secret" not in repr(summary)


def test_smoke_write_request_requires_explicit_flag() -> None:
    """指定出站目标但未开启写入开关时不得触碰 client。"""

    from scripts.milky_smoke import _parser, _run_writes

    arguments = _parser().parse_args(["--group-chat", "group:700000001"])
    result = asyncio.run(
        _run_writes(
            SimpleNamespace(allowed_chats=frozenset({"group:700000001"})),
            object(),
            object(),
            arguments,
        )
    )
    assert result == {"status": "blocked_write_flag"}
