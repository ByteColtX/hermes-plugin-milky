"""验证 T03 Milky 协议 fixture 的层级、覆盖范围和脱敏边界。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"
KNOWN_SEGMENT_TYPES = {
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
SYSTEM_EVENT_TYPES = {
    "bot_offline",
    "message_recall",
    "friend_request",
    "group_join_request",
    "group_invitation",
    "friend_nudge",
    "group_nudge",
    "group_mute",
    "group_whole_mute",
    "group_file_upload",
    "group_admin_change",
}


def load_fixture(relative_path: str) -> Any:
    """读取单个 JSON fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def test_expected_classifications_reference_existing_fixture_layers() -> None:
    """预期分类应覆盖四层目录且只使用稳定分类词汇。"""

    expected = load_fixture("expected/classifications.json")
    expected_paths = {entry["path"] for entry in expected["fixtures"]}
    actual_paths = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for directory in ("actions", "events", "sse")
        for path in (FIXTURE_ROOT / directory).iterdir()
        if path.is_file()
    }

    assert expected["schema_version"] == 1
    assert set(expected["classification_vocabulary"]) == {
        "accepted",
        "ignored_temp",
        "observe_only",
        "malformed",
        "protocol_rejected",
    }
    assert expected_paths == actual_paths
    assert {entry["classification"] for entry in expected["fixtures"]} == set(
        expected["classification_vocabulary"]
    )


def test_action_fixtures_keep_milky_envelopes_and_data_layers() -> None:
    """Action fixture 应保留 v1.3 的 envelope 和对象型 data 层级。"""

    login = load_fixture("actions/get_login_info.ok.json")
    groups = load_fixture("actions/get_group_list.ok.json")
    member = load_fixture("actions/get_group_member_info.ok_omits_shut_up_end_time.json")
    member_null = load_fixture("actions/get_group_member_info.ok_null_shut_up_end_time.json")

    assert login["status"] == "ok" and login["retcode"] == 0
    assert login["data"]["uin"] == 900000001
    assert groups["status"] == "ok" and groups["retcode"] == 0
    assert isinstance(groups["data"]["groups"], list)
    assert member["status"] == "ok" and isinstance(member["data"]["member"], dict)
    assert "shut_up_end_time" not in member["data"]["member"]
    assert member_null["data"]["member"]["shut_up_end_time"] is None


def test_action_fixtures_distinguish_malformed_and_protocol_rejected() -> None:
    """缺字段、错误容器和协议拒绝应保持可区分。"""

    missing_uin = load_fixture("actions/get_login_info.malformed_missing_uin.json")
    wrong_groups = load_fixture("actions/get_group_list.malformed_groups_type.json")
    rejected = load_fixture("actions/get_group_member_info.protocol_rejected.json")

    assert "uin" not in missing_uin["data"]
    assert isinstance(wrong_groups["data"]["groups"], dict)
    assert rejected["status"] == "failed"
    assert rejected["retcode"] != 0


def test_outbound_media_request_fixture_keeps_native_and_upload_boundaries() -> None:
    """多媒体请求 fixture 应固定 group/dm、segment 和独立 upload 形状。"""

    payload = load_fixture("actions/outbound_media_requests.json")
    requests = payload["requests"]

    assert payload["outcomes"] == [
        "accepted",
        "protocol_rejected",
        "malformed",
        "transport_unknown",
    ]
    assert [item["method"] for item in requests] == ["POST"] * 8
    assert [item["action"] for item in requests] == [
        "send_group_message",
        "send_private_message",
        "send_group_message",
        "send_private_message",
        "send_group_message",
        "send_private_message",
        "upload_group_file",
        "upload_private_file",
    ]
    assert [item["body"]["message"][0]["type"] for item in requests[:6]] == [
        "text",
        "image",
        "record",
        "record",
        "video",
        "video",
    ]
    assert all(
        all(segment["type"] != "file" for segment in item["body"].get("message", []))
        for item in requests[:6]
    )
    assert all(item["body"]["file_uri"].startswith("base64://") for item in requests[6:])


