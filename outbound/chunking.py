"""提供不丢失内容的出站文本分块。"""

from __future__ import annotations

DEFAULT_TEXT_LENGTH = 4000


def chunk_text(text: object, max_length: int = DEFAULT_TEXT_LENGTH) -> tuple[str, ...]:
    """按长度拆分文本，优先在空白边界切分并保留全部分隔符。"""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length <= 0:
        raise ValueError("max_length must be a positive integer")
    if not text:
        return ()
    if len(text) <= max_length:
        return (text,)

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        cut = _boundary_cut(remaining, max_length)
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


def _boundary_cut(text: str, max_length: int) -> int:
    """返回不超过上限的切点，至少推进一个字符。"""

    protected = _cq_spans(text)
    for index in range(max_length, 0, -1):
        if text[index - 1].isspace() and _is_safe_cut(index, protected):
            return index
    for index in range(max_length, 0, -1):
        if _is_safe_cut(index, protected):
            return index
    for start, end in protected:
        if start < max_length < end:
            return end
    return max_length


def _cq_spans(text: str) -> tuple[tuple[int, int], ...]:
    """找出不能被文本分块切开的 CQ-compatible 片段。"""

    spans: list[tuple[int, int]] = []
    position = 0
    while True:
        start = text.find("[CQ:", position)
        if start < 0:
            break
        end = text.find("]", start + 4)
        if end < 0:
            spans.append((start, len(text)))
            break
        spans.append((start, end + 1))
        position = end + 1
    return tuple(spans)


def _is_safe_cut(index: int, spans: tuple[tuple[int, int], ...]) -> bool:
    """判断切点是否位于所有 CQ 片段之外。"""

    return all(not start < index < end for start, end in spans)


__all__ = ["DEFAULT_TEXT_LENGTH", "chunk_text"]
