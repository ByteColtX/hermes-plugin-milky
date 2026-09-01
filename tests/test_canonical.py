"""验证 T07 canonical、chat key 和 TTL dedup 边界。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest

from inbound.canonical import (
    CanonicalError,
    canonicalize_event,
    canonicalize_message,
    make_dedup_key,
    normalize_chat_key,
)
from milky.parser import parse_event, parse_incoming_message
from session.dedup import TtlDeduplicator

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


def parsed_message(relative_path: str):
    """读取并解析一个消息 fixture。"""

    return parse_incoming_message(parse_event(load_fixture(relative_path))).value


def test_chat_keys_keep_same_numeric_id_in_separate_namespaces() -> None:
    """相同数字的群号和 QQ 号必须生成不同 chat key。"""

    assert normalize_chat_key("group", 800000001) == "group:800000001"
    assert normalize_chat_key("friend", 800000001) == "dm:800000001"
    assert make_dedup_key(900000001, "group:800000001", "7") != make_dedup_key(
        900000001, "dm:800000001", "7"
    )


@pytest.mark.parametrize(
    ("scene", "peer_id"),
    [
        ("group", ""),
        ("group", "-1"),
        ("group", "not-a-number"),
        ("group", "1:2"),
        ("group", " 1"),
        ("friend", True),
        ("private", 1),
    ],
)
def test_invalid_chat_identity_fails_before_any_downstream_work(scene, peer_id) -> None:
    """非法身份不得被转换成另一种命名空间或伪造默认目标。"""

    with pytest.raises(CanonicalError):
        normalize_chat_key(scene, peer_id)


def test_canonical_record_uses_event_identity_and_stable_group_display_name() -> None:
    """canonical 应保存完整身份、规范时间、群名片和 typed segments。"""

    result = canonicalize_event(load_fixture("events/message_receive.group.all_segments.json"))

    assert result.classification == "accepted"
    assert result.value is not None
    assert result.value.platform == "milky"
    assert result.value.self_id == 900000001
    assert result.value.scene == "group"
    assert result.value.chat_key == "group:700000001"
    assert result.value.peer_id == 700000001
    assert result.value.sender_id == 800000002
    assert result.value.message_id == "1002"
    assert result.value.timestamp == 1700000020
    assert result.value.sender_name == "合成名片"
    assert result.value.body.startswith("中性文本")
    assert "[img:file_name=[合成图片]]" in result.value.body
    assert result.value.mention_kind == "self"
    assert result.value.mention_kinds == ("self", "all")
    assert result.value.mention_signals == ("self", "all")
    assert result.value.quote_message_id == "1000"
    assert result.value.media_resource_references[0].resource_id == "fixture-image-resource"
    assert result.value.file_attachment_references[0].file_id == "fixture-file-id"
    assert result.value.forward_references[0].forward_id == "fixture-forward-id"
    assert result.value.dedup_key == "milky:900000001:group:700000001:1002"


def test_friend_display_name_does_not_use_group_member_fields() -> None:
    """friend canonical 只使用 friend.nickname。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["friend"]["nickname"] = "  好友昵称  "
    payload["data"]["group_member"] = {
        "user_id": 800000001,
        "group_id": 800000001,
        "nickname": "错误群昵称",
        "card": "错误群名片",
    }

    result = canonicalize_event(payload)

    assert result.value.sender_name == "好友昵称"


@pytest.mark.parametrize(
    ("field", "value"),
    [("peer_id", -1), ("sender_id", -1), ("time", -1), ("self_id", -1)],
)
def test_canonical_rejects_invalid_direct_dto_identity(field: str, value: int) -> None:
    """即使绕过 parser，canonical 也不得接收非法身份或时间。"""

    message = parsed_message("events/message_receive.friend.json")
    with pytest.raises(CanonicalError):
        canonicalize_message(replace(message, **{field: value}))


def test_canonical_rejects_event_identity_different_from_login_identity() -> None:
    """事件 self_id 必须与启动时确认的 Bot 身份一致。"""

    result = canonicalize_event(
        load_fixture("events/message_receive.friend.json"), expected_self_id=900000002
    )

    assert result.classification == "malformed"
    assert result.value is None


def test_group_and_friend_sender_names_fallback_without_blank_values() -> None:
    """显示名候选为空时应按场景安全回退到 sender ID。"""

    group_payload = load_fixture("events/message_receive.group.all_segments.json")
    group_payload["data"]["group_member"]["card"] = "  "
    group_payload["data"]["group_member"]["nickname"] = " 群昵称 "
    group = canonicalize_event(group_payload)
    assert group.value.sender_name == "群昵称"

    group_payload["data"]["group_member"]["nickname"] = ""
    group = canonicalize_event(group_payload)
    assert group.value.sender_name == "800000002"

    friend_payload = load_fixture("events/message_receive.friend.json")
    friend_payload["data"]["friend"]["nickname"] = "  "
    friend = canonicalize_event(friend_payload)
    assert friend.value.sender_name == "800000001"


