"""验证 Agent-facing CQ-compatible 出站语法和安全 fallback。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from outbound.chunking import chunk_text
from outbound.formatter import (
    CQ_TYPE_REGISTRY,
    CQ_TYPES,
    format_message,
    parse_cq_code,
)

FIXTURE = Path(__file__).parent / "fixtures" / "cq_message_controls.json"


def test_cq_contract_fixture_is_complete_and_sanitized() -> None:
    """CQ 契约 fixture 应覆盖文档类型且只使用脱敏占位符。"""

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    documented = set(payload["documented_types"])

    assert documented == CQ_TYPES == set(CQ_TYPE_REGISTRY)
    assert set(payload["confirmed_native_types"]) | set(payload["fallback_types"]) == documented
    assert set(payload["confirmed_native_types"]) & set(payload["fallback_types"]) == set()
    assert payload["safety"] == {
        "contains_credentials": False,
        "contains_real_identity": False,
        "contains_sensitive_body": False,
        "uses_only_placeholders_for_ids": True,
    }
    serialized = FIXTURE.read_text(encoding="utf-8")
    assert re.search(r"\b\d{5,}\b", serialized) is None
    assert "Authorization" not in serialized
    assert "Bearer " not in serialized


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (
            "[CQ:text,text=你好]",
            [{"type": "text", "data": {"text": "你好"}}],
        ),
        (
            "[CQ:face,id=14,large=1]",
            [{"type": "face", "data": {"face_id": "14", "is_large": True}}],
        ),
        (
            "[CQ:image,file=https://media.example/image,type=sticker]",
            [
                {
                    "type": "image",
                    "data": {"uri": "https://media.example/image", "sub_type": "sticker"},
                }
            ],
        ),
        (
            "[CQ:record,file=https://media.example/record]",
            [{"type": "record", "data": {"uri": "https://media.example/record"}}],
        ),
        (
            "[CQ:video,file=https://media.example/video]",
            [{"type": "video", "data": {"uri": "https://media.example/video"}}],
        ),
        (
            "[CQ:at,qq=10001]",
            [{"type": "mention", "data": {"user_id": 10001}}],
        ),
        (
            "[CQ:reply,id=9001]",
            [{"type": "reply", "data": {"message_seq": 9001}}],
        ),
    ],
)
def test_confirmed_cq_types_convert_to_native_segments(
    content: str, expected: list[dict[str, object]]
) -> None:
    """已有确认映射的 CQ 类型应生成对应 Milky segment。"""

    assert format_message(content) == expected


def test_cq_parser_decodes_values_but_fallback_keeps_raw_text() -> None:
    """参数实体只影响 native 转换，fallback 必须保留原始控制码。"""

    assert parse_cq_code("[CQ:text,text=甲&#44;乙]") == ("text", {"text": "甲,乙"})
    assert format_message("[CQ:text,text=甲&#44;乙]") == [
        {"type": "text", "data": {"text": "甲,乙"}}
    ]
    raw = "[CQ:location,lat=1&#44;2,lon=3]"
    assert format_message(raw) == [{"type": "text", "data": {"text": raw}}]


@pytest.mark.parametrize(
    "cq_type", sorted(CQ_TYPES - {"text", "face", "image", "record", "video", "at", "reply"})
)
def test_unconfirmed_cq_types_are_identified_and_sent_as_raw_text(cq_type: str) -> None:
    """没有确认 native 映射的每个文档类型都必须原样放行。"""

    raw = f"[CQ:{cq_type},value=fixture]"
    assert format_message(raw) == [{"type": "text", "data": {"text": raw}}]


@pytest.mark.parametrize(
    "raw",
    [
        "[CQ:at]",
        "[CQ:at,qq=not-a-number]",
        "[CQ:at,qq=010001]",
        "[CQ:at,qq=1]",
        "[CQ:at,qq=10001,broken]",
        "[CQ:reply,id=00]",
        "[CQ:image,type=normal]",
        "[CQ:face,id=not-a-number]",
        "[CQ:]",
    ],
)
def test_malformed_cq_is_preserved_without_blocking_message(raw: str) -> None:
    """malformed、缺参和非法范围 CQ 只回退当前原文。"""

    assert format_message(f"前文{raw}后文") == [
        {"type": "text", "data": {"text": "前文"}},
        {"type": "text", "data": {"text": raw}},
        {"type": "text", "data": {"text": "后文"}},
    ]


def test_unclosed_cq_keeps_the_remaining_raw_text() -> None:
    """无法确认闭合边界时应保留从控制码起的全部原文。"""

    raw = "[CQ:at,qq=10001"
    assert format_message(f"前文{raw}后文") == [
        {"type": "text", "data": {"text": "前文"}},
        {"type": "text", "data": {"text": f"{raw}后文"}},
    ]


def test_combined_cq_controls_keep_order_and_do_not_add_implicit_reply() -> None:
    """@ 和引用组合应保留顺序，格式化器不接管隐式 reply。"""

    assert format_message("[CQ:reply,id=9001][CQ:at,qq=10001]答复") == [
        {"type": "reply", "data": {"message_seq": 9001}},
        {"type": "mention", "data": {"user_id": 10001}},
        {"type": "text", "data": {"text": "答复"}},
    ]


def test_formatter_ignores_legacy_reply_to_parameter() -> None:
    """兼容保留的 reply_to 参数不应绕过模型控制边界。"""

    assert format_message("普通回复", reply_to="9001") == [
        {"type": "text", "data": {"text": "普通回复"}}
    ]


def test_structured_text_segment_also_uses_cq_parser() -> None:
    """结构化 text segment 进入同一 CQ 解析路径。"""

    assert format_message(
        [
            {"type": "text", "data": {"text": "前"}},
            {"type": "text", "data": {"text": "[CQ:at,qq=10001]后"}},
        ]
    ) == [
        {"type": "text", "data": {"text": "前"}},
        {"type": "mention", "data": {"user_id": 10001}},
        {"type": "text", "data": {"text": "后"}},
    ]


def test_converter_exception_falls_back_to_only_its_raw_cq(monkeypatch) -> None:
    """单个转换器异常不能丢失其他文本或 CQ 内容。"""

    def fail(_parameters: object) -> None:
        raise RuntimeError("not exposed")

    monkeypatch.setitem(CQ_TYPE_REGISTRY, "at", fail)
    assert format_message("前[CQ:at,qq=10001]后[CQ:reply,id=9001]") == [
        {"type": "text", "data": {"text": "前"}},
        {"type": "text", "data": {"text": "[CQ:at,qq=10001]"}},
        {"type": "text", "data": {"text": "后"}},
        {"type": "reply", "data": {"message_seq": 9001}},
    ]


def test_chunking_never_splits_a_cq_control_code() -> None:
    """普通文本分块必须把 CQ 控制码作为不可分割边界。"""

    content = "前[CQ:at,qq=10001]后"
    chunks = chunk_text(content, max_length=10)

    assert "".join(chunks) == content
    assert chunks == ("前", "[CQ:at,qq=10001]", "后")
