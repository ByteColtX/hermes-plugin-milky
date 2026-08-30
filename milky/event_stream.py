"""Milky SSE ``/event`` 事件流。

本模块只负责 SSE 连接、帧解码、重连和 handler 隔离。事件业务语义交给现有 parser
和后续入站边界处理，不实现 WebSocket echo 或 pending response map。
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, Self

from config import MilkyConfig

from .models import Event
from .parser import ParseError, parse_event


class EventStreamError(Exception):
    """表示事件流连接或协议边界错误。"""

    def __init__(self, classification: str, reason: str) -> None:
        self.classification = classification
        self.reason = reason
        super().__init__(f"{classification}: {reason}")


@dataclass(frozen=True, slots=True)
class SseFrame:
    """保存一个已经按空行边界收集的 SSE frame。"""

    event: str
    data: str


@dataclass(frozen=True, slots=True)
class StreamDiagnostic:
    """保存不包含原始 payload 的安全事件流诊断。"""

    classification: str
    reason: str


class SseResponse(Protocol):
    """定义可逐行读取并可关闭的 SSE 响应。"""

    async def readline(self) -> str | bytes | None:
        """读取下一行，EOF 返回 None。"""

    async def close(self) -> None:
        """关闭响应和底层连接。"""


class SseTransport(Protocol):
    """定义可注入的 SSE 连接 transport。"""

    async def connect(self, url: str, headers: dict[str, str], timeout: float) -> SseResponse:
        """建立一个 GET SSE 连接。"""

    async def close(self) -> None:
        """释放 transport 级资源。"""


class HttpxSseTransportError(OSError):
    """表示 HTTPX SSE transport 不可用或读取结果未知。"""


def _import_httpx() -> Any:
    """延迟导入 Hermes 核心提供的 HTTPX。"""

    try:
        import httpx
    except ImportError:
        raise HttpxSseTransportError("httpx dependency is unavailable") from None
    return httpx


class _HttpxSseResponse:
    """把 HTTPX 异步响应包装成可取消的逐行响应。"""

    def __init__(self, response: Any, stream_context: Any, httpx: Any) -> None:
        self._response = response
        self._stream_context = stream_context
        self._httpx = httpx
        self._chunks = response.aiter_bytes().__aiter__()
        self._buffer = bytearray()
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def readline(self) -> bytes:
        """从原生异步字节流中读取一行，保留 UTF-8 校验边界。"""

        if self._closed:
            return b""
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                end = newline + 1
                line = bytes(self._buffer[:end])
                del self._buffer[:end]
                return line
            try:
                chunk = await anext(self._chunks)
            except StopAsyncIteration:
                if not self._buffer:
                    return b""
                line = bytes(self._buffer)
                self._buffer.clear()
                return line
            except asyncio.CancelledError:
                raise
            except self._httpx.HTTPError:
                raise HttpxSseTransportError("event stream read failed") from None
            if not isinstance(chunk, bytes):
                raise HttpxSseTransportError("event stream returned an invalid chunk")
            self._buffer.extend(chunk)

    async def close(self) -> None:
        """关闭响应上下文，重复关闭保持安全。"""

        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                await self._response.aclose()
            finally:
                await self._stream_context.__aexit__(None, None, None)


class HttpxSseTransport:
    """使用 HTTPX 异步 stream 建立 GET SSE 连接。"""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._response: _HttpxSseResponse | None = None
        self._closed = False
        self._close_lock = asyncio.Lock()

    async def connect(self, url: str, headers: dict[str, str], timeout: float) -> SseResponse:
        """只限制连接建立阶段，读取阶段保持无限时长。"""

        if self._closed:
            raise EventStreamError("transport_unknown", "event stream transport is closed")
        try:
            httpx = _import_httpx()
        except HttpxSseTransportError:
            raise EventStreamError(
                "transport_unknown", "event stream transport dependency is unavailable"
            ) from None
        if self._client is None:
            self._client = httpx.AsyncClient()
        request_timeout = httpx.Timeout(None, connect=timeout, pool=timeout)
        stream_context = self._client.stream(
            "GET",
            url,
            headers=headers,
            timeout=request_timeout,
        )
        try:
            response = await stream_context.__aenter__()
        except asyncio.CancelledError:
            raise
        except httpx.HTTPError:
            raise EventStreamError("transport_unknown", "event stream connection failed") from None
        except (TimeoutError, OSError):
            raise EventStreamError("transport_unknown", "event stream connection failed") from None

        status = getattr(response, "status_code", None)
        if not isinstance(status, int) or not 200 <= status < 300:
            try:
                await response.aclose()
            finally:
                await stream_context.__aexit__(None, None, None)
            raise EventStreamError("http_error", "event stream returned an HTTP error")
        wrapped = _HttpxSseResponse(response, stream_context, httpx)
        self._response = wrapped
        return wrapped

    async def close(self) -> None:
        """幂等关闭当前响应和 HTTPX 连接池。"""

        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            response = self._response
            self._response = None
            first_error: BaseException | None = None
            if response is not None:
                try:
                    await response.close()
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - 继续关闭连接池
                    first_error = error
            if self._client is not None:
                try:
                    await self._client.aclose()
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # noqa: BLE001 - 记录第一个关闭错误
                    if first_error is None:
                        first_error = error
            if first_error is not None:
                raise first_error


Handler = Callable[[Event], Awaitable[object] | object]
Sleep = Callable[[float], Awaitable[object]]


class SseEventStream:
    """消费 Milky ``/event`` SSE，并隔离慢速或失败的 handler。"""

    def __init__(
        self,
        config: MilkyConfig,
        transport: SseTransport | None = None,
        *,
        timeout: float = 10.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
        if (
            not isinstance(initial_backoff, (int, float))
            or isinstance(initial_backoff, bool)
            or initial_backoff < 0
        ):
            raise ValueError("initial_backoff must be a non-negative number")
        if (
            not isinstance(max_backoff, (int, float))
            or isinstance(max_backoff, bool)
            or max_backoff < initial_backoff
        ):
            raise ValueError("max_backoff must not be less than initial_backoff")
        self._config = config
        self._transport = transport or HttpxSseTransport()
        self._timeout = float(timeout)
        self._initial_backoff = float(initial_backoff)
        self._max_backoff = float(max_backoff)
        self._sleep_callback = sleep
        self._connection: SseResponse | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._diagnostics: deque[StreamDiagnostic] = deque(maxlen=128)
        self._stopping = False
        self._stop_event: asyncio.Event | None = None

    @property
    def diagnostics(self) -> tuple[StreamDiagnostic, ...]:
        """返回有界的安全诊断快照。"""

        return tuple(self._diagnostics)

    async def run(self, handler: Handler) -> None:
        """持续消费事件，直到主动关闭或任务被取消。"""

        if self._run_task is not None:
            raise RuntimeError("event stream is already running")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._stopping = False
        self._stop_event = asyncio.Event()
        self._run_task = asyncio.current_task()
        backoff = self._initial_backoff
        try:
            while not self._stopping:
                try:
                    self._connection = await self._connect()
                    if self._connection is None:
                        break
                    backoff = self._initial_backoff
                    await self._consume_connection(handler)
                except asyncio.CancelledError:
                    if not self._stopping:
                        raise
                    break
                except EventStreamError as error:
                    self._record(error.classification, error.reason)
                except (TimeoutError, OSError):
                    self._record("transport_unknown", "event stream connection failed")
                except Exception:  # noqa: BLE001
                    self._record("stream_error", "event stream processing failed")
                finally:
                    await self._close_connection()

                if self._stopping:
                    break
                await self._wait_backoff(backoff)
                backoff = min(self._max_backoff, max(self._initial_backoff, backoff * 2))
        finally:
            self._stopping = True
            if self._stop_event is not None:
                self._stop_event.set()
            await self._close_connection()
            await self._cancel_handlers()
            try:
                await self._transport.close()
            except Exception:  # noqa: BLE001
                self._record("resource_error", "event stream transport close failed")
            self._run_task = None

    async def close(self) -> None:
        """主动停止 receive loop，取消 handler 并释放连接资源。"""

        self._stopping = True
        if self._stop_event is not None:
            self._stop_event.set()
        await self._close_connection()
        await self._cancel_handlers()

    async def _connect(self) -> SseResponse | None:
        """并发等待连接或停止信号，避免取消时卡在连接建立。"""

        if self._stop_event is None:
            raise EventStreamError("transport_unknown", "event stream stop state is unavailable")
        connect_task = asyncio.create_task(
            self._transport.connect(
                self._config.event_url,
                dict(self._config.auth_headers),
                self._timeout,
            )
        )
        stop_task = asyncio.create_task(self._stop_event.wait())
        done, pending = await asyncio.wait(
            {connect_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if stop_task in done and connect_task not in done:
            connect_task.cancel()
            await asyncio.gather(connect_task, return_exceptions=True)
            return None
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return connect_task.result()

    async def _consume_connection(self, handler: Handler) -> None:
        """读取一条连接内的所有 frame，并只调度不等待 handler。"""

        lines: list[str] = []
        while not self._stopping:
            line = await self._readline()
            if self._stopping:
                return
            if line is None:
                if lines:
                    await self._dispatch_frame(lines, handler)
                return
            if not line.strip("\r\n"):
                if lines:
                    await self._dispatch_frame(lines, handler)
                    lines = []
                continue
            lines.append(line)

    async def _readline(self) -> str | None:
        """读取并校验一行 SSE 文本。"""

        if self._connection is None:
            raise EventStreamError("transport_unknown", "event stream connection is unavailable")
        line = await self._connection.readline()
        if line is None or line == b"" or line == "":
            return None
        if isinstance(line, bytes):
            try:
                return line.decode("utf-8")
            except UnicodeDecodeError:
                raise EventStreamError("malformed", "event stream line is not UTF-8") from None
        if isinstance(line, str):
            return line
        raise EventStreamError("malformed", "event stream line has an invalid type")

    async def _dispatch_frame(self, lines: Sequence[str], handler: Handler) -> None:
        """解析 frame，并将合法事件交给独立 task。"""

        if all(not line.strip("\r\n") or line.rstrip("\r\n").startswith(":") for line in lines):
            return
        try:
            frame = decode_sse_frame(lines)
        except EventStreamError as error:
            self._record(error.classification, error.reason)
            return
        if frame.event != "milky_event":
            self._record("unknown", "unsupported SSE event name")
            return
        try:
            payload = json.loads(frame.data)
            event = parse_event(payload, outer_event_type=frame.event)
            if not event.event_type.strip():
                raise ParseError("malformed", "event_type is empty")
        except (json.JSONDecodeError, ParseError, TypeError, ValueError):
            self._record("malformed", "event frame payload is malformed")
            return
        task = asyncio.create_task(self._invoke_handler(event, handler))
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_tasks.discard)

    async def _invoke_handler(self, event: Event, handler: Handler) -> None:
        """执行单个 handler，并隔离其异常。"""

        try:
            result = handler(event)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            self._record("handler_error", "event handler failed")

    async def _wait_backoff(self, delay: float) -> None:
        """等待退避或在主动停止时立即结束等待。"""

        if delay <= 0:
            await asyncio.sleep(0)
            return
        if self._stop_event is None:
            return
        sleep_task = asyncio.create_task(self._sleep_callback(delay))
        stop_task = asyncio.create_task(self._stop_event.wait())
        done, pending = await asyncio.wait(
            {sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()

    async def _cancel_handlers(self) -> None:
        """取消并等待仍在运行的 handler。"""

        tasks = tuple(self._handler_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._handler_tasks.clear()

    async def _close_connection(self) -> None:
        """关闭当前响应，避免重复 close。"""

        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            await connection.close()
        except Exception:  # noqa: BLE001
            self._record("resource_error", "event stream response close failed")

    def _record(self, classification: str, reason: str) -> None:
        """记录不含凭证、正文和原始 URL 的固定诊断。"""

        self._diagnostics.append(StreamDiagnostic(classification, reason))

    async def __aenter__(self) -> Self:
        """支持异步上下文管理器形式使用。"""

        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """离开上下文时停止事件流。"""

        await self.close()


def decode_sse_frame(lines: Sequence[str]) -> SseFrame:
    """按 SSE 字段规则解码一组 frame 行。"""

    if isinstance(lines, (str, bytes, bytearray)) or not isinstance(lines, Sequence):
        raise EventStreamError("malformed", "event frame lines are invalid")
    event = "message"
    data: list[str] = []
    for line in lines:
        if not isinstance(line, str):
            raise EventStreamError("malformed", "event frame line is invalid")
        value = line.rstrip("\r\n")
        if not value or value.startswith(":"):
            continue
        field, separator, field_value = value.partition(":")
        if separator and field_value.startswith(" "):
            field_value = field_value[1:]
        if field == "event":
            event = field_value
        elif field == "data":
            data.append(field_value)
    if not data or not any(data):
        raise EventStreamError("malformed", "event frame has no data")
    return SseFrame(event=event, data="\n".join(data))


__all__ = [
    "EventStreamError",
    "HttpxSseTransport",
    "HttpxSseTransportError",
    "SseEventStream",
    "SseFrame",
    "SseResponse",
    "SseTransport",
    "StreamDiagnostic",
    "decode_sse_frame",
]