def test_temp_message_is_ignored_without_canonical_or_chat_key() -> None:
    """temp 消息应在 canonical 边界返回 ignored_temp。"""

    result = canonicalize_event(load_fixture("events/message_receive.temp.json"))

    assert result.classification == "ignored_temp"
    assert result.value is None
    assert result.reason == "temporary message scene"


def test_missing_message_id_is_processed_once_without_dedup_key() -> None:
    """无序号消息只能显式降级，不能把缺失值写入稳定 key。"""

    result = canonicalize_event(load_fixture("events/message_receive.friend.no_message_seq.json"))

    assert result.value is not None
    assert result.value.message_id is None
    assert result.value.dedup_key is None
    assert "no_stable_message_id" in result.value.diagnostics


def test_make_dedup_key_rejects_missing_or_invalid_stable_id() -> None:
    """稳定 key 不得包含空值、负数或额外分隔符。"""

    with pytest.raises(CanonicalError):
        make_dedup_key(1, "dm:2", None)
    with pytest.raises(CanonicalError):
        make_dedup_key(1, "dm:2", "1:2")
    with pytest.raises(CanonicalError):
        make_dedup_key(1, "private:2", "3")


def test_canonical_drops_sensitive_raw_fields_without_dropping_message_fields() -> None:
    """canonical raw 仅保留安全诊断字段，不扩散认证信息。"""

    payload = load_fixture("events/message_receive.friend.json")
    payload["data"]["authorization"] = "Bearer fixture-secret"
    payload["data"]["token"] = "fixture-secret"

    result = canonicalize_event(payload)

    assert result.value.body == "朋友消息"
    assert "authorization" not in result.value.raw
    assert "token" not in result.value.raw
    assert "fixture-secret" not in repr(result.value.raw)


def test_ttl_dedup_is_bounded_expires_and_does_not_record_missing_key() -> None:
    """TTL dedup 应在容量和过期边界内工作。"""

    now = [100.0]
    dedup = TtlDeduplicator(ttl_seconds=10, max_entries=2, clock=lambda: now[0])

    assert dedup.check_and_mark(None) is False
    assert dedup.check_and_mark("first") is False
    assert dedup.check_and_mark("second") is False
    assert dedup.check_and_mark("first") is True
    assert dedup.check_and_mark("third") is False
    assert dedup.size == 2
    assert dedup.check_and_mark("second") is True

    now[0] += 10
    assert dedup.check_and_mark("third") is False
    assert dedup.size == 1


def test_ttl_dedup_atomic_check_and_mark_has_one_winner() -> None:
    """并发重复帧只能有一个新消息获准进入后续副作用。"""

    dedup = TtlDeduplicator(ttl_seconds=30, max_entries=10)
    barrier = Barrier(8)

    def attempt() -> bool:
        barrier.wait()
        return dedup.check_and_mark("same-message")

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: attempt(), range(8)))

    assert results.count(False) == 1
    assert results.count(True) == 7


def test_ttl_dedup_keeps_entry_during_clock_rollback_and_expires_at_boundary() -> None:
    """时钟回拨不能让重复消息重新获准，恰好 TTL 时应过期。"""

    now = [100.0]
    dedup = TtlDeduplicator(ttl_seconds=10, clock=lambda: now[0])

    assert dedup.check_and_mark("same") is False
    now[0] = 99.0
    assert dedup.check_and_mark("same") is True
    now[0] = 110.0
    assert dedup.check_and_mark("same") is False


def test_ttl_dedup_zero_capacity_never_retains_a_key() -> None:
    """零容量是安全的禁用状态，不得增长内存。"""

    dedup = TtlDeduplicator(max_entries=0)

    assert dedup.check_and_mark("same") is False
    assert dedup.check_and_mark("same") is False
    assert dedup.size == 0


def test_same_text_with_different_message_ids_is_not_deduplicated() -> None:
    """去重只能使用稳定消息序号，不能使用正文或时间。"""

    first_payload = load_fixture("events/message_receive.friend.json")
    second_payload = load_fixture("events/message_receive.friend.json")
    second_payload["data"]["message_seq"] = 1002

    first = canonicalize_event(first_payload).value
    second = canonicalize_event(second_payload).value
    dedup = TtlDeduplicator()

    assert first.body == second.body
    assert dedup.check_and_mark(first.dedup_key) is False
    assert dedup.check_and_mark(second.dedup_key) is False


def test_duplicate_canonical_is_stopped_before_downstream_side_effects() -> None:
    """同一 canonical key 第二次到达时不应调用资源、Will 或 Hermes。"""

    event = load_fixture("events/message_receive.friend.json")
    dedup = TtlDeduplicator()
    downstream_calls = []

    for _ in range(2):
        canonical = canonicalize_event(event).value
        if dedup.check_and_mark(canonical.dedup_key):
            continue
        downstream_calls.append("resource")
        downstream_calls.append("will")
        downstream_calls.append("hermes")

    assert downstream_calls == ["resource", "will", "hermes"]
