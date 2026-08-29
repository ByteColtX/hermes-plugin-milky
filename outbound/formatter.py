"""将 Hermes 出站内容转换为 Milky v1.3 outgoing segments。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_MAX_SAFE_INTEGER = 9007199254740991
_SEGMENT_TYPES = frozenset(
    {
        "text",
        "mention",
        "mention_all",
        "face",
        "reply",
        "image",
        "record",
        "video",
        "forward",
        "light_app",
    }
)


class OutboundFormatError(ValueError):
    """表示出站内容不符合 Milky outgoing segment 契约。"""

    def __init__(self, classification: str, reason: str) -> None:
        self.classification = classification
        self.reason = reason
        super().__init__(f"{classification}: {reason}")


def text_segment(text: object) -> dict[str, Any]:
    """构造文本 segment，并保留文本的原始空白。"""

    if not isinstance(text, str):
        raise OutboundFormatError("invalid_input", "text is invalid")
    return {"type": "text", "data": {"text": text}}


def mention_segment(user_id: object) -> dict[str, Any]:
    """构造用户提及 segment。"""

    return {"type": "mention", "data": {"user_id": _qq_id(user_id, "mention.user_id")}}


def mention_all_segment() -> dict[str, Any]:
    """构造全体提及 segment。"""

    return {"type": "mention_all", "data": {}}


def face_segment(face_id: object, *, is_large: object = None) -> dict[str, Any]:
    """构造表情 segment。"""

    data: dict[str, Any] = {"face_id": _required_text(face_id, "face.face_id")}
    if is_large is not None:
        if not isinstance(is_large, bool):
            raise OutboundFormatError("invalid_input", "face.is_large is invalid")
        data["is_large"] = is_large
    return {"type": "face", "data": data}


def reply_segment(message_seq: object) -> dict[str, Any]:
    """构造引用 segment。"""

    return {
        "type": "reply",
        "data": {
            "message_seq": _integer(message_seq, "reply.message_seq", maximum=_MAX_SAFE_INTEGER)
        },
    }


def image_segment(
    uri: object,
    *,
    sub_type: object = None,
    summary: object = None,
) -> dict[str, Any]:
    """构造图片 segment。"""

    data: dict[str, Any] = {"uri": _required_text(uri, "image.uri")}
    if sub_type is not None:
        if sub_type not in {"normal", "sticker"}:
            raise OutboundFormatError("invalid_input", "image.sub_type is invalid")
        data["sub_type"] = sub_type
    if summary is not None:
        if not isinstance(summary, str):
            raise OutboundFormatError("invalid_input", "image.summary is invalid")
        data["summary"] = summary
    return {"type": "image", "data": data}


def record_segment(uri: object) -> dict[str, Any]:
    """构造语音 segment。"""

    return {"type": "record", "data": {"uri": _required_text(uri, "record.uri")}}


def video_segment(uri: object, *, thumb_uri: object = None) -> dict[str, Any]:
    """构造视频 segment。"""

    data: dict[str, Any] = {"uri": _required_text(uri, "video.uri")}
    if thumb_uri is not None:
        data["thumb_uri"] = _required_text(thumb_uri, "video.thumb_uri")
    return {"type": "video", "data": data}


def forward_segment(
    messages: object,
    *,
    title: object = None,
    preview: object = None,
    summary: object = None,
    prompt: object = None,
) -> dict[str, Any]:
    """构造合并转发 segment。"""

    if isinstance(messages, (str, bytes, bytearray)) or not isinstance(messages, Sequence):
        raise OutboundFormatError("invalid_input", "forward.messages is invalid")
    normalized_messages = [_forward_message(message) for message in messages]
    data: dict[str, Any] = {"messages": normalized_messages}
    _optional_text_field(data, "title", title)
    if preview is not None:
        if (
            isinstance(preview, (str, bytes, bytearray))
            or not isinstance(preview, Sequence)
            or not all(isinstance(item, str) for item in preview)
            or not 1 <= len(preview) <= 4
        ):
            raise OutboundFormatError("invalid_input", "forward.preview is invalid")
        data["preview"] = list(preview)
    _optional_text_field(data, "summary", summary)
    _optional_text_field(data, "prompt", prompt)
    return {"type": "forward", "data": data}


def light_app_segment(json_payload: object) -> dict[str, Any]:
    """构造小程序 segment。"""

    return {
        "type": "light_app",
        "data": {"json_payload": _required_text(json_payload, "light_app.json_payload")},
    }


def format_message(
    content: object,
    *,
    reply_to: object = None,
) -> list[dict[str, Any]]:
    """把文本或 outgoing segment 序列格式化为可发送的 segment 列表。"""

    if isinstance(content, str):
        if not content.strip():
            raise OutboundFormatError("invalid_input", "message is blank")
        segments = [text_segment(content)]
    elif isinstance(content, Mapping):
        segments = [format_segment(content)]
    elif isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        segments = [format_segment(segment) for segment in content]
        if not segments:
            raise OutboundFormatError("invalid_input", "message is empty")
        if not _contains_visible_content(segments):
            raise OutboundFormatError("invalid_input", "message is blank")
    else:
        raise OutboundFormatError("invalid_input", "message must be text or segments")

    if reply_to is not None:
        segments.insert(0, reply_segment(reply_to))
    return segments


def format_segments(content: object, *, reply_to: object = None) -> list[dict[str, Any]]:
    """提供语义化别名，统一走 ``format_message``。"""

    return format_message(content, reply_to=reply_to)


def format_segment(segment: object) -> dict[str, Any]:
    """校验并复制一个已声明的 Milky outgoing segment。"""

    if not isinstance(segment, Mapping):
        raise OutboundFormatError("invalid_input", "message segment is not an object")
    _reject_unknown_fields(segment, {"type", "data"}, "segment")
    kind = segment.get("type")
    if not isinstance(kind, str) or kind not in _SEGMENT_TYPES:
        if kind == "file":
            raise OutboundFormatError("unsupported", "file requires file_upload")
        raise OutboundFormatError("unsupported", "outgoing segment is unsupported")
    data = segment.get("data")
    if not isinstance(data, Mapping):
        raise OutboundFormatError("invalid_input", "segment data is not an object")
    if kind == "text":
        _reject_unknown_fields(data, {"text"}, kind)
        return text_segment(data.get("text"))
    if kind == "mention":
        _reject_unknown_fields(data, {"user_id"}, kind)
        return mention_segment(data.get("user_id"))
    if kind == "mention_all":
        _require_no_data_fields(data, "mention_all")
        return mention_all_segment()
    if kind == "face":
        _reject_unknown_fields(data, {"face_id", "is_large"}, kind)
        return face_segment(data.get("face_id"), is_large=data.get("is_large"))
    if kind == "reply":
        _reject_unknown_fields(data, {"message_seq"}, kind)
        return reply_segment(data.get("message_seq"))
    if kind == "image":
        _reject_unknown_fields(data, {"uri", "sub_type", "summary"}, kind)
        return image_segment(
            data.get("uri"), sub_type=data.get("sub_type"), summary=data.get("summary")
        )
    if kind == "record":
        _reject_unknown_fields(data, {"uri"}, kind)
        return record_segment(data.get("uri"))
    if kind == "video":
        _reject_unknown_fields(data, {"uri", "thumb_uri"}, kind)
        return video_segment(data.get("uri"), thumb_uri=data.get("thumb_uri"))
    if kind == "forward":
        _reject_unknown_fields(data, {"messages", "title", "preview", "summary", "prompt"}, kind)
        return forward_segment(
            data.get("messages"),
            title=data.get("title"),
            preview=data.get("preview"),
            summary=data.get("summary"),
            prompt=data.get("prompt"),
        )
    if kind == "light_app":
        _reject_unknown_fields(data, {"json_payload"}, kind)
        return light_app_segment(data.get("json_payload"))
    raise AssertionError(f"unhandled outgoing segment: {kind}")


def _forward_message(value: object) -> dict[str, Any]:
    """校验一个 OutgoingForwardedMessage，并拒绝 file/未知 nested segment。"""

    if not isinstance(value, Mapping):
        raise OutboundFormatError("invalid_input", "forward message is not an object")
    segments = value.get("segments")
    if isinstance(segments, (str, bytes, bytearray)) or not isinstance(segments, Sequence):
        raise OutboundFormatError("invalid_input", "forward message segments are invalid")
    _reject_unknown_fields(value, {"user_id", "sender_name", "time", "segments"}, "forward")
    result: dict[str, Any] = {
        "user_id": _qq_id(value.get("user_id"), "forward.user_id"),
        "sender_name": _required_text(value.get("sender_name"), "forward.sender_name"),
        "segments": [format_segment(segment) for segment in segments],
    }
    if "time" in value:
        time_value = value["time"]
        result["time"] = (
            None
            if time_value is None
            else _integer(time_value, "forward.time", maximum=_MAX_SAFE_INTEGER)
        )
    return result


def _contains_visible_content(segments: Sequence[Mapping[str, Any]]) -> bool:
    """判断结构化消息是否至少包含非空白文本或非文本内容。"""

    return any(
        segment["type"] != "text" or bool(segment["data"]["text"].strip()) for segment in segments
    )


def _require_no_data_fields(data: Mapping[str, Any], kind: str) -> None:
    """确保无参数 segment 不携带未知字段。"""

    if data:
        raise OutboundFormatError("invalid_input", f"{kind}.data is invalid")


def _reject_unknown_fields(data: Mapping[str, Any], allowed: set[str], kind: str) -> None:
    """拒绝不在当前 Milky segment schema 中的字段。"""

    if set(data) - allowed:
        raise OutboundFormatError("invalid_input", f"{kind}.data is invalid")


def _optional_text_field(data: dict[str, Any], field: str, value: object) -> None:
    """添加可空文本字段，并屏蔽不可信值本身。"""

    if value is None:
        return
    data[field] = _required_text(value, f"forward.{field}")


def _required_text(value: object, field: str) -> str:
    """校验非空文本，但不在错误中回显具体值。"""

    if not isinstance(value, str) or not value.strip():
        raise OutboundFormatError("invalid_input", f"{field} is invalid")
    return value


def _qq_id(value: object, field: str) -> int:
    """校验 OpenAPI 要求的 QQ ID 范围。"""

    return _integer(value, field, minimum=_MIN_QQ_ID, maximum=_MAX_QQ_ID)


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = _MAX_SAFE_INTEGER,
) -> int:
    """校验非布尔整数或十进制字符串的安全范围。"""

    if isinstance(value, bool):
        raise OutboundFormatError("invalid_input", f"{field} is invalid")
    if isinstance(value, int) and minimum <= value <= maximum:
        return value
    if isinstance(value, str) and value.isdecimal() and (value == "0" or not value.startswith("0")):
        converted = int(value)
        if minimum <= converted <= maximum:
            return converted
    raise OutboundFormatError("invalid_input", f"{field} is invalid")


__all__ = [
    "OutboundFormatError",
    "face_segment",
    "format_message",
    "format_segment",
    "format_segments",
    "forward_segment",
    "image_segment",
    "light_app_segment",
    "mention_all_segment",
    "mention_segment",
    "record_segment",
    "reply_segment",
    "text_segment",
    "video_segment",
]
