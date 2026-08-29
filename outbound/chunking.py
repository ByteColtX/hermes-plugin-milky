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

    for index in range(max_length, 0, -1):
        if text[index - 1].isspace():
            return index
    return max_length


__all__ = ["DEFAULT_TEXT_LENGTH", "chunk_text"]
