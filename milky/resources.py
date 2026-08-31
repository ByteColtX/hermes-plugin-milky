"""Milky trigger 阶段的分类资源和 reply 补全边界。

本模块只在 detached trigger batch 已经建立后工作。Milky 负责提供经过协议校验的
引用，Hermes seam 负责下载安全、缓存和本地路径；插件不实现第三套下载或缓存逻辑。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from inbound.extractor import extract_segments
from milky.client import ActionError
from milky.models import IncomingMessage, Segment
from milky.observability import log_event
from milky.parser import ParseError, parse_forwarded_message, parse_incoming_message_data
from session.identity import validate_chat_key

logger = logging.getLogger(__name__)


class ResourceClient(Protocol):
    """定义 resolver 所需的已确认 Milky Action。"""

    async def get_resource_temp_url(self, resource_id: object) -> object:
        """按资源 ID 返回包含 ``data.url`` 的 envelope。"""

    async def get_group_file_download_url(self, group_id: object, file_id: object) -> object:
        """按群号和文件 ID 返回包含 ``data.download_url`` 的 envelope。"""

    async def get_private_file_download_url(
        self,
        user_id: object,
        file_id: object,
        file_hash: object,
        *,
        is_self_send: object = None,
    ) -> object:
        """按用户号、文件 ID 和文件 hash 返回下载 envelope。"""

    async def get_forwarded_messages(self, forward_id: object) -> object:
        """按 forward ID 返回包含 ``data.messages`` 的 envelope。"""

    async def get_message(
        self, message_scene: object, peer_id: object, message_seq: object
    ) -> object:
        """按场景、会话对象和消息序号返回包含 ``data.message`` 的 envelope。"""


class HermesMediaHelpers(Protocol):
    """描述 Hermes 已确认的远端媒体 helper 能力，不复制其实现。"""

    async def cache_image_from_url(self, url: str, ext: str = ".jpg", retries: int = 2) -> str:
        """将图片 URL 交给 Hermes 安全缓存并返回本地路径。"""

    async def cache_audio_from_url(self, url: str, ext: str = ".ogg", retries: int = 2) -> str:
        """将音频 URL 交给 Hermes 安全缓存并返回本地路径。"""


@dataclass(frozen=True, slots=True)
class HermesAttachmentMaterialization:
    """保存 Hermes helper 已经生成的本地附件。"""

    path: str
    mime_type: str
    kind: str
    display_name: str
    reference_kind: str
    reference_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceDiagnostic:
    """保存不包含 URL、正文、凭证或本地路径的资源诊断。"""

    classification: str
    reference_kind: str
    reason: str
    reference_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedReply:
    """保存 inline 或远端补全后的 reply 内容。"""

    message_seq: int
    sender_id: int | None
    sender_name: str | None
    timestamp: int | None
    body: str
    segments: tuple[Segment, ...]
    hermes_attachment_materializations: tuple[HermesAttachmentMaterialization, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedForward:
    """保存一个 forward ID 和其已解析的完整消息。"""

    forward_id: str
    messages: tuple[ResolvedForwardedMessage, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedForwardedMessage:
    """保存一条完整转发消息及其中的 Hermes 附件。"""

    time: int
    sender_name: str
    avatar_url: str
    body: str
    segments: tuple[Segment, ...]
    message_seq: int
    sender_id: int | None = None
    hermes_attachment_materializations: tuple[HermesAttachmentMaterialization, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedMessage:
    """保存一条 trigger 消息的正文、附件和引用补全结果。"""

    body: str
    hermes_attachment_materializations: tuple[HermesAttachmentMaterialization, ...] = ()
    replies: tuple[ResolvedReply, ...] = ()
    forwards: tuple[ResolvedForward, ...] = ()
    diagnostics: tuple[ResourceDiagnostic, ...] = ()

    @property
    def media_materializations(self) -> tuple[HermesAttachmentMaterialization, ...]:
        """返回供未来 Hermes mapper 使用的附件 materialization。"""

        return self.hermes_attachment_materializations

    @property
    def attachments(self) -> tuple[HermesAttachmentMaterialization, ...]:
        """返回附件的兼容别名。"""

        return self.hermes_attachment_materializations

    @property
    def reply_results(self) -> tuple[ResolvedReply, ...]:
        """返回 reply 补全结果的兼容别名。"""

        return self.replies

    @property
    def forward_results(self) -> tuple[ResolvedForward, ...]:
        """返回 forward 补全结果的兼容别名。"""

        return self.forwards


@dataclass(frozen=True, slots=True)
class ResolvedTriggerBatch:
    """保存 detached batch 中已完成资源处理的历史和当前消息。"""

    chat_key: str
    history: tuple[ResolvedMessage, ...]
    current: ResolvedMessage


@dataclass(frozen=True, slots=True)
class _ContentResolution:
    """保存递归内容解析的内部结果。"""

    body: str
    materializations: tuple[HermesAttachmentMaterialization, ...]
    replies: tuple[ResolvedReply, ...]
    forwards: tuple[ResolvedForward, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


class ResourceResolver:
    """在 trigger 阶段解析引用，并把结果交给 Hermes media seam。"""

    def __init__(
        self,
        client: ResourceClient,
        hermes: HermesMediaHelpers,
        *,
        max_nested_depth: int = 4,
    ) -> None:
        """创建只使用已确认 Hermes helper 的 resolver。"""

        if isinstance(max_nested_depth, bool) or not isinstance(max_nested_depth, int):
            raise TypeError("max_nested_depth must be an integer")
        if max_nested_depth < 0:
            raise ValueError("max_nested_depth must be non-negative")
        self._client = client
        self._hermes = hermes
        self._max_nested_depth = max_nested_depth

    async def resolve(self, message: object) -> ResolvedMessage:
        """解析一条已经进入 trigger 的 normalized 或 canonical 消息。"""

        content = await self._resolve_message_content(message, depth=0)
        return ResolvedMessage(
            body=content.body,
            hermes_attachment_materializations=content.materializations,
            replies=content.replies,
            forwards=content.forwards,
            diagnostics=content.diagnostics,
        )

    async def resolve_message(self, message: object) -> ResolvedMessage:
        """提供描述性别名，明确该调用属于 trigger 阶段。"""

        return await self.resolve(message)

    async def resolve_batch(self, batch: object) -> ResolvedTriggerBatch:
        """解析 detached trigger batch，不重新写入 wait buffer。"""

        history = getattr(batch, "history", None)
        current = getattr(batch, "current", None)
        chat_key = getattr(batch, "chat_key", None)
        if not isinstance(chat_key, str) or not isinstance(history, tuple) or current is None:
            raise TypeError("batch must be a detached trigger batch")
        log_fields = _resource_log_fields(chat_key, batch)
        log_event(
            logger,
            "milky_resource_resolution_started",
            logging.DEBUG,
            stage="resource",
            **log_fields,
            history_count=len(history),
        )
        resolved_history = tuple([await self.resolve(item) for item in history])
        resolved_current = await self.resolve(current)
        result = ResolvedTriggerBatch(chat_key, resolved_history, resolved_current)
        materialized_count, degraded_count, reply_count, forward_count = _resource_counts(result)
        completion_fields = _resource_log_fields(chat_key, batch)
        log_event(
            logger,
            "milky_resource_resolution_completed",
            logging.INFO,
            stage="resource",
            **completion_fields,
            history_count=len(resolved_history),
            materialized_count=materialized_count,
            degraded_count=degraded_count,
            reply_count=reply_count,
            forward_count=forward_count,
        )
        if degraded_count:
            log_event(
                logger,
                "milky_resource_resolution_degraded",
                logging.WARNING,
                stage="resource",
                **completion_fields,
                classification=_resource_classification(result),
                reason="resource_resolution_failed",
                degraded_count=degraded_count,
            )
        return result

    async def _resolve_message_content(self, message: object, *, depth: int) -> _ContentResolution:
        body = _required_text(message, "body")
        scene = _required_text(message, "scene")
        if scene not in {"friend", "group"}:
            raise ValueError("message scene is unsupported")
        return await self._resolve_content(
            body=body,
            media_references=_tuple_field(message, "media_resource_references"),
            file_references=_tuple_field(message, "file_attachment_references"),
            forward_references=_tuple_field(message, "forward_references"),
            reply_references=_tuple_field(message, "reply_references"),
            scene=scene,
            peer_id=_required_non_negative_int(message, "peer_id"),
            self_id=_required_non_negative_int(message, "self_id"),
            depth=depth,
        )

    async def _resolve_content(
        self,
        *,
        body: str,
        media_references: tuple[object, ...],
        file_references: tuple[object, ...],
        forward_references: tuple[object, ...],
        reply_references: tuple[object, ...],
        scene: str,
        peer_id: int,
        self_id: int,
        depth: int,
    ) -> _ContentResolution:
        materializations: list[HermesAttachmentMaterialization] = []
        diagnostics: list[ResourceDiagnostic] = []
        replies: list[ResolvedReply] = []
        forwards: list[ResolvedForward] = []

        for reference in media_references:
            resolved, diagnostic = await self._resolve_media_reference(reference)
            if resolved is not None:
                materializations.append(resolved)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                body = _replace_first(
                    body,
                    _available_marker(_field(reference, "kind")),
                    _failure_marker(_field(reference, "kind")),
                )

        for reference in file_references:
            resolved, diagnostic = await self._resolve_file_reference(reference, scene, peer_id)
            if resolved is not None:
                materializations.append(resolved)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                body = _replace_first(body, "[文件]", "[文件不可用]")

        for reference in reply_references:
            reply, nested_diagnostics = await self._resolve_reply_reference(
                reference,
                scene=scene,
                peer_id=peer_id,
                self_id=self_id,
                depth=depth,
            )
            if reply is not None:
                replies.append(reply)
                materializations.extend(reply.hermes_attachment_materializations)
                diagnostics.extend(reply.diagnostics)
                if reply.body == "[引用不可用]":
                    body = _replace_first(body, "[引用]", "[引用不可用]")
            else:
                diagnostics.extend(nested_diagnostics)
                body = _replace_first(body, "[引用]", "[引用不可用]")

        for reference in forward_references:
            forward, nested_diagnostics = await self._resolve_forward_reference(
                reference,
                scene=scene,
                peer_id=peer_id,
                self_id=self_id,
                depth=depth,
            )
            if forward is not None:
                forwards.append(forward)
                diagnostics.extend(forward.diagnostics)
                if forward.diagnostics:
                    body = _replace_first(body, "[转发]", "[转发不可用]")
                for message_value in forward.messages:
                    materializations.extend(message_value.hermes_attachment_materializations)
                    diagnostics.extend(message_value.diagnostics)
            else:
                diagnostics.extend(nested_diagnostics)
                body = _replace_first(body, "[转发]", "[转发不可用]")

        return _ContentResolution(
            body=body,
            materializations=tuple(materializations),
            replies=tuple(replies),
            forwards=tuple(forwards),
            diagnostics=tuple(diagnostics),
        )

    async def _resolve_media_reference(
        self, reference: object
    ) -> tuple[HermesAttachmentMaterialization | None, ResourceDiagnostic | None]:
        kind = _field(reference, "kind")
        if kind not in {"image", "record", "video"}:
            return None, _diagnostic("unsupported", kind, "unsupported media kind", None)
        url = _optional_text(reference, "temp_url")
        resource_id = _optional_text(reference, "resource_id")
        if url is None and resource_id is not None:
            try:
                envelope = await self._client.get_resource_temp_url(resource_id)
                url = _data_text(envelope, "url")
            except Exception as error:  # noqa: BLE001 - resolver must downgrade helper failures
                return None, _diagnostic_from_error(
                    error, kind, "resource lookup failed", resource_id
                )
        if url is None:
            return None, _diagnostic(
                "malformed", kind, "media reference has no usable URL", resource_id
            )

        mime_type = _media_mime(reference, kind)
        display_name = _safe_display_name(_optional_text(reference, "name"))
        reference_id = resource_id
        try:
            if kind == "image":
                result = await self._cache_url_with_helper(
                    "cache_image_from_url",
                    url,
                    ext=_extension_for_mime(mime_type, ".jpg"),
                    mime_type=mime_type,
                    kind="image",
                    filename=display_name,
                    reference_kind=kind,
                    reference_id=reference_id,
                )
            elif kind == "record":
                result = await self._cache_url_with_helper(
                    "cache_audio_from_url",
                    url,
                    ext=_extension_for_mime(mime_type, ".ogg"),
                    mime_type=mime_type,
                    kind="audio",
                    filename=display_name,
                    reference_kind=kind,
                    reference_id=reference_id,
                )
            else:
                result = None
        except Exception as error:  # noqa: BLE001 - resolver must downgrade helper failures
            return None, _diagnostic_from_error(
                error, kind, "media materialization failed", reference_id
            )
        if result is None:
            return None, _diagnostic(
                "unsupported", kind, "media materialization is unavailable", reference_id
            )
        return result, None

    async def _resolve_file_reference(
        self, reference: object, scene: str, peer_id: int
    ) -> tuple[HermesAttachmentMaterialization | None, ResourceDiagnostic | None]:
        file_id = _optional_text(reference, "file_id")
        reference_id = file_id
        if file_id is None:
            return None, _diagnostic("malformed", "file", "file reference has no file ID", None)
        if scene == "group":
            try:
                envelope = await self._client.get_group_file_download_url(peer_id, file_id)
            except Exception as error:  # noqa: BLE001 - resolver must downgrade Action failures
                return None, _diagnostic_from_error(
                    error, "file", "file lookup failed", reference_id
                )
        elif scene == "friend":
            file_hash = _optional_text(reference, "file_hash")
            if file_hash is None:
                return None, _diagnostic(
                    "unsupported", "file", "private file hash is missing", reference_id
                )
            try:
                envelope = await self._client.get_private_file_download_url(
                    peer_id, file_id, file_hash
                )
            except Exception as error:  # noqa: BLE001 - resolver must downgrade Action failures
                return None, _diagnostic_from_error(
                    error, "file", "file lookup failed", reference_id
                )
        else:
            return None, _diagnostic(
                "unsupported", "file", "file scene is unsupported", reference_id
            )

        try:
            url = _data_text(envelope, "download_url")
        except Exception as error:  # noqa: BLE001 - resolver must downgrade envelope failures
            return None, _diagnostic_from_error(
                error, "file", "file download URL is malformed", reference_id
            )
        del url
        return None, _diagnostic(
            "unsupported", "file", "Hermes file resource entry is unavailable", reference_id
        )

    async def _resolve_reply_reference(
        self,
        reference: object,
        *,
        scene: str,
        peer_id: int,
        self_id: int,
        depth: int,
    ) -> tuple[ResolvedReply | None, tuple[ResourceDiagnostic, ...]]:
        message_seq = _optional_non_negative_int(reference, "message_seq")
        reference_id = None if message_seq is None else str(message_seq)
        if message_seq is None:
            return None, (_diagnostic("malformed", "reply", "reply target is missing", None),)

        if _optional_bool(reference, "complete"):
            segments = _tuple_field(reference, "segments")
            sender_id = _optional_non_negative_int(reference, "sender_id")
            sender_name = _optional_text(reference, "sender_name")
            timestamp = _optional_non_negative_int(reference, "time")
        else:
            try:
                envelope = await self._client.get_message(scene, peer_id, message_seq)
                source = _data_mapping(envelope, "message")
                fetched_message = parse_incoming_message_data(source)
                if (
                    fetched_message.message_scene != scene
                    or fetched_message.peer_id != peer_id
                    or fetched_message.message_seq != message_seq
                ):
                    raise ParseError("malformed", "reply message identity disagrees")
            except Exception as error:  # noqa: BLE001 - resolver must downgrade Action failures
                diagnostic = _diagnostic_from_error(
                    error, "reply", "reply lookup failed", reference_id
                )
                return (
                    ResolvedReply(
                        message_seq=message_seq,
                        sender_id=None,
                        sender_name=None,
                        timestamp=None,
                        body="[引用不可用]",
                        segments=(),
                        diagnostics=(diagnostic,),
                    ),
                    (diagnostic,),
                )
            segments = fetched_message.segments
            sender_id = fetched_message.sender_id
            sender_name = _incoming_sender_name(fetched_message)
            timestamp = fetched_message.time

        if depth >= self._max_nested_depth:
            diagnostic = _diagnostic(
                "unsupported", "reply", "nested reference depth exceeded", reference_id
            )
            return ResolvedReply(
                message_seq=message_seq,
                sender_id=sender_id,
                sender_name=sender_name,
                timestamp=timestamp,
                body=_segments_body(segments, self_id),
                segments=segments,
                diagnostics=(diagnostic,),
            ), (diagnostic,)

        extracted = extract_segments(segments, self_id)
        content = await self._resolve_content(
            body=extracted.body,
            media_references=extracted.media_resource_references,
            file_references=extracted.file_attachment_references,
            forward_references=extracted.forward_references,
            reply_references=extracted.reply_references,
            scene=scene,
            peer_id=peer_id,
            self_id=self_id,
            depth=depth + 1,
        )
        return ResolvedReply(
            message_seq=message_seq,
            sender_id=sender_id,
            sender_name=sender_name,
            timestamp=timestamp,
            body=content.body,
            segments=segments,
            hermes_attachment_materializations=content.materializations,
            diagnostics=content.diagnostics,
        ), ()

    async def _resolve_forward_reference(
        self,
        reference: object,
        *,
        scene: str,
        peer_id: int,
        self_id: int,
        depth: int,
    ) -> tuple[ResolvedForward | None, tuple[ResourceDiagnostic, ...]]:
        forward_id = _optional_text(reference, "forward_id")
        if forward_id is None:
            return None, (_diagnostic("malformed", "forward", "forward ID is missing", None),)
        if depth >= self._max_nested_depth:
            diagnostic = _diagnostic(
                "unsupported", "forward", "nested reference depth exceeded", forward_id
            )
            return ResolvedForward(forward_id, diagnostics=(diagnostic,)), (diagnostic,)
        try:
            envelope = await self._client.get_forwarded_messages(forward_id)
            values = _data_sequence(envelope, "messages")
            forwarded_messages = tuple(parse_forwarded_message(value) for value in values)
        except Exception as error:  # noqa: BLE001 - resolver must downgrade Action failures
            diagnostic = _diagnostic_from_error(
                error, "forward", "forward lookup failed", forward_id
            )
            return ResolvedForward(forward_id, diagnostics=(diagnostic,)), (diagnostic,)

        resolved_messages: list[ResolvedForwardedMessage] = []
        for forwarded in forwarded_messages:
            extracted = extract_segments(forwarded.segments, self_id)
            content = await self._resolve_content(
                body=extracted.body,
                media_references=extracted.media_resource_references,
                file_references=extracted.file_attachment_references,
                forward_references=extracted.forward_references,
                reply_references=extracted.reply_references,
                scene=scene,
                peer_id=peer_id,
                self_id=self_id,
                depth=depth + 1,
            )
            resolved_messages.append(
                ResolvedForwardedMessage(
                    time=forwarded.time,
                    sender_name=forwarded.sender_name,
                    avatar_url=forwarded.avatar_url,
                    body=content.body,
                    segments=forwarded.segments,
                    message_seq=forwarded.message_seq,
                    sender_id=None,
                    hermes_attachment_materializations=content.materializations,
                    diagnostics=content.diagnostics,
                )
            )
        return ResolvedForward(forward_id, tuple(resolved_messages)), ()

    async def _cache_url_with_helper(
        self,
        helper_name: str,
        url: str,
        *,
        ext: str,
        mime_type: str,
        kind: str,
        filename: str,
        reference_kind: str,
        reference_id: str | None,
    ) -> HermesAttachmentMaterialization | None:
        helper = getattr(self._hermes, helper_name, None)
        if not callable(helper):
            return None
        result = helper(url, ext=ext)
        path = await _await_result(result)
        return _materialization_from_path(
            path,
            mime_type=mime_type,
            kind=kind,
            display_name=filename,
            reference_kind=reference_kind,
            reference_id=reference_id,
        )


def _required_text(value: object, field_name: str) -> str:
    result = getattr(value, field_name, None)
    if not isinstance(result, str) or not result.strip():
        raise TypeError(f"message {field_name} is invalid")
    return result.strip()


def _required_non_negative_int(value: object, field_name: str) -> int:
    result = getattr(value, field_name, None)
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        raise TypeError(f"message {field_name} is invalid")
    return result


def _tuple_field(value: object, field_name: str) -> tuple[object, ...]:
    result = getattr(value, field_name, ())
    if not isinstance(result, tuple):
        raise TypeError(f"message {field_name} is invalid")
    return result


def _field(value: object, field_name: str) -> object:
    return getattr(value, field_name, None)


def _optional_text(value: object, field_name: str) -> str | None:
    result = _field(value, field_name)
    if not isinstance(result, str) or not result.strip():
        return None
    return result.strip()


def _optional_bool(value: object, field_name: str) -> bool:
    result = _field(value, field_name)
    return result is True


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    result = _field(value, field_name)
    if isinstance(result, bool) or not isinstance(result, int) or result < 0:
        return None
    return result


def _data_mapping(envelope: object, field_name: str) -> Mapping[str, Any]:
    data = _envelope_data(envelope)
    value = data.get(field_name)
    if not isinstance(value, Mapping):
        raise ParseError("malformed", f"data.{field_name} must be an object")
    return value


def _data_sequence(envelope: object, field_name: str) -> Sequence[object]:
    data = _envelope_data(envelope)
    value = data.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ParseError("malformed", f"data.{field_name} must be an array")
    return value


def _data_text(envelope: object, field_name: str) -> str:
    data = _envelope_data(envelope)
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ParseError("malformed", f"data.{field_name} must be non-empty text")
    return value.strip()


def _envelope_data(envelope: object) -> Mapping[str, Any]:
    data = getattr(envelope, "data", None)
    if data is None and isinstance(envelope, Mapping):
        data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise ParseError("malformed", "response data is malformed")
    return data


async def _await_result(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


def _materialization_from_path(
    path: object,
    *,
    mime_type: str,
    kind: str,
    display_name: str,
    reference_kind: str,
    reference_id: str | None,
) -> HermesAttachmentMaterialization:
    if not isinstance(path, str) or not path.strip() or "://" in path:
        raise ValueError("Hermes URL helper did not return a local path")
    return HermesAttachmentMaterialization(
        path=path,
        mime_type=mime_type,
        kind=kind,
        display_name=display_name,
        reference_kind=reference_kind,
        reference_id=reference_id,
    )


def _segments_body(segments: tuple[Segment, ...], self_id: int) -> str:
    return extract_segments(segments, self_id).body


def _incoming_sender_name(message: IncomingMessage) -> str:
    """按 Milky 场景选择完整 reply 的安全显示名。"""

    if message.message_scene == "friend" and message.friend is not None:
        nickname = message.friend.nickname.strip()
        if nickname:
            return nickname
    if message.message_scene == "group" and message.group_member is not None:
        for candidate in (message.group_member.card, message.group_member.nickname):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return str(message.sender_id)


def _replace_first(body: str, old: str, new: str) -> str:
    if old not in body:
        return body
    return body.replace(old, new, 1)


def _available_marker(kind: object) -> str:
    return {"image": "[图片]", "record": "[语音]", "video": "[视频]"}.get(kind, "[媒体]")


def _failure_marker(kind: object) -> str:
    return {
        "image": "[图片不可用]",
        "record": "[语音转写失败]",
        "video": "[视频不可用]",
    }.get(kind, "[媒体不可用]")


def _media_mime(reference: object, kind: str) -> str:
    explicit = _optional_text(reference, "mime_type")
    if explicit is not None:
        return explicit
    return {"image": "image/jpeg", "record": "audio/ogg", "video": "video/mp4"}[kind]


def _extension_for_mime(mime_type: str, fallback: str) -> str:
    return {
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
    }.get(mime_type.lower(), fallback)


def _safe_display_name(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(char if char.isprintable() else "_" for char in value).strip()[:128]


def _diagnostic(
    classification: str, reference_kind: object, reason: str, reference_id: str | None
) -> ResourceDiagnostic:
    kind = reference_kind if isinstance(reference_kind, str) and reference_kind else "unknown"
    return ResourceDiagnostic(classification, kind, reason, reference_id)


def _diagnostic_from_error(
    error: Exception, reference_kind: object, reason: str, reference_id: str | None
) -> ResourceDiagnostic:
    if isinstance(error, ActionError):
        classification = error.classification
    elif isinstance(error, (TimeoutError, OSError)):
        classification = "transport_unknown"
    elif isinstance(error, (ParseError, TypeError, ValueError, KeyError)):
        classification = "malformed"
    else:
        classification = "unsupported"
    return _diagnostic(classification, reference_kind, reason, reference_id)


def _resource_log_fields(chat_key: str, batch: object) -> dict[str, object]:
    """提取资源 batch 的安全关联字段。"""

    fields: dict[str, object] = {}
    try:
        fields["chat_key"] = validate_chat_key(chat_key)
    except (TypeError, ValueError):
        pass
    sequence = getattr(batch, "trigger_ingress_sequence", None)
    if isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 0:
        fields["ingress_sequence"] = sequence
    current = getattr(batch, "current", None)
    message_id = getattr(current, "message_id", None)
    if message_id is not None:
        fields["message_id"] = message_id
    scene = getattr(current, "scene", None)
    if scene in {"friend", "group"}:
        fields["scene"] = scene
    return fields


def _resource_counts(batch: ResolvedTriggerBatch) -> tuple[int, int, int, int]:
    """汇总 materialization、降级、reply 和 forward 数量。"""

    messages = (*batch.history, batch.current)
    return (
        sum(len(message.hermes_attachment_materializations) for message in messages),
        sum(len(message.diagnostics) for message in messages),
        sum(len(message.replies) for message in messages),
        sum(len(message.forwards) for message in messages),
    )


def _resource_classification(batch: ResolvedTriggerBatch) -> str:
    """返回第一个安全的资源错误分类。"""

    allowed = {
        "rejected",
        "transport_unknown",
        "malformed",
        "unsupported",
        "invalid_input",
        "http_error",
    }
    for message in (*batch.history, batch.current):
        for diagnostic in message.diagnostics:
            if diagnostic.classification in allowed:
                return diagnostic.classification
    return "unsupported"


__all__ = [
    "HermesAttachmentMaterialization",
    "HermesMediaHelpers",
    "ResolvedForward",
    "ResolvedForwardedMessage",
    "ResolvedMessage",
    "ResolvedReply",
    "ResolvedTriggerBatch",
    "ResourceClient",
    "ResourceDiagnostic",
    "ResourceResolver",
]
