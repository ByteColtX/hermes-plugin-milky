"""Hermes 出站发送器：目标路由、分块、上传和安全结果转换。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from milky.client import ActionError
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
from .materialization import prepare_materialization

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

        del metadata, reply_to
        try:
            target = parse_outbound_target(chat_id)
            parts = self._message_parts(content, None)
            parts = await self._materialize_message_parts(parts)
        except (ActionError, OutboundFormatError, ValueError) as error:
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

    async def _materialize_message_parts(
        self, parts: tuple[list[dict[str, Any]], ...]
    ) -> tuple[list[dict[str, Any]], ...]:
        """在消息 Action 前物化 CQ 或结构化输入中的图片。"""

        materialized_parts: list[list[dict[str, Any]]] = []
        for segments in parts:
            materialized_parts.append(
                [await self._materialize_image_segment(segment) for segment in segments]
            )
        return tuple(materialized_parts)

    async def _materialize_image_segment(self, segment: dict[str, Any]) -> dict[str, Any]:
        """将 image segment 的本地 URI 转换为 Milky 可接受的 URI。"""

        if segment.get("type") != "image":
            return segment
        data = segment["data"]
        attachment = await prepare_materialization(
            data["uri"],
            expected_kind="image",
            action="send_image",
        )
        materialized_data = dict(data)
        materialized_data["uri"] = attachment.uri
        return {"type": "image", "data": materialized_data}

    async def send_image(
        self,
        chat_id: str,
        image_url: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> OutboundSendResult:
        """将图片 URI 或本地路径转换为 image segment 后发送。"""

        del metadata
        try:
            parse_outbound_target(chat_id)
            uri = (
                await prepare_materialization(
                    image_url,
                    expected_kind="image",
                    action="send_image",
                )
            ).uri
            media = image_segment(uri)
        except (ActionError, OutboundFormatError) as error:
            return _failure(error.classification, _safe_reason(error))
        return await self._send_media(chat_id, media, caption=caption, reply_to=reply_to)

    async def send_voice(
        self,
        chat_id: str,
        audio_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> OutboundSendResult:
        """将语音 URI 或本地路径转换为 record segment 后发送。"""

        del metadata, kwargs
        try:
            parse_outbound_target(chat_id)
            uri = (
                await prepare_materialization(
                    audio_path,
                    expected_kind="audio",
                    action="send_voice",
                )
            ).uri
            media = record_segment(uri)
        except (ActionError, OutboundFormatError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        return await self._send_media(chat_id, media, caption=caption, reply_to=reply_to)

    async def send_video(
        self,
        chat_id: str,
        video_path: object,
        caption: str | None = None,
        reply_to: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> OutboundSendResult:
        """将视频 URI 或本地路径转换为 video segment 后发送。"""

        del metadata, kwargs
        try:
            parse_outbound_target(chat_id)
            uri = (
                await prepare_materialization(
                    video_path,
                    expected_kind="video",
                    action="send_video",
                )
            ).uri
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

    async def _call_tool(
        self,
        action: str,
        params: Mapping[str, object],
        fallback: Callable[[], Any],
    ) -> object:
        """调用已注册 Tool 的 raw client 入口，并兼容旧 fake client。"""

        call_tool = getattr(self._client, "call_tool", None)
        if callable(call_tool):
            return await _maybe_await(call_tool(action, params))
        call = getattr(self._client, "call", None)
        if callable(call):
            return await _maybe_await(call(action, params))
        return await _maybe_await(fallback())

    async def _execute_tool_action(
        self,
        action: str,
        params: Mapping[str, object],
        fallback: Callable[[], Any],
    ) -> object:
        """执行一次显式 Tool Action，并把失败收敛为固定结果。"""

        try:
            result = await self._call_tool(action, params, fallback)
            envelope = _action_success(result)
            _validate_tool_response(action, envelope)
            return envelope
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))
        except Exception:  # noqa: BLE001 - 工具边界不回显底层异常
            return _failure("malformed", "tool action failed")

    async def get_group_info(self, group_id: object, *, no_cache: bool | None = False) -> object:
        """查询群信息并保留 Milky 的原始成功 envelope。"""

        group_value = _qq_id(group_id, "group_id")
        params: dict[str, object] = {"group_id": group_value}
        if no_cache is not False:
            if not isinstance(no_cache, bool) and no_cache is not None:
                raise ActionError("invalid_input", "get_group_info", "no_cache is invalid")
            params["no_cache"] = no_cache
        return await self._call_tool(
            "get_group_info",
            params,
            lambda: self._client.get_group_info(group_value, no_cache=no_cache),
        )

    async def get_group_member_list(
        self, group_id: object, *, no_cache: bool | None = False
    ) -> object:
        """查询群成员列表并保留 Milky 的原始成功 envelope。"""

        group_value = _qq_id(group_id, "group_id")
        params: dict[str, object] = {"group_id": group_value}
        if no_cache is not False:
            if not isinstance(no_cache, bool) and no_cache is not None:
                raise ActionError("invalid_input", "get_group_member_list", "no_cache is invalid")
            params["no_cache"] = no_cache
        return await self._call_tool(
            "get_group_member_list",
            params,
            lambda: self._client.get_group_member_list(group_value, no_cache=no_cache),
        )

    async def get_group_member_info(
        self, group_id: object, user_id: object, *, no_cache: bool | None = False
    ) -> object:
        """查询群成员信息并保留 Milky 的原始成功 envelope。"""

        group_value = _qq_id(group_id, "group_id")
        user_value = _qq_id(user_id, "user_id")
        params: dict[str, object] = {"group_id": group_value, "user_id": user_value}
        if no_cache is not False:
            if not isinstance(no_cache, bool) and no_cache is not None:
                raise ActionError("invalid_input", "get_group_member_info", "no_cache is invalid")
            params["no_cache"] = no_cache
        return await self._call_tool(
            "get_group_member_info",
            params,
            lambda: self._client.get_group_member_info(group_value, user_value, no_cache=no_cache),
        )

    async def set_group_member_mute(
        self, group_id: object, user_id: object, duration: object = _MISSING
    ) -> object:
        """设置群成员禁言状态。"""

        group_value = _qq_id(group_id, "group_id")
        user_value = _qq_id(user_id, "user_id")
        params: dict[str, object] = {"group_id": group_value, "user_id": user_value}
        if duration is _MISSING:
            return await self._call_tool(
                "set_group_member_mute",
                params,
                lambda: self._client.set_group_member_mute(group_value, user_value),
            )
        params["duration"] = None if duration is None else _integer(duration, "duration")
        return await self._call_tool(
            "set_group_member_mute",
            params,
            lambda: self._client.set_group_member_mute(group_value, user_value, duration),
        )

    async def set_group_whole_mute(self, group_id: object, is_mute: object = _MISSING) -> object:
        """设置群全员禁言状态。"""

        group_value = _qq_id(group_id, "group_id")
        params: dict[str, object] = {"group_id": group_value}
        if is_mute is _MISSING:
            return await self._call_tool(
                "set_group_whole_mute",
                params,
                lambda: self._client.set_group_whole_mute(group_value),
            )
        if is_mute is not None and not isinstance(is_mute, bool):
            raise ActionError("invalid_input", "set_group_whole_mute", "is_mute is invalid")
        params["is_mute"] = is_mute
        return await self._call_tool(
            "set_group_whole_mute",
            params,
            lambda: self._client.set_group_whole_mute(group_value, is_mute),
        )

    async def profile_like(self, user_id: object, count: object = _MISSING) -> object:
        """执行已确认的名片点赞 Action。"""

        try:
            user_value = _qq_id(user_id, "user_id")
            if count is _MISSING:
                params = {"user_id": user_value}
                envelope = await self._call_tool(
                    "send_profile_like",
                    params,
                    lambda: self._client.send_profile_like(user_value),
                )
            elif count is None:
                params = {"user_id": user_value, "count": None}
                envelope = await self._call_tool(
                    "send_profile_like",
                    params,
                    lambda: self._client.send_profile_like(user_value, None),
                )
            else:
                count_value = _integer(count, "count")
                params = {"user_id": user_value, "count": count_value}
                envelope = await self._call_tool(
                    "send_profile_like",
                    params,
                    lambda: self._client.send_profile_like(user_value, count_value),
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
                    envelope = await self._call_tool(
                        "send_friend_nudge",
                        {"user_id": parsed.peer_id},
                        lambda: self._client.send_friend_nudge(parsed.peer_id),
                    )
                else:
                    envelope = await self._call_tool(
                        "send_friend_nudge",
                        {"user_id": parsed.peer_id, "is_self": is_self},
                        lambda: self._client.send_friend_nudge(parsed.peer_id, is_self),
                    )
            else:
                if is_self is not None:
                    raise ActionError("invalid_input", "send_group_nudge", "is_self is unsupported")
                target_user = _qq_id(user_id, "user_id")
                envelope = await self._call_tool(
                    "send_group_nudge",
                    {"group_id": parsed.peer_id, "user_id": target_user},
                    lambda: self._client.send_group_nudge(parsed.peer_id, target_user),
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
            envelope = await self._call_tool(
                "recall_group_message",
                {"group_id": parsed.peer_id, "message_seq": sequence},
                lambda: self._client.recall_group_message(parsed.peer_id, sequence),
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

    async def get_forwarded_messages(self, forward_id: object) -> object:
        """查询合并转发消息并保留完整成功 envelope。"""

        try:
            value = _strict_text(forward_id, "forward_id")
            return await self._execute_tool_action(
                "get_forwarded_messages",
                {"forward_id": value},
                lambda: self._client.get_forwarded_messages(value),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def get_private_file_download_url(
        self,
        user_id: object,
        file_id: object,
        file_hash: object,
        *,
        is_self_send: object = _MISSING,
    ) -> object:
        """查询私聊文件链接，不下载、缓存或改写该链接。"""

        try:
            user_value = _strict_qq_id(user_id, "user_id")
            file_value = _strict_text(file_id, "file_id")
            hash_value = _strict_text(file_hash, "file_hash")
            params: dict[str, object] = {
                "user_id": user_value,
                "file_id": file_value,
                "file_hash": hash_value,
            }
            if is_self_send is not _MISSING:
                if is_self_send is not None and not isinstance(is_self_send, bool):
                    raise ActionError(
                        "invalid_input",
                        "get_private_file_download_url",
                        "is_self_send is invalid",
                    )
                params["is_self_send"] = is_self_send
            return await self._execute_tool_action(
                "get_private_file_download_url",
                params,
                lambda: _invoke_without_missing(
                    self._client.get_private_file_download_url,
                    user_value,
                    file_value,
                    hash_value,
                    is_self_send=is_self_send,
                ),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def kick_group_member(
        self,
        group_id: object,
        user_id: object,
        *,
        reject_add_request: object = _MISSING,
    ) -> object:
        """显式踢出群成员，最多提交一次远端 Action。"""

        try:
            group_value = _strict_qq_id(group_id, "group_id")
            user_value = _strict_qq_id(user_id, "user_id")
            params: dict[str, object] = {"group_id": group_value, "user_id": user_value}
            if reject_add_request is not _MISSING:
                if reject_add_request is not None and not isinstance(reject_add_request, bool):
                    raise ActionError(
                        "invalid_input", "kick_group_member", "reject_add_request is invalid"
                    )
                params["reject_add_request"] = reject_add_request
            return await self._execute_tool_action(
                "kick_group_member",
                params,
                lambda: _invoke_without_missing(
                    self._client.kick_group_member,
                    group_value,
                    user_value,
                    reject_add_request=reject_add_request,
                ),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def quit_group(self, group_id: object) -> object:
        """显式退出群聊，最多提交一次远端 Action。"""

        try:
            group_value = _strict_qq_id(group_id, "group_id")
            return await self._execute_tool_action(
                "quit_group",
                {"group_id": group_value},
                lambda: self._client.quit_group(group_value),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def delete_friend(self, user_id: object) -> object:
        """显式删除好友关系，最多提交一次远端 Action。"""

        try:
            user_value = _strict_qq_id(user_id, "user_id")
            return await self._execute_tool_action(
                "delete_friend",
                {"user_id": user_value},
                lambda: self._client.delete_friend(user_value),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def get_friend_requests(
        self,
        *,
        limit: object = _MISSING,
        is_filtered: object = _MISSING,
    ) -> object:
        """查询好友请求并保留完整成功 envelope。"""

        try:
            params: dict[str, object] = {}
            if limit is not _MISSING:
                params["limit"] = (
                    None
                    if limit is None
                    else _strict_integer(limit, "limit", maximum=_MAX_SAFE_INTEGER)
                )
            if is_filtered is not _MISSING:
                if is_filtered is not None and not isinstance(is_filtered, bool):
                    raise ActionError(
                        "invalid_input", "get_friend_requests", "is_filtered is invalid"
                    )
                params["is_filtered"] = is_filtered
            return await self._execute_tool_action(
                "get_friend_requests",
                params,
                lambda: _invoke_without_missing(
                    self._client.get_friend_requests,
                    limit=limit,
                    is_filtered=is_filtered,
                ),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def accept_friend_request(
        self,
        initiator_uid: object,
        *,
        is_filtered: object = _MISSING,
    ) -> object:
        """显式接受好友请求，最多提交一次远端 Action。"""

        try:
            uid_value = _strict_text(initiator_uid, "initiator_uid")
            params: dict[str, object] = {"initiator_uid": uid_value}
            if is_filtered is not _MISSING:
                if is_filtered is not None and not isinstance(is_filtered, bool):
                    raise ActionError(
                        "invalid_input", "accept_friend_request", "is_filtered is invalid"
                    )
                params["is_filtered"] = is_filtered
            return await self._execute_tool_action(
                "accept_friend_request",
                params,
                lambda: _invoke_without_missing(
                    self._client.accept_friend_request,
                    uid_value,
                    is_filtered=is_filtered,
                ),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    async def reject_friend_request(
        self,
        initiator_uid: object,
        *,
        is_filtered: object = _MISSING,
        reason: object = _MISSING,
    ) -> object:
        """显式拒绝好友请求，最多提交一次远端 Action。"""

        try:
            uid_value = _strict_text(initiator_uid, "initiator_uid")
            params: dict[str, object] = {"initiator_uid": uid_value}
            if is_filtered is not _MISSING:
                if is_filtered is not None and not isinstance(is_filtered, bool):
                    raise ActionError(
                        "invalid_input", "reject_friend_request", "is_filtered is invalid"
                    )
                params["is_filtered"] = is_filtered
            if reason is not _MISSING:
                if reason is not None and not isinstance(reason, str):
                    raise ActionError("invalid_input", "reject_friend_request", "reason is invalid")
                params["reason"] = reason
            return await self._execute_tool_action(
                "reject_friend_request",
                params,
                lambda: _invoke_without_missing(
                    self._client.reject_friend_request,
                    uid_value,
                    is_filtered=is_filtered,
                    reason=reason,
                ),
            )
        except asyncio.CancelledError:
            raise
        except (ActionError, TypeError, ValueError) as error:
            return _failure(_error_classification(error), _safe_reason(error))

    def _message_parts(self, content: object, reply_to: object) -> tuple[list[dict[str, Any]], ...]:
        """格式化普通内容，并保持 CQ 片段不跨越分块边界。"""

        del reply_to
        if isinstance(content, str):
            chunks = chunk_text(content, self._max_text_length)
            if not chunks:
                return (format_message(content),)
            return tuple(format_message(chunk) for chunk in chunks)
        return (format_message(content),)

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

        del reply_to
        try:
            content: list[dict[str, Any]] = []
            if caption is not None:
                if not isinstance(caption, str):
                    raise OutboundFormatError("invalid_input", "caption is invalid")
                if caption:
                    content.append(text_segment(caption))
            content.append(media)
            return await self.send(chat_id, content)
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


def _invoke_without_missing(method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """调用兼容 fake/client 方法时省略未提供的可选字段。"""

    return method(*args, **{key: value for key, value in kwargs.items() if value is not _MISSING})


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


def _strict_qq_id(value: object, field: str) -> int:
    """校验新增 QQ Tool 使用的整数 QQ ID，不接受字符串伪装。"""

    return _strict_integer(value, field, minimum=_MIN_QQ_ID, maximum=_MAX_QQ_ID)


def _strict_text(value: object, field: str) -> str:
    """校验新增 QQ Tool 使用的非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ActionError("invalid_input", "tool", f"{field} is invalid")
    return value


