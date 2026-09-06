"""解析 Milky 出站文本中的 [SPLIT] 标记。"""

from __future__ import annotations

from dataclasses import dataclass

from .formatter import parse_cq_code

_SPLIT_MARKER = "[SPLIT]"
_LITERAL_MARKER = "[[SPLIT]]"


@dataclass(frozen=True, slots=True)
class ParsedOutboundText:
    """保存归一化正文和可选的有效分段。"""

    normalized_text: str
    sections: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _Line:
    """保存一行正文和其绝对位置。"""

    start: int
    body_end: int
    ending: str


def parse_outbound_text(text: str) -> ParsedOutboundText:
    """解析出站文本并区分有效分段和字面量归一化。"""

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    cq_spans = _valid_cq_spans(text)
    escaped_spans = _escaped_literal_spans(text, cq_spans)
    marker_positions = _effective_marker_positions(text, cq_spans, escaped_spans)
    lines = _lines(text)
    sections: list[str] = []
    current: list[tuple[str, str]] = []
    skip_blank_after_standalone = False
    has_effective_marker = False

    for line in lines:
        body = text[line.start : line.body_end]
        positions = [
            position for position in marker_positions if line.start <= position < line.body_end
        ]
        standalone = body == _SPLIT_MARKER and not _is_protected(line.start, cq_spans)
        if standalone:
            has_effective_marker = True
            _drop_trailing_blank_lines(current)
            if current:
                current[-1] = (current[-1][0], "")
            sections.append(_join_lines(current))
            current = []
            skip_blank_after_standalone = True
            continue

        if skip_blank_after_standalone and not body.strip():
            continue
        skip_blank_after_standalone = False

        if positions and _has_nonblank_outside_markers(
            text,
            line.start,
            line.body_end,
            positions,
        ):
            has_effective_marker = True
            cursor = line.start
            for position in positions:
                current.append(
                    (
                        _normalize_range(
                            text,
                            cursor,
                            position,
                            escaped_spans,
                        ),
                        "",
                    )
                )
                sections.append(_join_lines(current))
                current = []
                cursor = position + len(_SPLIT_MARKER)
            current.append(
                (
                    _normalize_range(
                        text,
                        cursor,
                        line.body_end,
                        escaped_spans,
                    ),
                    line.ending,
                )
            )
            continue

        current.append(
            (
                _normalize_range(
                    text,
                    line.start,
                    line.body_end,
                    escaped_spans,
                ),
                line.ending,
            )
        )

    sections.append(_join_lines(current))
    filtered_sections = tuple(section for section in sections if section.strip())
    normalized_text = _normalize_range(text, 0, len(text), escaped_spans)
    return ParsedOutboundText(
        normalized_text=normalized_text,
        sections=filtered_sections if has_effective_marker else None,
    )


def split_outbound_text(text: str) -> tuple[str, ...] | None:
    """按有效独立行或行中标记拆分文本。"""

    return parse_outbound_text(text).sections


def normalize_outbound_text(text: str) -> str:
    """还原字面量 [SPLIT]，不启用分段控制。"""

    return parse_outbound_text(text).normalized_text


def _lines(text: str) -> tuple[_Line, ...]:
    """按 LF 或 CRLF 保存正文行边界。"""

    lines: list[_Line] = []
    start = 0
    while True:
        newline = text.find("\n", start)
        if newline < 0:
            lines.append(_Line(start, len(text), ""))
            return tuple(lines)
        body_end = newline
        ending = "\n"
        if body_end > start and text[body_end - 1] == "\r":
            body_end -= 1
            ending = "\r\n"
        lines.append(_Line(start, body_end, ending))
        start = newline + 1


def _valid_cq_spans(text: str) -> tuple[tuple[int, int], ...]:
    """找出基础语法完整的 CQ-compatible 候选范围。"""

    spans: list[tuple[int, int]] = []
    position = 0
    while True:
        start = text.find("[CQ:", position)
        if start < 0:
            return tuple(spans)
        end = text.find("]", start + len("[CQ:"))
        if end < 0:
            position = start + len("[CQ:")
            continue
        raw = text[start : end + 1]
        if parse_cq_code(raw) is not None:
            spans.append((start, end + 1))
            position = end + 1
        else:
            position = start + len("[CQ:")


def _escaped_literal_spans(
    text: str,
    protected_spans: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    """找出完整 CQ 候选范围外的字面量转义。"""

    spans: list[tuple[int, int]] = []
    position = 0
    while True:
        start = text.find(_LITERAL_MARKER, position)
        if start < 0:
            return tuple(spans)
        end = start + len(_LITERAL_MARKER)
        if not _is_protected(start, protected_spans):
            spans.append((start, end))
        position = end


def _effective_marker_positions(
    text: str,
    protected_spans: tuple[tuple[int, int], ...],
    escaped_spans: tuple[tuple[int, int], ...],
) -> tuple[int, ...]:
    """找出未转义且不在完整 CQ 候选内的标记起点。"""

    positions: list[int] = []
    position = 0
    while True:
        start = text.find(_SPLIT_MARKER, position)
        if start < 0:
            return tuple(positions)
        if not _is_protected(start, protected_spans) and not _is_escaped(
            start,
            escaped_spans,
        ):
            positions.append(start)
        position = start + len(_SPLIT_MARKER)


def _has_nonblank_outside_markers(
    text: str,
    start: int,
    end: int,
    marker_positions: list[int],
) -> bool:
    """判断标记所在行是否还包含非空白正文。"""

    cursor = start
    for position in marker_positions:
        if text[cursor:position].strip():
            return True
        cursor = position + len(_SPLIT_MARKER)
    return bool(text[cursor:end].strip())


def _normalize_range(
    text: str,
    start: int,
    end: int,
    escaped_spans: tuple[tuple[int, int], ...],
) -> str:
    """只还原范围内的字面量转义。"""

    relevant = [
        (span_start, span_end)
        for span_start, span_end in escaped_spans
        if start <= span_start and span_end <= end
    ]
    if not relevant:
        return text[start:end]

    pieces: list[str] = []
    cursor = start
    for span_start, span_end in relevant:
        pieces.append(text[cursor:span_start])
        pieces.append(_SPLIT_MARKER)
        cursor = span_end
    pieces.append(text[cursor:end])
    return "".join(pieces)


def _is_escaped(
    position: int,
    escaped_spans: tuple[tuple[int, int], ...],
) -> bool:
    """判断标记起点是否位于字面量转义范围内。"""

    return any(start < position < end for start, end in escaped_spans)


def _is_protected(
    position: int,
    protected_spans: tuple[tuple[int, int], ...],
) -> bool:
    """判断位置是否位于完整 CQ 候选范围内。"""

    return any(start <= position < end for start, end in protected_spans)


def _join_lines(lines: list[tuple[str, str]]) -> str:
    """拼接正文行并保留行尾。"""

    return "".join(body + ending for body, ending in lines)


def _drop_trailing_blank_lines(lines: list[tuple[str, str]]) -> None:
    """删除独立行标记前紧邻的空白行。"""

    while lines and not lines[-1][0].strip():
        lines.pop()


__all__ = [
    "ParsedOutboundText",
    "normalize_outbound_text",
    "parse_outbound_text",
    "split_outbound_text",
]
