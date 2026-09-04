"""解析 Milky 出站文本中的严格 `[SPLIT]` 行。"""

from __future__ import annotations


def split_outbound_text(text: str) -> tuple[str, ...] | None:
    """按严格独立行拆分文本，未命中标记时返回 ``None``。

    只有 LF 或 CRLF 行结尾参与行匹配。标记行两侧的分隔换行属于控制
    边界；其他段内换行和空白保持原样。只含空白的段不会出现在结果中。
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    lines = text.split("\n")
    bodies: list[str] = []
    endings: list[str] = []
    for index, line in enumerate(lines):
        if index < len(lines) - 1:
            if line.endswith("\r"):
                bodies.append(line[:-1])
                endings.append("\r\n")
            else:
                bodies.append(line)
                endings.append("\n")
        else:
            bodies.append(line)

    if "[SPLIT]" not in bodies:
        return None

    sections: list[str] = []
    current: list[str] = []
    for index, body in enumerate(bodies):
        if body == "[SPLIT]":
            sections.append("".join(current))
            current = []
            continue
        current.append(body)
        if index < len(bodies) - 1 and bodies[index + 1] != "[SPLIT]":
            current.append(endings[index])
    sections.append("".join(current))

    return tuple(section for section in sections if section.strip())


__all__ = ["split_outbound_text"]
