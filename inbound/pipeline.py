"""编排 Milky message_receive 到 Hermes 的入站流水线。"""

from __future__ import annotations

import asyncio
import inspect
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from gates import GateContext, GateRegistry
from milky.models import Event
from milky.parser import ParseError, parse_event
from milky.resources import ResolvedTriggerBatch, ResourceResolver
from session import (
    ChatAdmissionCoordinator,
    TtlDeduplicator,
    WaitBuffer,
    render_channel_context,
)
from will import WillInput

from .canonical import CanonicalMessage, canonicalize_event
from .hermes_mapper import build_source, map_message_event

Observer = Callable[[Event], Awaitable[object] | object]


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """表示一次事件在入站边界的可观察结果。"""

    classification: str
    canonical: CanonicalMessage | None = None
    reason: str | None = None
    batch: object | None = None


class InboundPipeline:
    """执行 canonical、dedup、Gate、Will、buffer 和 Hermes detached 交接。"""

    def __init__(
        self,
        *,
        self_id: int,
        hermes: object,
        resource_resolver: ResourceResolver,
        gate_registry: GateRegistry,
        will_engine: object,
        wait_buffer: WaitBuffer[CanonicalMessage],
        admission: ChatAdmissionCoordinator,
        deduplicator: TtlDeduplicator,
        message_event_cls: type | None = None,
        message_type_cls: type | None = None,
        observer: Observer | None = None,
        mute_tracker: object | None = None,
    ) -> None:
        """创建一次入站 pipeline；不在构造阶段联网或启动任务。"""

        if isinstance(self_id, bool) or not isinstance(self_id, int) or self_id < 0:
            raise ValueError("self_id must be a non-negative integer")
        self._self_id = self_id
        self._hermes = hermes
        self._resolver = resource_resolver
        self._gates = gate_registry
        self._will = will_engine
        self._buffer = wait_buffer
        self._admission = admission
        self._deduplicator = deduplicator
        self._message_event_cls = message_event_cls
        self._message_type_cls = message_type_cls
        self._observer = observer
        self._mute_tracker = mute_tracker
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._diagnostics: deque[str] = deque(maxlen=128)
        self._reply_costs = 0
        self._accepting = True

    def start(self) -> None:
        """重新开放事件进入 pipeline 的边界。"""

        self._accepting = True

    async def close(self) -> None:
        """停止接收事件并取消尚未完成的 detached 交接任务。"""

        self._accepting = False
        tasks = tuple(self._background_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    @property
    def diagnostics(self) -> tuple[str, ...]:
        """返回不含正文、凭证和路径的有界诊断。"""

        return tuple(self._diagnostics)

    @property
    def reply_costs(self) -> int:
        """返回本 pipeline 成功提交后的反馈次数。"""

        return self._reply_costs

    def with_observer(self, observer: Observer | None) -> InboundPipeline:
        """返回共享依赖但替换系统事件观察回调的 pipeline。"""

        return self._copy(observer=observer)

    def with_will_engine(self, will_engine: object) -> InboundPipeline:
        """返回共享依赖但替换 Will engine 的 pipeline。"""

        return self._copy(will_engine=will_engine)

    async def handle_event(self, event: Event | object) -> PipelineResult:
        """处理一帧事件；trigger 的资源和 Hermes 交接以 detached task 执行。"""

        if not self._accepting:
            return PipelineResult("stopped", reason="inbound pipeline is stopped")
        try:
            parsed_event = event if isinstance(event, Event) else parse_event(event)
        except ParseError as error:
            self._record(f"{error.classification}:event")
            return PipelineResult(error.classification, reason=error.reason)

        if parsed_event.event_type != "message_receive":
            await self._observe(parsed_event)
            return PipelineResult("observe_only", reason="event is not message_receive")

        canonical_result = canonicalize_event(
            parsed_event,
            expected_self_id=self._self_id,
        )
        if canonical_result.classification != "accepted" or canonical_result.value is None:
            return PipelineResult(
                canonical_result.classification,
                reason=canonical_result.reason,
            )
        canonical = canonical_result.value
        if self._deduplicator.check_and_mark(canonical.dedup_key):
            self._record("duplicate")
            return PipelineResult("duplicate", canonical=canonical, reason="duplicate_message")

        async with self._admission.admit(canonical.chat_key) as ticket:
            gate_result = self._gates.check(self._gate_context(canonical))
            if not gate_result.allow:
                self._record(f"gate:{gate_result.reason}")
                return PipelineResult("denied", canonical=canonical, reason=gate_result.reason)
            if canonical.will_input is None:
                self._record("malformed:missing_will_input")
                return PipelineResult(
                    "malformed", canonical=canonical, reason="normalized Will input is missing"
                )
            decision = self._will_decide(canonical.will_input)
            if decision == "wait":
                self._buffer.append(
                    canonical.chat_key,
                    canonical,
                    ingress_sequence=ticket.ingress_sequence,
                )
                return PipelineResult("wait", canonical=canonical)
            if decision != "trigger":
                self._record("will:invalid_decision")
                return PipelineResult(
                    "malformed", canonical=canonical, reason="invalid Will decision"
                )
            batch = self._buffer.drain(
                canonical.chat_key,
                canonical,
                ingress_sequence=ticket.ingress_sequence,
            )
            self._start_detached(batch)
            return PipelineResult("trigger", canonical=canonical, batch=batch)

    async def wait_idle(self) -> None:
        """等待当前已创建的 detached 交接任务，不等待 Hermes Agent。"""

        while self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks))

    async def _process_batch(self, batch: object) -> None:
        try:
            resolved_batch = await self._resolver.resolve_batch(batch)
            source_builder = getattr(self._hermes, "build_source", None)
            if not callable(source_builder):
                raise TypeError("Hermes source builder is unavailable")
            current = batch.current
            source = build_source(current, source_builder)
            event = map_message_event(
                current,
                resolved_batch.current,
                channel_context=_render_resolved_history(batch, resolved_batch),
                source=source,
                message_event_cls=self._message_event_cls,
                message_type_cls=self._message_type_cls,
            )
            handle_message = getattr(self._hermes, "handle_message", None)
            if not callable(handle_message):
                raise TypeError("Hermes handle_message is unavailable")
            result = handle_message(event)
            if inspect.isawaitable(result):
                await result
            self._notify_reply_cost(current.chat_key)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - detached boundary records safe failure
            self._buffer.record_handoff_failure(batch, recoverable=False)
            self._record(f"trigger_failed:{_error_category(error)}")

    def _start_detached(self, batch: object) -> None:
        task = asyncio.create_task(self._process_batch(batch))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _gate_context(self, message: CanonicalMessage) -> GateContext:
        member_mute = "muted"
        whole_mute = "muted"
        if message.scene == "group" and self._mute_tracker is not None:
            snapshot = getattr(self._mute_tracker, "gate_snapshot", None)
            if callable(snapshot):
                try:
                    member_mute, whole_mute = snapshot(message.peer_id)
                except Exception:  # noqa: BLE001 - unknown state stays fail-closed
                    member_mute, whole_mute = "muted", "muted"
        return GateContext(
            self_id=str(message.self_id),
            sender_id=str(message.sender_id),
            scene=message.scene,  # type: ignore[arg-type]
            chat_key=message.chat_key,
            member_mute=member_mute,  # type: ignore[arg-type]
            whole_mute=whole_mute,  # type: ignore[arg-type]
        )

    def _will_decide(self, value: WillInput) -> str:
        decide = getattr(self._will, "decide", None)
        if not callable(decide):
            raise TypeError("Will engine must provide decide")
        return decide(value)

    def _notify_reply_cost(self, chat_key: str) -> None:
        callback = getattr(self._will, "on_reply_submitted", None)
        if callable(callback):
            try:
                callback(chat_key)
            except Exception:  # noqa: BLE001 - feedback cannot undo a submitted turn
                self._record("will_feedback_error")
        self._reply_costs += 1

    async def _observe(self, event: Event) -> None:
        if self._mute_tracker is not None:
            apply_event = getattr(self._mute_tracker, "apply_event", None)
            if callable(apply_event):
                try:
                    apply_event(event)
                except Exception:  # noqa: BLE001 - observe-only state cannot trigger Agent
                    self._record("observe_state_error")
        if self._observer is None:
            return
        try:
            result = self._observer(event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - observer must not break event processing
            self._record("observer_error")

    def _record(self, reason: str) -> None:
        self._diagnostics.append(reason)

    def _copy(self, **overrides: object) -> InboundPipeline:
        values: dict[str, Any] = {
            "self_id": self._self_id,
            "hermes": self._hermes,
            "resource_resolver": self._resolver,
            "gate_registry": self._gates,
            "will_engine": self._will,
            "wait_buffer": self._buffer,
            "admission": self._admission,
            "deduplicator": self._deduplicator,
            "message_event_cls": self._message_event_cls,
            "message_type_cls": self._message_type_cls,
            "observer": self._observer,
            "mute_tracker": self._mute_tracker,
        }
        values.update(overrides)
        return type(self)(**values)


def _render_resolved_history(batch: object, resolved_batch: ResolvedTriggerBatch) -> str | None:
    """使用 resolver 完成后的正文渲染历史上下文，不带当前消息。"""

    records = []
    for canonical, resolved in zip(batch.history, resolved_batch.history, strict=True):
        records.append(
            _HistoryRecord(
                chat_key=canonical.chat_key,
                sender_name=canonical.sender_name,
                sender_id=canonical.sender_id,
                body=resolved.body,
                message_id=canonical.message_id,
                quote_message_id=canonical.quote_message_id,
            )
        )
    return render_channel_context(records)


@dataclass(frozen=True, slots=True)
class _HistoryRecord:
    """提供历史上下文 renderer 所需的安全字段。"""

    chat_key: str
    sender_name: str
    sender_id: int
    body: str
    message_id: str | None
    quote_message_id: str | None


def _error_category(error: Exception) -> str:
    return type(error).__name__.lower().replace("error", "")[:64] or "failure"


__all__ = ["InboundPipeline", "PipelineResult"]
