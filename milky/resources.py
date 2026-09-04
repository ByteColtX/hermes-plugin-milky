"""Milky trigger 阶段的分类资源和 reply 补全边界。

本模块只在 detached trigger batch 已经建立后工作。Milky 负责提供经过协议校验的
引用，Hermes seam 负责下载安全、缓存和本地路径；插件不实现第三套下载或缓存逻辑。
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Protocol

from milky.client import ActionError
from milky.models import IncomingMessage, Segment
from milky.observability import log_event
from milky.parser import ParseError, parse_incoming_message_data
from session.identity import validate_chat_key

if TYPE_CHECKING:
    from inbound.extractor import ExtractedSegments

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
class ResolvedImageOccurrence:
    """保存图片 occurrence、展示槽位和最终代表之间的关联。"""

    materialization: HermesAttachmentMaterialization
    body_marker: str
    body_start: int | None = None
    body_end: int | None = None
    order: tuple[int, ...] = ()
    surface: str = "message"
    representative: HermesAttachmentMaterialization | None = None
    retained: bool = True

    @property
    def representative_materialization(self) -> HermesAttachmentMaterialization:
        """返回该 occurrence 使用的首个代表 materialization。"""

        return self.representative or self.materialization

    @property
    def path(self) -> str:
        """返回最终展示和媒体输入使用的代表路径。"""

        return self.representative_materialization.path

    @property
    def basename(self) -> str:
        """返回最终代表路径的 basename。"""

        return _path_basename(self.path)

    @property
    def mime_type(self) -> str:
        """返回首次代表的 MIME。"""

        return self.representative_materialization.mime_type

    @property
    def merged(self) -> bool:
        """返回该 occurrence 是否合并到其他代表。"""

        return not self.retained


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
    body_template: str | None = None
    image_occurrences: tuple[ResolvedImageOccurrence, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedForward:
    """保存一个 forward ID；普通 trigger 不自动展开其消息。"""

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
    context_image_materializations: tuple[HermesAttachmentMaterialization, ...] = ()
    body_template: str | None = None
    image_occurrences: tuple[ResolvedImageOccurrence, ...] = ()

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
    context_image_materializations: tuple[HermesAttachmentMaterialization, ...]
    replies: tuple[ResolvedReply, ...]
    forwards: tuple[ResolvedForward, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]
    body_template: str
    image_occurrences: tuple[ResolvedImageOccurrence, ...]


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
            context_image_materializations=content.context_image_materializations,
            body_template=content.body_template,
            image_occurrences=content.image_occurrences,
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
        result = _finalize_trigger_batch(
            ResolvedTriggerBatch(chat_key, resolved_history, resolved_current)
        )
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
        image_order_prefix: tuple[int, ...] = (),
    ) -> _ContentResolution:
        body_template = body
        materializations: list[HermesAttachmentMaterialization] = []
        context_image_materializations: list[HermesAttachmentMaterialization] = []
        image_occurrences: list[ResolvedImageOccurrence] = []
        diagnostics: list[ResourceDiagnostic] = []
        replies: list[ResolvedReply] = []
        forwards: list[ResolvedForward] = []
        replacements: list[tuple[int, int, str]] = []
        fallback_replacements: list[tuple[str, str]] = []

        for reference_index, reference in enumerate(media_references):
            resolved, diagnostic = await self._resolve_media_reference(reference)
            if resolved is not None:
                materializations.append(resolved)
                if _field(reference, "kind") == "image":
                    context_image_materializations.append(resolved)
                    marker = _available_marker(reference)
                    image_occurrences.append(
                        ResolvedImageOccurrence(
                            materialization=resolved,
                            body_marker=marker,
                            body_start=_optional_non_negative_int(reference, "body_start"),
                            body_end=_optional_non_negative_int(reference, "body_end"),
                            order=image_order_prefix
                            + (_reference_index(reference, reference_index), 0),
                        )
                    )
                    _add_body_replacement(
                        replacements,
                        fallback_replacements,
                        body_template,
                        reference,
                        marker,
                        _image_path_marker(resolved.path),
                    )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
                _add_body_replacement(
                    replacements,
                    fallback_replacements,
                    body_template,
                    reference,
                    _available_marker(reference),
                    _failure_marker(_field(reference, "kind")),
                )

        for reference in file_references:
            resolved, diagnostic = await self._resolve_file_reference(reference, scene, peer_id)
            if resolved is not None:
                materializations.append(resolved)
            if diagnostic is not None:
                diagnostics.append(diagnostic)

        for reference_index, reference in enumerate(reply_references):
            reply, nested_diagnostics = await self._resolve_reply_reference(
                reference,
                scene=scene,
                peer_id=peer_id,
                self_id=self_id,
                depth=depth,
                image_order_prefix=image_order_prefix
                + (_reference_index(reference, reference_index), 1),
            )
            if reply is not None:
                replies.append(reply)
                materializations.extend(reply.hermes_attachment_materializations)
                diagnostics.extend(reply.diagnostics)
            else:
                diagnostics.extend(nested_diagnostics)

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
                for message_value in forward.messages:
                    materializations.extend(message_value.hermes_attachment_materializations)
                    diagnostics.extend(message_value.diagnostics)
            else:
                diagnostics.extend(nested_diagnostics)

        return _ContentResolution(
            body=_render_body_replacements(
                body_template,
                replacements,
                fallback_replacements,
            ),
            materializations=tuple(materializations),
            context_image_materializations=tuple(context_image_materializations),
            replies=tuple(replies),
            forwards=tuple(forwards),
            diagnostics=tuple(diagnostics),
            body_template=body_template,
            image_occurrences=tuple(image_occurrences),
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
        image_order_prefix: tuple[int, ...] = (),
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
                        body="[reply:NOT SUPPORTED]",
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

        extracted = _extract_segments(segments, self_id)
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
            image_order_prefix=image_order_prefix,
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
            body_template=content.body_template,
            image_occurrences=tuple(
                replace(occurrence, surface="reply") for occurrence in content.image_occurrences
            ),
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
        """只保留 forward 引用，不自动查询转发详情。"""

        del scene, peer_id, self_id, depth
        forward_id = _optional_text(reference, "forward_id")
        if forward_id is None:
            return None, (_diagnostic("malformed", "forward", "forward ID is missing", None),)
        return ResolvedForward(forward_id), ()

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


def _is_local_path(value: object) -> bool:
    """判断 helper 返回值是否是非空本地路径，而非远端 URI。"""

    return isinstance(value, str) and bool(value.strip()) and "://" not in value


def _segments_body(segments: tuple[Segment, ...], self_id: int) -> str:
    return _extract_segments(segments, self_id).body


def _extract_segments(segments: tuple[Segment, ...], self_id: int) -> ExtractedSegments:
    """延迟加载入站 extractor，避免 ``milky`` 与 ``inbound`` 的导入循环。"""

    from inbound.extractor import extract_segments

    return extract_segments(segments, self_id)


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


def _reference_index(reference: object, fallback: int) -> int:
    """返回引用的原始 segment 顺序；缺失时使用引用列表顺序。"""

    value = _optional_non_negative_int(reference, "segment_index")
    return fallback if value is None else value


def _add_body_replacement(
    replacements: list[tuple[int, int, str]],
    fallback_replacements: list[tuple[str, str]],
    body: str,
    reference: object,
    old: str,
    new: str,
) -> None:
    """登记一个有结构化槽位的正文替换，避免从正文反解析图片身份。"""

    start = _optional_non_negative_int(reference, "body_start")
    end = _optional_non_negative_int(reference, "body_end")
    if (
        start is not None
        and end is not None
        and start < end <= len(body)
        and body[start:end] == old
    ):
        replacements.append((start, end, new))
        return
    fallback_replacements.append((old, new))


def _render_body_replacements(
    body: str,
    replacements: Sequence[tuple[int, int, str]],
    fallback_replacements: Sequence[tuple[str, str]],
) -> str:
    """按记录的正文槽位替换图片或媒体 placeholder。"""

    rendered = body
    previous_end = len(body) + 1
    for start, end, replacement in sorted(replacements, reverse=True):
        if start < 0 or start >= end or end > len(body) or end > previous_end:
            continue
        rendered = rendered[:start] + replacement + rendered[end:]
        previous_end = start
    for old, new in fallback_replacements:
        rendered = _replace_first(rendered, old, new)
    return rendered


def _available_marker(reference: object) -> str:
    kind = _field(reference, "kind")
    if kind == "image":
        summary = _optional_text(reference, "name")
        resource_id = _optional_text(reference, "resource_id")
        return f"[img:file_name={summary or resource_id or 'NOT SUPPORTED'}]"
    return {
        "record": "[record:NOT SUPPORTED]",
        "video": "[video:NOT SUPPORTED]",
    }.get(kind, "[media:NOT SUPPORTED]")


def _image_path_marker(path: object) -> str:
    """用 Hermes helper 返回路径的 basename 生成最终图片占位符。"""

    return f"[img:file_name={_path_basename(path)}]"


def _path_basename(path: object) -> str:
    """提取已通过 materialization 校验的路径 basename。"""

    if not isinstance(path, str) or not path.strip():
        raise ValueError("Hermes image helper returned an empty path")
    basename = path.replace("\\", "/").rsplit("/", 1)[-1]
    if not basename or basename in {".", ".."}:
        raise ValueError("Hermes image helper returned an invalid basename")
    return basename


def _failure_marker(kind: object) -> str:
    return {
        "image": "[img:file_name=NOT SUPPORTED]",
        "record": "[record:NOT SUPPORTED]",
        "video": "[video:NOT SUPPORTED]",
    }.get(kind, "[media:NOT SUPPORTED]")


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


_MAX_IMAGE_HASH_BYTES = 8 * 1024 * 1024
_IMAGE_HASH_CHUNK_BYTES = 64 * 1024


def _finalize_trigger_batch(batch: ResolvedTriggerBatch) -> ResolvedTriggerBatch:
    """在单个 trigger batch 内选择图片内容代表并重建展示正文。"""

    hash_cache: dict[str, str | None] = {}
    registry: dict[tuple[str, str], HermesAttachmentMaterialization] = {}
    occurrence_updates: dict[int, ResolvedImageOccurrence] = {}
    diagnostics_by_message: dict[int, list[ResourceDiagnostic]] = {}

    candidates: list[tuple[ResolvedMessage, ResolvedImageOccurrence]] = []
    for message in batch.history:
        candidates.extend((message, occurrence) for occurrence in message.image_occurrences)

    current_reply = batch.current.replies[:1]
    current_occurrences = [*batch.current.image_occurrences]
    current_occurrences.extend(
        occurrence for reply in current_reply for occurrence in reply.image_occurrences
    )
    current_occurrences.sort(key=lambda occurrence: occurrence.order)
    candidates.extend((batch.current, occurrence) for occurrence in current_occurrences)

    for _owner, occurrence in candidates:
        materialization = occurrence.materialization
        path = materialization.path
        digest = hash_cache.get(path) if path in hash_cache else _safe_image_digest(path)
        hash_cache[path] = digest
        if digest is None:
            key = ("path", path)
        else:
            key = ("digest", digest)
        representative = registry.setdefault(key, materialization)
        occurrence_updates[id(occurrence)] = replace(
            occurrence,
            representative=representative,
            retained=representative is materialization,
        )

    # 对 hash 失败路径只产生一次无敏感字段诊断；诊断归属通过第二次遍历补齐。
    failed_paths: set[str] = set()
    for owner, occurrence in candidates:
        path = occurrence.materialization.path
        if hash_cache.get(path) is not None or path in failed_paths:
            continue
        failed_paths.add(path)
        diagnostics_by_message.setdefault(id(owner), []).append(
            _diagnostic("unsupported", "image", "image_hash_unavailable", None)
        )

    history = tuple(
        _finalize_message(
            message,
            occurrence_updates,
            diagnostics_by_message.get(id(message), ()),
            is_current=False,
        )
        for message in batch.history
    )
    current = _finalize_message(
        batch.current,
        occurrence_updates,
        diagnostics_by_message.get(id(batch.current), ()),
        is_current=True,
    )
    return replace(batch, history=history, current=current)


def _finalize_message(
    message: ResolvedMessage,
    occurrence_updates: Mapping[int, ResolvedImageOccurrence],
    hash_diagnostics: Sequence[ResourceDiagnostic],
    *,
    is_current: bool,
) -> ResolvedMessage:
    """更新一条消息的直接图片展示和最终媒体集合。"""

    occurrences = tuple(
        occurrence_updates.get(id(occurrence), occurrence)
        for occurrence in message.image_occurrences
    )
    body = _rewrite_resolved_body(message.body, message.body_template, occurrences)
    replies = message.replies
    materializations = message.hermes_attachment_materializations
    if is_current:
        replies = tuple(
            _finalize_reply(
                reply,
                occurrence_updates,
                visible=index == 0,
            )
            for index, reply in enumerate(replies)
        )
        materializations = _finalize_current_materializations(
            materializations,
            occurrences,
            replies,
        )
    context_images = tuple(
        occurrence.materialization
        for occurrence in occurrences
        if occurrence.retained and _is_local_path(occurrence.materialization.path)
    )
    return replace(
        message,
        body=body,
        hermes_attachment_materializations=materializations,
        replies=replies,
        diagnostics=(*message.diagnostics, *hash_diagnostics),
        context_image_materializations=context_images,
        image_occurrences=occurrences,
    )


def _finalize_reply(
    reply: ResolvedReply,
    occurrence_updates: Mapping[int, ResolvedImageOccurrence],
    *,
    visible: bool,
) -> ResolvedReply:
    """更新当前 MessageEvent 实际展示的 reply 文本。"""

    if not visible:
        return reply
    occurrences = tuple(
        occurrence_updates.get(id(occurrence), occurrence) for occurrence in reply.image_occurrences
    )
    return replace(
        reply,
        body=_rewrite_resolved_body(reply.body, reply.body_template, occurrences),
        image_occurrences=occurrences,
    )


def _rewrite_resolved_body(
    body: str,
    body_template: str | None,
    occurrences: Sequence[ResolvedImageOccurrence],
) -> str:
    """依据 image occurrence 槽位重建正文，不从 basename 反解析内容。"""

    if not occurrences:
        return body
    if body_template is None:
        rendered = body
        for occurrence in occurrences:
            old = _image_path_marker(occurrence.materialization.path)
            new = _image_path_marker(occurrence.path)
            rendered = _replace_first(rendered, old, new)
        return rendered
    replacements = [
        (occurrence.body_start, occurrence.body_end, _image_path_marker(occurrence.path))
        for occurrence in occurrences
        if occurrence.body_start is not None and occurrence.body_end is not None
    ]
    fallback = [
        (occurrence.body_marker, _image_path_marker(occurrence.path))
        for occurrence in occurrences
        if occurrence.body_start is None or occurrence.body_end is None
    ]
    return _render_body_replacements(body_template, replacements, fallback)


def _finalize_current_materializations(
    materializations: Sequence[HermesAttachmentMaterialization],
    direct_occurrences: Sequence[ResolvedImageOccurrence],
    replies: Sequence[ResolvedReply],
) -> tuple[HermesAttachmentMaterialization, ...]:
    """过滤 current 的重复图片，并保留当前既有的非图片附件。"""

    all_occurrences = [*direct_occurrences]
    all_occurrences.extend(
        occurrence for reply in replies for occurrence in reply.image_occurrences
    )
    if not all_occurrences:
        return tuple(materializations)
    occurrence_ids = {id(occurrence.materialization) for occurrence in all_occurrences}
    visible_occurrences = [*direct_occurrences]
    if replies:
        visible_occurrences.extend(replies[0].image_occurrences)
    visible_occurrences.sort(key=lambda occurrence: occurrence.order)
    kept_images = [
        occurrence.materialization
        for occurrence in visible_occurrences
        if occurrence.retained and _is_local_path(occurrence.materialization.path)
    ]
    image_indices = [
        index
        for index, materialization in enumerate(materializations)
        if materialization.kind == "image" and id(materialization) in occurrence_ids
    ]
    if not image_indices:
        return tuple(materializations)
    kept_index = 0
    result: list[HermesAttachmentMaterialization] = []
    image_index_set = set(image_indices)
    for index, materialization in enumerate(materializations):
        if index not in image_index_set:
            result.append(materialization)
            continue
        if kept_index < len(kept_images):
            result.append(kept_images[kept_index])
            kept_index += 1
    return tuple(result)


def _safe_image_digest(path: object) -> str | None:
    """以 descriptor 和固定块大小读取一个受限的普通图片文件。"""

    if not _is_local_path(path) or not isinstance(path, str):
        return None
    flags = os.O_RDONLY
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    flags |= no_follow
    try:
        if not no_follow:
            before_path = os.lstat(path)
            if not stat.S_ISREG(before_path.st_mode):
                return None
        descriptor = os.open(path, flags)
    except (OSError, TypeError, ValueError):
        return None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None
        if before.st_size <= 0 or before.st_size > _MAX_IMAGE_HASH_BYTES:
            return None
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, _IMAGE_HASH_CHUNK_BYTES)
            if not isinstance(chunk, bytes):
                return None
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_IMAGE_HASH_BYTES:
                return None
            digest.update(chunk)
        after = os.fstat(descriptor)
        if not _same_file_snapshot(before, after) or total != before.st_size:
            return None
        return digest.hexdigest()
    except Exception:  # noqa: BLE001 - hash failure must conservatively downgrade
        return None
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _same_file_snapshot(before: os.stat_result, after: os.stat_result) -> bool:
    """比较 descriptor 两端的文件身份和大小状态。"""

    return (
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
        and before.st_ctime_ns == after.st_ctime_ns
    )


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
    "ResolvedImageOccurrence",
    "ResolvedMessage",
    "ResolvedReply",
    "ResolvedTriggerBatch",
    "ResourceClient",
    "ResourceDiagnostic",
    "ResourceResolver",
]
