"""Milky 出站附件的统一类型、文件名和 URI materialization 边界。"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from config import DEFAULT_MAX_LOCAL_MEDIA_BYTES
from milky.client import ActionError, materialize_media_uri, validate_media_uri

MaterializationKind = Literal["image", "audio", "video", "document"]

_KIND_ALIASES = {"voice": "audio"}
_MATERIALIZATION_KINDS = frozenset({"image", "audio", "video", "document"})


class OutboundMaterialization:
    """保存已经转换为 Milky URI 的出站附件引用。"""

    __slots__ = ("caption", "file_name", "kind", "mime_type", "uri")

    def __init__(
        self,
        kind: str,
        uri: str,
        file_name: str | None = None,
        mime_type: str | None = None,
        caption: str | None = None,
    ) -> None:
        """创建一个只保存 URI 和必要元数据的结果。"""

        self.kind = kind
        self.uri = uri
        self.file_name = file_name
        self.mime_type = mime_type
        self.caption = caption

    def __repr__(self) -> str:
        """提供不包含 URI、文件名或正文的调试表示。"""

        return f"{type(self).__name__}(kind={self.kind!r})"


def materialization_kind(value: object, *, action: str = "media") -> MaterializationKind:
    """读取并校验结构化附件的类型。"""

    raw_kind = _field(value, "kind")
    normalized = _normalize_kind(raw_kind)
    if normalized is None:
        raise ActionError("unsupported", action, "attachment kind is unavailable")
    return normalized


def validate_materialization(
    value: object,
    *,
    expected_kind: MaterializationKind | None = None,
    action: str = "media",
    file_name: str | None = None,
) -> OutboundMaterialization:
    """校验已经 materialize 的 URI 或结构化出站附件。"""

    if isinstance(value, str):
        if expected_kind is None:
            raise ActionError("unsupported", action, "attachment kind is unavailable")
        if file_name is not None:
            _validate_file_name(file_name, action)
        uri = validate_media_uri(value, action=action)
        return OutboundMaterialization(expected_kind, uri, file_name=file_name)

    kind = materialization_kind(value, action=action)
    if expected_kind is not None and kind != expected_kind:
        raise ActionError("unsupported", action, "attachment kind is incompatible")
    uri_value = _field(value, "uri")
    if uri_value is None:
        uri_value = _field(value, "file_uri")
    uri = validate_media_uri(uri_value, action=action)
    source_file_name = _field(value, "file_name")
    if source_file_name is not None:
        _validate_file_name(source_file_name, action)
    resolved_file_name = file_name if file_name is not None else source_file_name
    if resolved_file_name is not None:
        _validate_file_name(resolved_file_name, action)
    caption = _field(value, "caption")
    if caption is not None and not isinstance(caption, str):
        raise ActionError("invalid_input", action, "attachment caption is invalid")
    mime_type = _field(value, "mime_type")
    if mime_type is not None and not isinstance(mime_type, str):
        raise ActionError("invalid_input", action, "attachment MIME type is invalid")
    return OutboundMaterialization(
        kind,
        uri,
        file_name=resolved_file_name if isinstance(resolved_file_name, str) else None,
        mime_type=mime_type if isinstance(mime_type, str) else None,
        caption=caption if isinstance(caption, str) else None,
    )


async def prepare_materialization(
    value: object,
    *,
    expected_kind: MaterializationKind,
    action: str,
    file_name: str | None = None,
    max_local_media_bytes: int = DEFAULT_MAX_LOCAL_MEDIA_BYTES,
) -> OutboundMaterialization:
    """将远端、内联或本地资源转换为并校验统一出站结果。"""

    resolved_file_name: str | None = None
    if expected_kind == "document":
        resolved_file_name = resolve_file_name(value, file_name, action=action)
    elif file_name is not None:
        _validate_file_name(file_name, action)
    uri = await materialize_media_uri(
        value,
        action=action,
        max_local_media_bytes=max_local_media_bytes,
    )
    return OutboundMaterialization(expected_kind, uri, file_name=resolved_file_name)


def resolve_file_name(
    value: object,
    explicit_name: object = None,
    *,
    action: str = "file_upload",
) -> str:
    """从显式名称或附件引用解析安全的上传文件名。"""

    if explicit_name is not None:
        _validate_file_name(explicit_name, action)
        return explicit_name  # type: ignore[return-value]

    if isinstance(value, Path):
        name = value.name
    elif isinstance(value, str):
        try:
            parsed = urlsplit(value.strip())
        except ValueError:
            name = ""
        else:
            if parsed.scheme == "base64":
                raise ActionError("invalid_input", action, "file name is required")
            if parsed.scheme in {"file", "http", "https"}:
                name = Path(unquote(parsed.path)).name
            elif parsed.scheme:
                name = ""
            else:
                name = Path(value).name
    else:
        name = ""
    _validate_file_name(name, action)
    return name


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    if isinstance(value, OutboundMaterialization):
        return getattr(value, name)
    return getattr(value, name, None)


def _normalize_kind(value: object) -> MaterializationKind | None:
    if not isinstance(value, str):
        return None
    normalized = _KIND_ALIASES.get(value, value)
    if normalized not in _MATERIALIZATION_KINDS:
        return None
    return normalized  # type: ignore[return-value]


def _validate_file_name(value: object, action: str) -> None:
    """校验用户可见文件名，不回显不安全值。"""

    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ActionError("invalid_input", action, "file name is invalid")


__all__ = [
    "MaterializationKind",
    "OutboundMaterialization",
    "materialization_kind",
    "prepare_materialization",
    "resolve_file_name",
    "validate_materialization",
]
