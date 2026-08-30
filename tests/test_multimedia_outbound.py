"""验证多媒体出站的本地资源、native segment 和 adapter 交接边界。"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import milky.client as client_module
from adapter import MilkyAdapter
from milky.client import ActionError, SendResult, materialize_media_uri
from milky.models import MilkyEnvelope
from outbound.sender import MilkyOutboundSender
from tests.fixtures.multimedia_inputs import SYNTHETIC_MEDIA_URIS


@dataclass
class MultimediaClient:
    """记录 group/dm message 和 upload Action 的脱敏 fake。"""

    error: ActionError | None = None
    message_sequences: list[int] = field(default_factory=lambda: [101, 102, 103, 104])
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def send_group_message(self, group_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("send_group_message", {"group_id": group_id, "message": message}))
        if self.error is not None:
            raise self.error
        return SendResult(str(self.message_sequences.pop(0)))

    async def send_private_message(self, user_id: int, message: list[dict[str, Any]]) -> SendResult:
        self.calls.append(("send_private_message", {"user_id": user_id, "message": message}))
        if self.error is not None:
            raise self.error
        return SendResult(str(self.message_sequences.pop(0)))

    async def upload_group_file(
        self,
        group_id: int,
        file_uri: str,
        file_name: str,
        *,
        parent_folder_id: object = None,
    ) -> MilkyEnvelope:
        self.calls.append(
            (
                "upload_group_file",
                {
                    "group_id": group_id,
                    "file_uri": file_uri,
                    "file_name": file_name,
                    "parent_folder_id": parent_folder_id,
                },
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "fixture-upload-group"})

    async def upload_private_file(
        self, user_id: int, file_uri: str, file_name: str
    ) -> MilkyEnvelope:
        self.calls.append(
            (
                "upload_private_file",
                {"user_id": user_id, "file_uri": file_uri, "file_name": file_name},
            )
        )
        if self.error is not None:
            raise self.error
        return MilkyEnvelope("ok", 0, {"file_id": "fixture-upload-private"})


def test_multimedia_fixture_is_synthetic_and_covers_uri_boundaries() -> None:
    """多媒体 fixture 只包含合成地址，不携带主机路径、凭证或 live 地址。"""

    assert set(SYNTHETIC_MEDIA_URIS) == {
        "remote_image",
        "remote_animation",
        "inline_audio",
        "local_image",
        "local_audio",
        "local_video",
        "local_document",
        "empty",
        "unknown_scheme",
    }
    assert all(
        ".invalid" in value
        for name, value in SYNTHETIC_MEDIA_URIS.items()
        if name.startswith("remote")
    )
    rendered = repr(SYNTHETIC_MEDIA_URIS)
    assert "Bearer " not in rendered
    assert "/Users/" not in rendered


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("http", "https://media.example.invalid/fixture.png"),
        ("base64", "base64://UklGRg=="),
    ],
)
def test_explicit_media_uris_are_preserved(name: str, value: str) -> None:
    """显式远端和内联 URI 不应被插件下载、解码或改写。"""

    assert asyncio.run(materialize_media_uri(value)) == value
    assert name in {"http", "base64"}


def test_local_path_and_file_uri_materialize_to_base64(tmp_path: Path) -> None:
    """本地路径和 file URI 应读取一次并产生相同的 base64 URI。"""

    media_path = tmp_path / "fixture-image.png"
    media_bytes = b"synthetic-image-bytes"
    media_path.write_bytes(media_bytes)

    expected = "base64://" + base64.b64encode(media_bytes).decode("ascii")
    assert asyncio.run(materialize_media_uri(media_path)) == expected
    assert asyncio.run(materialize_media_uri(media_path.as_uri())) == expected


@pytest.mark.parametrize("value_kind", ["empty", "missing", "directory", "unknown_scheme"])
def test_invalid_local_media_fails_without_uri_or_exception_echo(
    tmp_path: Path, value_kind: str
) -> None:
    """空值、非普通文件和未知 scheme 应在网络前安全失败。"""

    if value_kind == "empty":
        value: object = ""
    elif value_kind == "missing":
        value = tmp_path / "missing-secret-name.bin"
    elif value_kind == "directory":
        value = tmp_path / "directory-secret-name"
        value.mkdir()
    else:
        value = "ftp://media.example.invalid/fixture.bin"

    with pytest.raises(ActionError) as error_info:
        asyncio.run(materialize_media_uri(value))

    assert error_info.value.classification == "invalid_input"
    if value:
        assert str(value) not in str(error_info.value)


def test_unreadable_local_media_fails_without_reading_or_echo(tmp_path: Path) -> None:
    """不可读文件应在 materialization 边界返回脱敏错误。"""

    media_path = tmp_path / "unreadable-secret-name.bin"
    media_path.write_bytes(b"synthetic")
    media_path.chmod(0)
    try:
        if os.access(media_path, os.R_OK):
            pytest.skip("当前测试用户仍可读取 chmod 000 文件")
        with pytest.raises(ActionError) as error_info:
            asyncio.run(materialize_media_uri(media_path))
        assert error_info.value.classification == "invalid_input"
        assert media_path.name not in str(error_info.value)
    finally:
        media_path.chmod(0o600)


def test_local_media_size_limit_rejects_before_full_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """超过固定上限的本地文件应在 Action 前被拒绝。"""

    monkeypatch.setattr(client_module, "MAX_LOCAL_MEDIA_BYTES", 4)
    media_path = tmp_path / "too-large.bin"
    media_path.write_bytes(b"12345")

    with pytest.raises(ActionError) as error_info:
        asyncio.run(materialize_media_uri(media_path))

    assert error_info.value.classification == "invalid_input"
    assert "too-large.bin" not in str(error_info.value)


def test_local_media_size_limit_accepts_exact_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """恰好达到上限的非空文件应被完整编码。"""

    monkeypatch.setattr(client_module, "MAX_LOCAL_MEDIA_BYTES", 4)
    media_path = tmp_path / "boundary.bin"
    media_path.write_bytes(b"1234")

    assert asyncio.run(materialize_media_uri(media_path)) == "base64://MTIzNA=="


@pytest.mark.parametrize(
    ("method_name", "argument", "segment_type"),
    [
        ("send_image_file", "image.png", "image"),
        ("send_voice", "audio.ogg", "record"),
        ("send_video", "video.mp4", "video"),
    ],
)
def test_sender_native_media_uses_base64_and_keeps_caption_order(
    tmp_path: Path, method_name: str, argument: str, segment_type: str
) -> None:
    """图片、语音和视频应进入 native segment，而不是路径文本。"""

    media_path = tmp_path / argument
    media_path.write_bytes(b"synthetic-media")
    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        getattr(sender, method_name)(
            "group:700000001",
            media_path,
            caption="合成说明",
        )
    )

    assert result.success is True
    assert len(client.calls) == 1
    body = client.calls[0][1]["message"]
    assert body[0] == {"type": "text", "data": {"text": "合成说明"}}
    assert body[1]["type"] == segment_type
    assert body[1]["data"]["uri"].startswith("base64://")
    assert str(media_path) not in str(body)


def test_sender_routes_remote_media_to_dm_without_download() -> None:
    """远端图片 URI 应保留并调用私聊 message Action。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)
    remote_uri = "https://media.example.invalid/fixture.gif"

    result = asyncio.run(sender.send_animation("dm:800000001", remote_uri, caption="动画"))

    assert result.success is True
    assert client.calls[0][0] == "send_private_message"
    assert client.calls[0][1]["message"][-1] == {
        "type": "image",
        "data": {"uri": remote_uri},
    }