def test_message_fixture_covers_friend_group_temp_and_all_known_segments() -> None:
    """消息 fixture 应覆盖场景边界和 14 类已知 incoming segment。"""

    friend = load_fixture("events/message_receive.friend.json")
    group = load_fixture("events/message_receive.group.all_segments.json")
    temporary = load_fixture("events/message_receive.temp.json")
    segments = group["data"]["segments"]

    assert friend["event_type"] == "message_receive"
    assert friend["data"]["message_scene"] == "friend"
    assert group["data"]["message_scene"] == "group"
    assert [segment["type"] for segment in segments] == sorted(
        KNOWN_SEGMENT_TYPES,
        key=[segment["type"] for segment in segments].index,
    )
    assert {segment["type"] for segment in segments} == KNOWN_SEGMENT_TYPES
    assert temporary["data"]["message_scene"] == "temp"
    assert temporary["data"]["group"] is None


def test_message_fixture_preserves_inline_reply_and_delayed_forward_reference() -> None:
    """reply 的内嵌内容和 forward 的延迟 ID 不应互相混淆。"""

    segments = load_fixture("events/message_receive.group.all_segments.json")["data"]["segments"]
    reply = next(segment for segment in segments if segment["type"] == "reply")
    forward = next(segment for segment in segments if segment["type"] == "forward")
    image = next(segment for segment in segments if segment["type"] == "image")
    file_segment = next(segment for segment in segments if segment["type"] == "file")

    assert reply["data"]["message_seq"] == 1000
    assert reply["data"]["sender_id"] == 800000003
    assert reply["data"]["segments"][0]["type"] == "text"
    assert forward["data"]["forward_id"] == "fixture-forward-id"
    assert forward["data"]["preview"] == ["预览内容"]
    assert image["data"]["resource_id"] == "fixture-image-resource"
    assert image["data"]["temp_url"] == ""
    assert file_segment["data"] == {
        "file_id": "fixture-file-id",
        "file_name": "fixture.txt",
        "file_size": 12,
        "file_hash": None,
    }


def test_event_fixtures_cover_system_observation_and_unknown_extension() -> None:
    """系统事件应全部可观察，未知事件和 segment 应保留 raw 扩展边界。"""

    system_types = {
        load_fixture(path.relative_to(FIXTURE_ROOT).as_posix())["event_type"]
        for path in (FIXTURE_ROOT / "events").glob("system.*.json")
    }
    unknown_event = load_fixture("events/unknown.event_extension.json")
    unknown_message = load_fixture("events/message_receive.group.unknown_extension.json")

    assert system_types == SYSTEM_EVENT_TYPES
    assert unknown_event["event_type"] == "future_event_extension"
    assert unknown_event["data"]["opaque"] == "仅供诊断"
    unknown_segment = unknown_message["data"]["segments"][1]
    assert unknown_segment["type"] == "future_segment_extension"
    assert unknown_segment["data"]["opaque"] == "仅供诊断"
    assert "[unknown]" not in json.dumps(unknown_message, ensure_ascii=False)


def test_sse_fixtures_separate_outer_event_name_and_inner_business_type() -> None:
    """SSE fixture 应显式测试 milky_event 包装、多行 data 和后续帧。"""

    multiline = (FIXTURE_ROOT / "sse/message_receive.multiline.sse").read_text(encoding="utf-8")
    mixed = (FIXTURE_ROOT / "sse/system-and-unknown.sse").read_text(encoding="utf-8")
    malformed = (FIXTURE_ROOT / "sse/malformed-then-valid.sse").read_text(encoding="utf-8")

    assert multiline.count("event: milky_event") == 1
    assert multiline.count("data: ") == 2
    assert '"event_type":"message_receive"' in multiline
    assert mixed.count("event: milky_event") == 2
    assert '"event_type":"future_event_extension"' in mixed
    assert '"event_type":"bot_offline"' in mixed
    assert malformed.count("event: milky_event") == 2
    assert '"event_type":"group_file_upload"' in malformed


def test_protocol_fixtures_contain_no_credentials_paths_or_live_urls() -> None:
    """协议资料不得包含凭证、认证 header、本地路径或可访问媒体 URL。"""

    forbidden = (
        "MILKY_ACCESS_TOKEN",
        "Authorization:",
        "Bearer ",
        "http://",
        "https://",
        "file://",
        "/Users/",
        "/home/",
        "[unknown]",
    )
    fixture_files = [
        path
        for directory in ("actions", "events", "sse", "expected")
        for path in (FIXTURE_ROOT / directory).iterdir()
        if path.is_file()
    ]

    for path in fixture_files:
        contents = path.read_text(encoding="utf-8")
        assert not any(value in contents for value in forbidden), path