def _strict_integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    """校验新增 QQ Tool 使用的非布尔整数和范围。"""

    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ActionError("invalid_input", "tool", f"{field} is invalid")
    return value


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


def _action_success(envelope: object) -> object:
    """确认显式 Action 已返回原始成功 envelope。"""

    if not isinstance(envelope, MilkyEnvelope):
        raise ActionError("malformed", "tool", "response envelope is malformed")
    return envelope


def _validate_tool_response(action: str, envelope: MilkyEnvelope) -> None:
    """在 sender 边界重复确认新增 Tool 的最小响应结构。"""

    if not isinstance(envelope.data, Mapping):
        raise ActionError("malformed", action, "response data is malformed")
    if action == "get_forwarded_messages":
        messages = envelope.data.get("messages")
        if not _is_object_sequence(messages):
            raise ActionError("malformed", action, "response messages are malformed")
    elif action == "get_private_file_download_url":
        if not isinstance(envelope.data.get("download_url"), str):
            raise ActionError("malformed", action, "response download_url is malformed")
    elif action == "get_friend_requests":
        requests = envelope.data.get("requests")
        if not _is_object_sequence(requests):
            raise ActionError("malformed", action, "response requests are malformed")
    elif (
        action
        in {
            "kick_group_member",
            "quit_group",
            "delete_friend",
            "accept_friend_request",
            "reject_friend_request",
        }
        and envelope.data
    ):
        raise ActionError("malformed", action, "response data is not an empty object")


def _is_object_sequence(value: object) -> bool:
    """确认响应数组由对象元素组成。"""

    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, Mapping) for item in value)
    )


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
