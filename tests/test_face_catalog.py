"""验证 face catalog 的本地读取、结构校验和冲突降级。"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

import pytest

from milky.face_catalog import load_face_catalog, parse_face_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "face_catalog" / "cases.json"


def load_fixture() -> dict[str, object]:
    """读取合成的 catalog fixture。"""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_real_catalog_is_valid_and_has_consistent_non_emoji_entries() -> None:
    """随插件发布的 catalog 必须满足解析边界，重复 ID 不得冲突。"""

    path = PROJECT_ROOT / "milky" / "face_catalog.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict)
    assert isinstance(payload.get("packs"), list)
    descriptions: dict[str, set[str]] = {}
    for pack in payload["packs"]:
        assert isinstance(pack, dict)
        assert isinstance(pack.get("emojis"), list)
        if pack.get("packName") == "emoji 表情":
            continue
        for emoji in pack["emojis"]:
            assert isinstance(emoji, dict)
            assert isinstance(emoji.get("qSid"), str) and emoji["qSid"].strip()
            assert isinstance(emoji.get("qDes"), str) and emoji["qDes"].strip()
            descriptions.setdefault(emoji["qSid"], set()).add(emoji["qDes"])

    assert all(len(values) == 1 for values in descriptions.values())
    labels = parse_face_catalog(payload)
    assert labels["14"] == "/微笑"
    assert "😊" not in labels


def test_synthetic_catalog_keeps_valid_labels_and_excludes_ambiguous_or_emoji_ids() -> None:
    """合成 catalog 应保留确定映射并跳过无效、冲突和 emoji 条目。"""

    fixture = load_fixture()
    labels = parse_face_catalog(fixture["valid_catalog"])

    assert labels == fixture["expected_labels"]
    assert isinstance(labels, MappingProxyType)
    with pytest.raises(TypeError):
        labels["new-face"] = "不应写入"  # type: ignore[index]
    for face_id in fixture["excluded_ids"]:
        assert face_id not in labels


def test_invalid_catalog_shapes_return_empty_read_only_mapping() -> None:
    """顶层结构错误不得阻止加载，结果必须是空只读映射。"""

    fixture = load_fixture()
    for payload in fixture["invalid_payloads"]:
        labels = parse_face_catalog(payload)
        assert labels == {}
        assert isinstance(labels, MappingProxyType)


def test_malformed_file_and_json_return_empty_mapping(tmp_path: Path) -> None:
    """文件缺失或 JSON 损坏时只返回安全降级结果。"""

    missing = load_face_catalog(tmp_path / "missing.json")
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("not-json", encoding="utf-8")

    assert missing == {}
    assert load_face_catalog(malformed_path) == {}


def test_catalog_fixture_contains_no_credentials_paths_urls_or_sensitive_text() -> None:
    """catalog fixture 不得带入凭证、路径、URL 或敏感正文。"""

    contents = FIXTURE_PATH.read_text(encoding="utf-8")
    forbidden = ("MILKY_ACCESS_TOKEN", "Authorization", "Bearer ", "http://", "https://", "/Users/")
    assert not any(value in contents for value in forbidden)
