"""识别不带结构化内容的 Milky 斜杠命令。"""

from __future__ import annotations

from dataclasses import dataclass

from milky.models import TextSegment


@dataclass(frozen=True, slots=True)
class SlashCommand:
    """保存交给 Hermes 的规范化斜杠命令。"""

    text: str
    name: str
    args: str


def recognize_slash_command(message: object) -> SlashCommand | None:
    """只识别纯 ``text`` segments 组成的斜杠命令正文。"""

    segments = getattr(message, "segments", None)
    if not isinstance(segments, tuple) or not segments:
        return None
    if any(not isinstance(segment, TextSegment) for segment in segments):
        return None

    body = getattr(message, "body", None)
    if not isinstance(body, str):
        return None
    command_text = body.lstrip()
    if not command_text.startswith("/"):
        return None
    parts = command_text.split(maxsplit=1)
    token = parts[0][1:]
    if not token:
        return None
    command_name = token.split("@", 1)[0]
    if not command_name or "/" in command_name:
        return None
    args = parts[1] if len(parts) == 2 else ""
    return SlashCommand(command_text, command_name.lower(), args)


def is_slash_command(message: object) -> bool:
    """返回消息是否满足纯文本斜杠命令边界。"""

    return recognize_slash_command(message) is not None


__all__ = ["SlashCommand", "is_slash_command", "recognize_slash_command"]
