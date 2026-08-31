"""Milky 运行时日志的无状态安全边界。"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType

_IDENTIFIER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")
_RAW_IDENTIFIER_PATTERN = re.compile(r"(?<![0-9])[0-9]{5,}(?![0-9])")
_OPAQUE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_CHAT_KEY_PATTERN = re.compile(r"^(group|dm):(0|[1-9][0-9]*)$")
_ACTION_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
_SAFE_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]*$")

EVENT_NAMES = frozenset(
    {
        "milky_adapter_connecting",
        "milky_adapter_connect_failed",
        "milky_adapter_ready",
        "milky_adapter_stopping",
        "milky_adapter_stopped",
        "milky_adapter_component_close_failed",
        "milky_adapter_fatal_error_report_failed",
        "milky_action_succeeded",
        "milky_action_failed",
        "milky_tool_call",
        "milky_event_stream_disconnected",
        "milky_event_stream_reconnect_scheduled",
        "milky_event_stream_reconnect_attempt",
        "milky_event_stream_reconnected",
        "milky_event_stream_cancelled",
        "milky_event_stream_frame_ignored",
        "milky_event_stream_handler_failed",
        "milky_inbound_observe_only",
        "milky_inbound_canonical_rejected",
        "milky_inbound_temp_ignored",
        "milky_inbound_duplicate",
        "milky_inbound_gate_denied",
        "milky_inbound_wait",
        "milky_inbound_trigger",
        "milky_inbound_drain",
        "milky_inbound_handoff_succeeded",
        "milky_inbound_handoff_failed",
        "milky_inbound_observer_failed",
        "milky_will_decision",
        "milky_will_reply_cost",
        "milky_resource_resolution_started",
        "milky_resource_resolution_completed",
        "milky_resource_resolution_degraded",
        "milky_outbound_route",
        "milky_outbound_chunked",
        "milky_outbound_succeeded",
        "milky_outbound_failed",
        "milky_outbound_upload_succeeded",
        "milky_outbound_upload_failed",
        "milky_mute_initial_sync_succeeded",
        "milky_mute_initial_sync_failed",
        "milky_mute_initial_sync_started",
        "milky_mute_group_muted",
        "milky_mute_event_updated",
        "milky_mute_refresh_succeeded",
        "milky_mute_refresh_failed",
    }
)

ALLOWED_FIELDS = frozenset(
    {
        "stage",
        "event_name",
        "scene",
        "action",
        "tool",
        "tool_args",
        "tool_result",
        "reason",
        "classification",
        "transport_phase",
        "decision",
        "attempt",
        "delay_seconds",
        "status_code",
        "duration_ms",
        "ingress_sequence",
        "chat_key",
        "uid",
        "self_id",
        "sender_id",
        "peer_id",
        "group_id",
        "user_id",
        "message_id",
        "reference_id",
        "file_id",
        "component",
        "nickname",
        "member_mute",
        "whole_mute",
        "gate",
        "scope",
        "route",
        "event_type",
        "total",
        "count",
        "succeeded",
        "failed",
        "muted",
        "unmuted",
        "unknown",
        "history_count",
        "materialized_count",
        "degraded_count",
        "reply_count",
        "forward_count",
        "attachment_count",
        "chunk_count",
        "sent_count",
        "failed_index",
        "batch_count",
        "buffer_size",
    }
)

SAFE_REASONS = frozenset(
    {
        "eof",
        "connection_error",
        "timeout",
        "http_error",
        "protocol_error",
        "stream_error",
        "unknown",
        "handler_failed",
        "fatal_error_report_failed",
        "cancelled",
        "stopped",
        "duplicate_message",
        "temporary_message",
        "invalid_message",
        "malformed_event",
        "unsupported_event",
        "canonical_rejected",
        "no_stable_message_id",
        "resource_resolution_failed",
        "handoff_failed",
        "reply_cost_failed",
        "initial_sync_failed",
        "component_close_failed",
        "send_failed",
        "upload_failed",
        "state_update_failed",
        "state_updated",
        "buffer_overflow",
        "invalid_decision",
        "observer_failed",
        "self_message",
        "chat_not_allowed",
        "member_muted",
        "whole_muted",
        "mute_state_unknown",
        "unsupported_scene",
        "action_rejected",
        "malformed_response",
        "invalid_input",
        "client_closed",
        "request_unknown",
        "operation_unsupported",
    }
)

SAFE_CLASSIFICATIONS = frozenset(
    {
        "accepted",
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
        "handler_error",
        "resource_error",
        "state_sync_failed",
        "internal_error",
    }
)

SAFE_STAGES = frozenset(
    {
        "lifecycle",
        "action",
        "event_stream",
        "canonical",
        "dedup",
        "gate",
        "buffer",
        "will",
        "resource",
        "handoff",
        "outbound",
        "mute",
    }
)

_SAFE_SCENES = frozenset({"friend", "group", "dm", "temp"})
_SAFE_DECISIONS = frozenset({"wait", "trigger", "allow", "deny"})
_SAFE_ROUTES = frozenset({"group", "dm"})
_SAFE_SCOPES = frozenset({"allowlist", "all_groups"})
_SAFE_GATES = frozenset({"self_message", "chat_allowlist", "muted_group"})
_SAFE_COMPONENTS = frozenset({"event_stream", "pipeline", "mute_tracker", "client", "hermes"})
_SAFE_MUTE_STATES = frozenset({"muted", "unmuted", "unknown"})
_LOG_SUBMISSION_SLOTS = threading.BoundedSemaphore(256)
_LOG_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="milky-log")
_DROPPED_LOG_COUNTS: Counter[int] = Counter()
_DROPPED_LOG_COUNTS_LOCK = threading.Lock()

_EVENT_LABELS = {
    "milky_adapter_connecting": "Connecting",
    "milky_adapter_connect_failed": "Connect failed",
    "milky_adapter_ready": "Ready",
    "milky_adapter_stopping": "Stopping",
    "milky_adapter_stopped": "Stopped",
    "milky_adapter_component_close_failed": "Component close failed",
    "milky_adapter_fatal_error_report_failed": "Fatal error report failed",
    "milky_action_succeeded": "Action succeeded",
    "milky_action_failed": "Action failed",
    "milky_tool_call": "Tool call",
    "milky_event_stream_disconnected": "Event stream disconnected",
    "milky_event_stream_reconnect_scheduled": "Event stream reconnect scheduled",
    "milky_event_stream_reconnect_attempt": "Event stream reconnect attempt",
    "milky_event_stream_reconnected": "Event stream reconnected",
    "milky_event_stream_cancelled": "Event stream cancelled",
    "milky_event_stream_frame_ignored": "Event stream frame ignored",
    "milky_event_stream_handler_failed": "Event stream handler failed",
    "milky_inbound_observe_only": "Inbound observe-only",
    "milky_inbound_canonical_rejected": "Inbound canonical rejected",
    "milky_inbound_temp_ignored": "Inbound temporary message ignored",
    "milky_inbound_duplicate": "Inbound duplicate",
    "milky_inbound_gate_denied": "Inbound gate denied",
    "milky_inbound_wait": "Waiting for trigger",
    "milky_inbound_trigger": "Inbound trigger",
    "milky_inbound_drain": "Inbound history drained",
    "milky_inbound_handoff_succeeded": "Inbound handoff succeeded",
    "milky_inbound_handoff_failed": "Inbound handoff failed",
    "milky_inbound_observer_failed": "Inbound observer failed",
    "milky_will_decision": "Will decision",
    "milky_will_reply_cost": "Will reply cost applied",
    "milky_resource_resolution_started": "Resource resolution started",
    "milky_resource_resolution_completed": "Resource resolution completed",
    "milky_resource_resolution_degraded": "Resource resolution degraded",
    "milky_outbound_route": "Outbound route",
    "milky_outbound_chunked": "Outbound message chunked",
    "milky_outbound_succeeded": "Outbound succeeded",
    "milky_outbound_failed": "Outbound failed",
    "milky_outbound_upload_succeeded": "Outbound upload succeeded",
    "milky_outbound_upload_failed": "Outbound upload failed",
    "milky_mute_initial_sync_succeeded": "Mute scan completed",
    "milky_mute_initial_sync_failed": "Mute scan failed",
    "milky_mute_initial_sync_started": "Cold-start identity",
    "milky_mute_group_muted": "Muted group",
    "milky_mute_event_updated": "Mute event updated",
    "milky_mute_refresh_succeeded": "Mute refresh succeeded",
    "milky_mute_refresh_failed": "Mute refresh failed",
}

_SENSITIVE_MARKERS = (
    "authorization",
    "bearer ",
    "token",
    "password",
    "secret",
    "response body",
    "payload",
    "http://",
    "https://",
    "file://",
    "base64://",
    "\\",
    "/",
    "\n",
    "\r",
)


def mask_identifier(value: object) -> str:
    """兼容旧名称，校验数字标识后原样返回。"""

    text = _decimal_identifier(value)
    return text


def mask_chat_key(value: object) -> str:
    """兼容旧名称，校验 namespaced chat key 后原样返回。"""

    if not isinstance(value, str):
        raise TypeError("chat_key must be text")
    match = _CHAT_KEY_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("chat_key is invalid")
    return value


def mask_opaque_identifier(value: object) -> str:
    """兼容旧名称，校验不透明标识后原样返回。"""

    if (
        not isinstance(value, str)
        or not value
        or _OPAQUE_IDENTIFIER_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("opaque identifier is invalid")
    return value


def safe_classification(value: object) -> str:
    """返回固定的错误分类，不接受原始异常文本。"""

    if not isinstance(value, str) or value not in SAFE_CLASSIFICATIONS:
        raise ValueError("classification is not safe")
    return value


def safe_reason(value: object) -> str:
    """返回固定的原因分类，不接受原始异常文本。"""

    if not isinstance(value, str) or value not in SAFE_REASONS:
        raise ValueError("reason is not safe")
    return value


def sanitize_fields(fields: Mapping[str, object]) -> dict[str, object]:
    """验证结构化日志字段并保留允许的业务值。"""

    if not isinstance(fields, Mapping):
        raise TypeError("log fields must be a mapping")
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError("log fields contain unsupported names")

    result: dict[str, object] = {}
    for name, value in fields.items():
        result[name] = _sanitize_field(name, value)
    return result


def log_event(
    logger: logging.Logger,
    event_name: str,
    level: int = logging.INFO,
    *,
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None,
    **fields: object,
) -> None:
    """以统一前缀输出一条安全、可检索的日志。"""

    if event_name not in EVENT_NAMES:
        raise ValueError("event_name is not supported")
    if level not in {logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR}:
        raise ValueError("log level is not supported")
    if exc_info is not None and not _is_safe_exc_info(exc_info):
        raise ValueError("exception details are not safe to log")
    safe_fields = sanitize_fields(fields)
    safe_fields["event_name"] = event_name
    label = _EVENT_LABELS[event_name]
    rendered_fields = " ".join(
        _render_human_field(key, value) for key, value in safe_fields.items()
    )
    rendered = f"[Milky] {label}"
    if rendered_fields:
        rendered = f"{rendered} {rendered_fields}"
    _emit_without_blocking(logger, level, rendered, safe_fields, exc_info)


def log_local_exception(
    logger: logging.Logger,
    event_name: str,
    exception: BaseException,
    **fields: object,
) -> bool:
    """仅为已确认安全的本地异常输出带 traceback 的 error 日志。"""

    if not _is_safe_local_exception(exception):
        return False
    log_event(
        logger,
        event_name,
        logging.ERROR,
        exc_info=(type(exception), exception, exception.__traceback__),
        **fields,
    )
    return True


def _sanitize_field(name: str, value: object) -> object:
    if name == "event_name":
        if not isinstance(value, str) or value not in EVENT_NAMES:
            raise ValueError("event_name is not supported")
        return value
    if name == "chat_key":
        if not isinstance(value, str) or _CHAT_KEY_PATTERN.fullmatch(value) is None:
            raise ValueError("chat_key is invalid")
        return value
    if name in {"uid", "self_id", "sender_id", "peer_id", "group_id", "user_id"}:
        if value is None:
            return None
        _decimal_identifier(value)
        return value
    if name in {"message_id", "reference_id", "file_id"}:
        if value is None:
            return None
        if isinstance(value, int) or (
            isinstance(value, str) and _IDENTIFIER_PATTERN.fullmatch(value)
        ):
            _decimal_identifier(value)
            return value
        if (
            not isinstance(value, str)
            or not value
            or _OPAQUE_IDENTIFIER_PATTERN.fullmatch(value) is None
        ):
            raise ValueError("opaque identifier is invalid")
        return value
    if name == "action":
        if not isinstance(value, str) or _ACTION_PATTERN.fullmatch(value) is None:
            raise ValueError("action is not safe")
        return value
    if name == "tool":
        if not isinstance(value, str) or _ACTION_PATTERN.fullmatch(value) is None:
            raise ValueError("tool is not safe")
        return value
    if name == "tool_args":
        if not isinstance(value, Mapping):
            raise ValueError("tool_args must be an object")
        return value
    if name == "tool_result":
        if value is None:
            raise ValueError("tool_result is required")
        return value
    if name == "stage":
        return _safe_choice(value, SAFE_STAGES, "stage")
    if name == "scene":
        return _safe_choice(value, _SAFE_SCENES, "scene")
    if name == "decision":
        return _safe_choice(value, _SAFE_DECISIONS, "decision")
    if name == "route":
        return _safe_choice(value, _SAFE_ROUTES, "route")
    if name == "scope":
        return _safe_choice(value, _SAFE_SCOPES, "scope")
    if name == "gate":
        return _safe_choice(value, _SAFE_GATES, "gate")
    if name == "classification":
        return safe_classification(value)
    if name == "reason":
        return safe_reason(value)
    if name == "transport_phase":
        return _safe_choice(
            value,
            frozenset({"connect", "write", "read", "pool", "unknown"}),
            "transport_phase",
        )
    if name == "event_type":
        if not isinstance(value, str) or _SAFE_TOKEN_PATTERN.fullmatch(value) is None:
            raise ValueError("event_type is not safe")
        return value
    if name == "component":
        return _safe_choice(value, _SAFE_COMPONENTS, "component")
    if name == "nickname":
        return _safe_nickname(value)
    if name in {"member_mute", "whole_mute"}:
        return _safe_choice(value, _SAFE_MUTE_STATES, name)
    if name in {
        "attempt",
        "status_code",
        "ingress_sequence",
        "total",
        "count",
        "succeeded",
        "failed",
        "muted",
        "unmuted",
        "unknown",
        "history_count",
        "materialized_count",
        "degraded_count",
        "reply_count",
        "forward_count",
        "attachment_count",
        "chunk_count",
        "sent_count",
        "failed_index",
        "batch_count",
        "buffer_size",
    }:
        return _non_negative_integer(value, name)
    if name in {"delay_seconds", "duration_ms"}:
        return _non_negative_number(value, name)
    raise ValueError("log field is not supported")


def _render_human_field(name: str, value: object) -> str:
    """渲染字段并避免宿主将 chat_key 误判为 secret assignment。"""

    if name == "chat_key":
        return f"chat_key[{value}]"
    return f"{name}={value}"


def _decimal_identifier(value: object) -> str:
    if isinstance(value, bool):
        raise TypeError("identifier is invalid")
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, str) and _IDENTIFIER_PATTERN.fullmatch(value):
        return value
    raise ValueError("identifier is invalid")


def _safe_choice(value: object, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} is not safe")
    return value


def _non_negative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _non_negative_number(value: object, name: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _safe_nickname(value: object) -> str:
    """验证昵称可安全放入日志，但不改写业务值。"""

    if not isinstance(value, str) or not value:
        return "<unknown>"
    if any(not char.isprintable() for char in value):
        raise ValueError("nickname is not safe")
    return value


def _is_safe_local_exception(exception: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exception
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if current.__traceback__ is not None:
            return False
        if not _is_safe_exception_value(str(current)):
            return False
        for note in getattr(current, "__notes__", ()) or ():
            if not _is_safe_exception_value(note):
                return False
        for argument in current.args:
            if not _is_safe_exception_value(argument):
                return False
        current = current.__cause__ or current.__context__
    return bool(seen)


def _is_safe_exc_info(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None],
) -> bool:
    """验证不会把异常 traceback 路径写入日志。"""

    if not isinstance(exc_info, tuple) or len(exc_info) != 3:
        return False
    exception_type, exception, traceback = exc_info
    return (
        isinstance(exception_type, type)
        and isinstance(exception, BaseException)
        and traceback is None
        and _is_safe_local_exception(exception)
    )


def _is_safe_exception_value(value: object) -> bool:
    """检查异常文本或参数是否不含敏感信息。"""

    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return (
        bool(value)
        and not _RAW_IDENTIFIER_PATTERN.search(value)
        and not any(marker in lowered for marker in _SENSITIVE_MARKERS)
    )


def _emit_without_blocking(
    logger: logging.Logger,
    level: int,
    message: str,
    fields: Mapping[str, object],
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None,
) -> None:
    """发射日志；事件循环内不等待宿主 handler。"""

    if not logger.isEnabledFor(level):
        return
    record = logger.makeRecord(
        logger.name,
        level,
        __file__,
        0,
        message,
        (),
        exc_info,
        func="log_event",
        extra=dict(fields),
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.handle(record)
        return
    if not _LOG_SUBMISSION_SLOTS.acquire(blocking=False):
        with _DROPPED_LOG_COUNTS_LOCK:
            _DROPPED_LOG_COUNTS[level] += 1
        return
    try:
        future = _LOG_EXECUTOR.submit(logger.handle, record)
    except RuntimeError:
        _LOG_SUBMISSION_SLOTS.release()
        return
    future.add_done_callback(_release_log_submission_slot)


def _release_log_submission_slot(_future: object) -> None:
    """释放一次后台日志提交额度。"""

    _LOG_SUBMISSION_SLOTS.release()


__all__ = [
    "ALLOWED_FIELDS",
    "EVENT_NAMES",
    "SAFE_CLASSIFICATIONS",
    "SAFE_REASONS",
    "log_event",
    "log_local_exception",
    "mask_chat_key",
    "mask_identifier",
    "mask_opaque_identifier",
    "safe_classification",
    "safe_reason",
    "sanitize_fields",
]
