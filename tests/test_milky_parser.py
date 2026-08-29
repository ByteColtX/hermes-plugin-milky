"""验证 T04 Milky DTO 和 tolerant parser 契约。"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from milky.models import (
    FaceSegment,
    FileSegment,
    ForwardSegment,
    ImageSegment,
    IncomingMessage,
    LightAppSegment,
    MarkdownSegment,
    MarketFaceSegment,
    MentionAllSegment,
    MentionSegment,
    RecordSegment,
    ReplySegment,
    TextSegment,
    UnknownSegment,
    VideoSegment,
    XmlSegment,
)
from milky.parser import (
    ParseError,
    parse_action_response,
    parse_event,
    parse_forwarded_message,
    parse_incoming_message,
    parse_incoming_message_data,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_action_responses_use_milky_data_layers() -> None:
    """Action DTO 应读取 uin、groups 和 member 的真实 data 层级。"""

    login = parse_action_response(load_fixture("actions/get_login_info.ok.json"), "get_login_info")
    groups = parse_action_response(load_fixture("actions/get_group_list.ok.json"), "get_group_list")
    member = parse_action_response(
        load_fixture("actions/get_group_member_info.ok_omits_shut_up_end_time.json"),
        "get_group_member_info",
    )

    assert login.classification == "accepted"
    assert login.value.uin == 900000001
    assert groups.value.groups[0].group_id == 700000001
    assert member.value.member.group_id == 700000001
    assert member.value.member.shut_up_end_time is None
    assert "fixture_extension" in login.value.extras


@pytest.mark.parametrize(
    ("path", "action", "classification"),
    [
        ("actions/get_login_info.malformed_missing_uin.json", "get_login_info", "malformed"),
        ("actions/get_group_list.malformed_groups_type.json", "get_group_list", "malformed"),
        (
            "actions/get_group_member_info.protocol_rejected.json",
            "get_group_member_info",
            "protocol_rejected",
        ),
    ],
)
def test_action_errors_are_classified_without_exposing_payload(
    path: str, action: str, classification: str
) -> None:
    """Action 缺字段和协议拒绝应保持不同分类。"""

    with pytest.raises(ParseError) as error_info:
        parse_action_response(load_fixture(path), action)

    assert error_info.value.classification == classification
    assert "请求被协议拒绝" not in str(error_info.value)


def test_all_known_segments_are_typed_and_unknown_is_raw_only() -> None:
    """所有已知 segment 应保留类型语义，未知扩展不得伪装成文本。"""

    event = parse_event(load_fixture("events/message_receive.group.all_segments.json"))
    result = parse_incoming_message(event)
    assert result.classification == "accepted"
    assert isinstance(result.value, IncomingMessage)

    segments = result.value.segments
    assert isinstance(segments[0], TextSegment)
    assert isinstance(segments[1], MentionSegment)
    assert isinstance(segments[2], MentionAllSegment)
    assert isinstance(segments[4], ReplySegment)
    assert isinstance(segments[5], ImageSegment)
    assert isinstance(segments[3], FaceSegment)
    assert isinstance(segments[6], RecordSegment)
    assert isinstance(segments[7], VideoSegment)
    assert isinstance(segments[8], FileSegment)
    assert isinstance(segments[9], ForwardSegment)
    assert isinstance(segments[10], MarketFaceSegment)
    assert isinstance(segments[11], LightAppSegment)
    assert isinstance(segments[12], XmlSegment)
    assert isinstance(segments[13], MarkdownSegment)
    assert segments[5].resource_id == "fixture-image-resource"
    assert segments[8].file_id == "fixture-file-id"
    assert result.value.segments[4].segments[0].text == "被引用的中性内容"
    assert result.value.segments[9].forward_id == "fixture-forward-id"

    unknown_event = parse_event(load_fixture("events/message_receive.group.unknown_extension.json"))
    unknown = parse_incoming_message(unknown_event).value.segments[1]
    assert isinstance(unknown, UnknownSegment)
    assert unknown.data["opaque"] == "仅供诊断"
    assert not hasattr(unknown, "text")


def test_friend_group_and_temp_have_explicit_boundary() -> None:
    """friend/group 应可解析，temp 只返回 ignored_temp。"""

    friend = parse_incoming_message(parse_event(load_fixture("events/message_receive.friend.json")))
    group = parse_incoming_message(
        parse_event(load_fixture("events/message_receive.group.all_segments.json"))
    )
    temporary = parse_incoming_message(
        parse_event(load_fixture("events/message_receive.temp.json"))
    )

    assert friend.value.message_scene == "friend"
    assert group.value.message_scene == "group"
    assert friend.value.friend.nickname == "合成好友"
    assert group.value.group_member.card == "合成名片"
    assert temporary.classification == "ignored_temp"
    assert temporary.value is None


def test_all_event_fixtures_have_deterministic_boundary_classification() -> None:
    """T03 的全部事件 fixture 应能确定归为消息、临时或观察路径。"""

    for path in sorted((FIXTURE_ROOT / "events").glob("*.json")):
        event = parse_event(load_fixture(path.relative_to(FIXTURE_ROOT).as_posix()))
        if event.event_type != "message_receive":
            assert event.classification == "observe_only"
            continue
        try:
            result = parse_incoming_message(event)
        except ParseError as error:
            assert error.classification == "malformed"
        else:
            assert result.classification in {"accepted", "ignored_temp"}


def test_forwarded_message_dto_matches_milky_action_shape() -> None:
    """get_forwarded_messages 的消息项应保留真实字段和 segment 顺序。"""

    payload = load_fixture("actions/get_forwarded_messages.ok.json")
    forwarded = parse_forwarded_message(payload["data"]["messages"][0])

    assert forwarded.message_seq == 1004
    assert forwarded.sender_name == "合成转发者"
    assert forwarded.avatar_url == ""
    assert forwarded.segments[0].type == "text"


def test_get_message_output_matches_full_incoming_message_shape() -> None:
    """get_message 的 data.message 应按完整 IncomingMessage 解析。"""

    payload = load_fixture("actions/get_message.ok.json")
    message = parse_incoming_message_data(payload["data"]["message"])

    assert message.message_scene == "friend"
    assert message.peer_id == 800000001
    assert message.message_seq == 1005
    assert message.friend.nickname == "合成好友"
    assert message.segments[0].type == "text"


def test_get_message_output_does_not_accept_event_or_inline_reply_shape() -> None:
    """get_message 解析不得把缺场景或 inline reply 当成完整消息。"""

    payload = load_fixture("actions/get_message.ok.json")
    del payload["data"]["message"]["message_scene"]
    with pytest.raises(ParseError, match="malformed"):
        parse_incoming_message_data(payload["data"]["message"])

    inline_reply = load_fixture("events/message_receive.group.all_segments.json")
    reply_data = inline_reply["data"]["segments"][4]["data"]
    with pytest.raises(ParseError, match="malformed"):
        parse_forwarded_message(reply_data)


def test_reply_with_only_target_id_remains_unexpanded() -> None:
    """只有目标序号的 reply 应保留引用，不伪造原文和作者。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"].append({"type": "reply", "data": {"message_seq": 1000}})

    reply = parse_incoming_message(parse_event(payload)).value.segments[1]

    assert isinstance(reply, ReplySegment)
    assert reply.message_seq == 1000
    assert reply.sender_id is None
    assert reply.segments == ()


