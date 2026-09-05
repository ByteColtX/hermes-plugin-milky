"""根据 Milky face catalog 生成去重后的 Markdown 参考表。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CATALOG = _PROJECT_ROOT / "milky" / "face_catalog.json"
_DEFAULT_OUTPUT = (
    _PROJECT_ROOT / "skills" / "milky-qq-cq-reference" / "references" / "face-id-to-chinese-name.md"
)
_EMOJI_PACK_NAME = "emoji 表情"
_START_MARKER = "<!-- BEGIN GENERATED FACE CATALOG -->"
_END_MARKER = "<!-- END GENERATED FACE CATALOG -->"


@dataclass(frozen=True, slots=True)
class FaceEntry:
    """一个去重后的 face 目录条目。"""

    face_id: str
    description: str
    pack_name: str


class FaceReferenceError(ValueError):
    """表示 catalog 或现有参考表无法安全生成。"""


def load_entries(catalog_path: Path) -> tuple[FaceEntry, ...]:
    """读取 catalog，跳过 Unicode emoji pack 并按 face ID 去重。"""

    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise FaceReferenceError(f"无法读取 face catalog: {catalog_path}") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("packs"), list):
        raise FaceReferenceError("face catalog 顶层必须包含 packs 数组")

    entries: dict[str, FaceEntry] = {}
    for pack_index, pack in enumerate(payload["packs"]):
        if not isinstance(pack, dict):
            raise FaceReferenceError(f"packs[{pack_index}] 不是对象")
        pack_name = _required_string(pack.get("packName"), f"packs[{pack_index}].packName")
        if pack_name == _EMOJI_PACK_NAME:
            continue
        emojis = pack.get("emojis")
        if not isinstance(emojis, list):
            raise FaceReferenceError(f"pack {pack_name!r} 的 emojis 必须是数组")

        for emoji_index, emoji in enumerate(emojis):
            if not isinstance(emoji, dict):
                raise FaceReferenceError(f"pack {pack_name!r} 的 emojis[{emoji_index}] 不是对象")
            face_id = _required_string(
                emoji.get("qSid"), f"pack {pack_name!r}.emojis[{emoji_index}].qSid"
            )
            description = _required_string(
                emoji.get("qDes"), f"pack {pack_name!r}.emojis[{emoji_index}].qDes"
            )
            previous = entries.get(face_id)
            if previous is None:
                entries[face_id] = FaceEntry(face_id, description, pack_name)
            elif previous.description != description:
                raise FaceReferenceError(
                    f"face ID {face_id!r} 的 qDes 冲突：{previous.description!r} 与 {description!r}"
                )

    return tuple(entries.values())


def read_notes(markdown: str, face_ids: set[str]) -> dict[str, str]:
    """从现有 Markdown 表格读取备注，并按 face ID 建立稳定索引。"""

    notes: dict[str, str] = {}
    for line in markdown.splitlines():
        cells = _table_cells(line)
        if cells is None or len(cells) != 3:
            continue
        face_id, _description, note = (part.strip() for part in cells)
        if face_id not in face_ids:
            continue
        previous = notes.get(face_id)
        if previous is not None and previous != note:
            raise FaceReferenceError(f"face ID {face_id!r} 存在不同备注，无法自动合并")
        notes[face_id] = note
    return notes


def render_generated_block(entries: tuple[FaceEntry, ...], notes: dict[str, str]) -> str:
    """按 catalog 首次出现顺序生成标记块。"""

    grouped: dict[str, list[FaceEntry]] = {}
    pack_order: list[str] = []
    for entry in entries:
        if entry.pack_name not in grouped:
            grouped[entry.pack_name] = []
            pack_order.append(entry.pack_name)
        grouped[entry.pack_name].append(entry)

    lines = [
        _START_MARKER,
        "",
        f"目录共 {len(entries)} 个唯一 face ID；重复 `qSid` 只保留首次出现的 pack。",
        "同一 `qSid` 出现不同 `qDes` 时脚本拒绝生成，避免静默选择错误名称。",
        "",
    ]
    for pack_name in pack_order:
        suffix = "；可使用 large=1" if pack_name == "超级表情" else ""
        lines.extend(
            [
                f"## {pack_name}（运行时参与映射{suffix}）",
                "",
                "| face ID (`qSid`) | 中文名称 (`qDes`) | 备注 |",
                "| --- | --- | --- |",
            ]
        )
        for entry in grouped[pack_name]:
            note = notes.get(entry.face_id, "—")
            lines.append(
                f"| {_escape_cell(entry.face_id)} | {_escape_cell(entry.description)} | "
                f"{_escape_cell(note)} |"
            )
        lines.append("")
    lines.extend([_END_MARKER, ""])
    return "\n".join(lines)


def validate_generated_block(document: str) -> None:
    """校验现有 generated 块的结构，避免异常内容被覆盖。"""

    lines, start_index, end_index = _marker_bounds(document)
    block_lines = [line.rstrip("\r\n") for line in lines[start_index + 1 : end_index]]
    if sum(line.startswith("目录共 ") for line in block_lines) != 1:
        raise FaceReferenceError("generated face catalog 块缺少目录统计行")
    if sum(line.startswith("同一 `qSid` 出现不同 `qDes` ") for line in block_lines) != 1:
        raise FaceReferenceError("generated face catalog 块缺少冲突处理说明")
    if sum(line.startswith("## ") for line in block_lines) == 0:
        raise FaceReferenceError("generated face catalog 块缺少 pack 标题")

    table_header = "| face ID (`qSid`) | 中文名称 (`qDes`) | 备注 |"
    if table_header not in block_lines:
        raise FaceReferenceError("generated face catalog 块缺少表头")

    seen_ids: set[str] = set()
    for line in block_lines:
        if not line:
            continue
        if line.startswith(("目录共 ", "同一 `qSid` 出现不同 `qDes` ", "## ")):
            continue
        if not line.startswith("|"):
            raise FaceReferenceError("generated face catalog 块包含异常文案")
        cells = _table_cells(line)
        if cells is None or len(cells) != 3:
            raise FaceReferenceError("generated face catalog 块包含格式错误的表格行")
        face_id = cells[0].strip()
        if face_id in {"face ID (`qSid`)", "---"}:
            continue
        if not face_id:
            raise FaceReferenceError("generated face catalog 块包含空 face ID")
        if face_id in seen_ids:
            raise FaceReferenceError(f"generated face catalog 块包含重复 face ID: {face_id}")
        seen_ids.add(face_id)


def replace_generated_block(document: str, generated_block: str) -> str:
    """只替换成对标记之间的内容，标记外文本保持原样。"""

    lines, start_index, end_index = _marker_bounds(document)

    generated_lines = generated_block.splitlines(keepends=True)
    return "".join(lines[:start_index] + generated_lines + lines[end_index + 1 :])


def _marker_bounds(document: str) -> tuple[list[str], int, int]:
    """返回 generated 标记所在行，拒绝缺失、重复或乱序标记。"""

    lines = document.splitlines(keepends=True)
    start_indexes = [
        index for index, line in enumerate(lines) if line.rstrip("\r\n") == _START_MARKER
    ]
    end_indexes = [index for index, line in enumerate(lines) if line.rstrip("\r\n") == _END_MARKER]
    if len(start_indexes) != 1 or len(end_indexes) != 1 or start_indexes[0] >= end_indexes[0]:
        raise FaceReferenceError("参考表必须包含且只能包含一对有效的 generated face catalog 标记")
    return lines, start_indexes[0], end_indexes[0]


def update_reference(catalog_path: Path, output_path: Path, *, check: bool = False) -> bool:
    """生成或检查参考表，返回内容是否需要更新。"""

    entries = load_entries(catalog_path)
    try:
        existing = output_path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise FaceReferenceError(
            f"参考表不存在或缺少 generated 块，请先添加 {_START_MARKER} 和 {_END_MARKER}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise FaceReferenceError(f"无法读取参考表: {output_path}") from error

    validate_generated_block(existing)
    notes = read_notes(existing, {entry.face_id for entry in entries})
    rendered_block = render_generated_block(entries, notes)
    rendered = replace_generated_block(existing, rendered_block)
    changed = existing != rendered
    if changed and not check:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise FaceReferenceError(f"无法写入参考表: {output_path}") from error
    return changed


def _required_string(value: Any, field: str) -> str:
    """返回非空字符串，拒绝会导致生成歧义的字段。"""

    if not isinstance(value, str) or not value.strip():
        raise FaceReferenceError(f"{field} 必须是非空字符串")
    return value


def _escape_cell(value: str) -> str:
    """转义 Markdown 表格单元格中的边界字符。"""

    return value.replace("|", "\\|").replace("\n", " ")


def _table_cells(line: str) -> list[str] | None:
    """按 Markdown 表格规则拆分一行，并保留转义竖线所在单元格。"""

    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped[1:-1]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current))
    return cells


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=_DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查参考表是否与 catalog 一致，不写入文件",
    )
    return parser.parse_args()


def main() -> int:
    """执行参考表生成或一致性检查。"""

    args = _parse_args()
    try:
        changed = update_reference(args.catalog, args.output, check=args.check)
    except FaceReferenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        if changed:
            print(f"参考表需要更新: {args.output}", file=sys.stderr)
            return 1
        print(f"参考表已是最新: {args.output}")
    elif changed:
        print(f"已更新参考表: {args.output}")
    else:
        print(f"参考表无需更新: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
