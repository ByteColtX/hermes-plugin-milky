"""验证 face reference 生成脚本的去重、冲突保护和备注保留。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.update_face_reference import (
    FaceEntry,
    FaceReferenceError,
    load_entries,
    read_notes,
    render_generated_block,
    replace_generated_block,
    update_reference,
    validate_generated_block,
)


def write_catalog(path: Path, packs: list[dict[str, object]]) -> None:
    """写入脱敏 catalog fixture。"""

    path.write_text(json.dumps({"packs": packs}, ensure_ascii=False), encoding="utf-8")


def test_load_entries_deduplicates_same_id_and_skips_unicode_emoji(tmp_path: Path) -> None:
    """相同 ID 同名时只保留首次 pack，Unicode emoji pack 不进入表格。"""

    path = tmp_path / "face_catalog.json"
    write_catalog(
        path,
        [
            {
                "packName": "超级表情",
                "emojis": [{"qSid": "478", "qDes": "/对的对的"}],
            },
            {
                "packName": "QQ黄脸",
                "emojis": [
                    {"qSid": "478", "qDes": "/对的对的"},
                    {"qSid": "14", "qDes": "/微笑"},
                ],
            },
            {"packName": "emoji 表情", "emojis": [{"qSid": "😊", "qDes": "/嘿嘿"}]},
        ],
    )

    entries = load_entries(path)

    assert [(entry.face_id, entry.description, entry.pack_name) for entry in entries] == [
        ("478", "/对的对的", "超级表情"),
        ("14", "/微笑", "QQ黄脸"),
    ]


def test_load_entries_rejects_conflicting_description(tmp_path: Path) -> None:
    """同一 ID 的不同名称必须停止生成，不能按顺序猜测。"""

    path = tmp_path / "face_catalog.json"
    write_catalog(
        path,
        [
            {"packName": "pack-a", "emojis": [{"qSid": "same", "qDes": "第一名称"}]},
            {"packName": "pack-b", "emojis": [{"qSid": "same", "qDes": "第二名称"}]},
        ],
    )

    with pytest.raises(FaceReferenceError, match="qDes 冲突"):
        load_entries(path)


def test_render_reference_preserves_notes_by_face_id() -> None:
    """目录名称或 pack 变化时，备注仍按 face ID 保留。"""

    entries = (
        # 模拟同一个 ID 后续换了 pack，但仍沿用原备注。
        FaceEntry("14", "/微笑", "小黄脸表情"),
    )
    notes = read_notes("| 14 | /旧名称 | 现代聊天中注意语气 |\n", {"14"})

    rendered = render_generated_block(entries, notes)

    assert "| 14 | /微笑 | 现代聊天中注意语气 |" in rendered
    assert rendered.count("| 14 |") == 1
    assert "目录共 1 个唯一 face ID" in rendered


def test_read_notes_supports_escaped_pipe_in_note() -> None:
    """备注中的 Markdown 竖线不应破坏后续自动更新。"""

    notes = read_notes("| 14 | /微笑 | 语气\\|讽刺 |\n", {"14"})

    assert notes == {"14": "语气|讽刺"}


def test_replace_generated_block_preserves_text_outside_markers() -> None:
    """生成脚本只能修改标记块，不得改写其他文案。"""

    document = "手工标题\n<!-- BEGIN GENERATED FACE CATALOG -->\n旧表格\n<!-- END GENERATED FACE CATALOG -->\n手工结语\n"
    generated = (
        "<!-- BEGIN GENERATED FACE CATALOG -->\n新表格\n<!-- END GENERATED FACE CATALOG -->\n"
    )

    assert replace_generated_block(document, generated) == (
        "手工标题\n<!-- BEGIN GENERATED FACE CATALOG -->\n新表格\n"
        "<!-- END GENERATED FACE CATALOG -->\n手工结语\n"
    )


def test_replace_generated_block_rejects_missing_or_duplicate_markers() -> None:
    """标记缺失或重复时必须拒绝写入，避免覆盖文案。"""

    generated = (
        "<!-- BEGIN GENERATED FACE CATALOG -->\n新表格\n<!-- END GENERATED FACE CATALOG -->\n"
    )
    with pytest.raises(FaceReferenceError, match="只能包含一对"):
        replace_generated_block("没有标记", generated)
    with pytest.raises(FaceReferenceError, match="只能包含一对"):
        replace_generated_block(
            "<!-- BEGIN GENERATED FACE CATALOG -->\n<!-- BEGIN GENERATED FACE CATALOG -->\n"
            "<!-- END GENERATED FACE CATALOG -->\n",
            generated,
        )


def test_validate_generated_block_rejects_malformed_content() -> None:
    """generated 块不完整或重复时必须拒绝。"""

    with pytest.raises(FaceReferenceError, match="缺少表头"):
        validate_generated_block(
            "<!-- BEGIN GENERATED FACE CATALOG -->\n"
            "目录共 1 个唯一 face ID；重复 `qSid` 只保留首次出现的 pack。\n"
            "同一 `qSid` 出现不同 `qDes` 时脚本拒绝生成，避免静默选择错误名称。\n"
            "## pack\n<!-- END GENERATED FACE CATALOG -->\n"
        )

    malformed = (
        "<!-- BEGIN GENERATED FACE CATALOG -->\n"
        "目录共 1 个唯一 face ID；重复 `qSid` 只保留首次出现的 pack。\n"
        "同一 `qSid` 出现不同 `qDes` 时脚本拒绝生成，避免静默选择错误名称。\n"
        "## pack\n"
        "| face ID (`qSid`) | 中文名称 (`qDes`) | 备注 |\n"
        "| --- | --- | --- |\n"
        "| 14 | /微笑 | — |\n"
        "| 14 | /微笑 | 重复 |\n"
        "<!-- END GENERATED FACE CATALOG -->\n"
    )
    with pytest.raises(FaceReferenceError, match="重复 face ID"):
        validate_generated_block(malformed)


def test_update_reference_does_not_edit_malformed_block(tmp_path: Path) -> None:
    """generated 块异常时，脚本不得写入或改动参考表。"""

    catalog_path = tmp_path / "face_catalog.json"
    write_catalog(
        catalog_path,
        [{"packName": "pack", "emojis": [{"qSid": "14", "qDes": "/微笑"}]}],
    )
    output_path = tmp_path / "reference.md"
    original = (
        "手工文案\n<!-- BEGIN GENERATED FACE CATALOG -->\n"
        "不完整\n<!-- END GENERATED FACE CATALOG -->\n手工结语\n"
    )
    output_path.write_text(original, encoding="utf-8")

    with pytest.raises(FaceReferenceError):
        update_reference(catalog_path, output_path)

    assert output_path.read_text(encoding="utf-8") == original
