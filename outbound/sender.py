"""Hermes 出站发送器：目标路由、分块、上传和安全结果转换。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from milky.client import ActionError, materialize_media_uri
from milky.models import MilkyEnvelope
from milky.observability import log_event
from session.identity import CanonicalError, normalize_chat_key

from .chunking import DEFAULT_TEXT_LENGTH, chunk_text
from .file_upload import FileUploader
from .formatter import (
    OutboundFormatError,
    format_message,
    image_segment,
    record_segment,
    text_segment,
    video_segment,
)

_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_MAX_SAFE_INTEGER = 9007199254740991
_MISSING = object()

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutboundTarget:
    """保存已通过 namespace 和 Milky ID 范围校验的目标。"""

    scene: Literal["group", "dm"]
    peer_id: int


@dataclass(frozen=True, slots=True)
class OutboundSendResult:
    """提供与 Hermes SendResult 兼容的最小结果结构。"""

    success: bool
    message_id: str | None = None
    error: str | None = None
    raw_response: Any = None
    retryable: bool = False
    continuation_message_ids: tuple[str, ...] = ()
    error_kind: str | None = None

    @property
    def classification(self) -> str | None:
        """返回机器可读的失败分类。"""

        return self.error_kind


class MilkyOutboundSender:
    """将 Hermes 的平台无关出站调用交给 Milky client。"""

    def __init__(
        self,
        client: object,
        *,
        mute_tracker: object | None = None,
        max_text_length: int = DEFAULT_TEXT_LENGTH,
    ) -> None:
        if isinstance(max_text_length, bool) or not isinstance(max_text_length, int):
            raise TypeError("max_text_length must be an integer")
        if max_text_length <= 0:
            raise ValueError("max_text_length must be positive")
        self._client = client
        self._mute_tracker = mute_tracker
        self._max_text_length = max_text_length
        self._uploader = FileUploader(client)  # type: ignore[arg-type]
        self._refresh_tasks: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        """取消由发送失败触发、尚未结束的群状态刷新任务。"""

        tasks = tuple(self._refresh_tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._refresh_tasks.clear()

    async def send(
        self,
        chat_id: str,
        content: object,
        reply_to: object = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OutboundSendResult:
        """按 chat key 发送文本或 Milky outgoing segments。"""

        del metadata
        try:
            target = parse_outbound_target(chat_id)
            parts = self._message_parts(content, reply_to)
        except (OutboundFormatError, ValueError) as error:
            result = _failure(_error_classification(error), _safe_reason(error))
            log_event(
                logger,
                "milky_outbound_failed",
                logging.WARNING,
                stage="outbound",
                classification=_log_classification(result.error_kind),
                reason=_log_reason(result.error_kind),
            )
            return result

        log_event(
            logger,
            "milky_outbound_route",
            logging.DEBUG,
            stage="outbound",
            route=target.scene,
            peer_id=target.peer_id,
        )
        if len(parts) > 1:
            log_event(
                logger,
                "milky_outbound_chunked",
                logging.DEBUG,
                stage="outbound",
                route=target.scene,
                peer_id=target.peer_id,
                chunk_count=len(parts),
            )

        sent_ids: list[str] = []
        for index, segments in enumerate(parts):
            result = await self._send_segments(target, segments)
            if not result.success:
                if sent_ids:
                    result = _with_partial(result, sent_ids, index)
                _log_outbound_result(target, result, chunk_count=len(parts))
                return result
            if result.message_id is None:
                result = _failure("malformed", "send result has no message id")
                _log_outbound_result(target, result, chunk_count=len(parts))
                return result
            sent_ids.append(result.message_id)
        result = _success(sent_ids[-1], continuation_message_ids=tuple(sent_ids[:-1]))
        _log_outbound_result(target, result, chunk_count=len(parts))
        return result

    async def send_image(
        self,
        chat_id: str,
        image_url: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OutboundSendResult:
        """以 image segment 发送 Hermes 提供的 URI。"""

        del metadata
        try:
            uri = await materialize_media_uri(image_url, action="send_image")
            media = image_segment(uri)
        except (ActionError, OutboundFormatError) as error:
            return _failure(error.classification, _safe_reason(error))
        return await self._send_media(chat_id, media, caption=caption, reply_to=reply_to)

    async def send_image_file(
        self,
        chat_id: str,
        image_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OutboundSendResult:
        """把本地图片路径转换为 Milky file URI 后发送。"""

        return await self.send_image(
            chat_id, image_path, caption=caption, reply_to=reply_to, metadata=metadata
        )

    async def send_animation(
        self,
        chat_id: str,
        animation_url: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OutboundSendResult:
        """按 Milky image segment 发送动画 URI。"""

        return await self.send_image(
            chat_id, animation_url, caption=caption, reply_to=reply_to, metadata=metadata
        )

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> OutboundSendResult:
        """以 record segment 发送 Hermes 提供的 URI。"""

        del metadata, kwargs
        try:
            uri = await materialize_media_uri(audio_path, action="send_voice")
            media = record_segment(uri)
        except (ActionError, OutboundFormatError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        return await self._send_media(chat_id, media, caption=caption, reply_to=reply_to)

    async def send_video(
        self,
        chat_id: str,
        video_path: str,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> OutboundSendResult:
        """以 video segment 发送 Hermes 提供的 URI。"""

        del metadata, kwargs
        try:
            uri = await materialize_media_uri(video_path, action="send_video")
            media = video_segment(uri)
        except (ActionError, OutboundFormatError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        return await self._send_media(chat_id, media, caption=caption, reply_to=reply_to)

    async def send_document(
        self,
        chat_id: str,
        file_path: object,
        caption: str | None = None,
        file_name: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> OutboundSendResult:
        """使用独立 file upload；不把文件放入消息 segments。"""

        del caption, reply_to, metadata
        try:
            target = parse_outbound_target(chat_id)
            parent_folder_id = kwargs.pop("parent_folder_id", _MISSING)
            if kwargs:
                raise ActionError("invalid_input", "file_upload", "unsupported file option")
            envelope = await self._upload_file(
                target, file_path, file_name, parent_folder_id=parent_folder_id
            )
            file_id = _file_id(envelope)
            result = _success(file_id)
            log_event(
                logger,
                "milky_outbound_upload_succeeded",
                logging.INFO,
                stage="outbound",
                route=target.scene,
                peer_id=target.peer_id,
                file_id=file_id,
                attachment_count=1,
            )
            return result
        except asyncio.CancelledError:
            raise
        except (ActionError, OSError, TypeError, ValueError) as error:
            result = _failure(_error_classification(error), _safe_reason(error))
            if _is_remote_failure(error):
                self._schedule_group_failure(target if "target" in locals() else None)
            _log_upload_result(target if "target" in locals() else None, result)
            return result
        except Exception:  # noqa: BLE001
            result = _failure("malformed", "file upload failed")
            self._schedule_group_failure(target if "target" in locals() else None)
            _log_upload_result(target if "target" in locals() else None, result)
            return result

    async def send_file(self, *args: Any, **kwargs: Any) -> OutboundSendResult:
        """提供 Hermes 旧式文件发送名称的兼容委托。"""

        return await self.send_document(*args, **kwargs)

    async def profile_like(self, user_id: object, count: object = _MISSING) -> OutboundSendResult:
        """执行已确认的名片点赞 Action。"""

        try:
            user_value = _qq_id(user_id, "user_id")
            if count is _MISSING:
                envelope = await _maybe_await(self._client.send_profile_like(user_value))
            elif count is None:
                envelope = await _maybe_await(self._client.send_profile_like(user_value, None))
            else:
                count_value = _integer(count, "count")
                envelope = await _maybe_await(
                    self._client.send_profile_like(user_value, count_value)
                )
            return _action_success(envelope)
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        except Exception:  # noqa: BLE001
            return _failure("malformed", "profile like failed")

    async def nudge(
        self,
        target: object,
        *,
        user_id: object = None,
        is_self: object = None,
    ) -> OutboundSendResult:
        """按 dm/group namespace 执行好友或群戳一戳 Action。"""

        try:
            parsed = parse_outbound_target(target)
            if parsed.scene == "dm":
                if user_id is not None:
                    raise ActionError(
                        "invalid_input", "send_friend_nudge", "user_id is unsupported"
                    )
                if is_self is not None and not isinstance(is_self, bool):
                    raise ActionError("invalid_input", "send_friend_nudge", "is_self is invalid")
                if is_self is None:
                    envelope = await _maybe_await(self._client.send_friend_nudge(parsed.peer_id))
                else:
                    envelope = await _maybe_await(
                        self._client.send_friend_nudge(parsed.peer_id, is_self)
                    )
            else:
                if is_self is not None:
                    raise ActionError("invalid_input", "send_group_nudge", "is_self is unsupported")
                target_user = _qq_id(user_id, "user_id")
                envelope = await _maybe_await(
                    self._client.send_group_nudge(parsed.peer_id, target_user)
                )
            result = _action_success(envelope)
            return result
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            result = _failure(_error_classification(error), _safe_reason(error))
            if "parsed" in locals() and parsed.scene == "group" and _is_remote_failure(error):
                self._schedule_group_failure(parsed)
            return result
        except Exception:  # noqa: BLE001
            if "parsed" in locals() and parsed.scene == "group":
                self._schedule_group_failure(parsed)
            return _failure("malformed", "nudge failed")

    async def recall_group_message(self, target: object, message_seq: object) -> OutboundSendResult:
        """撤回合法群消息且只调用一次，不自动重试。"""

        try:
            parsed = parse_outbound_target(target)
            if parsed.scene != "group":
                raise ActionError(
                    "unsupported", "recall_group_message", "target scene is unsupported"
                )
            sequence = _integer(message_seq, "message_seq")
            envelope = await _maybe_await(
                self._client.recall_group_message(parsed.peer_id, sequence)
            )
            return _action_success(envelope)
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            result = _failure(_error_classification(error), _safe_reason(error))
            if _is_remote_failure(error) and "parsed" in locals():
                self._schedule_group_failure(parsed)
            return result
        except Exception:  # noqa: BLE001
            if "parsed" in locals():
                self._schedule_group_failure(parsed)
            return _failure("malformed", "recall failed")

    def _message_parts(self, content: object, reply_to: object) -> tuple[list[dict[str, Any]], ...]:
        """格式化普通内容并仅在首个 chunk 添加 reply。"""

        if isinstance(content, str):
            chunks = chunk_text(content, self._max_text_length)
            return tuple(
                format_message(chunk, reply_to=reply_to if index == 0 else None)
                for index, chunk in enumerate(chunks)
            )
        return (format_message(content, reply_to=reply_to),)

    async def _send_segments(
        self, target: OutboundTarget, segments: list[dict[str, Any]]
    ) -> OutboundSendResult:
        """执行单个消息 Action，并把 Milky 结果转换为 Hermes 结果。"""

        action = "send_group_message" if target.scene == "group" else "send_private_message"
        try:
            if target.scene == "group":
                raw_result = await _maybe_await(
                    self._client.send_group_message(target.peer_id, segments)
                )
            else:
                raw_result = await _maybe_await(
                    self._client.send_private_message(target.peer_id, segments)
                )
            message_id = getattr(raw_result, "message_id", None)
            if not isinstance(message_id, str) or not message_id:
                self._schedule_group_failure(target)
                return _failure("malformed", "send result has no message id")
            return _success(message_id)
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            result = _failure(_error_classification(error), _safe_reason(error))
            if _is_remote_failure(error):
                self._schedule_group_failure(target)
            return result
        except Exception:  # noqa: BLE001
            self._schedule_group_failure(target)
            return _failure("malformed", f"{action} failed")

    async def _send_media(
        self,
        chat_id: str,
        media: dict[str, Any],
        *,
        caption: str | None,
        reply_to: str | None,
    ) -> OutboundSendResult:
        """把可选 caption、reply 和单一媒体 segment 交给统一发送路径。"""

        try:
            content: list[dict[str, Any]] = []
            if caption is not None:
                if not isinstance(caption, str):
                    raise OutboundFormatError("invalid_input", "caption is invalid")
                if caption:
                    content.append(text_segment(caption))
            content.append(media)
            return await self.send(chat_id, content, reply_to=reply_to)
        except (OutboundFormatError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def _upload_file(
        self,
        target: OutboundTarget,
        file_path: object,
        file_name: str | None,
        *,
        parent_folder_id: object,
    ) -> MilkyEnvelope:
        """交给 FileUploader，确保本地路径不直接进入 Action body。"""

        if parent_folder_id is _MISSING:
            return await self._uploader.upload(target.scene, target.peer_id, file_path, file_name)
        return await self._uploader.upload(
            target.scene,
            target.peer_id,
            file_path,
            file_name,
            parent_folder_id=parent_folder_id,
        )

    def _schedule_group_failure(self, target: OutboundTarget | None) -> None:
        """独立调度群失败后的只读刷新，不阻塞原始发送结果。"""

        if target is None or target.scene != "group" or self._mute_tracker is None:
            return
        callback = getattr(self._mute_tracker, "refresh_after_send_failure", None)
        if not callable(callback):
            return
        task = asyncio.create_task(
            self._notify_group_failure(callback, target),
            name="milky-mute-refresh-after-send-failure",
        )
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def _notify_group_failure(self, callback: object, target: OutboundTarget) -> None:
        """执行已调度的群失败刷新，并隔离刷新异常。"""

        try:
            await _maybe_await(callback(f"group:{target.peer_id}"))  # type: ignore[operator]
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return


def parse_outbound_target(value: object) -> OutboundTarget:
    """解析严格的 group/dm 目标，拒绝 temp 和隐式默认目标。"""

    if isinstance(value, str) and value.startswith("temp:"):
        raise OutboundFormatError("unsupported", "temporary target is unsupported")
    try:
        normalized = normalize_chat_key(value)
    except CanonicalError as error:
        raise OutboundFormatError("invalid_input", "target is invalid") from error
    scene_name, raw_id = normalized.split(":", 1)
    peer_id = int(raw_id)
    if not _MIN_QQ_ID <= peer_id <= _MAX_QQ_ID:
        raise OutboundFormatError("invalid_input", "target is invalid")
    return OutboundTarget("group" if scene_name == "group" else "dm", peer_id)


async def _maybe_await(value: object) -> Any:
    """兼容同步 fake 与异步 Milky client，而不改变 Action 语义。"""

    if inspect.isawaitable(value):
        return await value
    return value


def _file_id(envelope: object) -> str:
    """校验上传成功返回的 file_id。"""

    if not isinstance(envelope, MilkyEnvelope) or not isinstance(envelope.data, Mapping):
        raise ActionError("malformed", "file_upload", "response data is malformed")
    file_id = envelope.data.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        raise ActionError("malformed", "file_upload", "response is missing file_id")
    return file_id


def _qq_id(value: object, field: str) -> int:
    """校验工具使用的 QQ ID。"""

    return _integer(value, field, minimum=_MIN_QQ_ID, maximum=_MAX_QQ_ID)


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    """校验非布尔整数或无前导零十进制字符串。"""

    if isinstance(value, bool):
        raise ActionError("invalid_input", "tool", f"{field} is invalid")
    if isinstance(value, int) and minimum <= value <= maximum:
        return value
    if isinstance(value, str) and value.isdecimal() and (value == "0" or not value.startswith("0")):
        converted = int(value)
        if minimum <= converted <= maximum:
            return converted
    raise ActionError("invalid_input", "tool", f"{field} is invalid")


def _action_success(envelope: object) -> OutboundSendResult:
    """确认显式 Action 已返回 envelope。"""

    if not isinstance(envelope, MilkyEnvelope):
        raise ActionError("malformed", "tool", "response envelope is malformed")
    return _success(None)


def _success(
    message_id: str | None,
    *,
    continuation_message_ids: tuple[str, ...] = (),
) -> OutboundSendResult:
    """创建成功结果，必要时优先使用 Hermes 公共 SendResult 类型。"""

    return _make_result(
        success=True,
        message_id=message_id,
        continuation_message_ids=continuation_message_ids,
    )


def _failure(classification: str, reason: str) -> OutboundSendResult:
    """创建不回显目标、路径、凭证或远端正文的失败结果。"""

    return _make_result(
        success=False,
        error=f"{classification}: {reason}",
        retryable=False,
        error_kind=classification,
    )


def _with_partial(
    result: OutboundSendResult,
    sent_ids: Sequence[str],
    failed_index: int,
) -> OutboundSendResult:
    """保留长文本失败位置和已经发送的远端序号。"""

    raw_response = {"failed_chunk": failed_index, "sent_message_ids": tuple(sent_ids)}
    return _make_result(
        success=False,
        message_id=sent_ids[-1],
        error=result.error,
        raw_response=raw_response,
        retryable=False,
        continuation_message_ids=tuple(sent_ids[:-1]),
        error_kind=result.error_kind,
    )


def _make_result(**kwargs: Any) -> OutboundSendResult:
    """在 Hermes 可用时生成宿主结果，否则使用兼容 fallback。"""

    try:
        from gateway.platforms.base import SendResult as HermesSendResult
    except ImportError:
        return OutboundSendResult(**kwargs)
    try:
        return HermesSendResult(**kwargs)
    except (TypeError, ValueError):
        return OutboundSendResult(**kwargs)


def _error_classification(error: BaseException) -> str:
    """把异常收敛到可观察错误分类。"""

    if isinstance(error, ActionError):
        return error.classification
    if isinstance(error, OutboundFormatError):
        return error.classification
    if isinstance(error, (TimeoutError, OSError)):
        return "transport_unknown"
    if isinstance(error, TypeError):
        return "invalid_input"
    return "malformed"


def _safe_reason(error: BaseException) -> str:
    """返回固定诊断，避免异常正文夹带秘密或主机路径。"""

    classification = _error_classification(error)
    return {
        "invalid_input": "input is invalid",
        "unsupported": "operation is unsupported",
        "rejected": "Milky Action was rejected",
        "transport_unknown": "request outcome is unknown",
        "malformed": "response or result is malformed",
        "http_error": "HTTP request failed",
    }.get(classification, "operation failed")


def _is_remote_failure(error: BaseException) -> bool:
    """判断是否已经进入可能失败的远端 Action。"""

    return isinstance(error, ActionError) and error.classification in {
        "rejected",
        "transport_unknown",
        "malformed",
        "http_error",
    }


def _log_outbound_result(
    target: OutboundTarget,
    result: OutboundSendResult,
    *,
    chunk_count: int,
) -> None:
    """记录文本或 segment 发送的最终安全结果。"""

    if result.success:
        log_event(
            logger,
            "milky_outbound_succeeded",
            logging.INFO,
            stage="outbound",
            route=target.scene,
            peer_id=target.peer_id,
            message_id=result.message_id,
            chunk_count=chunk_count,
            sent_count=chunk_count,
        )
        return
    log_event(
        logger,
        "milky_outbound_failed",
        logging.WARNING,
        stage="outbound",
        route=target.scene,
        peer_id=target.peer_id,
        classification=_log_classification(result.error_kind),
        reason=_log_reason(result.error_kind),
        chunk_count=chunk_count,
    )


def _log_upload_result(target: OutboundTarget | None, result: OutboundSendResult) -> None:
    """记录文件上传失败且不回显路径、文件名或远端正文。"""

    fields: dict[str, object] = {
        "stage": "outbound",
        "classification": _log_classification(result.error_kind),
        "reason": _log_reason(result.error_kind),
    }
    if target is not None:
        fields["route"] = target.scene
        fields["peer_id"] = target.peer_id
    log_event(logger, "milky_outbound_upload_failed", logging.WARNING, **fields)


def _log_classification(value: str | None) -> str:
    """将出站结果分类转换为共享日志允许的值。"""

    return (
        value
        if value
        in {
            "rejected",
            "transport_unknown",
            "malformed",
            "unsupported",
            "invalid_input",
            "http_error",
        }
        else "unknown"
    )


def _log_reason(value: str | None) -> str:
    """将出站结果原因转换为固定的安全值。"""

    return {
        "invalid_input": "invalid_input",
        "unsupported": "operation_unsupported",
        "rejected": "action_rejected",
        "transport_unknown": "request_unknown",
        "malformed": "malformed_response",
        "http_error": "http_error",
    }.get(value, "unknown")


__all__ = [
    "MilkyOutboundSender",
    "OutboundSendResult",
    "OutboundTarget",
    "parse_outbound_target",
]