def test_sender_image_file_accepts_host_extension_kwargs(tmp_path: Path) -> None:
    """图片文件 sender 应兼容 Hermes 宿主扩展参数。"""

    media_path = tmp_path / "fixture-image.png"
    media_path.write_bytes(b"synthetic-image")
    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(
        sender.send_image_file("group:700000001", media_path, hermes_extension="fixture")
    )

    assert result.success is True
    assert client.calls[0][1]["message"][0]["type"] == "image"


@pytest.mark.parametrize("target", ["group:700000001", "dm:800000001"])
def test_sender_uploads_local_file_with_explicit_file_uri(target: str, tmp_path: Path) -> None:
    """本地文档必须走独立 upload，并在 JSON 中只出现 file_uri/file_name。"""

    media_path = tmp_path / "fixture-report.txt"
    media_path.write_bytes(b"synthetic-document")
    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_document(target, media_path))

    assert result.success is True
    action, body = client.calls[0]
    assert action == ("upload_group_file" if target.startswith("group:") else "upload_private_file")
    assert body["file_uri"].startswith("base64://")
    assert body["file_name"] == "fixture-report.txt"
    assert "file_path" not in body


def test_sender_requires_file_name_for_explicit_base64_upload() -> None:
    """内联文件没有可安全推导的名称时应在网络前拒绝。"""

    client = MultimediaClient()
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_document("dm:800000001", "base64://synthetic-file"))

    assert result.success is False
    assert result.error_kind == "invalid_input"
    assert client.calls == []


