"""实现按 chat 隔离的有界 wait buffer 和 detached trigger batch。"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from threading import RLock
from typing import Literal

from .context import ContextOnlyEvent
from .identity import validate_chat_key

_MAX_DIAGNOSTICS = 256


@dataclass(frozen=True, slots=True)
class WaitBufferEntry[T]:
    """保存一条 wait 历史及其 ingress 顺序。"""

    chat_key: str
    message: T
    ingress_sequence: int


@dataclass(frozen=True, slots=True)
class BufferDiagnostic:
    """保存不包含消息正文的 buffer 安全诊断。"""

    chat_key: str
    reason: str
    ingress_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class BufferAppendResult[T]:
    """表示 wait 消息是否保存以及是否淘汰了最早历史。"""

    accepted: bool
    reason: str
    evicted: WaitBufferEntry[T] | None = None

    @property
    def dropped(self) -> WaitBufferEntry[T] | None:
        """返回因容量限制被丢弃的历史消息。"""

        return self.evicted


@dataclass(frozen=True, slots=True)
class DetachedTriggerBatch[T]:
    """表示已经从 buffer 原子取出、可独立交接的 trigger 批次。"""

    chat_key: str
    history: tuple[T, ...]
    current: T
    trigger_ingress_sequence: int = 0
    history_ingress_sequences: tuple[int, ...] = ()
    system_context: tuple[ContextOnlyEvent, ...] = ()

    @property
    def channel_context(self) -> str | None:
        """将历史消息渲染为 Hermes 的只读 channel_context。"""

        sequences = self.history_ingress_sequences
        if len(sequences) != len(self.history):
            sequences = tuple(range(len(self.history)))
        regular = tuple(
            (
                sequence,
                message,
            )
            for sequence, message in zip(
                sequences,
                self.history,
                strict=False,
            )
        )
        system = tuple((event.ingress_sequence or 0, event) for event in self.system_context)
        return render_ordered_context((*regular, *system))

    @property
    def current_text(self) -> str:
        """将当前消息渲染为本次 turn 的正文，不混入历史上下文。"""

        return render_message_record(self.current)

    @property
    def history_entries(self) -> tuple[T, ...]:
        """返回历史消息的兼容别名。"""

        return self.history

    def retry(self) -> DetachedTriggerBatch[T]:
        """返回同一 detached batch，供失败交接重试。"""

        return self


HandoffAction = Literal["retry_same_batch", "recorded_failure"]


@dataclass(frozen=True, slots=True)
class HandoffFailureResult[T]:
    """表示 detached batch 失败后的明确处理结果。"""

    action: HandoffAction
    batch: DetachedTriggerBatch[T] | None


class WaitBuffer[T]:
    """管理每个 chat 独立且有界的 Will wait 历史。"""

    def __init__(self, max_size: int = 20) -> None:
        """创建 wait buffer；零容量表示禁用历史保存。"""

        if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < 0:
            raise ValueError("wait buffer max_size must be a non-negative integer")
        self._max_size = max_size
        self._buffers: dict[str, deque[WaitBufferEntry[T]]] = {}
        self._diagnostics: deque[BufferDiagnostic] = deque(maxlen=_MAX_DIAGNOSTICS)
        self._next_sequence_value = 1
        self._lock = RLock()

    @property
    def max_size(self) -> int:
        """返回每个 chat 的历史上限。"""

        return self._max_size

    @property
    def capacity(self) -> int:
        """返回与配置语义一致的容量别名。"""

        return self._max_size

    @property
    def diagnostics(self) -> tuple[BufferDiagnostic, ...]:
        """返回不包含正文和 raw 的诊断快照。"""

        with self._lock:
            return tuple(self._diagnostics)

    def append(
        self,
        chat_key: str,
        message: T,
        *,
        ingress_sequence: int | None = None,
    ) -> BufferAppendResult[T]:
        """保存一条 wait 消息，必要时按 FIFO 淘汰最早历史。"""

        normalized_key = validate_chat_key(chat_key)
        _validate_message_chat_key(message, normalized_key)
        with self._lock:
            sequence = self._next_sequence(ingress_sequence)
            if self._max_size == 0:
                self._diagnostics.append(
                    BufferDiagnostic(normalized_key, "wait_buffer_disabled", sequence)
                )
                return BufferAppendResult(False, "wait_buffer_disabled")

            buffer = self._buffers.setdefault(normalized_key, deque())
            evicted = buffer.popleft() if len(buffer) >= self._max_size else None
            buffer.append(WaitBufferEntry(normalized_key, message, sequence))
            if evicted is not None:
                self._diagnostics.append(
                    BufferDiagnostic(
                        normalized_key, "wait_buffer_overflow", evicted.ingress_sequence
                    )
                )
                return BufferAppendResult(True, "wait_buffer_overflow", evicted)
            return BufferAppendResult(True, "stored", None)

    def add(
        self,
        chat_key: str,
        message: T,
        *,
        ingress_sequence: int | None = None,
    ) -> BufferAppendResult[T]:
        """提供语义化的 wait 保存入口。"""

        return self.append(chat_key, message, ingress_sequence=ingress_sequence)

    def snapshot(self, chat_key: str) -> tuple[T, ...]:
        """返回指定 chat 的 oldest-first 历史消息快照。"""

        return tuple(entry.message for entry in self.snapshot_entries(chat_key))

    def snapshot_entries(self, chat_key: str) -> tuple[WaitBufferEntry[T], ...]:
        """返回指定 chat 的带 ingress 顺序历史快照。"""

        normalized_key = validate_chat_key(chat_key)
        with self._lock:
            return tuple(self._buffers.get(normalized_key, ()))

    def size(self, chat_key: str) -> int:
        """返回指定 chat 当前保存的历史数量。"""

        return len(self.snapshot_entries(chat_key))

    def drain(
        self,
        chat_key: str,
        current: T,
        *,
        ingress_sequence: int | None = None,
    ) -> DetachedTriggerBatch[T]:
        """原子清空指定 chat 历史，并返回不持有 buffer 的 detached batch。"""

        normalized_key = validate_chat_key(chat_key)
        _validate_message_chat_key(current, normalized_key)
        with self._lock:
            sequence = self._next_sequence(ingress_sequence)
            entries = tuple(self._buffers.pop(normalized_key, ()))
        return DetachedTriggerBatch(
            chat_key=normalized_key,
            history=tuple(entry.message for entry in entries),
            current=current,
            trigger_ingress_sequence=sequence,
            history_ingress_sequences=tuple(entry.ingress_sequence for entry in entries),
        )

    def record_handoff_failure(
        self,
        batch: DetachedTriggerBatch[T],
        *,
        recoverable: bool,
    ) -> HandoffFailureResult[T]:
        """记录安全失败并明确返回重试原 batch 或终止交接。"""

        if not isinstance(batch, DetachedTriggerBatch):
            raise TypeError("batch must be a DetachedTriggerBatch")
        normalized_key = validate_chat_key(batch.chat_key)
        action: HandoffAction
        if recoverable:
            action = "retry_same_batch"
            reason = "detached_handoff_retry"
            returned_batch: DetachedTriggerBatch[T] | None = batch.retry()
        else:
            action = "recorded_failure"
            reason = "detached_handoff_failed"
            returned_batch = None
        with self._lock:
            self._diagnostics.append(
                BufferDiagnostic(normalized_key, reason, batch.trigger_ingress_sequence)
            )
        return HandoffFailureResult(action, returned_batch)

    def handle_handoff_failure(
        self,
        batch: DetachedTriggerBatch[T],
        *,
        recoverable: bool,
    ) -> HandoffFailureResult[T]:
        """提供与 ``record_handoff_failure`` 等价的入口。"""

        return self.record_handoff_failure(batch, recoverable=recoverable)

    def _next_sequence(self, explicit: int | None) -> int:
        if explicit is None:
            sequence = self._next_sequence_value
            self._next_sequence_value += 1
            return sequence
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit < 0:
            raise ValueError("ingress_sequence must be a non-negative integer")
        self._next_sequence_value = max(self._next_sequence_value, explicit + 1)
        return explicit


def render_message_record(message: object) -> str:
    """按稳定单行尖括号格式渲染消息，不读取 raw payload。"""

    sender_name = _required_field(message, "sender_name")
    sender_id = _required_field(message, "sender_id")
    body = _required_field(message, "body")
    message_id = getattr(message, "message_id", None)
    reply_id = getattr(message, "quote_message_id", None)
    if reply_id is None:
        reply_id = getattr(message, "reply_message_id", None)

    fields = [
        _escape_header(sender_name),
        "uid",
        _escape_header(sender_id),
    ]
    if message_id is not None:
        fields.extend(("msg_id", _escape_header(message_id)))
    if reply_id is not None:
        fields.extend(("reply_to", _escape_header(reply_id)))
    return f"<{' '.join(fields)}> {_escape_body(body)}"


def render_channel_context(messages: Iterable[object]) -> str | None:
    """按 oldest-first 顺序渲染历史；空历史返回 None。"""

    records = tuple(render_message_record(message) for message in messages)
    return None if not records else "\n".join(records)


def render_system_context_record(event: ContextOnlyEvent) -> str:
    """渲染一条 context-only 系统事件。"""

    if not isinstance(event, ContextOnlyEvent):
        raise TypeError("event must be a ContextOnlyEvent")
    return f"<event {_escape_header(event.event_type)}> {_escape_body(event.body)}"


def render_ordered_context(records: Iterable[tuple[int, object]]) -> str | None:
    """按 ingress sequence 合并普通历史和系统上下文。"""

    ordered = sorted(records, key=lambda item: item[0])
    rendered: list[str] = []
    for _sequence, record in ordered:
        if isinstance(record, ContextOnlyEvent):
            rendered.append(render_system_context_record(record))
        else:
            rendered.append(render_message_record(record))
    return None if not rendered else "\n".join(rendered)


def _required_field(message: object, field_name: str) -> object:
    try:
        value = getattr(message, field_name)
    except AttributeError as error:
        raise TypeError(f"message must provide {field_name}") from error
    if value is None:
        raise TypeError(f"message {field_name} cannot be None")
    return value


def _escape_header(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def _escape_body(value: object) -> str:
    return str(value).replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")


def _validate_message_chat_key(message: object, chat_key: str) -> None:
    message_key = getattr(message, "chat_key", None)
    if message_key is None:
        return
    try:
        normalized_message_key = validate_chat_key(message_key)
    except (TypeError, ValueError) as error:
        raise ValueError("message chat_key is invalid") from error
    if normalized_message_key != chat_key:
        raise ValueError("message chat_key disagrees with buffer chat_key")


# 为调用方提供描述性别名，同时保持实际状态只有 WaitBuffer 一个拥有者。
format_message_record = render_message_record
format_channel_context = render_channel_context


__all__ = [
    "BufferAppendResult",
    "BufferDiagnostic",
    "DetachedTriggerBatch",
    "HandoffFailureResult",
    "WaitBuffer",
    "WaitBufferEntry",
    "format_channel_context",
    "format_message_record",
    "render_channel_context",
    "render_message_record",
    "render_ordered_context",
    "render_system_context_record",
]
