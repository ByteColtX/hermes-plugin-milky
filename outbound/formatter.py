"""将 Hermes 出站内容转换为 Milky v1.3 outgoing segments。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from html import unescape
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
_CQ_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_CQ_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CQ_TYPES = (
    "text",
    "face",
    "image",
    "record",
    "video",
    "at",
    "rps",
    "dice",
    "shake",
    "poke",
    "share",
    "contact",
    "location",
    "music",
    "reply",
    "forward",
    "node",
    "json",
    "mface",
    "file",
    "markdown",
    "lightapp",
    "anonymous",
    "redbag",
    "gift",
    "cardimage",
    "tts",
    "xml",
)
CQ_TYPES = frozenset(_CQ_TYPES)


class OutboundFormatError(ValueError):
    """表示出站内容不符合 Milky outgoing segment 契约。"""

    def __init__(self, classification: str, reason: str) -> None:
        self.classification = classification
        self.reason = reason
        super().__init__(f"{classification}: {reason}")


class _CqConversionError(ValueError):
    """表示单个 CQ 片段不能安全转换。"""


class _CqCode:
    """保存已经通过边界解析的 CQ 片段。"""

    __slots__ = ("name", "parameters", "raw")

    def __init__(self, name: str, parameters: dict[str, str], raw: str) -> None:
        self.name = name
        self.parameters = parameters
        self.raw = raw


def parse_cq_code(raw: object) -> tuple[str, dict[str, str]] | None:
    """解析一个完整 CQ 片段，并解码参数而不改变 fallback 原文。"""

    if not isinstance(raw, str) or not raw.startswith("[CQ:") or not raw.endswith("]"):
        return None
    body = raw[4:-1]
    if not body:
        return None
    name, separator, parameter_text = body.partition(",")
    if _CQ_NAME_PATTERN.fullmatch(name) is None:
        return None
    if not separator:
        return name.lower(), {}
    if not parameter_text:
        return None

    parameters: dict[str, str] = {}
    for field in parameter_text.split(","):
        key, equals, value = field.partition("=")
        if not equals or _CQ_KEY_PATTERN.fullmatch(key) is None or key in parameters:
            return None
        if "[" in value or "]" in value:
            return None
        parameters[key] = _decode_cq_value(value)
    return name.lower(), parameters


def format_cq_message(content: str) -> list[dict[str, Any]]:
    """把 CQ-compatible 文本逐片段转换为 Milky segments。"""

    if not isinstance(content, str):
        raise OutboundFormatError("invalid_input", "message must be text")
    segments: list[dict[str, Any]] = []
    position = 0
    while position < len(content):
        start = content.find("[CQ:", position)
        if start < 0:
            _append_text(segments, content[position:])
            break
        _append_text(segments, content[position:start])
        end = content.find("]", start + 4)
        if end < 0:
            _append_text(segments, content[start:])
            break
        raw = content[start : end + 1]
        parsed = parse_cq_code(raw)
        if parsed is None:
            _append_text(segments, raw)
        else:
            name, parameters = parsed
            converted = _convert_cq_code(_CqCode(name, parameters, raw))
            segments.append(converted)
        position = end + 1
    return segments


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


def _convert_cq_code(code: _CqCode) -> dict[str, Any]:
    """转换单个 CQ 片段，失败时只回退当前原文。"""

    converter = CQ_TYPE_REGISTRY.get(code.name)
    if converter is None:
        return text_segment(code.raw)
    try:
        converted = converter(code.parameters)
        if converted is None:
            return text_segment(code.raw)
        return format_segment(converted)
    except Exception:  # noqa: BLE001 - 单片段失败必须安全 fallback
        return text_segment(code.raw)


def _append_text(segments: list[dict[str, Any]], value: str) -> None:
    """追加非空文本片段，并保留其原始空白。"""

    if value:
        segments.append(text_segment(value))


def _decode_cq_value(value: str) -> str:
    """解码 NapCat CQ 参数中的实体，转换失败仍保留原始控制码。"""

    return unescape(value)


def _cq_text(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ text。"""

    _require_cq_fields(parameters, {"text"}, {"text"})
    if not parameters["text"]:
        raise _CqConversionError("text is empty")
    return text_segment(parameters["text"])