def test_sender_preserves_media_failure_and_does_not_send_fallback(tmp_path: Path) -> None:
    """协议拒绝应原样分类，且不能二次发送文本 fallback。"""

    media_path = tmp_path / "fixture.png"
    media_path.write_bytes(b"synthetic-image")
    client = MultimediaClient(error=ActionError("rejected", "send_group_message", "denied"))
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_image_file("group:700000001", media_path))

    assert result.success is False
    assert result.error_kind == "rejected"
    assert len(client.calls) == 1
    assert client.calls[0][1]["message"][0]["type"] == "image"


def test_media_logs_do_not_include_uri_path_or_base64(caplog: pytest.LogCaptureFixture) -> None:
    """媒体 Action 失败日志只允许安全分类和路由字段。"""

    caplog.set_level(logging.DEBUG)
    client = MultimediaClient(error=ActionError("transport_unknown", "send_group_message", "x"))
    sender = MilkyOutboundSender(client)
    media_uri = "base64://synthetic-secret-payload"

    result = asyncio.run(sender.send_image("group:700000001", media_uri))

    assert result.error_kind == "transport_unknown"
    rendered = caplog.text
    assert media_uri not in rendered
    assert "send_group_message" not in rendered


@dataclass
class RecordingMediaSender:
    """记录 adapter native media 委托，不读取传入资源。"""

    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def _record(self, name: str, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.calls.append((name, {"args": args, **kwargs}))
        return SimpleNamespace(success=True, message_id=name)

    async def send_image(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_image", *args, **kwargs)

    async def send_image_file(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_image_file", *args, **kwargs)

    async def send_animation(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_animation", *args, **kwargs)

    async def send_voice(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_voice", *args, **kwargs)

    async def send_video(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_video", *args, **kwargs)

    async def send_document(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_document", *args, **kwargs)

    async def send_file(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        return await self._record("send_file", *args, **kwargs)


def test_adapter_media_methods_delegate_without_base_text_fallback() -> None:
    """连接后的 adapter 各媒体入口应独立委托给 sender。"""

    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = sender

    async def scenario() -> None:
        await adapter.send_image("dm:800000001", "https://media.example.invalid/a.png")
        await adapter.send_image_file(
            "dm:800000001", "/fixture/image.png", hermes_extension="fixture"
        )
        await adapter.send_animation("dm:800000001", "https://media.example.invalid/a.gif")
        await adapter.send_voice("dm:800000001", "/fixture/audio.ogg")
        await adapter.send_video("dm:800000001", "/fixture/video.mp4")
        await adapter.send_document("dm:800000001", "/fixture/report.txt")

    asyncio.run(scenario())

    assert [name for name, _ in sender.calls] == [
        "send_image",
        "send_image_file",
        "send_animation",
        "send_voice",
        "send_video",
        "send_document",
    ]
    assert sender.calls[1][1]["hermes_extension"] == "fixture"


def test_adapter_media_gate_prevents_read_and_sender_call_after_disconnect(tmp_path: Path) -> None:
    """断开后的媒体入口应在 sender 和本地文件边界之前返回 unsupported。"""

    media_path = tmp_path / "not-read.png"
    media_path.write_bytes(b"should-not-be-read")
    sender = RecordingMediaSender()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = False
    adapter._closed = True
    adapter._outbound = sender

    result = asyncio.run(adapter.send_image_file("group:700000001", media_path))

    assert result.success is False
    assert result.error_kind == "unsupported"
    assert sender.calls == []


def test_media_transport_unknown_is_not_retried_or_fallbacked(tmp_path: Path) -> None:
    """媒体 Action 的未知结果只能提交一次，并保留原始分类。"""

    media_path = tmp_path / "fixture.ogg"
    media_path.write_bytes(b"synthetic-audio")
    client = MultimediaClient(
        error=ActionError("transport_unknown", "send_group_message", "unknown")
    )
    sender = MilkyOutboundSender(client)

    result = asyncio.run(sender.send_voice("group:700000001", media_path))

    assert result.success is False
    assert result.error_kind == "transport_unknown"
    assert len(client.calls) == 1
    assert client.calls[0][1]["message"][0]["type"] == "record"


class FakeHermesMediaDispatcher:
    """模拟 Hermes 解析 MEDIA 指令后按资源类型动态 dispatch。"""

    async def dispatch(self, adapter: MilkyAdapter, chat_id: str, directive: str) -> object:
        """将已通过宿主路径检查的 MEDIA 指令交给 adapter native 入口。"""

        prefix, path_and_caption = directive.split(":", 1)
        assert prefix == "MEDIA"
        path, _, caption = path_and_caption.partition(" ")
        suffix = Path(path).suffix.lower()
        if suffix in {".png", ".jpg", ".gif"}:
            return await adapter.send_image_file(chat_id, path, caption or None)
        if suffix in {".ogg", ".wav"}:
            return await adapter.send_voice(chat_id, path, caption or None)
        if suffix in {".mp4", ".webm"}:
            return await adapter.send_video(chat_id, path, caption or None)
        return await adapter.send_document(chat_id, path, caption or None)


def test_fake_hermes_media_dispatch_reaches_native_sender(tmp_path: Path) -> None:
    """模拟 Hermes MEDIA 交接应产生 native segment 或独立 upload。"""

    paths = {
        "image": tmp_path / "fixture.png",
        "audio": tmp_path / "fixture.ogg",
        "video": tmp_path / "fixture.mp4",
        "document": tmp_path / "fixture.txt",
    }
    for path in paths.values():
        path.write_bytes(b"synthetic-attachment")

    client = MultimediaClient()
    adapter = object.__new__(MilkyAdapter)
    adapter._connected = True
    adapter._closed = False
    adapter._outbound = MilkyOutboundSender(client)
    dispatcher = FakeHermesMediaDispatcher()

    async def scenario() -> list[object]:
        return await asyncio.gather(
            dispatcher.dispatch(adapter, "group:700000001", f"MEDIA:{paths['image']} 图片"),
            dispatcher.dispatch(adapter, "group:700000001", f"MEDIA:{paths['audio']} 语音"),
            dispatcher.dispatch(adapter, "group:700000001", f"MEDIA:{paths['video']} 视频"),
            dispatcher.dispatch(adapter, "group:700000001", f"MEDIA:{paths['document']} 文档"),
        )

    results = asyncio.run(scenario())

    assert all(getattr(result, "success", False) for result in results)
    assert [name for name, _ in client.calls].count("send_group_message") == 3
    assert [name for name, _ in client.calls].count("upload_group_file") == 1
    message_calls = [body for name, body in client.calls if name == "send_group_message"]
    upload_body = next(body for name, body in client.calls if name == "upload_group_file")
    for body in message_calls:
        assert body["message"][0]["type"] == "text"
        assert body["message"][1]["data"]["uri"].startswith("base64://")
        assert "MEDIA:" not in str(body)
    assert upload_body["file_uri"].startswith("base64://")
    assert "file_path" not in upload_body
