"""验证入站图片在单个 trigger batch 内按内容去重。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from inbound.canonical import canonicalize_event
from milky import resources
from milky.resources import ResourceResolver

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "protocol"


def load_fixture(relative_path: str) -> object:
    """读取脱敏协议 fixture。"""

    return json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))


class FileHermesMedia:
    """返回测试临时文件，不模拟任何远端下载逻辑。"""

    def __init__(self, paths: dict[str, str]) -> None:
        self.paths = paths
        self.url_calls: list[str] = []

    async def cache_image_from_url(self, url: str, ext: str = ".jpg") -> str:
        """按脱敏 URL 映射到测试文件。"""

        del ext
        self.url_calls.append(url)
        return self.paths[url]

    async def cache_audio_from_url(self, url: str, ext: str = ".ogg") -> str:
        """该测试不使用音频。"""

        del url, ext
        raise AssertionError("audio helper should not be called")


def make_message(*segments: dict[str, object], message_seq: int) -> object:
    """用 friend fixture 构造带指定 segments 的 canonical 消息。"""

    payload = load_fixture("events/message_receive.friend.json")
    assert isinstance(payload, dict)
    data = payload["data"]
    assert isinstance(data, dict)
    data["message_seq"] = message_seq
    data["segments"] = list(segments)
    result = canonicalize_event(payload)
    assert result.classification == "accepted"
    assert result.value is not None
    return result.value


def make_batch(history: tuple[object, ...], current: object) -> object:
    """构造 resolver 所需的最小 detached batch。"""

    return SimpleNamespace(
        chat_key=current.chat_key,
        history=history,
        current=current,
        trigger_ingress_sequence=3,
    )


def test_batch_content_dedup_prefers_history_and_preserves_first_mime(tmp_path: Path) -> None:
    """历史图片成为代表，当前重复图片只改写正文而不重复入媒体。"""

    history_path = tmp_path / "history.png"
    current_path = tmp_path / "current.webp"
    history_path.write_bytes(b"same-image")
    current_path.write_bytes(b"same-image")
    hermes = FileHermesMedia({"history": str(history_path), "current": str(current_path)})
    history = make_message(
        {
            "type": "image",
            "data": {
                "resource_id": "history-id",
                "temp_url": "history",
                "mime_type": "image/png",
            },
        },
        message_seq=1,
    )
    current = make_message(
        {"type": "text", "data": {"text": "触发"}},
        {
            "type": "image",
            "data": {
                "resource_id": "current-id",
                "temp_url": "current",
                "mime_type": "image/webp",
            },
        },
        message_seq=2,
    )

    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((history,), current))
    )

    assert resolved.history[0].body == "[img:file_name=history.png]"
    assert resolved.current.body == "触发[img:file_name=history.png]"
    assert [item.path for item in resolved.history[0].context_image_materializations] == [
        str(history_path)
    ]
    assert [item.path for item in resolved.current.hermes_attachment_materializations] == []
    assert resolved.current.image_occurrences[0].retained is False
    assert resolved.current.image_occurrences[0].basename == "history.png"
    assert resolved.current.image_occurrences[0].mime_type == "image/png"


def test_occurrence_offsets_keep_user_text_that_repeats_image_marker(tmp_path: Path) -> None:
    """重复 marker 时只改写记录的图片槽位，不误改普通文本。"""

    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    hermes = FileHermesMedia({"first": str(first_path), "second": str(second_path)})
    current = make_message(
        {"type": "text", "data": {"text": "[img:file_name=[图片]]"}},
        {
            "type": "image",
            "data": {"resource_id": "first-id", "temp_url": "first", "summary": "[图片]"},
        },
        {
            "type": "image",
            "data": {"resource_id": "second-id", "temp_url": "second", "summary": "[图片]"},
        },
        message_seq=4,
    )

    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert resolved.current.body == (
        "[img:file_name=[图片]][img:file_name=first.png][img:file_name=second.png]"
    )


def test_current_visible_reply_uses_history_image_representative(tmp_path: Path) -> None:
    """当前可见 reply 的图片也复用历史代表并保留 reply 正文。"""

    history_path = tmp_path / "history.png"
    current_path = tmp_path / "current.png"
    reply_path = tmp_path / "reply.png"
    for path in (history_path, current_path, reply_path):
        path.write_bytes(b"same-image")
    hermes = FileHermesMedia(
        {"history": str(history_path), "current": str(current_path), "reply": str(reply_path)}
    )
    history = make_message(
        {"type": "image", "data": {"temp_url": "history", "summary": "历史图"}},
        message_seq=8,
    )
    current = make_message(
        {"type": "image", "data": {"temp_url": "current", "summary": "当前图"}},
        {
            "type": "reply",
            "data": {
                "message_seq": 80,
                "sender_id": 800000001,
                "sender_name": "合成好友",
                "time": 1700000010,
                "segments": [{"type": "image", "data": {"temp_url": "reply", "summary": "引用图"}}],
            },
        },
        message_seq=9,
    )

    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((history,), current))
    )

    assert resolved.current.body == "[img:file_name=history.png]"
    assert resolved.current.replies[0].body == "[img:file_name=history.png]"
    assert [item.path for item in resolved.current.hermes_attachment_materializations] == []
    assert resolved.current.replies[0].image_occurrences[0].basename == "history.png"


def test_same_path_is_read_once_for_multiple_occurrences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一 materialization path 在一个 batch 内只执行一次文件读取。"""

    image_path = tmp_path / "same.png"
    image_path.write_bytes(b"same-image")
    hermes = FileHermesMedia({"one": str(image_path), "two": str(image_path)})
    current = make_message(
        {"type": "image", "data": {"temp_url": "one", "summary": "一"}},
        {"type": "image", "data": {"temp_url": "two", "summary": "二"}},
        message_seq=12,
    )
    read_calls = 0
    original_read = os.read

    def count_reads(fd: int, size: int) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return original_read(fd, size)

    monkeypatch.setattr(resources.os, "read", count_reads)
    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert read_calls == 2
    assert [item.path for item in resolved.current.hermes_attachment_materializations] == [
        str(image_path)
    ]
    assert resolved.current.body == "[img:file_name=same.png][img:file_name=same.png]"


