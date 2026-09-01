"""管理按 chat 隔离的短期 context-only 系统事件。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock

from .identity import validate_chat_key

_MAX_DIAGNOSTICS = 256


@dataclass(frozen=True, slots=True)
class ContextOnlyEvent:
    """保存一条不进入普通消息流水线的系统上下文记录。"""

    chat_key: str
    event_type: str
    body: str
    ingress_sequence: int | None = None
    sender_id: int | None = None
    receiver_id: int | None = None
    is_self_poke: bool = False

    @property
    def sequence(self) -> int | None:
        """返回兼容命名的 ingress 顺序。"""

        return self.ingress_sequence

    @property
    def self_poke(self) -> bool:
        """返回 nudge 是否明确指向 Bot。"""

        return self.is_self_poke


SystemContextEntry = ContextOnlyEvent


@dataclass(frozen=True, slots=True)
class ContextBufferDiagnostic:
    """保存不包含事件正文的 system context 诊断。"""

    chat_key: str
    reason: str
    ingress_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class ContextAppendResult:
    """表示 system context 是否保存及是否淘汰了最早事件。"""

    accepted: bool
    reason: str
    evicted: ContextOnlyEvent | None = None

    @property
    def dropped(self) -> ContextOnlyEvent | None:
        """返回因容量限制被丢弃的最早事件。"""

        return self.evicted


class SystemContextBuffer:
    """维护每个 chat 独立、有界且可丢失的系统上下文 FIFO。"""

    def __init__(self, max_size: int = 20) -> None:
        """创建 system context buffer；零容量表示禁用注入。"""

        if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size < 0:
            raise ValueError("system context max_size must be a non-negative integer")
        self._max_size = max_size
        self._buffers: dict[str, deque[ContextOnlyEvent]] = {}
        self._diagnostics: deque[ContextBufferDiagnostic] = deque(maxlen=_MAX_DIAGNOSTICS)
        self._next_sequence_value = 1
        self._lock = RLock()

    @property
    def max_size(self) -> int:
        """返回每个 chat 的系统事件上限。"""

        return self._max_size

    @property
    def diagnostics(self) -> tuple[ContextBufferDiagnostic, ...]:
        """返回不包含事件正文的有界诊断快照。"""

        with self._lock:
            return tuple(self._diagnostics)

    def append(
        self,
        event_or_chat_key: ContextOnlyEvent | str,
        event_type: str | None = None,
        body: str | None = None,
        *,
        ingress_sequence: int | None = None,
    ) -> ContextAppendResult:
        """保存一条系统事件，必要时淘汰最早记录。"""

        sender_id: int | None = None
        receiver_id: int | None = None
        is_self_poke = False
        if isinstance(event_or_chat_key, ContextOnlyEvent):
            if event_type is not None or body is not None:
                raise TypeError("event fields must be omitted for ContextOnlyEvent")
            event = event_or_chat_key
            normalized_key = validate_chat_key(event.chat_key)
            event_type = event.event_type
            body = event.body
            sender_id = event.sender_id
            receiver_id = event.receiver_id
            is_self_poke = event.is_self_poke
            if ingress_sequence is None:
                ingress_sequence = event.ingress_sequence
        else:
            normalized_key = validate_chat_key(event_or_chat_key)

        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("system context event_type must be non-empty text")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("system context body must be non-empty text")

        with self._lock:
            sequence = self._next_sequence(ingress_sequence)
            if self._max_size == 0:
                self._diagnostics.append(
                    ContextBufferDiagnostic(normalized_key, "system_context_disabled", sequence)
                )
                return ContextAppendResult(False, "system_context_disabled")

            event = ContextOnlyEvent(
                chat_key=normalized_key,
                event_type=event_type.strip(),
                body=body,
                ingress_sequence=sequence,
                sender_id=sender_id,
                receiver_id=receiver_id,
                is_self_poke=is_self_poke,
            )
            buffer = self._buffers.setdefault(normalized_key, deque())
            evicted = buffer.popleft() if len(buffer) >= self._max_size else None
            buffer.append(event)
            if evicted is not None:
                self._diagnostics.append(
                    ContextBufferDiagnostic(
                        normalized_key,
                        "system_context_overflow",
                        evicted.ingress_sequence,
                    )
                )
                return ContextAppendResult(True, "system_context_overflow", evicted)
            return ContextAppendResult(True, "stored", None)

    def add(
        self,
        event_or_chat_key: ContextOnlyEvent | str,
        event_type: str | None = None,
        body: str | None = None,
        *,
        ingress_sequence: int | None = None,
    ) -> ContextAppendResult:
        """提供语义化的 system context 保存入口。"""

        return self.append(
            event_or_chat_key,
            event_type,
            body,
            ingress_sequence=ingress_sequence,
        )

    def snapshot(self, chat_key: str) -> tuple[ContextOnlyEvent, ...]:
        """返回指定 chat 的 oldest-first 系统事件快照。"""

        normalized_key = validate_chat_key(chat_key)
        with self._lock:
            return tuple(
                sorted(
                    self._buffers.get(normalized_key, ()),
                    key=lambda event: event.ingress_sequence or 0,
                )
            )

    def size(self, chat_key: str) -> int:
        """返回指定 chat 当前的系统事件数量。"""

        return len(self.snapshot(chat_key))

    def snapshot_entries(self, chat_key: str) -> tuple[ContextOnlyEvent, ...]:
        """返回指定 chat 的带 ingress 顺序事件快照。"""

        return self.snapshot(chat_key)

    def drain(self, chat_key: str) -> tuple[ContextOnlyEvent, ...]:
        """原子取出并清除指定 chat 的系统事件。"""

        normalized_key = validate_chat_key(chat_key)
        with self._lock:
            events = tuple(self._buffers.pop(normalized_key, ()))
        return tuple(sorted(events, key=lambda event: event.ingress_sequence or 0))

    def _next_sequence(self, explicit: int | None) -> int:
        if explicit is None:
            sequence = self._next_sequence_value
            self._next_sequence_value += 1
            return sequence
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit < 0:
            raise ValueError("ingress_sequence must be a non-negative integer")
        self._next_sequence_value = max(self._next_sequence_value, explicit + 1)
        return explicit


ContextBuffer = SystemContextBuffer


__all__ = [
    "ContextAppendResult",
    "ContextBuffer",
    "ContextBufferDiagnostic",
    "ContextOnlyEvent",
    "SystemContextBuffer",
    "SystemContextEntry",
]
