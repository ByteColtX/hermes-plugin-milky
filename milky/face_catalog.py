"""读取并校验随插件发布的 Milky face catalog。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

FaceLabelMap = Mapping[str, str]

_CATALOG_FILENAME = "face_catalog.json"
_EMOJI_PACK_NAME = "emoji 表情"
_EMPTY_LABELS: FaceLabelMap = MappingProxyType({})


def parse_face_catalog(payload: object) -> FaceLabelMap:
    """从已读取的 JSON 值生成只读 face ID 到显示名称映射。

    无效的 pack 或条目会被跳过；同一 ID 的不同名称会从结果中排除。
    """

    if not isinstance(payload, Mapping) or not isinstance(payload.get("packs"), list):
        return _EMPTY_LABELS

    descriptions: dict[str, set[str]] = {}
    for pack in payload["packs"]:
        if not isinstance(pack, Mapping) or pack.get("packName") == _EMOJI_PACK_NAME:
            continue
        emojis = pack.get("emojis")
        if not isinstance(emojis, list):
            continue
        for emoji in emojis:
            if not isinstance(emoji, Mapping):
                continue
            face_id = _non_blank_string(emoji.get("qSid"))
            description = _non_blank_string(emoji.get("qDes"))
            if face_id is None or description is None:
                continue
            descriptions.setdefault(face_id, set()).add(description)

    return MappingProxyType(
        {
            face_id: next(iter(values))
            for face_id, values in descriptions.items()
            if len(values) == 1
        }
    )


def load_face_catalog(path: Path | None = None) -> FaceLabelMap:
    """从插件自身目录读取一次 face catalog，失败时返回空映射。"""

    catalog_path = path or Path(__file__).with_name(_CATALOG_FILENAME)
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return _EMPTY_LABELS
    return parse_face_catalog(payload)


def _non_blank_string(value: Any) -> str | None:
    """返回非空字符串原值；只用去空白结果判断可用性。"""

    if not isinstance(value, str) or not value.strip():
        return None
    return value


FACE_LABELS = load_face_catalog()


__all__ = ["FACE_LABELS", "FaceLabelMap", "load_face_catalog", "parse_face_catalog"]