def test_image_at_eight_mib_limit_is_hashable(tmp_path: Path) -> None:
    """恰好 8 MiB 的普通文件仍可参与内容去重。"""

    image_path = tmp_path / "limit.png"
    with image_path.open("wb") as output:
        output.truncate(8 * 1024 * 1024)
    hermes = FileHermesMedia({"limit": str(image_path)})
    current = make_message(
        {"type": "image", "data": {"temp_url": "limit", "summary": "边界图"}},
        message_seq=13,
    )

    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert len(resolved.current.hermes_attachment_materializations) == 1
    assert not any(item.reason == "image_hash_unavailable" for item in resolved.current.diagnostics)


def test_image_read_failure_keeps_path_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件读取失败时不作内容等价推断。"""

    image_path = tmp_path / "unreadable.png"
    image_path.write_bytes(b"image")
    hermes = FileHermesMedia({"unreadable": str(image_path)})
    current = make_message(
        {"type": "image", "data": {"temp_url": "unreadable", "summary": "不可读"}},
        message_seq=14,
    )

    def fail_read(_fd: int, _size: int) -> bytes:
        """模拟 descriptor 读取失败。"""

        raise OSError("sensitive read failure")

    monkeypatch.setattr(resources.os, "read", fail_read)
    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert len(resolved.current.hermes_attachment_materializations) == 1
    assert any(item.reason == "image_hash_unavailable" for item in resolved.current.diagnostics)
    assert "sensitive" not in str(resolved.current.diagnostics)


def test_image_change_during_read_keeps_path_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """读取前后文件状态变化时放弃 digest。"""

    image_path = tmp_path / "changed.png"
    image_path.write_bytes(b"image")
    hermes = FileHermesMedia({"changed": str(image_path)})
    current = make_message(
        {"type": "image", "data": {"temp_url": "changed", "summary": "变化"}},
        message_seq=15,
    )
    original_fstat = os.fstat
    fstat_calls = 0

    def changed_fstat(fd: int) -> os.stat_result:
        nonlocal fstat_calls
        fstat_calls += 1
        result = original_fstat(fd)
        if fstat_calls == 2:
            return os.stat_result(
                (
                    result.st_mode,
                    result.st_ino,
                    result.st_dev,
                    result.st_nlink,
                    result.st_uid,
                    result.st_gid,
                    result.st_size + 1,
                    result.st_atime,
                    result.st_mtime,
                    result.st_ctime,
                )
            )
        return result

    monkeypatch.setattr(resources.os, "fstat", changed_fstat)
    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert fstat_calls == 2
    assert len(resolved.current.hermes_attachment_materializations) == 1
    assert any(item.reason == "image_hash_unavailable" for item in resolved.current.diagnostics)


def test_history_nested_reply_image_is_not_a_media_candidate(tmp_path: Path) -> None:
    """未展示的历史嵌套 reply 图片不能抢占当前图片代表。"""

    nested_path = tmp_path / "nested.png"
    current_path = tmp_path / "current.png"
    nested_path.write_bytes(b"same-image")
    current_path.write_bytes(b"same-image")
    hermes = FileHermesMedia({"nested": str(nested_path), "current": str(current_path)})
    history = make_message(
        {"type": "text", "data": {"text": "历史"}},
        {
            "type": "reply",
            "data": {
                "message_seq": 81,
                "sender_id": 800000001,
                "sender_name": "合成好友",
                "time": 1700000011,
                "segments": [
                    {"type": "image", "data": {"temp_url": "nested", "summary": "嵌套图"}}
                ],
            },
        },
        message_seq=10,
    )
    current = make_message(
        {"type": "image", "data": {"temp_url": "current", "summary": "当前图"}},
        message_seq=11,
    )

    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((history,), current))
    )

    assert resolved.history[0].context_image_materializations == ()
    assert [item.path for item in resolved.current.hermes_attachment_materializations] == [
        str(current_path)
    ]
    assert resolved.current.image_occurrences[0].basename == "current.png"


@pytest.mark.parametrize("kind", ["empty", "oversized", "directory", "symlink"])
def test_unsafe_image_paths_do_not_enter_content_registry(tmp_path: Path, kind: str) -> None:
    """空文件、超限文件、目录和符号链接都安全回退到 path identity。"""

    target = tmp_path / "target.bin"
    target.write_bytes(b"content")
    if kind == "empty":
        target.write_bytes(b"")
        image_path = target
    elif kind == "oversized":
        with target.open("wb") as output:
            output.truncate(8 * 1024 * 1024 + 1)
        image_path = target
    elif kind == "directory":
        target.unlink()
        target.mkdir()
        image_path = target
    else:
        link = tmp_path / "link.bin"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("当前文件系统不支持符号链接 fixture")
        image_path = link

    hermes = FileHermesMedia({"image": str(image_path)})
    current = make_message(
        {"type": "image", "data": {"resource_id": "unsafe-id", "temp_url": "image"}},
        message_seq=5,
    )
    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((), current))
    )

    assert len(resolved.current.hermes_attachment_materializations) == 1
    assert resolved.current.image_occurrences[0].retained is True
    assert any(item.reason == "image_hash_unavailable" for item in resolved.current.diagnostics)


def test_hash_failure_has_safe_diagnostic_and_same_path_is_processed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """hash 异常不泄露敏感值，并在同一 batch 内复用同一路径结果。"""

    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image")
    hermes = FileHermesMedia({"one": str(image_path), "two": str(image_path)})
    first = make_message(
        {"type": "image", "data": {"resource_id": "secret-one", "temp_url": "one"}},
        message_seq=6,
    )
    second = make_message(
        {"type": "image", "data": {"resource_id": "secret-two", "temp_url": "two"}},
        message_seq=7,
    )
    digest_calls = 0

    def fail_digest() -> object:
        nonlocal digest_calls
        digest_calls += 1
        raise ValueError("sensitive hash failure")

    monkeypatch.setattr(resources.hashlib, "sha256", fail_digest)
    resolved = asyncio.run(
        ResourceResolver(object(), hermes).resolve_batch(make_batch((first,), second))
    )

    assert digest_calls == 1
    assert len(resolved.current.hermes_attachment_materializations) == 0
    diagnostics = (*resolved.history[0].diagnostics, *resolved.current.diagnostics)
    assert any(item.reason == "image_hash_unavailable" for item in diagnostics)
    assert all(item.reference_id is None for item in diagnostics)
    assert "sensitive" not in str(diagnostics)
