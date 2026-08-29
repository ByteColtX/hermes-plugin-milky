"""Milky v1.3 协议 DTO 的无网络容错解析器。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeVar

from .models import (
    Event,
    FaceSegment,
    FileSegment,
    ForwardSegment,
    FriendEntity,
    GroupEntity,
    GroupList,
    GroupMemberEntity,
    GroupMemberInfo,
    ImageSegment,
    IncomingForwardedMessage,
    IncomingMessage,
    LightAppSegment,
    LoginInfo,
    MarkdownSegment,
    MarketFaceSegment,
    MentionAllSegment,
    MentionSegment,
    MilkyEnvelope,
    RecordSegment,
    ReplySegment,
    SegmentValue,
    TextSegment,
    UnknownSegment,
    VideoSegment,
    XmlSegment,
)

T = TypeVar("T")
_KNOWN_SEGMENTS = {
    "text",
    "mention",
    "mention_all",
    "face",
    "reply",
    "image",
    "record",
    "video",
    "file",
    "forward",
    "market_face",
    "light_app",
    "xml",
    "markdown",
}
_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "token",
}
_MIN_QQ_ID = 10001
_MAX_QQ_ID = 4294967295
_MAX_SAFE_INTEGER = 9007199254740991


class ParseError(ValueError):
    """表示协议数据无法安全归类或无法满足 DTO 最小结构。"""

    def __init__(self, classification: str, reason: str) -> None:
        super().__init__(f"{classification}: {reason}")
        self.classification = classification
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ParseResult[T]:
    """表示成功解析、临时忽略或可观察的解析结果。"""

    classification: str
    value: T | None
    reason: str | None = None


def parse_action_response(payload: object, action: str) -> ParseResult[Any]:
    """解析一个 Action 响应，并按 Action 校验最小 data 结构。"""

    envelope = _parse_envelope(payload)
    if envelope.status != "ok" or envelope.retcode != 0:
        raise ParseError("protocol_rejected", "Milky Action envelope rejected")
    if action == "get_login_info":
        return ParseResult("accepted", _parse_login_info(envelope.data))
    if action == "get_group_list":
        return ParseResult("accepted", _parse_group_list(envelope.data))
    if action == "get_group_member_info":
        return ParseResult("accepted", _parse_group_member_info(envelope.data))
    return ParseResult("accepted", envelope)


def parse_envelope(payload: object) -> MilkyEnvelope:
    """解析通用 Milky envelope；业务 data 由调用方继续校验。"""

    return _parse_envelope(payload)


def parse_event(payload: object, outer_event_type: str | None = None) -> Event:
    """解析事件外层，允许 SSE 的 ``milky_event`` 作为包装名传入。"""

    source = _mapping(payload, "event")
    event_type = _text(source, "event_type")
    event_time = _non_negative_int(source.get("time"), "time")
    self_id = _non_negative_int(source.get("self_id"), "self_id")
    data = _mapping(source.get("data"), "data")
    if outer_event_type is not None and not isinstance(outer_event_type, str):
        raise ParseError("malformed", "outer event type must be text")
    known = {"event_type", "time", "self_id", "data"}
    return Event(
        event_type=event_type,
        time=event_time,
        self_id=self_id,
        data=_freeze_mapping(data),
        raw=_freeze_mapping(source),
        extras=_freeze_mapping(_extras(source, known)),
        outer_event_type=outer_event_type,
    )


def parse_incoming_message(event: Event | object) -> ParseResult[IncomingMessage]:
    """解析 ``message_receive``，并在协议边界忽略 temp 消息。"""

    parsed_event = event if isinstance(event, Event) else parse_event(event)
    if parsed_event.event_type != "message_receive":
        raise ParseError("observe_only", "event is not message_receive")
    data = parsed_event.data
    scene = _text(data, "message_scene")
    if scene not in {"friend", "group", "temp"}:
        raise ParseError("malformed", "message_scene is unsupported")
    if scene == "temp":
        return ParseResult("ignored_temp", None, "temporary message scene")

    value = _parse_incoming_message_data(
        data,
        self_id=parsed_event.self_id,
        require_scene_entities=False,
    )
    reason = "no_stable_message_id" if value.message_seq is None else None
    return ParseResult("accepted", value, reason)


def parse_incoming_message_data(payload: object, *, self_id: int | None = None) -> IncomingMessage:
    """解析 Action 返回的完整 ``data.message``。"""

    source = _mapping(payload, "message")
    return _parse_incoming_message_data(
        source,
        self_id=self_id,
        require_scene_entities=True,
    )


def _parse_incoming_message_data(
    data: Mapping[str, Any], *, self_id: int | None, require_scene_entities: bool
) -> IncomingMessage:
    """解析消息对象并按需要校验场景实体。"""

    scene = _text(data, "message_scene")
    if scene not in {"friend", "group", "temp"}:
        raise ParseError("malformed", "message_scene is unsupported")

    peer_id = _qq_id(data.get("peer_id"), "peer_id")
    sender_id = _qq_id(data.get("sender_id"), "sender_id")
    message_seq = _optional_present_int(data, "message_seq")
    if require_scene_entities and message_seq is None:
        raise ParseError("malformed", "message_seq is missing")
    message_time = _non_negative_int(data.get("time"), "data.time")
    segments = _parse_segments(data.get("segments"), "segments")

    friend = _optional_entity(data, "friend", _parse_friend)
    group = _optional_entity(data, "group", _parse_group)
    group_member = _optional_entity(data, "group_member", _parse_group_member)
    if scene == "friend":
        if require_scene_entities and friend is None:
            raise ParseError("malformed", "friend is missing")
        if "friend" in data and friend is None:
            raise ParseError("malformed", "friend must be an object")
        if friend is not None and friend.user_id != peer_id:
            raise ParseError("malformed", "friend.user_id disagrees with peer_id")
        if sender_id != peer_id:
            raise ParseError("malformed", "friend sender_id disagrees with peer_id")
    if scene == "group":
        if require_scene_entities and group is None:
            raise ParseError("malformed", "group is missing")
        if require_scene_entities and group_member is None:
            raise ParseError("malformed", "group_member is missing")
        if "group" in data and group is None:
            raise ParseError("malformed", "group must be an object")
        if "group_member" in data and group_member is None:
            raise ParseError("malformed", "group_member must be an object")
        if group is not None and group.group_id != peer_id:
            raise ParseError("malformed", "group.group_id disagrees with peer_id")
        if group_member is not None:
            if group_member.group_id != peer_id:
                raise ParseError("malformed", "group_member.group_id disagrees with peer_id")
            if group_member.user_id != sender_id:
                raise ParseError("malformed", "group_member.user_id disagrees with sender_id")
    if scene == "temp" and "group" in data and data["group"] is not None:
        raise ParseError("malformed", "temp group must be null")

    known = {
        "message_scene",
        "peer_id",
        "message_seq",
        "sender_id",
        "time",
        "segments",
        "friend",
        "group",
        "group_member",
    }
    value = IncomingMessage(
        message_scene=scene,
        peer_id=peer_id,
        message_seq=message_seq,
        sender_id=sender_id,
        time=message_time,
        segments=segments,
        friend=friend,
        group=group,
        group_member=group_member,
        self_id=self_id,
        raw=_freeze_mapping(data),
        extras=_freeze_mapping(_extras(data, known)),
    )
    return value


def parse_message(payload: object) -> ParseResult[IncomingMessage]:
    """兼容调用方的消息解析命名。"""

    return parse_incoming_message(parse_event(payload))


def parse_forwarded_message(payload: object) -> IncomingForwardedMessage:
    """解析 ``get_forwarded_messages`` 返回的一条消息。"""

    source = _mapping(payload, "forwarded message")
    value = IncomingForwardedMessage(
        message_seq=_non_negative_int(source.get("message_seq"), "forwarded.message_seq"),
        sender_name=_text(source, "sender_name"),
        avatar_url=_text(source, "avatar_url"),
        time=_non_negative_int(source.get("time"), "forwarded.time"),
        segments=_parse_segments(source.get("segments"), "forwarded.segments"),
        extras=_freeze_mapping(
            _extras(source, {"message_seq", "sender_name", "avatar_url", "time", "segments"})
        ),
    )
    return value


def _parse_envelope(payload: object) -> MilkyEnvelope:
    source = _mapping(payload, "envelope")
    status = _text(source, "status")
    retcode = _non_negative_int(source.get("retcode"), "retcode")
    data_value = source.get("data")
    if data_value is None:
        data = None
    else:
        data = _freeze_mapping(_mapping(data_value, "data"))
    known = {"status", "retcode", "data", "message", "wording"}
    return MilkyEnvelope(
        status=status,
        retcode=retcode,
        data=data,
        message=_optional_text(source, "message"),
        wording=_optional_text(source, "wording"),
        extras=_freeze_mapping(_extras(source, known)),
    )


def _parse_login_info(data: Mapping[str, Any] | None) -> LoginInfo:
    source = _required_data(data, "login data")
    return LoginInfo(
        uin=_qq_id(source.get("uin"), "data.uin"),
        nickname=_text(source, "nickname"),
        extras=_freeze_mapping(_extras(source, {"uin", "nickname"})),
    )


def _parse_group_list(data: Mapping[str, Any] | None) -> GroupList:
    source = _required_data(data, "group list data")
    groups = source.get("groups")
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        raise ParseError("malformed", "data.groups must be an array")
    return GroupList(
        groups=tuple(_parse_group(item) for item in groups),
        extras=_freeze_mapping(_extras(source, {"groups"})),
    )


def _parse_group_member_info(data: Mapping[str, Any] | None) -> GroupMemberInfo:
    source = _required_data(data, "group member data")
    return GroupMemberInfo(
        member=_parse_group_member(source.get("member")),
        extras=_freeze_mapping(_extras(source, {"member"})),
    )


def _parse_segments(value: object, field_name: str) -> tuple[SegmentValue, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ParseError("malformed", f"{field_name} must be an array")
    return tuple(_parse_segment(item) for item in value)


def _parse_segment(value: object) -> SegmentValue:
    source = _mapping(value, "segment")
    kind = _text(source, "type")
    raw = _freeze_mapping(source)
    if kind not in _KNOWN_SEGMENTS:
        return UnknownSegment(
            kind=kind,
            raw=raw,
            data=_freeze_value(source.get("data")),
        )
    data = _mapping(source.get("data"), f"{kind}.data")
    extras = _freeze_mapping(_extras(data, _segment_fields(kind)))

    if kind == "text":
        return TextSegment(kind=kind, raw=raw, extras=extras, text=_text(data, "text"))
    if kind == "mention":
        return MentionSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            user_id=_qq_id(data.get("user_id"), "mention.user_id"),
            name=_optional_text(data, "name"),
        )
    if kind == "mention_all":
        return MentionAllSegment(kind=kind, raw=raw, extras=extras)
    if kind == "face":
        return FaceSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            face_id=_optional_text(data, "face_id"),
            is_large=_optional_bool(data, "is_large"),
        )
    if kind == "reply":
        return _parse_reply(kind, raw, data, extras)
    if kind == "image":
        return ImageSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            resource_id=_optional_text(data, "resource_id"),
            temp_url=_optional_text(data, "temp_url"),
            width=_optional_present_non_negative_int(data, "width"),
            height=_optional_present_non_negative_int(data, "height"),
            summary=_optional_text(data, "summary"),
            sub_type=_optional_text(data, "sub_type"),
        )
    if kind == "record":
        return RecordSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            resource_id=_optional_text(data, "resource_id"),
            temp_url=_optional_text(data, "temp_url"),
            duration=_optional_present_non_negative_int(data, "duration"),
        )
    if kind == "video":
        return VideoSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            resource_id=_optional_text(data, "resource_id"),
            temp_url=_optional_text(data, "temp_url"),
            width=_optional_present_non_negative_int(data, "width"),
            height=_optional_present_non_negative_int(data, "height"),
            duration=_optional_present_non_negative_int(data, "duration"),
        )
    if kind == "file":
        return FileSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            file_id=_optional_text(data, "file_id"),
            file_name=_optional_text(data, "file_name"),
            file_size=_optional_present_non_negative_int(data, "file_size"),
            file_hash=_optional_text(data, "file_hash"),
        )
    if kind == "forward":
        preview = data.get("preview", [])
        if (
            not isinstance(preview, Sequence)
            or isinstance(preview, (str, bytes))
            or not all(isinstance(item, str) for item in preview)
        ):
            raise ParseError("malformed", "forward.preview must be an array of text")
        return ForwardSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            forward_id=_optional_text(data, "forward_id"),
            title=_optional_text(data, "title"),
            preview=tuple(preview),
            summary=_optional_text(data, "summary"),
        )
    if kind == "market_face":
        return MarketFaceSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            emoji_package_id=_optional_present_non_negative_int(data, "emoji_package_id"),
            emoji_id=_optional_text(data, "emoji_id"),
            key=_optional_text(data, "key"),
            summary=_optional_text(data, "summary"),
            url=_optional_text(data, "url"),
        )
    if kind == "light_app":
        return LightAppSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            app_name=_optional_text(data, "app_name"),
            json_payload=_optional_text(data, "json_payload"),
        )
    if kind == "xml":
        return XmlSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            service_id=_optional_present_non_negative_int(data, "service_id"),
            xml_payload=_optional_text(data, "xml_payload"),
        )
    if kind == "markdown":
        return MarkdownSegment(
            kind=kind,
            raw=raw,
            extras=extras,
            content=_text(data, "content"),
        )
    raise AssertionError(f"unhandled known segment: {kind}")


def _parse_reply(
    kind: str, raw: Mapping[str, Any], data: Mapping[str, Any], extras: Mapping[str, Any]
) -> ReplySegment:
    return ReplySegment(
        kind=kind,
        raw=raw,
        extras=extras,
        message_seq=_non_negative_int(data.get("message_seq"), "reply.message_seq"),
        sender_id=_optional_present_qq_id(data, "sender_id"),
        sender_name=_optional_text(data, "sender_name"),
        time=_optional_present_non_negative_int(data, "time"),
        segments=(
            _parse_segments(data["segments"], "reply.segments") if "segments" in data else ()
        ),
    )


def _parse_friend(value: object) -> FriendEntity:
    source = _mapping(value, "friend")
    return FriendEntity(
        user_id=_qq_id(source.get("user_id"), "friend.user_id"),
        nickname=_text(source, "nickname"),
        sex=_optional_text(source, "sex"),
        qid=_optional_text(source, "qid"),
        remark=_optional_text(source, "remark"),
        category=_optional_frozen_mapping(source, "category"),
        extras=_freeze_mapping(
            _extras(source, {"user_id", "nickname", "sex", "qid", "remark", "category"})
        ),
    )


def _parse_group(value: object) -> GroupEntity:
    source = _mapping(value, "group")
    return GroupEntity(
        group_id=_qq_id(source.get("group_id"), "group.group_id"),
        group_name=_optional_text(source, "group_name"),
        member_count=_optional_present_non_negative_int(source, "member_count"),
        max_member_count=_optional_present_non_negative_int(source, "max_member_count"),
        remark=_optional_text(source, "remark"),
        created_time=_optional_present_non_negative_int(source, "created_time"),
        description=_optional_text(source, "description"),
        question=_optional_text(source, "question"),
        announcement=_optional_text(source, "announcement"),
        extras=_freeze_mapping(
            _extras(
                source,
                {
                    "group_id",
                    "group_name",
                    "member_count",
                    "max_member_count",
                    "remark",
                    "created_time",
                    "description",
                    "question",
                    "announcement",
                },
            )
        ),
    )


def _parse_group_member(value: object) -> GroupMemberEntity:
    source = _mapping(value, "group_member")
    return GroupMemberEntity(
        user_id=_qq_id(source.get("user_id"), "group_member.user_id"),
        group_id=_qq_id(source.get("group_id"), "group_member.group_id"),
        nickname=_text(source, "nickname"),
        card=_optional_text(source, "card"),
        sex=_optional_text(source, "sex"),
        title=_optional_text(source, "title"),
        level=_optional_present_non_negative_int(source, "level"),
        role=_optional_text(source, "role"),
        join_time=_optional_present_non_negative_int(source, "join_time"),
        last_sent_time=_optional_present_non_negative_int(source, "last_sent_time"),
        shut_up_end_time=_optional_present_nullable_non_negative_int(source, "shut_up_end_time"),
        extras=_freeze_mapping(
            _extras(
                source,
                {
                    "user_id",
                    "group_id",
                    "nickname",
                    "card",
                    "sex",
                    "title",
                    "level",
                    "role",
                    "join_time",
                    "last_sent_time",
                    "shut_up_end_time",
                },
            )
        ),
    )


def _segment_fields(kind: str) -> set[str]:
    fields = {
        "text": {"text"},
        "mention": {"user_id", "name"},
        "mention_all": set(),
        "face": {"face_id", "is_large"},
        "reply": {"message_seq", "sender_id", "sender_name", "time", "segments"},
        "image": {"resource_id", "temp_url", "width", "height", "summary", "sub_type"},
        "record": {"resource_id", "temp_url", "duration"},
        "video": {"resource_id", "temp_url", "width", "height", "duration"},
        "file": {"file_id", "file_name", "file_size", "file_hash"},
        "forward": {"forward_id", "title", "preview", "summary"},
        "market_face": {"emoji_package_id", "emoji_id", "key", "summary", "url"},
        "light_app": {"app_name", "json_payload"},
        "xml": {"service_id", "xml_payload"},
        "markdown": {"content"},
    }
    return fields.get(kind, set())


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ParseError("malformed", f"{field_name} must be an object")
    return value


def _required_data(data: Mapping[str, Any] | None, field_name: str) -> Mapping[str, Any]:
    if data is None:
        raise ParseError("malformed", f"{field_name} is missing")
    return data


def _text(source: Mapping[str, Any], field_name: str) -> str:
    value = source.get(field_name)
    if not isinstance(value, str):
        raise ParseError("malformed", f"{field_name} must be text")
    return value


def _optional_text(source: Mapping[str, Any], field_name: str) -> str | None:
    if field_name not in source or source[field_name] is None:
        return None
    return _text(source, field_name)


def _non_negative_int(value: object, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _MAX_SAFE_INTEGER
    ):
        raise ParseError("malformed", f"{field_name} must be an integer in protocol range")
    return value


def _qq_id(value: object, field_name: str) -> int:
    """校验 Milky QQ ID 的 OpenAPI 范围。"""

    result = _non_negative_int(value, field_name)
    if not _MIN_QQ_ID <= result <= _MAX_QQ_ID:
        raise ParseError("malformed", f"{field_name} is outside QQ ID range")
    return result


def _optional_present_int(source: Mapping[str, Any], field_name: str) -> int | None:
    if field_name not in source:
        return None
    return _non_negative_int(source[field_name], field_name)


def _optional_present_non_negative_int(source: Mapping[str, Any], field_name: str) -> int | None:
    return _optional_present_int(source, field_name)


def _optional_present_qq_id(source: Mapping[str, Any], field_name: str) -> int | None:
    if field_name not in source or source[field_name] is None:
        return None
    return _qq_id(source[field_name], field_name)


def _optional_present_nullable_non_negative_int(
    source: Mapping[str, Any], field_name: str
) -> int | None:
    if field_name not in source or source[field_name] is None:
        return None
    return _non_negative_int(source[field_name], field_name)


def _optional_bool(source: Mapping[str, Any], field_name: str) -> bool | None:
    if field_name not in source or source[field_name] is None:
        return None
    value = source[field_name]
    if not isinstance(value, bool):
        raise ParseError("malformed", f"{field_name} must be boolean")
    return value


def _optional_entity[T](source: Mapping[str, Any], field_name: str, parser: Any) -> T | None:
    if field_name not in source or source[field_name] is None:
        return None
    return parser(source[field_name])


def _optional_frozen_mapping(
    source: Mapping[str, Any], field_name: str
) -> Mapping[str, Any] | None:
    if field_name not in source or source[field_name] is None:
        return None
    return _freeze_mapping(_mapping(source[field_name], field_name))


def _extras(source: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key not in known}


def _freeze_mapping(source: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            str(key): _freeze_value(value)
            for key, value in source.items()
            if str(key).casefold() not in _SENSITIVE_KEYS
        }
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value
