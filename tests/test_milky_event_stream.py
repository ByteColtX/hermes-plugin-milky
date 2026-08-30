"""验证 T06 SSE /event 事件流边界。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from config import load_config
from milky.event_stream import (
    EventStreamError,
    HttpxSseTransport,
    SseEventStream,
    decode_sse_frame,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"
CONFIG = load_config(
    {
        "MILKY_BASE_URL": "https://host.example/milky/",
        "MILKY_ACCESS_TOKEN": "stream-test-secret",
    }
)

RECONNECT_LOG_EVENTS = {
    "milky_event_stream_disconnected",
    "milky_event_stream_reconnect_scheduled",
    "milky_event_stream_reconnect_attempt",
    "milky_event_stream_reconnected",
    "milky_event_stream_cancelled",
}
SAFE_RECONNECT_REASONS = {
    "eof",
    "connection_error",
    "timeout",
    "http_error",
    "protocol_error",
    "stream_error",
    "unknown",
}


@dataclass
class FakeResponse:
    """按行提供 SSE 响应并记录关闭。"""

    lines: list[str | bytes | None | BaseException]

    def __post_init__(self) -> None:
        self.close_calls = 0

    async def readline(self) -> str | bytes | None:
        """返回下一行或模拟读取错误。"""

        await asyncio.sleep(0)
        value = self.lines.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self) -> None:
        """记录响应释放。"""

        self.close_calls += 1


@dataclass
class BlockingResponse(FakeResponse):
    """提供一帧后等待关闭，用于稳定观察重连日志。"""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.read_started = asyncio.Event()
        self.release_read = asyncio.Event()

    async def readline(self) -> str | bytes | None:
        """读取预置 frame，后续读取等待 close 释放。"""

        if self.lines:
            return await super().readline()
        self.read_started.set()
        await self.release_read.wait()
        return None

    async def close(self) -> None:
        """记录关闭并解除阻塞读取。"""

        self.close_calls += 1
        self.release_read.set()


@dataclass
class FakeTransport:
    """按顺序建立 fake SSE 响应。"""

    responses: list[FakeResponse | BaseException]

    def __post_init__(self) -> None:
        self.connections: list[dict[str, Any]] = []
        self.close_calls = 0

    async def connect(self, url: str, headers: dict[str, str], timeout: float) -> FakeResponse:
        """记录连接参数并返回下一条 fake 响应。"""

        self.connections.append({"url": url, "headers": headers, "timeout": timeout})
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    async def close(self) -> None:
        """记录 transport 释放。"""

        self.close_calls += 1


def fixture_lines(name: str) -> list[str]:
    """读取 SSE fixture 的逐行内容，并补充 EOF 哨兵。"""

    return (FIXTURE_ROOT / "sse" / name).read_text(encoding="utf-8").splitlines(keepends=True) + [
        None
    ]


def lifecycle_log_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """返回事件流生命周期日志记录。"""

    return [
        record
        for record in caplog.records
        if record.name == "milky.event_stream"
        and getattr(record, "event_name", None) in RECONNECT_LOG_EVENTS
    ]


def test_reconnect_log_contract_is_ordered_structured_and_safe(caplog) -> None:
    """断连、退避、重连和取消日志应遵循固定标签与字段契约。"""

    first_response = FakeResponse(fixture_lines("reconnect-after-eof.sse"))
    second_response = BlockingResponse(fixture_lines("reconnect-after-eof.sse")[:-1])
    transport = FakeTransport([first_response, second_response])
    delays = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        await asyncio.sleep(0)

    stream = SseEventStream(
        CONFIG,
        transport=transport,
        initial_backoff=0.25,
        max_backoff=1,
        sleep=fake_sleep,
    )
    received = []

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(received.append))
            await asyncio.wait_for(second_response.read_started.wait(), 1)
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == [
        "milky_event_stream_disconnected",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnected",
        "milky_event_stream_cancelled",
    ]
    assert records[0].reason == "eof"
    assert records[1].attempt == 1
    assert records[1].delay_seconds == 0.25
    assert records[1].reason == "eof"
    assert records[2].attempt == 1
    assert records[2].reason == "eof"
    assert records[3].attempt == 1
    assert records[3].reason == "eof"
    assert not hasattr(records[4], "reason")
    assert delays == [0.25]
    assert all(getattr(record, "reason", None) in SAFE_RECONNECT_REASONS for record in records[:-1])
    rendered = " ".join(record.getMessage() for record in records)
    assert "stream-test-secret" not in rendered
    assert "Authorization" not in rendered
    assert "https://host.example/milky/event" not in rendered


def test_reconnect_attempt_resets_after_successful_recovery(caplog) -> None:
    """成功恢复后新的断连周期应重新从 attempt 1 开始。"""

    first_response = FakeResponse(fixture_lines("reconnect-after-eof.sse"))
    second_response = FakeResponse(fixture_lines("reconnect-after-eof.sse"))
    third_response = BlockingResponse(fixture_lines("reconnect-after-eof.sse")[:-1])
    transport = FakeTransport([first_response, second_response, third_response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0, max_backoff=1)

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(lambda event: None))
            await asyncio.wait_for(third_response.read_started.wait(), 1)
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    records = lifecycle_log_records(caplog)
    attempts = [
        record for record in records if record.event_name == "milky_event_stream_reconnect_attempt"
    ]
    scheduled = [
        record
        for record in records
        if record.event_name == "milky_event_stream_reconnect_scheduled"
    ]
    recovered = [
        record for record in records if record.event_name == "milky_event_stream_reconnected"
    ]
    assert [record.attempt for record in attempts] == [1, 1]
    assert [record.attempt for record in scheduled] == [1, 1]
    assert [record.attempt for record in recovered] == [1, 1]


def test_failed_reconnects_log_safe_reason_and_max_backoff(caplog) -> None:
    """连续连接失败应记录递增 attempt、封顶退避和安全 reason。"""

    final_response = BlockingResponse(fixture_lines("reconnect-after-eof.sse")[:-1])
    transport = FakeTransport(
        [
            OSError("secret socket detail"),
            TimeoutError("secret timeout detail"),
            RuntimeError("secret response detail"),
            EventStreamError("http_error", "secret HTTP response detail"),
            EventStreamError("malformed", "secret malformed response detail"),
            final_response,
        ]
    )
    delays = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        await asyncio.sleep(0)

    stream = SseEventStream(
        CONFIG,
        transport=transport,
        initial_backoff=0.25,
        max_backoff=0.5,
        sleep=fake_sleep,
    )

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(lambda event: None))
            await asyncio.wait_for(final_response.read_started.wait(), 1)
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == [
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnected",
        "milky_event_stream_cancelled",
    ]
    scheduled = [
        record
        for record in records
        if record.event_name == "milky_event_stream_reconnect_scheduled"
    ]
    attempts = [
        record for record in records if record.event_name == "milky_event_stream_reconnect_attempt"
    ]
    assert [record.attempt for record in scheduled] == [1, 2, 3, 4, 5]
    assert [record.delay_seconds for record in scheduled] == [0.25, 0.5, 0.5, 0.5, 0.5]
    assert [record.reason for record in scheduled] == [
        "connection_error",
        "timeout",
        "stream_error",
        "http_error",
        "protocol_error",
    ]
    assert [record.attempt for record in attempts] == [1, 2, 3, 4, 5]
    assert all(record.reason in SAFE_RECONNECT_REASONS for record in records[:-1])
    assert not any(record.event_name == "milky_event_stream_disconnected" for record in records)
    rendered = repr([(record.getMessage(), record.__dict__) for record in records])
    assert "secret socket detail" not in rendered
    assert "secret timeout detail" not in rendered
    assert "secret response detail" not in rendered
    assert "secret HTTP response detail" not in rendered
    assert "secret malformed response detail" not in rendered
    assert "stream-test-secret" not in rendered
    assert "https://host.example/milky/event" not in rendered
    assert delays == [0.25, 0.5, 0.5, 0.5, 0.5]


def test_event_stream_gets_prefixed_event_url_and_bearer() -> None:
    """事件流应 GET 正确的 prefix URL 并使用 Bearer。"""

    response = FakeResponse([None])
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(lambda event: None))
        await asyncio.sleep(0)
        await stream.close()
        await task

    asyncio.run(scenario())

    assert transport.connections[0] == {
        "url": "https://host.example/milky/event",
        "headers": {"Authorization": "Bearer stream-test-secret"},
        "timeout": 10.0,
    }


def test_multiline_data_is_decoded_once_and_outer_name_is_preserved() -> None:
    """多行 data 应拼接一次，并把 milky_event 作为包装名保留。"""

    response = FakeResponse(fixture_lines("message_receive.multiline.sse"))
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    received = []

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(received.append))
        while not received:
            await asyncio.sleep(0)
        await stream.close()
        await task

    asyncio.run(scenario())

    assert len(received) == 1
    assert received[0].event_type == "message_receive"
    assert received[0].outer_event_type == "milky_event"


def test_malformed_and_unknown_outer_events_do_not_stop_later_frames() -> None:
    """malformed 和未知外层事件应被记录并继续处理后续 frame。"""

    malformed = FakeResponse(fixture_lines("malformed-then-valid.sse"))
    unknown = FakeResponse(fixture_lines("unknown-outer-then-valid.sse"))
    transport = FakeTransport([malformed, unknown])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    received = []

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(received.append))
        while len(received) < 2:
            await asyncio.sleep(0)
        await stream.close()
        await task

    asyncio.run(scenario())

    assert [event.event_type for event in received] == ["group_file_upload", "bot_offline"]
    assert {item.classification for item in stream.diagnostics} >= {"malformed", "unknown"}


def test_handler_exception_isolated_and_receive_loop_continues(caplog) -> None:
    """handler 异常不得终止后续 frame 的接收。"""

    response = FakeResponse(fixture_lines("system-and-unknown.sse"))
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    received = []

    async def handler(event) -> None:
        received.append(event.event_type)
        if event.event_type == "future_event_extension":
            raise RuntimeError("不应进入诊断正文")

    async def scenario() -> None:
        with caplog.at_level(logging.DEBUG, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(handler))
            while len(received) < 2 or not any(
                item.classification == "handler_error" for item in stream.diagnostics
            ):
                await asyncio.sleep(0)
            await stream.close()
            await task

    asyncio.run(scenario())

    assert received == ["future_event_extension", "bot_offline"]
    assert any(item.classification == "handler_error" for item in stream.diagnostics)
    assert "不应进入诊断正文" not in repr(stream.diagnostics)
    assert "stream-test-secret" not in repr(stream.diagnostics)
    handler_logs = [
        record
        for record in caplog.records
        if record.name == "milky.event_stream"
        and getattr(record, "event_name", None) == "milky_event_stream_handler_failed"
    ]
    assert len(handler_logs) == 1
    assert handler_logs[0].reason == "handler_failed"
    assert not any(
        record.name == "milky.event_stream"
        and getattr(record, "event_name", None) == "milky_event_stream_frame_ignored"
        for record in caplog.records
    )


def test_slow_handler_does_not_block_receive_loop() -> None:
    """慢 handler 执行期间 receive loop 仍应读取并调度下一帧。"""

    payload = {
        "event_type": "bot_offline",
        "time": 1700000082,
        "self_id": 900000001,
        "data": {"reason": "合成观察"},
    }
    lines = [
        "event: milky_event\n",
        f"data: {json.dumps(payload, ensure_ascii=False)}\n",
        "\n",
        "event: milky_event\n",
        f"data: {json.dumps(payload, ensure_ascii=False)}\n",
        "\n",
        None,
    ]
    response = FakeResponse(lines)
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    started = asyncio.Event()
    release = asyncio.Event()
    received = []

    async def handler(event) -> None:
        received.append(event)
        started.set()
        await release.wait()

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(handler))
        await asyncio.wait_for(started.wait(), 1)
        for _ in range(20):
            if len(received) == 2:
                break
            await asyncio.sleep(0)
        assert len(received) == 2
        release.set()
        await stream.close()
        await task

    asyncio.run(scenario())


def test_disconnect_cancels_handlers_releases_response_and_transport(caplog) -> None:
    """主动取消应停止读取、取消 handler 并释放所有资源。"""

    payload = {
        "event_type": "bot_offline",
        "time": 1700000083,
        "self_id": 900000001,
        "data": {"reason": "合成观察"},
    }
    response = BlockingResponse(
        [
            "event: milky_event\n",
            f"data: {json.dumps(payload, ensure_ascii=False)}\n",
            "\n",
        ]
    )
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(event) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(handler))
            await asyncio.wait_for(started.wait(), 1)
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    assert cancelled.is_set()
    assert response.close_calls == 1
    assert transport.close_calls == 1
    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == ["milky_event_stream_cancelled"]


def test_reconnect_applies_backoff_after_connection_failure() -> None:
    """连接异常后应按退避重连，并继续消费新的响应。"""

    payload = {
        "event_type": "bot_offline",
        "time": 1700000084,
        "self_id": 900000001,
        "data": {"reason": "重连观察"},
    }
    response = FakeResponse(
        [
            "event: milky_event\n",
            f"data: {json.dumps(payload, ensure_ascii=False)}\n",
            "\n",
            None,
        ]
    )
    transport = FakeTransport([OSError("secret socket detail"), response])
    delays = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        await asyncio.sleep(0)

    stream = SseEventStream(
        CONFIG,
        transport=transport,
        initial_backoff=0.25,
        max_backoff=1,
        sleep=fake_sleep,
    )
    received = []

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(received.append))
        while not received:
            await asyncio.sleep(0)
        await stream.close()
        await task

    asyncio.run(scenario())

    assert len(transport.connections) == 2
    assert delays == [0.25, 0.25]
    assert [item.classification for item in stream.diagnostics] == ["transport_unknown"]
    assert "secret socket detail" not in repr(stream.diagnostics)


def test_decoder_ignores_comments_and_unknown_fields_and_accepts_bytes() -> None:
    """SSE 解码应遵循字段规则，不把未知字段当作 payload。"""

    frame = decode_sse_frame(
        [
            ": keep-alive\r\n",
            "event: milky_event\r\n",
            "id: ignored\r\n",
            "data: 第一行\r\n",
            "data: 第二行\r\n",
        ]
    )

    assert frame.event == "milky_event"
    assert frame.data == "第一行\n第二行"


def test_comment_heartbeat_is_ignored_before_next_event() -> None:
    """SSE 注释心跳不应产生 malformed 诊断或阻断后续事件。"""

    payload = {
        "event_type": "bot_offline",
        "time": 1700000085,
        "self_id": 900000001,
        "data": {"reason": "心跳观察"},
    }
    response = FakeResponse(
        [
            ": keep-alive\n",
            "\n",
            "event: milky_event\n",
            f"data: {json.dumps(payload, ensure_ascii=False)}\n",
            "\n",
            None,
        ]
    )
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=0)
    received = []

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(received.append))
        while not received:
            await asyncio.sleep(0)
        await stream.close()
        await task

    asyncio.run(scenario())

    assert [event.event_type for event in received] == ["bot_offline"]
    assert not any(item.classification == "malformed" for item in stream.diagnostics)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        ["event: milky_event\n"],
        ["data: \n"],
        ["data: 内容\n", 1],
    ],
)
def test_decoder_rejects_malformed_frames_without_echoing_data(lines: list[object]) -> None:
    """缺少 data 或行类型错误的 frame 应安全分类。"""

    with pytest.raises(EventStreamError) as error_info:
        decode_sse_frame(lines)

    assert error_info.value.classification == "malformed"
    assert "内容" not in str(error_info.value)


def test_close_interrupts_backoff_and_is_idempotent(caplog) -> None:
    """停止应打断长退避，重复关闭不产生额外资源操作。"""

    response = FakeResponse([None])
    transport = FakeTransport([response])
    sleep_started = asyncio.Event()
    release_sleep = asyncio.Event()

    async def blocking_sleep(delay: float) -> None:
        sleep_started.set()
        await release_sleep.wait()

    stream = SseEventStream(
        CONFIG,
        transport=transport,
        initial_backoff=60,
        max_backoff=60,
        sleep=blocking_sleep,
    )

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(lambda event: None))
            await asyncio.wait_for(sleep_started.wait(), 1)
            await stream.close()
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    assert response.close_calls == 1
    assert transport.close_calls == 1
    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == [
        "milky_event_stream_disconnected",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_cancelled",
    ]
    assert records[0].reason == "eof"
    assert records[1].attempt == 1
    assert records[1].delay_seconds == 60.0


def test_close_cancels_connection_attempt_without_reconnecting(caplog) -> None:
    """连接建立期间停止也应取消连接，不等待超时或发起新连接。"""

    class BlockingTransport(FakeTransport):
        def __post_init__(self) -> None:
            super().__post_init__()
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def connect(self, url: str, headers: dict[str, str], timeout: float) -> FakeResponse:
            self.connections.append({"url": url, "headers": headers, "timeout": timeout})
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise
            raise AssertionError("连接不应在测试中返回")

    transport = BlockingTransport([])
    stream = SseEventStream(CONFIG, transport=transport)

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(lambda event: None))
            await asyncio.wait_for(transport.started.wait(), 1)
            await stream.close()
            await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    assert transport.cancelled.is_set()
    assert len(transport.connections) == 1
    assert transport.close_calls == 1
    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == ["milky_event_stream_cancelled"]


def test_direct_run_task_cancellation_releases_resources(caplog) -> None:
    """直接取消 receive loop 任务也应释放响应、handler 和 transport。"""

    payload = {
        "event_type": "bot_offline",
        "time": 1700000086,
        "self_id": 900000001,
        "data": {"reason": "取消观察"},
    }
    response = BlockingResponse(
        [
            "event: milky_event\n",
            f"data: {json.dumps(payload, ensure_ascii=False)}\n",
            "\n",
        ]
    )
    transport = FakeTransport([response])
    stream = SseEventStream(CONFIG, transport=transport, initial_backoff=60, max_backoff=60)
    started = asyncio.Event()

    async def handler(event) -> None:
        started.set()
        await asyncio.Event().wait()

    async def scenario() -> None:
        with caplog.at_level(logging.INFO, logger="milky.event_stream"):
            task = asyncio.create_task(stream.run(handler))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())

    assert response.close_calls == 1
    assert transport.close_calls == 1
    records = lifecycle_log_records(caplog)
    assert [record.event_name for record in records] == ["milky_event_stream_cancelled"]


def test_httpx_transport_opens_sse_with_get_and_unlimited_read_timeout() -> None:
    """HTTPX transport 应使用 GET、Bearer 和无固定读取超时。"""

    httpx = pytest.importorskip("httpx")
    seen: dict[str, object] = {}

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": heartbeat\n\n"

    def handler(request):
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    transport = HttpxSseTransport(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def scenario() -> None:
        response = await transport.connect(CONFIG.event_url, CONFIG.auth_headers, 3.5)
        assert await response.readline() == b": heartbeat\n"
        assert await response.readline() == b"\n"
        await response.close()
        await transport.close()
        await transport.close()

    asyncio.run(scenario())

    assert seen["method"] == "GET"
    assert seen["url"] == "https://host.example/milky/event"
    assert seen["headers"]["authorization"] == "Bearer stream-test-secret"
    assert seen["timeout"] == {
        "connect": 3.5,
        "read": None,
        "write": None,
        "pool": 3.5,
    }


def test_httpx_reconnect_does_not_send_unconfirmed_recovery_headers() -> None:
    """重连只使用已确认的 /event 请求，不伪造 Last-Event-ID。"""

    httpx = pytest.importorskip("httpx")
    requests: list[object] = []
    received: list[object] = []
    received_twice = asyncio.Event()
    payload = {
        "event_type": "bot_offline",
        "time": 1700000087,
        "self_id": 900000001,
        "data": {"reason": "恢复边界"},
    }
    frame = (
        b"event: milky_event\n" + f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
    )

    class EventStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield frame

    def handler(request):
        requests.append(dict(request.headers))
        return httpx.Response(200, stream=EventStream())

    transport = HttpxSseTransport(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    stream = SseEventStream(
        CONFIG,
        transport=transport,
        initial_backoff=0.01,
        max_backoff=0.01,
    )

    async def on_event(event) -> None:
        received.append(event)
        if len(received) >= 2:
            received_twice.set()

    async def scenario() -> None:
        task = asyncio.create_task(stream.run(on_event))
        await asyncio.wait_for(received_twice.wait(), 1)
        await stream.close()
        await asyncio.wait_for(task, 1)

    asyncio.run(scenario())

    assert len(requests) >= 2
    assert all(item["authorization"] == "Bearer stream-test-secret" for item in requests)
    assert all("last-event-id" not in item for item in requests)
    assert all("event-id" not in item for item in requests)