def _cq_face(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ face。"""

    _require_cq_fields(parameters, {"id", "large"}, {"id"})
    face_id = _cq_safe_integer(parameters["id"], maximum=_MAX_SAFE_INTEGER)
    large = None
    if "large" in parameters:
        if parameters["large"] not in {"0", "1"}:
            raise _CqConversionError("large is invalid")
        large = parameters["large"] == "1"
    return face_segment(str(face_id), is_large=large)


def _cq_image(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ image；只接受 Milky 已确认的图片子类型。"""

    _require_cq_fields(parameters, {"file", "type", "summary"}, {"file"})
    sub_type = parameters.get("type")
    if sub_type is not None and sub_type not in {"normal", "sticker"}:
        raise _CqConversionError("image type is unsupported")
    return image_segment(
        parameters["file"],
        sub_type=sub_type,
        summary=parameters.get("summary"),
    )


def _cq_record(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ record。"""

    _require_cq_fields(parameters, {"file"}, {"file"})
    return record_segment(parameters["file"])


def _cq_video(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ video。"""

    _require_cq_fields(parameters, {"file"}, {"file"})
    return video_segment(parameters["file"])


def _cq_at(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ at；all 保持 fallback，避免猜测 Milky 等价语义。"""

    _require_cq_fields(parameters, {"qq", "text"}, {"qq"})
    if parameters["qq"] == "all":
        raise _CqConversionError("all mention has no confirmed mapping")
    return mention_segment(_cq_safe_integer(parameters["qq"], maximum=_MAX_QQ_ID))


def _cq_reply(parameters: Mapping[str, str]) -> dict[str, Any]:
    """转换 CQ reply。"""

    _require_cq_fields(parameters, {"id", "text", "seq"}, {"id"})
    return reply_segment(_cq_safe_integer(parameters["id"], maximum=_MAX_SAFE_INTEGER))


def _require_cq_fields(
    parameters: Mapping[str, str], allowed: set[str], required: set[str]
) -> None:
    """校验 CQ 转换器支持的字段集合。"""

    if set(parameters) - allowed or required - set(parameters):
        raise _CqConversionError("CQ fields are invalid")
    for field in required:
        if not parameters[field].strip():
            raise _CqConversionError("CQ field is empty")


def _cq_safe_integer(value: object, *, maximum: int) -> int:
    """校验 CQ 中的无前导零十进制 ID。"""

    if not isinstance(value, str) or (value != "0" and value.startswith("0")):
        raise _CqConversionError("CQ integer is invalid")
    if not value.isdecimal():
        raise _CqConversionError("CQ integer is invalid")
    converted = int(value)
    if converted > maximum:
        raise _CqConversionError("CQ integer is out of range")
    return converted


CQ_TYPE_REGISTRY: dict[str, Any] = {
    "text": _cq_text,
    "face": _cq_face,
    "image": _cq_image,
    "record": _cq_record,
    "video": _cq_video,
    "at": _cq_at,
    "rps": None,
    "dice": None,
    "shake": None,
    "poke": None,
    "share": None,
    "contact": None,
    "location": None,
    "music": None,
    "reply": _cq_reply,
    "forward": None,
    "node": None,
    "json": None,
    "mface": None,
    "file": None,
    "markdown": None,
    "lightapp": None,
    "anonymous": None,
    "redbag": None,
    "gift": None,
    "cardimage": None,
    "tts": None,
    "xml": None,
}


def format_message(
    content: object,
    *,
    reply_to: object = None,
) -> list[dict[str, Any]]:
    """把文本或 outgoing segment 序列格式化为可发送的 segment 列表。"""

    del reply_to
    if isinstance(content, str):
        if not content.strip():
            raise OutboundFormatError("invalid_input", "message is blank")
        segments = format_cq_message(content)
    elif isinstance(content, Mapping):
        segments = _format_message_segment(content)
    elif isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        segments = []
        for segment in content:
            segments.extend(_format_message_segment(segment))
        if not segments:
            raise OutboundFormatError("invalid_input", "message is empty")
    else:
        raise OutboundFormatError("invalid_input", "message must be text or segments")

    if not segments or not _contains_visible_content(segments):
        raise OutboundFormatError("invalid_input", "message is blank")

    return segments


def _format_message_segment(segment: object) -> list[dict[str, Any]]:
    """格式化结构化消息，并展开其中的 CQ-compatible text。"""

    formatted = format_segment(segment)
    if formatted["type"] != "text":
        return [formatted]
    return format_cq_message(formatted["data"]["text"])


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
    "CQ_TYPES",
    "CQ_TYPE_REGISTRY",
    "OutboundFormatError",
    "face_segment",
    "format_cq_message",
    "format_message",
    "format_segment",
    "format_segments",
    "forward_segment",
    "image_segment",
    "light_app_segment",
    "mention_all_segment",
    "mention_segment",
    "parse_cq_code",
    "record_segment",
    "reply_segment",
    "text_segment",
    "video_segment",
]