def test_missing_message_seq_is_explicitly_non_stable() -> None:
    """缺失 message_seq 时 parser 保留单帧，不伪造消息 ID。"""

    payload = load_fixture("events/message_receive.friend.json")
    del payload["data"]["message_seq"]

    result = parse_incoming_message(parse_event(payload))

    assert result.value.message_seq is None
    assert result.reason == "no_stable_message_id"


def test_parser_does_not_perform_network_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """解析协议 fixture 不得触发 socket 等网络副作用。"""

    def fail_socket(*args, **kwargs):
        raise AssertionError("parser attempted network I/O")

    monkeypatch.setattr(socket, "socket", fail_socket)
    parse_action_response(load_fixture("actions/get_login_info.ok.json"), "get_login_info")
    parse_incoming_message(parse_event(load_fixture("events/message_receive.friend.json")))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(self_id=-1),
        lambda payload: payload["data"].update(peer_id="700000001"),
        lambda payload: payload["data"].update(sender_id=True),
        lambda payload: payload["data"].update(segments={}),
        lambda payload: payload["data"].update(message_scene="friend", friend=None),
    ],
)
def test_invalid_identity_or_container_is_malformed(mutate) -> None:
    """非法身份、布尔 ID 和容器类型必须在协议边界失败。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    mutate(payload)

    with pytest.raises(ParseError, match="malformed") as error_info:
        parse_incoming_message(parse_event(payload))

    assert error_info.value.classification == "malformed"


def test_group_identity_mismatch_is_rejected_without_guessing() -> None:
    """peer、group 和 group_member 不一致时不得选择任一字段猜测。"""

    payload = load_fixture("events/message_receive.group.all_segments.json")
    payload["data"]["group_member"]["group_id"] = 700000002

    with pytest.raises(ParseError) as error_info:
        parse_incoming_message(parse_event(payload))

    assert error_info.value.classification == "malformed"


def test_outer_milky_event_name_does_not_replace_business_event_type() -> None:
    """外层 milky_event 只作为包装，业务类型仍来自 data event_type。"""

    payload = load_fixture("events/message_receive.friend.json")
    event = parse_event(payload, outer_event_type="milky_event")

    assert event.event_type == "message_receive"
    assert event.outer_event_type == "milky_event"


def test_parser_sanitizes_sensitive_unknown_raw() -> None:
    """未知扩展可诊断保留，但不得把凭证字段带入 raw。"""

    payload = load_fixture("events/message_receive.group.unknown_extension.json")
    payload["data"]["segments"][1]["data"].update(
        authorization="Bearer secret", access_token="secret"
    )

    unknown = parse_incoming_message(parse_event(payload)).value.segments[1]
    assert isinstance(unknown, UnknownSegment)
    assert "authorization" not in unknown.data
    assert "access_token" not in unknown.data


def test_unknown_segment_with_non_object_data_stays_raw_only() -> None:
    """未知扩展的数据容器变化不应被解释成文本或已知 segment。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["segments"].append({"type": "future_scalar_extension", "data": [1, 2]})

    unknown = parse_incoming_message(parse_event(payload)).value.segments[1]

    assert isinstance(unknown, UnknownSegment)
    assert unknown.data == (1, 2)
