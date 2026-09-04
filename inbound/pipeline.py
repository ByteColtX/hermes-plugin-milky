"""编排 Milky message_receive 到 Hermes 的入站流水线。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any

from gates import GateContext, GateRegistry
from milky.models import Event
from milky.observability import log_event
from milky.parser import ParseError, parse_event
from milky.resources import (
    HermesAttachmentMaterialization,
    ResolvedTriggerBatch,
    ResourceResolver,
)
from session import (
    ChatAdmissionCoordinator,
    ContextOnlyEvent,
    SystemContextBuffer,
    TtlDeduplicator,
    WaitBuffer,
    render_ordered_context,
)
from will import WillInput

from .canonical import CanonicalMessage, canonicalize_event
from .commands import recognize_slash_command
from .hermes_mapper import build_source, map_command_event, map_message_event
from .system_events import parse_context_event

Observer = Callable[[Event], Awaitable[object] | object]

logger = logging.getLogger(__name__)


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
        system_context_buffer: SystemContextBuffer | None = None,
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
        self._system_context = system_context_buffer or SystemContextBuffer(wait_buffer.max_size)
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
            log_event(
                logger,
                "milky_inbound_canonical_rejected",
                logging.DEBUG,
                stage="canonical",
                classification=_safe_classification(error.classification),
                reason="invalid_message",
            )
            return PipelineResult(error.classification, reason=error.reason)

        if parsed_event.event_type != "message_receive":
            context_result = parse_context_event(parsed_event)
            if context_result.value is not None:
                await self._store_context_event(context_result.value)
            elif context_result.classification in {"malformed", "unsupported"}:
                self._record(f"system_context:{context_result.classification}")
            log_event(
                logger,
                "milky_inbound_observe_only",
                logging.DEBUG,
                stage="canonical",
                reason="unsupported_event",
            )
            await self._observe(parsed_event)
            return PipelineResult("observe_only", reason="event is not message_receive")

        canonical_result = canonicalize_event(
            parsed_event,
            expected_self_id=self._self_id,
        )
        if canonical_result.classification != "accepted" or canonical_result.value is None:
            event_name = (
                "milky_inbound_temp_ignored"
                if canonical_result.classification == "ignored_temp"
                else "milky_inbound_canonical_rejected"
            )
            log_event(
                logger,
                event_name,
                logging.DEBUG,
                stage="canonical",
                scene="temp" if event_name == "milky_inbound_temp_ignored" else "friend",
                classification=(
                    "unsupported"
                    if event_name == "milky_inbound_temp_ignored"
                    else _safe_classification(canonical_result.classification)
                ),
                reason=(
                    "temporary_message"
                    if event_name == "milky_inbound_temp_ignored"
                    else "canonical_rejected"
                ),
            )
            return PipelineResult(
                canonical_result.classification,
                reason=canonical_result.reason,
            )
        canonical = canonical_result.value
        if self._deduplicator.check_and_mark(canonical.dedup_key):
            self._record("duplicate")
            log_event(
                logger,
                "milky_inbound_duplicate",
                logging.DEBUG,
                stage="dedup",
                scene=canonical.scene,
                chat_key=canonical.chat_key,
                message_id=canonical.message_id,
                reason="duplicate_message",
            )
            return PipelineResult("duplicate", canonical=canonical, reason="duplicate_message")

        async with self._admission.admit(canonical.chat_key) as ticket:
            gate_result = self._gates.check(self._gate_context(canonical))
            if not gate_result.allow:
                self._record(f"gate:{gate_result.reason}")
                log_event(
                    logger,
                    "milky_inbound_gate_denied",
                    logging.DEBUG,
                    stage="gate",
                    scene=canonical.scene,
                    chat_key=canonical.chat_key,
                    message_id=canonical.message_id,
                    gate=_gate_name(gate_result.reason),
                    reason=_safe_gate_reason(gate_result.reason),
                )
                return PipelineResult("denied", canonical=canonical, reason=gate_result.reason)
            command = recognize_slash_command(canonical)
            if command is not None:
                self._start_command(canonical)
                return PipelineResult("command", canonical=canonical)
            if canonical.will_input is None:
                self._record("malformed:missing_will_input")
                log_event(
                    logger,
                    "milky_inbound_canonical_rejected",
                    logging.DEBUG,
                    stage="canonical",
                    scene=canonical.scene,
                    chat_key=canonical.chat_key,
                    message_id=canonical.message_id,
                    classification="malformed",
                    reason="invalid_message",
                )
                return PipelineResult(
                    "malformed", canonical=canonical, reason="normalized Will input is missing"
                )
            decision = self._will_decide(canonical.will_input)
            if decision in {"wait", "trigger"}:
                log_event(
                    logger,
                    "milky_will_decision",
                    logging.DEBUG,
                    stage="will",
                    scene=canonical.scene,
                    chat_key=canonical.chat_key,
                    message_id=canonical.message_id,
                    decision=decision,
                    ingress_sequence=ticket.ingress_sequence,
                )
            if decision == "wait":
                append_result = self._buffer.append(
                    canonical.chat_key,
                    canonical,
                    ingress_sequence=ticket.ingress_sequence,
                )
                wait_fields: dict[str, object] = {
                    "stage": "buffer",
                    "scene": canonical.scene,
                    "chat_key": canonical.chat_key,
                    "message_id": canonical.message_id,
                    "decision": "wait",
                    "ingress_sequence": ticket.ingress_sequence,
                }
                if not append_result.accepted:
                    wait_fields["reason"] = "buffer_overflow"
                log_event(logger, "milky_inbound_wait", logging.INFO, **wait_fields)
                return PipelineResult("wait", canonical=canonical)
            if decision != "trigger":
                self._record("will:invalid_decision")
                log_event(
                    logger,
                    "milky_inbound_canonical_rejected",
                    logging.WARNING,
                    stage="will",
                    scene=canonical.scene,
                    chat_key=canonical.chat_key,
                    message_id=canonical.message_id,
                    classification="malformed",
                    reason="invalid_decision",
                )
                return PipelineResult(
                    "malformed", canonical=canonical, reason="invalid Will decision"
                )
            batch = self._buffer.drain(
                canonical.chat_key,
                canonical,
                ingress_sequence=ticket.ingress_sequence,
            )
            batch = replace(
                batch,
                system_context=self._system_context.drain(canonical.chat_key),
            )
            log_event(
                logger,
                "milky_inbound_trigger",
                logging.INFO,
                stage="will",
                scene=canonical.scene,
                chat_key=canonical.chat_key,
                message_id=canonical.message_id,
                decision="trigger",
                ingress_sequence=ticket.ingress_sequence,
                history_count=len(batch.history),
            )
            log_event(
                logger,
                "milky_inbound_drain",
                logging.DEBUG,
                stage="buffer",
                scene=canonical.scene,
                chat_key=canonical.chat_key,
                ingress_sequence=batch.trigger_ingress_sequence,
                history_count=len(batch.history),
            )
            self._start_detached(batch)
            return PipelineResult("trigger", canonical=canonical, batch=batch)

    async def wait_idle(self) -> None:
        """等待当前已创建的 detached 交接任务，不等待 Hermes Agent。"""

        while self._background_tasks:
            await asyncio.gather(*tuple(self._background_tasks))

    async def _process_batch(self, batch: object) -> None:
        current = getattr(batch, "current", None)
        chat_key = getattr(batch, "chat_key", None)
        ingress_sequence = getattr(batch, "trigger_ingress_sequence", None)
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
                context_image_materializations=_context_image_materializations(resolved_batch),
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
            log_event(
                logger,
                "milky_inbound_handoff_succeeded",
                logging.INFO,
                stage="handoff",
                **_batch_log_fields(chat_key, ingress_sequence, current),
            )
            self._notify_reply_cost(current.chat_key)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - detached boundary records safe failure
            self._buffer.record_handoff_failure(batch, recoverable=False)
            self._record(f"trigger_failed:{_error_category(error)}")
            failure_fields = _batch_log_fields(chat_key, ingress_sequence, current)
            log_event(
                logger,
                "milky_inbound_handoff_failed",
                logging.WARNING,
                stage="handoff",
                **failure_fields,
                classification=_error_classification(error),
                reason="handoff_failed",
            )

    def _start_detached(self, batch: object) -> None:
        task = asyncio.create_task(self._process_batch(batch))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _start_command(self, message: CanonicalMessage) -> None:
        """启动不经过资源、buffer 和 Will 的 Hermes 命令交接。"""

        task = asyncio.create_task(self._process_command(message))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _process_command(self, message: CanonicalMessage) -> None:
        """将命令事件提交给 Hermes，并隔离宿主执行异常。"""

        try:
            source_builder = getattr(self._hermes, "build_source", None)
            if not callable(source_builder):
                raise TypeError("Hermes source builder is unavailable")
            source = build_source(message, source_builder)
            event = map_command_event(
                message,
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
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - 命令边界只记录安全分类
            self._record(f"command_failed:{_error_category(error)}")
            log_event(
                logger,
                "milky_inbound_handoff_failed",
                logging.WARNING,
                stage="handoff",
                chat_key=message.chat_key,
                message_id=message.message_id,
                scene=message.scene,
                classification=_error_classification(error),
                reason="handoff_failed",
            )

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
                log_event(
                    logger,
                    "milky_will_reply_cost",
                    logging.WARNING,
                    stage="will",
                    chat_key=chat_key,
                    classification="malformed",
                    reason="reply_cost_failed",
                )
            else:
                log_event(
                    logger,
                    "milky_will_reply_cost",
                    logging.DEBUG,
                    stage="will",
                    chat_key=chat_key,
                    classification="accepted",
                    reason="state_updated",
                )
        self._reply_costs += 1

    async def _observe(self, event: Event) -> None:
        if self._mute_tracker is not None:
            apply_event = getattr(self._mute_tracker, "apply_event", None)
            if callable(apply_event):
                try:
                    apply_event(event)
                except Exception:  # noqa: BLE001 - observe-only state cannot trigger Agent
                    self._record("observe_state_error")
                    log_event(
                        logger,
                        "milky_inbound_observer_failed",
                        logging.DEBUG,
                        stage="mute",
                        classification="malformed",
                        reason="observer_failed",
                    )
        if self._observer is None:
            return
        try:
            result = self._observer(event)
            if inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001 - observer must not break event processing
            self._record("observer_error")
            log_event(
                logger,
                "milky_inbound_observer_failed",
                logging.DEBUG,
                stage="canonical",
                classification="handler_error",
                reason="observer_failed",
            )

    async def _store_context_event(self, event: ContextOnlyEvent) -> None:
        """在 admission 内登记一条 context-only 系统事件。"""

        async with self._admission.admit(event.chat_key) as ticket:
            result = self._system_context.append(event, ingress_sequence=ticket.ingress_sequence)
            if not result.accepted:
                self._record(f"system_context:{result.reason}")
                reason = "buffer_overflow"
            else:
                reason = "context_only"
            log_event(
                logger,
                "milky_inbound_context_only",
                logging.INFO,
                stage="buffer",
                scene="group" if event.chat_key.startswith("group:") else "friend",
                chat_key=event.chat_key,
                event_type=event.event_type,
                ingress_sequence=ticket.ingress_sequence,
                reason=reason,
            )

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
            "system_context_buffer": self._system_context,
        }
        values.update(overrides)
        return type(self)(**values)


def _render_resolved_history(batch: object, resolved_batch: ResolvedTriggerBatch) -> str | None:
    """使用 resolver 完成后的正文渲染历史上下文，不带当前消息。"""

    records: list[tuple[int, object]] = []
    sequences = getattr(batch, "history_ingress_sequences", ())
    if not isinstance(sequences, tuple) or len(sequences) != len(batch.history):
        sequences = tuple(range(len(batch.history)))
    for sequence, canonical, resolved in zip(
        sequences,
        batch.history,
        resolved_batch.history,
        strict=True,
    ):
        records.append(
            (
                sequence,
                _HistoryRecord(
                    chat_key=canonical.chat_key,
                    sender_name=canonical.sender_name,
                    sender_id=canonical.sender_id,
                    body=resolved.body,
                    message_id=canonical.message_id,
                    quote_message_id=canonical.quote_message_id,
                    quote_target_is_self=canonical.quote_target_is_self,
                ),
            )
        )
    records.extend(
        (
            event.ingress_sequence or 0,
            event,
        )
        for event in getattr(batch, "system_context", ())
    )
    return render_ordered_context(records)


def _context_image_materializations(
    resolved_batch: ResolvedTriggerBatch,
) -> tuple[HermesAttachmentMaterialization, ...]:
    """按历史 context 顺序提取正文中实际展示的图片附件。"""

    return tuple(
        materialization
        for message in resolved_batch.history
        for materialization in message.context_image_materializations
    )


@dataclass(frozen=True, slots=True)
class _HistoryRecord:
    """提供历史上下文 renderer 所需的安全字段。"""

    chat_key: str
    sender_name: str
    sender_id: int
    body: str
    message_id: str | None
    quote_message_id: str | None
    quote_target_is_self: bool = False


def _error_category(error: Exception) -> str:
    return type(error).__name__.lower().replace("error", "")[:64] or "failure"


def _safe_classification(value: object) -> str:
    """把 parser 分类收敛到日志允许的固定集合。"""

    return value if value in {"malformed", "unsupported", "unknown"} else "malformed"


def _safe_gate_reason(value: object) -> str:
    """把 Gate 原因限制为固定日志分类。"""

    allowed = {
        "self_message",
        "chat_not_allowed",
        "member_muted",
        "whole_muted",
        "mute_state_unknown",
        "unsupported_scene",
    }
    return value if value in allowed else "unknown"


def _gate_name(value: object) -> str:
    """将 Gate 结果映射到稳定 Gate 名称。"""

    if value == "self_message":
        return "self_message"
    if value == "chat_not_allowed":
        return "chat_allowlist"
    if value in {"member_muted", "whole_muted", "mute_state_unknown", "unsupported_scene"}:
        return "muted_group"
    return "muted_group"


def _batch_log_fields(chat_key: object, sequence: object, current: object) -> dict[str, object]:
    """提取 detached batch 的安全关联字段。"""

    fields: dict[str, object] = {}
    if isinstance(chat_key, str):
        fields["chat_key"] = chat_key
    if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0:
        fields["ingress_sequence"] = sequence
    message_id = getattr(current, "message_id", None)
    if message_id is not None:
        fields["message_id"] = message_id
    scene = getattr(current, "scene", None)
    if scene in {"friend", "group"}:
        fields["scene"] = scene
    return fields


def _error_classification(error: BaseException) -> str:
    """将本地或远端错误映射到安全分类。"""

    classification = getattr(error, "classification", None)
    allowed = {
        "rejected",
        "transport_unknown",
        "malformed",
        "unsupported",
        "invalid_input",
        "http_error",
        "stream_error",
        "protocol_error",
        "connection_error",
        "timeout",
        "unknown",
    }
    return classification if classification in allowed else "malformed"


__all__ = ["InboundPipeline", "PipelineResult"]
